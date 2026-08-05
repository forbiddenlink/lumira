"""Backend factory for image generators.

Selects the image-generation backend from ``config.model.backend`` and returns a
duck-typed generator exposing ``load_model()`` and
``generate(prompt, ...) -> list[PIL.Image]``.

Backends:
    - ``"local"``     : :class:`ImageGenerator` (diffusers SDXL/FLUX, local GPU)
    - ``"replicate"`` : :class:`ReplicateGenerator` (hosted Replicate API)

    - ``"magica"``    : :class:`MagicaGenerator` (Magica/Galaxy AI hosted REST API,
      multi-model image; gated on ``MAGICA_API_KEY``). See ``AI/diagrams/MAGICA_INTEGRATION.md``.

All backends share a construction signature ``(model_id, device, dtype)`` where the remote
backends ignore ``device``/``dtype`` — so callers can swap backends without changing their
call site.
"""

from __future__ import annotations

import os
from typing import Any, Literal, Protocol, cast, runtime_checkable

from ..utils.logging import get_logger

logger = get_logger(__name__)

BACKEND_LOCAL = "local"
BACKEND_REPLICATE = "replicate"
BACKEND_MAGICA = "magica"
KNOWN_BACKENDS = (BACKEND_LOCAL, BACKEND_REPLICATE, BACKEND_MAGICA)

_Device = Literal["cuda", "mps", "cpu"]


@runtime_checkable
class ImageBackend(Protocol):
    """Minimal duck-typed surface every image backend must expose."""

    def load_model(self, *args: Any, **kwargs: Any) -> None: ...

    def generate(self, prompt: str, *args: Any, **kwargs: Any) -> list: ...

    def unload(self) -> None: ...


def resolve_web_image_backend(configured: str | None = None) -> str:
    """Resolve the image backend for studio / cloud create paths.

    Explicit ``magica`` / ``replicate`` / ``local`` values win. When the config
    still says ``local`` (the Pydantic default) but Magica or Replicate keys are
    present, prefer Magica then Replicate — matching Magica-first studio intent
    and torch-free Railway deploys. Set ``LUMIRA_FORCE_LOCAL_WEB=1`` to keep
    on-device generation even when cloud keys exist.
    """
    backend = (configured or BACKEND_LOCAL).lower()
    if backend not in KNOWN_BACKENDS:
        logger.warning("unknown_image_backend", backend=backend, fallback=BACKEND_LOCAL)
        backend = BACKEND_LOCAL

    if backend != BACKEND_LOCAL:
        return backend

    if os.getenv("LUMIRA_FORCE_LOCAL_WEB", "").strip() in {"1", "true", "yes"}:
        return BACKEND_LOCAL
    if os.environ.get("MAGICA_API_KEY"):
        return BACKEND_MAGICA
    if os.environ.get("REPLICATE_API_TOKEN"):
        return BACKEND_REPLICATE
    return BACKEND_LOCAL


def _model_id_for_backend(backend: str, config: Any, mood: str | None) -> str:
    """Pick a backend-appropriate model id (mood-aware for Magica)."""
    if backend == BACKEND_MAGICA:
        from .magica_generator import DEFAULT_MODEL, model_for_mood

        return model_for_mood(mood) if mood else DEFAULT_MODEL

    if backend == BACKEND_REPLICATE:
        from .replicate_generator import DEFAULT_MODEL as REP_DEFAULT
        from .replicate_generator import REPLICATE_MODELS

        base = getattr(getattr(config, "model", None), "base_model", None) or ""
        # HuggingFace-style ids (e.g. Lykon/dreamshaper-8) are not Replicate keys;
        # fall back to the cloud default so studio create keeps working.
        if base in REPLICATE_MODELS or "/" in base and ":" in base:
            return base
        lowered = base.lower()
        for key in REPLICATE_MODELS:
            if key in lowered:
                return key
        return REP_DEFAULT

    return getattr(getattr(config, "model", None), "base_model", "") or (
        "stabilityai/stable-diffusion-xl-base-1.0"
    )


def build_web_image_generator(
    config: Any,
    *,
    mood: str | None = None,
    dtype: Any = None,
    require_img2img: bool = False,
    preferred_model_id: str | None = None,
) -> tuple[str, ImageBackend]:
    """Build the studio/cloud image generator from config + env keys.

    Returns ``(backend, generator)``. When ``require_img2img`` is True and the
    resolved backend is Magica (no img2img yet), fall back to Replicate if a
    token is present; otherwise raise ``RuntimeError``.

    ``preferred_model_id`` (from the adaptive learner) is honored for local and
    Replicate backends only — Magica keeps mood-routed Nano Banana / Flux ids.
    """
    backend = resolve_web_image_backend(getattr(config.model, "backend", None))

    if require_img2img and backend == BACKEND_MAGICA:
        if os.environ.get("REPLICATE_API_TOKEN"):
            logger.info(
                "img2img_backend_fallback",
                requested=BACKEND_MAGICA,
                using=BACKEND_REPLICATE,
            )
            backend = BACKEND_REPLICATE
        else:
            raise RuntimeError(
                "img2img is not available on the Magica image backend yet. "
                "Set REPLICATE_API_TOKEN or config.model.backend=local."
            )

    model_id = _model_id_for_backend(backend, config, mood)
    if preferred_model_id and backend != BACKEND_MAGICA:
        # Accept learner suggestion when it looks usable for this backend
        if backend == BACKEND_REPLICATE:
            from .replicate_generator import REPLICATE_MODELS

            if (
                preferred_model_id in REPLICATE_MODELS
                or "/" in preferred_model_id
                and ":" in preferred_model_id
            ):
                model_id = preferred_model_id
        else:
            model_id = preferred_model_id
        logger.info(
            "learner_model_suggestion_applied",
            backend=backend,
            model_id=model_id,
            mood=mood,
        )

    device = getattr(config.model, "device", "cpu")
    generator = get_image_generator(
        backend, model_id=model_id, device=device, dtype=dtype
    )
    return backend, generator


def get_image_generator(
    backend: str = BACKEND_LOCAL,
    *,
    model_id: str,
    device: str = "cuda",
    dtype: Any = None,
) -> ImageBackend:
    """Construct the image generator for the given backend.

    Args:
        backend: One of :data:`KNOWN_BACKENDS`. Unknown/empty values fall back to
            ``"local"`` with a warning (behavior-preserving default).
        model_id: Model identifier. Interpretation depends on the backend
            (HuggingFace repo for local; ``REPLICATE_MODELS`` key or full id for replicate).
        device: Torch device for the local backend (ignored by remote backends).
        dtype: Torch dtype for the local backend. When ``None`` the local backend
            uses its own default (ignored by remote backends).

    Returns:
        A duck-typed generator implementing :class:`ImageBackend`.
    """
    backend = (backend or BACKEND_LOCAL).lower()

    if backend == BACKEND_REPLICATE:
        from .replicate_generator import ReplicateGenerator

        logger.info("image_backend_selected", backend=backend, model_id=model_id)
        return ReplicateGenerator(
            model_id=model_id, device=cast(_Device, device), dtype=dtype
        )

    if backend == BACKEND_MAGICA:
        from .magica_generator import MagicaGenerator

        logger.info("image_backend_selected", backend=backend, model_id=model_id)
        return MagicaGenerator(
            model_id=model_id, device=cast(_Device, device), dtype=dtype
        )

    if backend != BACKEND_LOCAL:
        logger.warning("unknown_image_backend", backend=backend, fallback=BACKEND_LOCAL)

    from .generator import ImageGenerator

    logger.info("image_backend_selected", backend=BACKEND_LOCAL, model_id=model_id)
    kwargs: dict[str, Any] = {"model_id": model_id, "device": device}
    if dtype is not None:
        kwargs["dtype"] = dtype
    return ImageGenerator(**kwargs)
