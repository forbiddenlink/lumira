"""Shared low-level REST client for the Magica hosted media API.

Extracted from :mod:`magica_generator` (the original image-only client) so
image, audio, and video generators share one HTTP/polling implementation
instead of drifting copies. ``magica_generator.py`` now delegates to this
module; its public API (``MagicaGenerator``, ``MAGICA_BASE_URL``, etc.) is
unchanged.

REST contract (verified against magica.com/docs/introduction/quickstart,
2026-07-28):
    - Base URL: ``https://api.magica.com/api`` (version ``/v1``)
    - Start run:  ``POST /v1/nodes/{nodeType}/run``  body ``{"input": {...}}``
      -> ``{"runId": ...}``
    - Poll run:   ``GET  /v1/nodes/runs/{runId}``  until ``COMPLETED`` /
      ``FAILED`` / ``CANCELED``
    - Auth:       ``Authorization: Bearer $MAGICA_API_KEY``  (401 if
      missing/invalid)
    - Run status returns asset URLs at ``output.result`` (a list of URL
      strings); older/MCP-style responses used ``assets[].url`` (also
      supported, see :func:`extract_urls`).
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Base REST URL (override via env for testing / self-host proxies).
MAGICA_BASE_URL = os.getenv("MAGICA_BASE_URL", "https://api.magica.com/api")

# Terminal run states (compared case-insensitively).
TERMINAL_OK = {"COMPLETE", "COMPLETED", "SUCCEEDED", "SUCCESS"}
TERMINAL_FAIL = {"FAILED", "FAILURE", "CANCELED", "CANCELLED", "ERROR"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def download_bytes(url: str) -> bytes:
    """Download an asset with bounded retry.

    The run has already executed and been billed by the time we download, so a
    transient network error here must not throw the result away. GET is
    idempotent, so retrying is safe (unlike the run POST, which is
    deliberately not retried).
    """
    resp = httpx.get(url, timeout=60.0)
    resp.raise_for_status()
    return bytes(resp.content)


def build_headers(api_key: str) -> dict[str, str]:
    """Build the standard Magica auth + JSON headers."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def extract_urls(data: dict[str, Any]) -> list[str]:
    """Extract asset URLs from a run-status response.

    The REST API returns them at ``output.result`` (a list of URL strings),
    verified against a live run 2026-07-28. Older/MCP-style responses used a
    top-level ``assets[].url``; both are supported.
    """
    output = data.get("output") or {}
    result = output.get("result") if isinstance(output, dict) else None
    urls = [u for u in (result or []) if isinstance(u, str)]
    if not urls:
        assets = data.get("assets") or []
        urls = [
            a["url"]
            for a in assets
            if isinstance(a, dict) and isinstance(a.get("url"), str)
        ]
    return urls


class MagicaClient:
    """Thin REST client: start a node run, poll to completion, download assets.

    Usable directly, or wrapped by higher-level generators (image/audio/video)
    that add model-specific input schemas, budget guards, and output handling.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("MAGICA_API_KEY")

    def headers(self) -> dict[str, str]:
        return build_headers(self.api_key or "")

    def start_run(
        self,
        node_type: str,
        input_params: dict[str, Any],
        sub_model_id: str | None = None,
    ) -> str:
        """POST a model run; return its runId.

        Deliberately NOT retried: a model run is non-idempotent, so retrying
        an ambiguous POST failure could enqueue (and bill) duplicate runs.
        """
        url = f"{MAGICA_BASE_URL}/v1/nodes/{node_type}/run"
        body: dict[str, Any] = {"input": input_params}
        if sub_model_id:
            body["subModelId"] = sub_model_id
        resp = httpx.post(url, headers=self.headers(), json=body, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        run_id = data.get("runId") or data.get("id")
        if not run_id:
            raise RuntimeError(f"Magica run response missing runId: {data}")
        return str(run_id)

    def poll_run(
        self,
        run_id: str,
        timeout_s: float = 300.0,
        poll_interval_s: float = 2.0,
    ) -> list[str]:
        """Poll a run to completion; return generated asset URLs."""
        url = f"{MAGICA_BASE_URL}/v1/nodes/runs/{run_id}"
        deadline = time.monotonic() + timeout_s
        while True:
            resp = httpx.get(url, headers=self.headers(), timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            status = str(data.get("status", "")).upper()
            if status in TERMINAL_OK:
                urls = extract_urls(data)
                if not urls:
                    raise RuntimeError(f"Magica run {run_id} completed with no assets")
                return urls
            if status in TERMINAL_FAIL:
                raise RuntimeError(
                    f"Magica run {run_id} failed: {data.get('error') or status}"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(f"Magica run {run_id} timed out after {timeout_s}s")
            time.sleep(poll_interval_s)

    def download_bytes(self, url: str) -> bytes:
        data = download_bytes(url)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"Expected bytes from Magica download, got {type(data)}")
        return bytes(data)
