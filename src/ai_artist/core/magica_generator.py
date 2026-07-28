"""Magica (Galaxy AI) hosted multi-model image generator.

Calls Magica's public REST API (https://magica.com/docs) to run hosted image
models (Nano Banana Pro, FLUX 2, GPT Image, Grok Imagine, ...). Signature-compatible
with :class:`ImageGenerator` and :class:`ReplicateGenerator` so it drops into the
generator factory (``config.model.backend = "magica"``).

REST contract (verified against magica.com/docs/introduction/quickstart, 2026-07-28):
    - Base URL: ``https://api.magica.com/api`` (version ``/v1``)
    - Start run:  ``POST /v1/nodes/{nodeType}/run``  body ``{"input": {...}}``  -> ``{"runId": ...}``
    - Poll run:   ``GET  /v1/nodes/runs/{runId}``  until ``COMPLETED`` / ``FAILED`` / ``CANCELED``
    - Auth:       ``Authorization: Bearer $MAGICA_API_KEY``  (401 if missing/invalid)

Gated behind ``MAGICA_API_KEY``: with no key, ``generate()`` raises (same as
``ReplicateGenerator`` with a missing token). Per-model input schemas vary; call
Magica's schema endpoint (or the MCP ``get_model_schema``) to confirm fields for a
specific nodeType. This client sends the common, widely-supported fields.

NOTE: end-to-end runtime execution is untested until a ``MAGICA_API_KEY`` is set;
the request/response shapes follow the documented contract and the MCP-verified node
schemas (e.g. ``nano_banana_pro``).
"""

from __future__ import annotations

import io
import os
from typing import Any, Literal

import httpx
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Base REST URL (override via env for testing / self-host proxies).
MAGICA_BASE_URL = os.getenv("MAGICA_BASE_URL", "https://api.magica.com/api")

# Friendly-name -> Magica nodeType. Values are real node ids (verified via the
# Magica MCP catalog); extend as new image models ship. Callers may also pass a
# raw nodeType (snake_case) directly.
MAGICA_MODELS = {
    "nano-banana-pro": "nano_banana_pro",  # Google Gemini 3 Pro Image (default)
    "nano-banana": "nano_banana_2",
    "flux2-max": "flux_2_max",
    "gpt-image": "gpt_image_2",
    "grok-image": "grok_imagine_image",
}

# Default model: Nano Banana Pro (schema verified, text-to-image, 1K/2K/4K).
DEFAULT_MODEL = "nano_banana_pro"

# Terminal run states (compared case-insensitively).
_TERMINAL_OK = {"COMPLETE", "COMPLETED", "SUCCEEDED", "SUCCESS"}
_TERMINAL_FAIL = {"FAILED", "FAILURE", "CANCELED", "CANCELLED", "ERROR"}

# Daily image budget backstop (mirrors ReplicateGenerator). 0 disables.
_spend_day: str | None = None
_spend_count = 0


def _check_magica_budget(num_images: int) -> None:
    """Enforce the per-day Magica image budget; raise if exceeded."""
    global _spend_day, _spend_count
    cap = int(os.getenv("LUMIRA_MAGICA_DAILY_MAX_IMAGES", "200"))
    if cap <= 0:
        return
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if today != _spend_day:
        _spend_day = today
        _spend_count = 0
    if _spend_count + num_images > cap:
        logger.error(
            "magica_budget_exceeded",
            used=_spend_count,
            requested=num_images,
            daily_cap=cap,
        )
        raise RuntimeError(
            f"Magica daily image budget exceeded ({_spend_count}/{cap}). "
            "Raise LUMIRA_MAGICA_DAILY_MAX_IMAGES or wait for the daily reset."
        )
    _spend_count += num_images


def _aspect_ratio(width: int, height: int) -> str:
    """Map pixel dims to a Magica aspect_ratio enum (nearest of the common set)."""
    if height <= 0:
        return "1:1"
    ratio = width / height
    candidates = {
        "1:1": 1.0,
        "4:3": 4 / 3,
        "3:4": 3 / 4,
        "16:9": 16 / 9,
        "9:16": 9 / 16,
        "3:2": 3 / 2,
        "2:3": 2 / 3,
    }
    return min(candidates, key=lambda k: abs(candidates[k] - ratio))


def _resolution_tier(width: int, height: int) -> str:
    """Map the larger pixel dimension to Magica's 1K/2K/4K resolution tier."""
    longest = max(width, height)
    if longest >= 3072:
        return "4K"
    if longest >= 1536:
        return "2K"
    return "1K"


class MagicaGenerator:
    """Hosted image generator backed by the Magica REST API.

    Usable as a context manager:
        with MagicaGenerator(model_id="nano_banana_pro") as gen:
            gen.load_model()
            images = gen.generate("a serene misty forest at dawn")
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        device: Literal["cuda", "mps", "cpu"] = "cpu",  # Ignored (cloud GPUs)
        dtype: Any = None,  # Ignored, for signature compatibility
    ) -> None:
        """Initialize the Magica generator.

        Args:
            model_id: A key from MAGICA_MODELS or a raw Magica nodeType.
            device: Ignored (Magica runs on cloud GPUs).
            dtype: Ignored (for compatibility with ImageGenerator).
        """
        # Friendly name -> nodeType; otherwise treat model_id as a raw nodeType
        # (falling back to the default when empty).
        self.node_type = MAGICA_MODELS.get(model_id, model_id or DEFAULT_MODEL)

        self.model_name = model_id
        self.api_key = os.environ.get("MAGICA_API_KEY")
        if not self.api_key:
            logger.warning(
                "magica_key_missing",
                message="MAGICA_API_KEY not set. Generation will fail.",
            )

    def load_model(self, *args: Any, **kwargs: Any) -> None:
        """No-op: Magica models load server-side. Present for interface parity."""
        logger.info("magica_model_ready", node_type=self.node_type)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _start_run(self, input_params: dict[str, Any]) -> str:
        """POST a model run; return its runId.

        Deliberately NOT retried: a model run is non-idempotent, so retrying an
        ambiguous POST failure could enqueue (and bill) duplicate runs.
        """
        url = f"{MAGICA_BASE_URL}/v1/nodes/{self.node_type}/run"
        resp = httpx.post(
            url, headers=self._headers(), json={"input": input_params}, timeout=60.0
        )
        resp.raise_for_status()
        data = resp.json()
        run_id = data.get("runId") or data.get("id")
        if not run_id:
            raise RuntimeError(f"Magica run response missing runId: {data}")
        return str(run_id)

    def _poll_run(self, run_id: str, timeout_s: float = 300.0) -> list[str]:
        """Poll a run to completion; return generated asset URLs."""
        import time

        url = f"{MAGICA_BASE_URL}/v1/nodes/runs/{run_id}"
        deadline = time.monotonic() + timeout_s
        while True:
            resp = httpx.get(url, headers=self._headers(), timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            status = str(data.get("status", "")).upper()
            if status in _TERMINAL_OK:
                assets = data.get("assets", []) or []
                urls = [
                    a["url"] for a in assets if isinstance(a, dict) and a.get("url")
                ]
                if not urls:
                    raise RuntimeError(f"Magica run {run_id} completed with no assets")
                return urls
            if status in _TERMINAL_FAIL:
                raise RuntimeError(
                    f"Magica run {run_id} failed: {data.get('error') or status}"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(f"Magica run {run_id} timed out after {timeout_s}s")
            time.sleep(2.0)

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,  # Ignored by most hosted models
        guidance_scale: float = 7.5,  # Ignored by most hosted models
        num_images: int = 1,
        seed: int | None = None,
        on_progress: Any = None,  # Not supported by REST poll
        system_prompt: str = "",
        **kwargs: Any,
    ) -> list[Image.Image]:
        """Generate images via the Magica REST API.

        Sends the widely-supported common fields. Model-specific fields (per
        get_model_schema) can be added via ``kwargs``, which are merged into the
        request input.

        Returns:
            List of PIL Image objects.
        """
        if not self.api_key:
            raise ValueError("MAGICA_API_KEY not set")
        if num_images < 1:
            raise ValueError("num_images must be >= 1")

        _check_magica_budget(num_images)

        logger.info(
            "magica_generation_start",
            node_type=self.node_type,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        input_params: dict[str, Any] = {
            "prompt": prompt,
            "num_images": num_images,
            "aspect_ratio": _aspect_ratio(width, height),
            "resolution": _resolution_tier(width, height),
            "output_format": "PNG",
        }
        if seed is not None:
            input_params["seed"] = seed
        if system_prompt:
            input_params["system_prompt"] = system_prompt
        # Allow caller to override / add model-specific fields.
        input_params.update(kwargs)

        try:
            run_id = self._start_run(input_params)
            urls = self._poll_run(run_id)

            images: list[Image.Image] = []
            for asset_url in urls:
                dl = httpx.get(asset_url, timeout=60.0)
                dl.raise_for_status()
                images.append(Image.open(io.BytesIO(dl.content)))

            logger.info("magica_generation_complete", num_images=len(images))
            return images
        except httpx.HTTPStatusError as e:
            logger.error(
                "magica_api_error", status=e.response.status_code, error=str(e)
            )
            raise RuntimeError(f"Magica API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("magica_request_error", error=str(e))
            raise RuntimeError(f"Magica request failed: {e}") from e

    def clear_vram(self) -> None:
        """No-op (remote). Present for interface parity."""

    def unload(self) -> None:
        """No-op (remote). Present for interface parity."""

    def __enter__(self) -> MagicaGenerator:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        self.unload()
        return False
