"""Spiral hosted multi-model image generator.

Calls the Spiral REST API (https://api.spiral.ai) to run hosted image models
(Nano Banana Pro, FLUX 2, GPT Image, Grok Imagine, ...). Signature-compatible
with :class:`ImageGenerator` and :class:`ReplicateGenerator` so it drops into the
generator factory (``config.model.backend = "spiral"``). Replaces the Magica
backend, which shuts down 2026-12-01.

Each model is a Spiral ``(provider, model)`` pair (see :class:`SpiralModel`);
input schemas differ per model and Spiral rejects unknown fields
(``INVALID_INPUT``), so each family has its own input builder. Schemas below
were read with Spiral's ``inspect`` on 2026-11-25.

Gated behind ``SPIRAL_API_KEY``: with no key, ``generate()`` raises (same as
``ReplicateGenerator`` with a missing token).

NOT validated against a live key: the Spiral account balance was $0 when this
was written, so only unit tests with mocked HTTP cover the run path.
"""

from __future__ import annotations

import io
import os
from typing import Any, Literal

import httpx
from PIL import Image

from ..utils.logging import get_logger
from .spend_guard import check_and_record_images
from .spiral_client import SpiralClient, SpiralModel, parse_model_ref
from .spiral_client import download_bytes as _download_bytes

logger = get_logger(__name__)

__all__ = ["SpiralGenerator", "SPIRAL_MODELS", "SPIRAL_MOOD_MODELS", "model_for_mood"]

# Catalog key -> Spiral (provider, model). Callers may also pass a raw
# ``"provider/model"`` reference (e.g. ``"fal/fal-ai/nano-banana-pro"``).
SPIRAL_MODELS: dict[str, SpiralModel] = {
    "nano_banana_pro": SpiralModel("fal", "fal-ai/nano-banana-pro"),
    "nano_banana_2": SpiralModel("fal", "fal-ai/nano-banana-2"),
    "flux_2_max": SpiralModel("fal", "fal-ai/flux-2-max"),
    "gpt_image_2": SpiralModel("fal", "openai/gpt-image-2"),
    "grok_imagine_image": SpiralModel("fal", "xai/grok-imagine-image"),
}

# Friendly alias -> catalog key.
_FRIENDLY_ALIASES = {
    "nano-banana-pro": "nano_banana_pro",  # Google Gemini 3 Pro Image (default)
    "nano-banana": "nano_banana_2",
    "flux2-max": "flux_2_max",
    "gpt-image": "gpt_image_2",
    "grok-image": "grok_imagine_image",
}

# Default model: Nano Banana Pro (text-to-image, 1K/2K/4K).
DEFAULT_MODEL = "nano_banana_pro"

# Input-schema families (verified via Spiral inspect, 2026-11-25).
_NANO_FAMILY = frozenset({"nano_banana_pro", "nano_banana_2"})
_FLUX_FAMILY = frozenset({"flux_2_max"})
_GPT_FAMILY = frozenset({"gpt_image_2"})
_GROK_FAMILY = frozenset({"grok_imagine_image"})

# Models whose schema has no ``num_images``: one run per image.
_SINGLE_IMAGE_PER_RUN = _FLUX_FAMILY

# Models with no ``seed`` field (sending one is INVALID_INPUT).
_NO_SEED = _GROK_FAMILY

# Mood -> catalog key. Gives Lumira per-mood model diversity (its core idea:
# many distinct models vs one local SDXL). Unknown moods fall back to DEFAULT_MODEL.
SPIRAL_MOOD_MODELS = {
    "contemplative": "nano_banana_pro",
    "introspective": "nano_banana_pro",
    "melancholic": "nano_banana_pro",
    "serene": "nano_banana_pro",
    "bold": "flux_2_max",
    "energized": "flux_2_max",
    "rebellious": "flux_2_max",
    "playful": "gpt_image_2",
    "chaotic": "grok_imagine_image",
    "restless": "grok_imagine_image",
}


def model_for_mood(mood: str) -> str:
    """Return the catalog key mapped to a Lumira mood (DEFAULT_MODEL if unknown)."""
    return SPIRAL_MOOD_MODELS.get(mood.lower(), DEFAULT_MODEL)


def resolve_model(model_id: str | None) -> tuple[str, SpiralModel]:
    """Resolve a catalog key, friendly alias, or ``provider/model`` ref.

    Returns ``(catalog_key, model)``. A raw ref not in the catalog gets its own
    string as the key and the minimal universal input (see
    :func:`_build_model_input`).
    """
    key = model_id or DEFAULT_MODEL
    key = _FRIENDLY_ALIASES.get(key, key)
    if key in SPIRAL_MODELS:
        return key, SPIRAL_MODELS[key]
    return key, parse_model_ref(key)


# Approximate USD per image (Spiral price sentences, 2026-11-25) for the shared
# dollar budget. LUMIRA_SPIRAL_COST_PER_IMAGE_USD overrides every model.
_COST_PER_IMAGE_USD = {
    "nano_banana_pro": 0.195,
    "nano_banana_2": 0.104,
    "flux_2_max": 0.13,
    "gpt_image_2": 0.24,
    "grok_imagine_image": 0.026,
}
_FALLBACK_COST_PER_IMAGE_USD = 0.20


def _cost_per_image(model_key: str) -> float:
    override = os.getenv("LUMIRA_SPIRAL_COST_PER_IMAGE_USD")
    if override:
        return float(override)
    return _COST_PER_IMAGE_USD.get(model_key, _FALLBACK_COST_PER_IMAGE_USD)


def _check_spiral_budget(num_images: int, model_key: str = DEFAULT_MODEL) -> None:
    """Enforce the per-day Spiral image budget (Redis-backed, cross-worker,
    survives restart) plus the global kill switch and dollar cap.

    Routed through the shared spend guard so Spiral spend lands in the same
    Redis-backed ledger as Replicate and the LLM calls (mirrors
    ReplicateGenerator). Like the Replicate path, the guard records on attempt.
    """
    cap = int(os.getenv("LUMIRA_SPIRAL_DAILY_MAX_IMAGES", "200"))
    check_and_record_images("spiral", num_images, cap, _cost_per_image(model_key))


# aspect_ratio values accepted by every image model that takes the field.
_ASPECT_CANDIDATES = {
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
}


def _aspect_ratio(width: int, height: int) -> str:
    """Map pixel dims to the nearest common aspect_ratio enum value."""
    if height <= 0:
        return "1:1"
    ratio = width / height
    return min(_ASPECT_CANDIDATES, key=lambda k: abs(_ASPECT_CANDIDATES[k] - ratio))


def _resolution_tier(width: int, height: int) -> str:
    """Map the larger pixel dimension to the 1K/2K/4K resolution tier."""
    longest = max(width, height)
    if longest >= 3072:
        return "4K"
    if longest >= 1536:
        return "2K"
    return "1K"


def _snap16(value: int, lo: int, hi: int) -> int:
    """Round to the nearest multiple of 16 inside [lo, hi] (lo/hi are multiples of 16)."""
    snapped = round(value / 16) * 16
    return min(max(snapped, lo), hi)


def _clamp_dims(
    width: int, height: int, lo: int = 256, hi: int = 2560
) -> dict[str, int]:
    """Clamp dimensions into [lo, hi], multiples of 16, preserving aspect ratio.

    Scales by the longest side (down) then the shortest (up), so a 3000x1000
    request becomes ~2560x848 rather than the aspect-breaking 2560x1000 a naive
    per-axis clamp would give. A hard clamp on both axes covers extreme ratios
    (> hi:lo) that cannot satisfy both bounds. FLUX 2 needs multiples of 16
    and at most 4,194,304 px (area-limited below).
    """
    w, h = max(width, 1), max(height, 1)
    longest = max(w, h)
    if longest > hi:
        scale = hi / longest
        w, h = round(w * scale), round(h * scale)
    shortest = min(w, h)
    if shortest < lo:
        scale = lo / shortest
        w, h = round(w * scale), round(h * scale)
    max_area = 4_194_304
    if w * h > max_area:
        scale = (max_area / (w * h)) ** 0.5
        w, h = int(w * scale), int(h * scale)
    return {"width": _snap16(w, lo, hi), "height": _snap16(h, lo, hi)}


def _gpt_image_size(width: int, height: int) -> dict[str, int]:
    """Fit dims to GPT Image 2 limits: multiples of 16, max edge 3840, aspect
    at most 3:1, area 655,360 to 8,294,400 px."""
    w, h = max(width, 1), max(height, 1)
    if w > 3 * h:
        w = 3 * h
    if h > 3 * w:
        h = 3 * w
    area = w * h
    scale = 1.0
    if area < 655_360:
        scale = (655_360 / area) ** 0.5
    elif area > 8_294_400:
        scale = (8_294_400 / area) ** 0.5
    w, h = round(w * scale), round(h * scale)
    longest = max(w, h)
    if longest > 3840:
        w, h = round(w * 3840 / longest), round(h * 3840 / longest)
    w, h = round(w / 16) * 16, round(h / 16) * 16
    # Rounding up from the lower bound can still land under it; bump both axes.
    while w * h < 655_360:
        w, h = w + 16, h + 16
    return {"width": w, "height": h}


def _build_model_input(
    model_key: str,
    prompt: str,
    width: int,
    height: int,
    num_images: int,
    seed: int | None,
    output_format: str,
    system_prompt: str,
) -> dict[str, Any]:
    """Build the per-model input payload (Spiral rejects unknown fields).

    Families (verified via Spiral inspect, 2026-11-25):
      - Nano Banana: ``resolution`` + ``aspect_ratio`` + ``system_prompt``.
      - FLUX 2 Max: ``image_size`` {width, height}; no ``num_images``.
      - GPT Image 2: ``image_size`` {width, height}; ``num_images`` up to 10.
      - Grok Imagine: ``resolution`` ("1k"/"2k") + ``aspect_ratio``; no ``seed``.
    Unknown models get the minimal universal fields (``prompt`` + ``seed``);
    callers can add or override model-specific fields via ``generate(**kwargs)``.
    """
    fmt = output_format.lower()
    inp: dict[str, Any] = {"prompt": prompt}
    if model_key in _NANO_FAMILY:
        inp["num_images"] = num_images
        inp["resolution"] = _resolution_tier(width, height)
        inp["aspect_ratio"] = _aspect_ratio(width, height)
        inp["output_format"] = fmt
        if system_prompt:
            inp["system_prompt"] = system_prompt
    elif model_key in _FLUX_FAMILY:
        inp["image_size"] = _clamp_dims(width, height)
        inp["output_format"] = fmt
    elif model_key in _GPT_FAMILY:
        inp["num_images"] = num_images
        inp["image_size"] = _gpt_image_size(width, height)
        inp["output_format"] = fmt
    elif model_key in _GROK_FAMILY:
        inp["num_images"] = num_images
        inp["resolution"] = "2k" if max(width, height) >= 1536 else "1k"
        inp["aspect_ratio"] = _aspect_ratio(width, height)
        inp["output_format"] = fmt
    elif num_images != 1:
        inp["num_images"] = num_images
    if seed is not None and model_key not in _NO_SEED:
        inp["seed"] = seed
    return inp


class SpiralGenerator:
    """Hosted image generator backed by the Spiral REST API.

    Usable as a context manager:
        with SpiralGenerator(model_id="nano_banana_pro") as gen:
            gen.load_model()
            images = gen.generate("a serene misty forest at dawn")
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        device: Literal["cuda", "mps", "cpu"] = "cpu",  # Ignored (cloud GPUs)
        dtype: Any = None,  # Ignored, for signature compatibility
    ) -> None:
        """Initialize the Spiral generator.

        Args:
            model_id: A catalog key from SPIRAL_MODELS, a friendly alias, or a
                raw ``provider/model`` reference.
            device: Ignored (Spiral runs on cloud GPUs).
            dtype: Ignored (for compatibility with ImageGenerator).
        """
        self.model_key, self.model = resolve_model(model_id)
        self.model_name = model_id
        self.api_key = os.environ.get("SPIRAL_API_KEY")
        if not self.api_key:
            logger.warning(
                "spiral_key_missing",
                message="SPIRAL_API_KEY not set. Generation will fail.",
            )

    def load_model(self, *args: Any, **kwargs: Any) -> None:
        """No-op: Spiral models load server-side. Present for interface parity."""
        logger.info(
            "spiral_model_ready",
            provider=self.model.provider,
            model=self.model.model,
        )

    @property
    def _client(self) -> SpiralClient:
        # Built lazily (rather than in __init__) so tests/callers that mutate
        # self.api_key after construction still get an up-to-date client.
        return SpiralClient(api_key=self.api_key)

    def _start_run(self, input_params: dict[str, Any]) -> str:
        """POST a model run; return its run id.

        Deliberately NOT retried: a model run is billed, so retrying an
        ambiguous POST failure could enqueue duplicate runs.
        """
        return self._client.start_run(self.model, input_params)

    def _poll_run(self, run_id: str, timeout_s: float = 300.0) -> list[str]:
        """Poll a run to completion; return generated image URLs."""
        return self._client.poll_run(run_id, timeout_s=timeout_s, kind="image")

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
        use_refiner: bool = False,  # Ignored: local-only concept, must not leak to payload
        system_prompt: str = "",
        **kwargs: Any,
    ) -> list[Image.Image]:
        """Generate images via the Spiral REST API.

        Common fields are built per model family. Genuine model-specific fields
        (per Spiral ``inspect``, e.g. ``safety_tolerance``) can be added via
        ``kwargs``, which are merged into the request input. Local-only params such
        as ``use_refiner`` / ``num_inference_steps`` / ``guidance_scale`` are named
        here so they are ignored rather than leaked into the REST payload.

        Returns:
            List of PIL Image objects.
        """
        if not self.api_key:
            raise ValueError("SPIRAL_API_KEY not set")
        if num_images < 1:
            raise ValueError("num_images must be >= 1")

        _check_spiral_budget(num_images, self.model_key)

        logger.info(
            "spiral_generation_start",
            provider=self.model.provider,
            model=self.model.model,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        # Strip local/Replicate-only kwargs so studio call sites can share one
        # generate(...) signature without leaking them into Spiral's REST input.
        for local_only in (
            "lora_url",
            "lora_scale",
            "reference_image",
            "ip_adapter_scale",
            "negative_prompt",
            "on_progress",
            "use_refiner",
            "num_inference_steps",
            "guidance_scale",
        ):
            kwargs.pop(local_only, None)

        runs = num_images if self.model_key in _SINGLE_IMAGE_PER_RUN else 1
        per_run_images = 1 if self.model_key in _SINGLE_IMAGE_PER_RUN else num_images

        try:
            images: list[Image.Image] = []
            for _ in range(runs):
                input_params = _build_model_input(
                    self.model_key,
                    prompt,
                    width,
                    height,
                    per_run_images,
                    seed,
                    output_format="png",
                    system_prompt=system_prompt,
                )
                # Allow caller to override / add model-specific fields.
                input_params.update(kwargs)
                run_id = self._start_run(input_params)
                for asset_url in self._poll_run(run_id):
                    images.append(Image.open(io.BytesIO(_download_bytes(asset_url))))

            logger.info("spiral_generation_complete", num_images=len(images))
            return images
        except httpx.HTTPStatusError as e:
            logger.error(
                "spiral_api_error", status=e.response.status_code, error=str(e)
            )
            raise RuntimeError(f"Spiral API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("spiral_request_error", error=str(e))
            raise RuntimeError(f"Spiral request failed: {e}") from e

    def clear_vram(self) -> None:
        """No-op (remote). Present for interface parity."""

    def unload(self) -> None:
        """No-op (remote). Present for interface parity."""

    def __enter__(self) -> SpiralGenerator:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        self.unload()
        return False
