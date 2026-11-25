"""Shared low-level REST client for the Spiral hosted media API.

Image, audio, and video generators share one HTTP/polling implementation
instead of drifting copies. Spiral replaced Magica (shut down 2026-12-01).

REST contract (verified against https://api.spiral.ai/v1/openapi.json,
2026-11-25):
    - Base URL: ``https://api.spiral.ai`` (paths are under ``/v1``)
    - Start run:  ``POST /v1/runs``  body ``{"provider", "model", "input"}``
      with an ``Idempotency-Key`` header -> run object, id at ``.id``
    - Poll run:   ``GET  /v1/runs/{id}?wait_seconds=N`` (long-poll, 0-60) until
      ``status`` is ``completed`` / ``failed`` / ``canceled``
    - Auth:       ``Authorization: Bearer $SPIRAL_API_KEY``
    - Outputs:    ``output.items[]`` of ``{type, url, mime_type, ...}``; links
      expire after 30 days, so callers download to their own storage.
    - Errors:     ``application/problem+json`` with ``code`` and ``retryable``
      (402 ``INSUFFICIENT_BALANCE`` when the account has no balance).
    - There is no sub-model parameter: the (provider, model) pair selects the
      exact variant.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, NamedTuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Base REST URL (override via env for testing / proxies).
SPIRAL_BASE_URL = os.getenv("SPIRAL_BASE_URL", "https://api.spiral.ai")

# Terminal run states (lowercase per the Spiral API).
TERMINAL_OK = {"completed"}
TERMINAL_FAIL = {"failed", "canceled"}

# Longest single long-poll the API accepts (seconds).
_MAX_WAIT_SECONDS = 60

# Provider ids are single tokens; model ids may contain slashes
# (e.g. ``fal-ai/nano-banana-pro``) but no empty, ``.`` or ``..`` segments and
# no whitespace or URL metacharacters. They travel in the JSON body, not the
# URL path, so this is defense in depth rather than the only barrier.
_PROVIDER_RE = re.compile(r"[A-Za-z0-9_-]+")
_MODEL_RE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")


def _valid_model(model: SpiralModel) -> bool:
    return (
        bool(_PROVIDER_RE.fullmatch(model.provider))
        and bool(_MODEL_RE.fullmatch(model.model))
        and all(seg not in {".", ".."} for seg in model.model.split("/"))
    )


class SpiralModel(NamedTuple):
    """A Spiral catalog entry: the (provider, model) pair that selects a run."""

    provider: str
    model: str


class SpiralError(RuntimeError):
    """A Spiral API error (problem+json) or a failed run."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable


def parse_model_ref(ref: str) -> SpiralModel:
    """Parse a raw ``"provider/model"`` string into a :class:`SpiralModel`.

    The first ``/`` splits provider from model, so
    ``"fal/fal-ai/nano-banana-pro"`` -> ``("fal", "fal-ai/nano-banana-pro")``.
    """
    provider, sep, model = ref.partition("/")
    parsed = SpiralModel(provider, model)
    if not sep or not _valid_model(parsed):
        raise ValueError(
            f"Invalid Spiral model reference: {ref!r} (expected 'provider/model')"
        )
    return parsed


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def download_bytes(url: str) -> bytes:
    """Download an asset with bounded retry.

    The run has already executed and been billed by the time we download, so a
    transient network error here must not throw the result away. GET is
    idempotent, so retrying is safe. Spiral output links expire after 30 days:
    callers must persist the bytes.
    """
    resp = httpx.get(url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    return bytes(resp.content)


def build_headers(api_key: str) -> dict[str, str]:
    """Build the standard Spiral auth + JSON headers."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def extract_urls(data: dict[str, Any], kind: str | None = None) -> list[str]:
    """Extract output URLs from a run object (``output.items[].url``).

    ``kind`` (``"image"``, ``"audio"``, ``"video"``) keeps only items of that
    type, so a model that also emits a JSON sidecar item (ElevenLabs Music)
    cannot hand a metadata file to the media saver.
    """
    output = data.get("output") or {}
    items = output.get("items") if isinstance(output, dict) else None
    urls: list[str] = []
    for item in items or []:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        if kind is not None:
            mime = str(item.get("mime_type") or "")
            if item.get("type") != kind and not mime.startswith(f"{kind}/"):
                continue
        urls.append(item["url"])
    return urls


def _error_from_response(resp: httpx.Response) -> SpiralError:
    """Build a :class:`SpiralError` from a problem+json error response."""
    code: str | None = None
    retryable: bool | None = None
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            code = body.get("code")
            retryable = body.get("retryable")
            detail = str(body.get("detail") or body.get("title") or "")
    except ValueError:
        pass
    msg = f"Spiral API error {resp.status_code}"
    if code:
        msg += f" {code}"
    if detail:
        msg += f": {detail}"
    return SpiralError(msg, status=resp.status_code, code=code, retryable=retryable)


def _raise_for_status(resp: httpx.Response) -> None:
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _error_from_response(exc.response) from exc


class SpiralClient:
    """Thin REST client: start a run, poll to completion, download outputs.

    Usable directly, or wrapped by higher-level generators (image/audio/video)
    that add model-specific input schemas, budget guards, and output handling.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SPIRAL_API_KEY")

    def headers(self) -> dict[str, str]:
        return build_headers(self.api_key or "")

    def start_run(self, model: SpiralModel, input_params: dict[str, Any]) -> str:
        """POST a run; return its id.

        Sends a fresh ``Idempotency-Key`` per call. Still NOT retried here: a
        run is billed, and a caller that wants retry semantics must reuse one
        key deliberately rather than get duplicates from a blind retry.
        """
        if not _valid_model(model):
            raise ValueError(f"Invalid Spiral model: {model!r}")
        headers = self.headers()
        headers["Idempotency-Key"] = str(uuid.uuid4())
        body = {
            "provider": model.provider,
            "model": model.model,
            "input": input_params,
        }
        resp = httpx.post(
            f"{SPIRAL_BASE_URL}/v1/runs", headers=headers, json=body, timeout=60.0
        )
        _raise_for_status(resp)
        data = resp.json()
        run_id = data.get("id")
        if not run_id:
            raise SpiralError(f"Spiral run response missing id: {data}")
        return str(run_id)

    def poll_run(
        self,
        run_id: str,
        timeout_s: float = 300.0,
        kind: str | None = None,
    ) -> list[str]:
        """Long-poll a run to completion; return output URLs (optionally of one type)."""
        url = f"{SPIRAL_BASE_URL}/v1/runs/{run_id}"
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            wait = int(max(0, min(_MAX_WAIT_SECONDS // 2, remaining)))
            resp = httpx.get(
                url,
                headers=self.headers(),
                params={"wait_seconds": wait},
                timeout=wait + 30.0,
            )
            _raise_for_status(resp)
            data = resp.json()
            status = str(data.get("status", "")).lower()
            if status in TERMINAL_OK:
                urls = extract_urls(data, kind)
                if not urls:
                    raise SpiralError(f"Spiral run {run_id} completed with no outputs")
                return urls
            if status in TERMINAL_FAIL:
                err = data.get("error") or status
                raise SpiralError(f"Spiral run {run_id} failed: {err}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Spiral run {run_id} timed out after {timeout_s}s")
            if wait == 0:
                # Long-poll gave no server-side wait; avoid a hot loop.
                time.sleep(1.0)

    def download_bytes(self, url: str) -> bytes:
        data = download_bytes(url)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"Expected bytes from Spiral download, got {type(data)}")
        return bytes(data)
