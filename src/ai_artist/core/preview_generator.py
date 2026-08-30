"""Fast preview generation using FLUX.1 Schnell.

The PreviewGenerator enables rapid iteration by generating
4-step previews (~2 seconds) before committing to full renders.
"""

import base64
import io
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from PIL import Image

logger = get_logger(__name__)


@dataclass
class PreviewResult:
    """Result from a preview generation."""

    image: "Image.Image | None" = None
    generation_time: float = 0.0
    prompt: str = ""
    style_weights: dict[str, float] = field(default_factory=dict)
    mood_blend: dict[str, float] = field(default_factory=dict)
    seed: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (without image)."""
        return {
            "generation_time": self.generation_time,
            "prompt": self.prompt,
            "style_weights": self.style_weights,
            "mood_blend": self.mood_blend,
            "seed": self.seed,
            "error": self.error,
            "has_image": self.image is not None,
        }

    def get_image_base64(self) -> str | None:
        """Get base64-encoded image for transmission."""
        if self.image is None:
            return None

        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


@dataclass
class PreviewConfig:
    """Configuration for preview generation."""

    model_id: str = "black-forest-labs/FLUX.1-schnell"
    num_inference_steps: int = 4  # Schnell optimized for 4 steps
    height: int = 1024
    width: int = 1024
    guidance_scale: float = 0.0  # Schnell doesn't use guidance
    device: str = "auto"  # auto | mps | cuda | cpu
    dtype: str = "bfloat16"
    enable_attention_slicing: bool = True
    auto_approve_threshold: float = 0.7


def _detect_device(preferred: str = "auto") -> str:
    """Pick a usable torch device, falling back when MPS/CUDA are unavailable."""
    if preferred and preferred != "auto":
        # Honor explicit choice only if that backend is actually usable
        try:
            import torch

            if preferred == "cuda" and torch.cuda.is_available():
                return "cuda"
            if (
                preferred == "mps"
                and getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
            ):
                return "mps"
            if preferred == "cpu":
                return "cpu"
        except Exception:
            if preferred == "cpu":
                return "cpu"
        # Fall through to auto if preferred isn't available
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _hf_token() -> str | None:
    """Return a real HF token, or None if missing/placeholder."""
    import os

    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        lowered = raw.lower()
        if (
            "your_" in lowered
            or lowered.endswith("_here")
            or lowered in {"changeme", "xxx", "hf_xxx"}
            or "huggingface_token" in lowered
        ):
            continue
        return raw
    return None


# Process-wide singleton so we don't reload FLUX on every preview request
# (defined after PreviewGenerator class below)


class PreviewGenerator:
    """Generates fast previews using FLUX.1 Schnell.

    Enables a two-stage workflow:
    1. Generate fast preview (~2 seconds)
    2. If approved, generate full quality (~30 seconds)

    This saves time by validating concepts before expensive renders.
    """

    def __init__(
        self,
        config: PreviewConfig | None = None,
        style_interpolator: Any = None,
        mood_blender: Any = None,
    ):
        """Initialize the preview generator.

        Args:
            config: Preview configuration
            style_interpolator: Optional StyleInterpolator for LoRA blending
            mood_blender: Optional MoodBlender for mood colors
        """
        self.config = config or PreviewConfig()
        self.config.device = _detect_device(self.config.device)
        self.style_interpolator = style_interpolator
        self.mood_blender = mood_blender

        # diffusers builds the pipeline dynamically; the declared class does
        # not carry .to()/.enable_attention_slicing()/__call__.
        self._pipeline: Any = None
        self._loaded = False
        self._load_time: float = 0.0
        self._last_error: str | None = None

        logger.info(
            "preview_generator_initialized",
            model=self.config.model_id,
            device=self.config.device,
        )

    @property
    def is_loaded(self) -> bool:
        """Check if pipeline is loaded."""
        return self._loaded and self._pipeline is not None

    async def ensure_loaded(self) -> bool:
        """Lazy load the FLUX.1 Schnell pipeline.

        Returns:
            True if loaded successfully
        """
        if self._loaded:
            return True

        try:
            import os

            import torch
            from diffusers import FluxPipeline

            start = time.time()
            self.config.device = _detect_device(self.config.device)

            # FLUX.1-schnell is gated — fail with a clear message when unauthenticated
            token = _hf_token()
            if not token:
                self._last_error = (
                    "Preview needs Hugging Face auth for FLUX.1-schnell. "
                    "Set a real HF_TOKEN in .env (https://huggingface.co/settings/tokens), "
                    "accept the model license, then restart the server."
                )
                logger.error("schnell_load_failed", error=self._last_error)
                return False

            # Pass token to huggingface hub
            os.environ.setdefault("HF_TOKEN", token)
            os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)
            # Determine dtype — bfloat16 is unreliable on CPU
            if self.config.device == "cpu":
                dtype = torch.float32
            elif self.config.dtype == "bfloat16":
                dtype = torch.bfloat16
            else:
                dtype = torch.float16

            # Load pipeline
            self._pipeline = FluxPipeline.from_pretrained(
                self.config.model_id,
                torch_dtype=dtype,
            )

            # Move to device
            self._pipeline = self._pipeline.to(self.config.device)

            # Enable optimizations
            if self.config.enable_attention_slicing:
                self._pipeline.enable_attention_slicing()

            self._load_time = time.time() - start
            self._loaded = True
            self._last_error = None

            logger.info(
                "schnell_pipeline_loaded",
                load_time=round(self._load_time, 2),
                device=self.config.device,
            )
            return True

        except ImportError as e:
            self._last_error = (
                f"Preview dependencies missing ({e}). "
                "Install with: pip install '.[flux]'"
            )
            logger.error("diffusers_import_failed", error=str(e))
            return False
        except Exception as e:
            err = str(e)
            if "401" in err or "gated" in err.lower() or "authorized" in err.lower():
                self._last_error = (
                    "Preview needs Hugging Face auth for FLUX.1-schnell. "
                    "Set HF_TOKEN in .env, accept the model license at "
                    "https://huggingface.co/black-forest-labs/FLUX.1-schnell, "
                    "then restart the server."
                )
            else:
                self._last_error = f"Failed to load preview pipeline: {e}"
            logger.error("schnell_load_failed", error=err)
            return False

    async def preview(
        self,
        prompt: str,
        style_weights: dict[str, float] | None = None,
        mood_blend: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> PreviewResult:
        """Generate a fast preview.

        Args:
            prompt: Generation prompt
            style_weights: Optional LoRA style blend
            mood_blend: Optional mood blend for color hints
            seed: Optional seed for reproducibility

        Returns:
            PreviewResult with image and metadata
        """
        import torch

        result = PreviewResult(
            prompt=prompt,
            style_weights=style_weights or {},
            mood_blend=mood_blend or {},
        )

        # Ensure pipeline is loaded
        if not await self.ensure_loaded():
            result.error = self._last_error or "Failed to load preview pipeline"
            return result

        start = time.time()

        try:
            # Handle seed
            generator = None
            if seed is not None:
                generator = torch.Generator(device=self.config.device)
                generator.manual_seed(seed)
                result.seed = seed
            else:
                result.seed = int(torch.randint(0, 2**32 - 1, (1,)).item())

            # Apply style blend if available
            if style_weights and self.style_interpolator:
                await self.style_interpolator.set_blend(style_weights)

            # Enhance prompt with mood colors if blending
            enhanced_prompt = prompt
            if mood_blend and self.mood_blender:
                blended = self.mood_blender.blend(mood_blend)
                if blended.colors:
                    color_str = ", ".join(blended.colors[:3])
                    enhanced_prompt = f"{prompt}, {color_str} color palette"
                if blended.atmosphere:
                    enhanced_prompt = f"{enhanced_prompt}, {blended.atmosphere}"

            # Generate preview (pipeline guaranteed loaded by ensure_loaded check above)
            assert self._pipeline is not None
            output = self._pipeline(
                prompt=enhanced_prompt,
                num_inference_steps=self.config.num_inference_steps,
                height=self.config.height,
                width=self.config.width,
                guidance_scale=self.config.guidance_scale,
                generator=generator,
            )

            result.image = output.images[0]
            result.generation_time = time.time() - start

            logger.info(
                "preview_generated",
                time=round(result.generation_time, 2),
                prompt_length=len(prompt),
            )

        except Exception as e:
            result.error = str(e)
            result.generation_time = time.time() - start
            logger.error("preview_failed", error=str(e))

        return result

    async def preview_variations(
        self,
        prompt: str,
        count: int = 4,
        style_weights: dict[str, float] | None = None,
    ) -> list[PreviewResult]:
        """Generate multiple preview variations.

        Args:
            prompt: Base prompt
            count: Number of variations
            style_weights: Optional style blend

        Returns:
            List of PreviewResult objects
        """
        results = []
        for _i in range(count):
            result = await self.preview(
                prompt=prompt,
                style_weights=style_weights,
                seed=None,  # Random seed for each variation
            )
            results.append(result)

        return results

    async def preview_with_approval(
        self,
        prompt: str,
        scorer: Any = None,
        threshold: float | None = None,
        style_weights: dict[str, float] | None = None,
        mood_blend: dict[str, float] | None = None,
    ) -> tuple[PreviewResult, bool, float]:
        """Generate preview and auto-evaluate for approval.

        Args:
            prompt: Generation prompt
            scorer: Optional quality scorer (e.g., ImageCurator)
            threshold: Approval threshold (uses config default if not set)
            style_weights: Optional style blend
            mood_blend: Optional mood blend

        Returns:
            Tuple of (result, approved, score)
        """
        threshold = threshold or self.config.auto_approve_threshold

        result = await self.preview(
            prompt=prompt,
            style_weights=style_weights,
            mood_blend=mood_blend,
        )

        if result.error or result.image is None:
            return result, False, 0.0

        # Score the preview if scorer available
        score = 0.0
        if scorer is not None:
            try:
                score = await scorer.quick_score(result.image)
            except Exception as e:
                logger.warning("scoring_failed", error=str(e))
                score = 0.5  # Neutral score on failure

        approved = score >= threshold

        logger.info(
            "preview_evaluated",
            score=round(score, 3),
            threshold=threshold,
            approved=approved,
        )

        return result, approved, score

    async def unload(self) -> None:
        """Unload the pipeline to free memory."""
        if self._pipeline is not None:
            del self._pipeline
            self._pipeline = None
            self._loaded = False

            # Force garbage collection
            import gc

            gc.collect()

            # Clear CUDA/MPS cache if available
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                elif hasattr(torch, "mps") and torch.backends.mps.is_available():
                    torch.mps.empty_cache()
            except Exception:
                pass

            logger.info("preview_pipeline_unloaded")

    def get_stats(self) -> dict[str, Any]:
        """Get generator statistics."""
        return {
            "loaded": self._loaded,
            "model_id": self.config.model_id,
            "device": self.config.device,
            "load_time": self._load_time,
            "steps": self.config.num_inference_steps,
            "resolution": f"{self.config.width}x{self.config.height}",
        }


class TwoStageGenerator:
    """Orchestrates two-stage generation: preview then full render.

    Workflow:
    1. Generate fast preview with FLUX.1 Schnell
    2. Evaluate or wait for user approval
    3. If approved, generate full quality with FLUX.2 or SDXL
    """

    def __init__(
        self,
        preview_generator: PreviewGenerator,
        full_generator: Any = None,  # ImageGenerator or FluxGenerator
        scorer: Any = None,
    ):
        """Initialize two-stage generator.

        Args:
            preview_generator: Fast preview generator
            full_generator: Full quality generator
            scorer: Quality scorer for auto-approval
        """
        self.preview = preview_generator
        self.full = full_generator
        self.scorer = scorer

        logger.info("two_stage_generator_initialized")

    async def generate_with_preview(
        self,
        prompt: str,
        style_weights: dict[str, float] | None = None,
        mood_blend: dict[str, float] | None = None,
        auto_approve: bool = True,
        on_preview: Any = None,  # Callback when preview ready
    ) -> dict[str, Any]:
        """Generate with preview step.

        Args:
            prompt: Generation prompt
            style_weights: Style blend
            mood_blend: Mood blend
            auto_approve: Whether to auto-approve based on score
            on_preview: Optional callback(PreviewResult, approved, score)

        Returns:
            Dict with preview_result, approved, final_image (if approved)
        """
        result: dict[str, Any] = {
            "prompt": prompt,
            "preview_result": None,
            "preview_approved": False,
            "preview_score": 0.0,
            "final_image": None,
            "total_time": 0.0,
        }

        start = time.time()

        # Stage 1: Preview
        preview_result, approved, score = await self.preview.preview_with_approval(
            prompt=prompt,
            scorer=self.scorer if auto_approve else None,
            style_weights=style_weights,
            mood_blend=mood_blend,
        )

        result["preview_result"] = preview_result
        result["preview_approved"] = approved
        result["preview_score"] = score

        # Call preview callback if provided
        if on_preview:
            try:
                callback_result = on_preview(preview_result, approved, score)
                if hasattr(callback_result, "__await__"):
                    await callback_result
            except Exception as e:
                logger.warning("preview_callback_failed", error=str(e))

        # Stage 2: Full render (if approved and generator available)
        if approved and self.full is not None:
            try:
                logger.info("starting_full_render", prompt=prompt[:50])

                # Apply style blend to full generator if supported
                if style_weights and hasattr(self.full, "set_lora_weights"):
                    await self.full.set_lora_weights(style_weights)

                # Generate full quality
                if hasattr(self.full, "generate"):
                    full_image = await self.full.generate(prompt=prompt)
                    result["final_image"] = full_image
                else:
                    logger.warning("full_generator_no_generate_method")

            except Exception as e:
                logger.error("full_render_failed", error=str(e))

        result["total_time"] = time.time() - start

        logger.info(
            "two_stage_complete",
            total_time=round(result["total_time"], 2),
            approved=approved,
            has_final=result["final_image"] is not None,
        )

        return result


# Process-wide singleton so we don't reload FLUX on every preview request
_preview_singleton: PreviewGenerator | None = None


def get_preview_generator(
    config: PreviewConfig | None = None,
    style_interpolator: Any = None,
    mood_blender: Any = None,
) -> PreviewGenerator:
    """Return a cached PreviewGenerator instance."""
    global _preview_singleton
    if _preview_singleton is None:
        cfg = config or PreviewConfig()
        cfg.device = _detect_device(cfg.device)
        _preview_singleton = PreviewGenerator(
            config=cfg,
            style_interpolator=style_interpolator,
            mood_blender=mood_blender,
        )
    elif mood_blender is not None:
        _preview_singleton.mood_blender = mood_blender
    return _preview_singleton
