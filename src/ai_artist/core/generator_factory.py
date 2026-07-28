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
