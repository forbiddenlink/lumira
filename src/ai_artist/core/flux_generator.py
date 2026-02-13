"""Image generation using Black Forest Labs' FLUX models.

FLUX.1 models are the 2025-2026 production standard with superior quality
and text rendering capabilities. This generator provides a compatible
interface with ImageGenerator for seamless integration.
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

import torch
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)

# FLUX model identifiers
FLUX_SCHNELL = "black-forest-labs/FLUX.1-schnell"  # Fast generation (4 steps)
FLUX_DEV = "black-forest-labs/FLUX.1-dev"  # Higher quality (50 steps)


class FluxGenerator:
    """FLUX image generator with support for schnell (fast) and dev (quality) models.

    FLUX models differ from SDXL in several ways:
    - Prefer detailed natural language prompts over keyword-style prompts
    - FLUX.1-schnell: Fast 4-step generation, ignores guidance_scale
    - FLUX.1-dev: High quality 50-step generation, uses guidance_scale
    - Better text rendering and prompt understanding
    - Larger memory footprint (8-bit quantization recommended)

    Can be used as a context manager for automatic cleanup:
        with FluxGenerator() as generator:
            generator.load_model()
            images = generator.generate("A serene landscape at dawn")
    """

    # Model configurations
    MODEL_CONFIGS = {
        FLUX_SCHNELL: {
            "default_steps": 4,
            "uses_guidance": False,
            "description": "Fast 4-step generation",
        },
        FLUX_DEV: {
            "default_steps": 50,
            "uses_guidance": True,
            "description": "High quality generation",
        },
    }

    def __init__(
        self,
        model_id: str = FLUX_SCHNELL,
        device: Literal["cuda", "mps", "cpu"] = "cuda",
        dtype: torch.dtype = torch.float16,
        use_8bit: bool = False,
    ):
        """Initialize FLUX generator.

        Args:
            model_id: FLUX model to use (schnell or dev)
            device: Target device (cuda/mps/cpu)
            dtype: Model dtype (float16 recommended for FLUX)
            use_8bit: Use 8-bit quantization for memory efficiency
        """
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.use_8bit = use_8bit
        self.pipeline = None

        # Get model config
        self.config = self.MODEL_CONFIGS.get(
            model_id,
            self.MODEL_CONFIGS[FLUX_SCHNELL],
        )

        # Validate model choice
        if model_id not in self.MODEL_CONFIGS:
            logger.warning(
                "unknown_flux_model",
                model_id=model_id,
                using=FLUX_SCHNELL,
                hint=f"Supported models: {list(self.MODEL_CONFIGS.keys())}",
            )
            self.model_id = FLUX_SCHNELL
            self.config = self.MODEL_CONFIGS[FLUX_SCHNELL]

        # FLUX on MPS can be unstable with float16
        if device == "mps" and dtype == torch.float16:
            logger.warning(
                "flux_mps_float16_warning",
                message="FLUX on MPS with float16 may be unstable. "
                "Consider using float32 or enabling 8-bit quantization.",
            )

        logger.info(
            "initializing_flux_generator",
            model=self.model_id,
            device=device,
            dtype=str(dtype),
            use_8bit=use_8bit,
            model_type=self.config["description"],
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically cleanup resources."""
        self.unload()
        return False

    @property
    def is_schnell(self) -> bool:
        """Check if using FLUX.1-schnell (fast) model."""
        return self.model_id == FLUX_SCHNELL

    @property
    def is_dev(self) -> bool:
        """Check if using FLUX.1-dev (quality) model."""
        return self.model_id == FLUX_DEV

    def load_model(self):
        """Load the FLUX pipeline.

        FLUX requires specific pipeline loading unlike SDXL.
        Uses FluxPipeline from diffusers with optional 8-bit quantization.
        """
        logger.info(
            "loading_flux_model",
            model=self.model_id,
            use_8bit=self.use_8bit,
        )

        try:
            # Import FLUX-specific pipeline
            from diffusers import FluxPipeline

            # Build loading kwargs
            load_kwargs = {
                "torch_dtype": self.dtype,
            }

            # 8-bit quantization for memory efficiency
            if self.use_8bit:
                try:
                    from transformers import BitsAndBytesConfig

                    quantization_config = BitsAndBytesConfig(load_in_8bit=True)
                    load_kwargs["quantization_config"] = quantization_config
                    logger.info("flux_8bit_quantization_enabled")
                except ImportError:
                    logger.warning(
                        "flux_8bit_unavailable",
                        message="bitsandbytes not installed, using full precision",
                        hint="pip install bitsandbytes for 8-bit quantization",
                    )

            # Load the pipeline
            pipeline = FluxPipeline.from_pretrained(
                self.model_id,
                **load_kwargs,
            )

            # Move to device (unless using 8-bit which handles this)
            if not self.use_8bit:
                pipeline = pipeline.to(self.device)

            # Enable memory optimizations
            self._apply_optimizations(pipeline)

            self.pipeline = pipeline
            logger.info("flux_model_loaded", model=self.model_id, device=self.device)

        except Exception as e:
            logger.error("flux_model_load_failed", model=self.model_id, error=str(e))
            raise

    def _apply_optimizations(self, pipeline):
        """Apply memory and speed optimizations to the pipeline."""
        # Enable attention slicing for memory efficiency
        if hasattr(pipeline, "enable_attention_slicing"):
            try:
                pipeline.enable_attention_slicing(1)
                logger.debug("flux_attention_slicing_enabled")
            except Exception as e:
                logger.debug("flux_attention_slicing_failed", error=str(e))

        # Enable VAE slicing
        if hasattr(pipeline, "enable_vae_slicing"):
            try:
                pipeline.enable_vae_slicing()
                logger.debug("flux_vae_slicing_enabled")
            except Exception as e:
                logger.debug("flux_vae_slicing_failed", error=str(e))

        # Try xFormers for CUDA
        if self.device == "cuda":
            try:
                pipeline.enable_xformers_memory_efficient_attention()
                logger.info("flux_xformers_enabled")
            except Exception:
                logger.debug("flux_xformers_not_available")

    def enhance_prompt_for_flux(self, prompt: str) -> str:
        """Enhance a prompt for FLUX's natural language preference.

        FLUX models prefer detailed, descriptive prompts over keyword-style
        prompts used by SDXL. This method converts terse prompts to more
        descriptive natural language.

        Args:
            prompt: Original prompt (may be keyword-style)

        Returns:
            Enhanced natural language prompt for FLUX
        """
        # If prompt is already long and descriptive, return as-is
        if len(prompt) > 100 and ", " not in prompt[:50]:
            return prompt

        # Check if prompt is keyword-style (contains many commas)
        keyword_indicators = prompt.count(",") > 3

        if keyword_indicators:
            # Convert keyword-style to natural language
            parts = [p.strip() for p in prompt.split(",") if p.strip()]

            if len(parts) > 3:
                # Group keywords into a natural sentence
                subject = parts[0]
                style_parts = [
                    p for p in parts[1:] if "style" in p.lower() or "art" in p.lower()
                ]
                quality_parts = [
                    p
                    for p in parts[1:]
                    if any(
                        q in p.lower()
                        for q in [
                            "detailed",
                            "high quality",
                            "professional",
                            "8k",
                            "4k",
                        ]
                    )
                ]
                mood_parts = [
                    p
                    for p in parts[1:]
                    if p not in style_parts and p not in quality_parts
                ]

                enhanced = f"A detailed image of {subject}"
                if style_parts:
                    enhanced += f", rendered in {', '.join(style_parts[:2])}"
                if mood_parts[:3]:
                    enhanced += f", featuring {', '.join(mood_parts[:3])}"
                if quality_parts:
                    enhanced += f". {', '.join(quality_parts[:2])}"

                logger.debug(
                    "flux_prompt_enhanced",
                    original_len=len(prompt),
                    enhanced_len=len(enhanced),
                )
                return enhanced

        return prompt

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int | None = None,
        guidance_scale: float = 3.5,
        num_images: int = 1,
        seed: int | None = None,
        on_progress: "Callable[[int, int, str], None] | None" = None,
        enhance_prompt: bool = True,
    ) -> list[Image.Image]:
        """Generate images from prompt using FLUX.

        Args:
            prompt: The text prompt for generation
            negative_prompt: What to avoid (note: FLUX has limited negative prompt support)
            width: Image width in pixels
            height: Image height in pixels
            num_inference_steps: Number of steps (defaults based on model)
            guidance_scale: Prompt guidance (only used by FLUX.1-dev)
            num_images: Number of images to generate
            seed: Random seed for reproducibility
            on_progress: Optional callback(step, total_steps, message)
            enhance_prompt: Auto-enhance prompts for FLUX's natural language preference

        Returns:
            List of generated PIL images
        """
        if not self.pipeline:
            raise RuntimeError("Load model first using load_model()")

        # Use model-appropriate defaults
        if num_inference_steps is None:
            num_inference_steps = self.config["default_steps"]

        # Enhance prompt if requested
        if enhance_prompt:
            prompt = self.enhance_prompt_for_flux(prompt)

        logger.info(
            "flux_generating_images",
            prompt=prompt[:100],
            num_images=num_images,
            steps=num_inference_steps,
            model=self.model_id,
            guidance_scale=guidance_scale if self.config["uses_guidance"] else "N/A",
        )

        # Set seed for reproducibility
        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)

        # Progress callback
        def progress_callback(pipeline, step_index, timestep, callback_kwargs):
            step = step_index + 1
            progress_pct = int((step / num_inference_steps) * 100)
            bar_length = 30
            filled = int(bar_length * step // num_inference_steps)
            bar = "\u2588" * filled + "\u2591" * (bar_length - filled)
            print(
                f"\r   [{bar}] {progress_pct}% ({step}/{num_inference_steps} steps)",
                end="",
                flush=True,
            )
            if on_progress is not None:
                message = f"FLUX generating: step {step}/{num_inference_steps}"
                on_progress(step, num_inference_steps, message)
            return callback_kwargs

        # Build generation kwargs
        gen_kwargs = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "num_images_per_prompt": num_images,
            "generator": generator,
            "callback_on_step_end": progress_callback,
        }

        # Only add guidance_scale for dev model (schnell ignores it)
        if self.config["uses_guidance"]:
            gen_kwargs["guidance_scale"] = guidance_scale

        # FLUX has limited negative prompt support, but try if provided
        if negative_prompt and hasattr(self.pipeline, "encode_prompt"):
            # Some FLUX implementations support negative prompts
            gen_kwargs["negative_prompt"] = negative_prompt

        try:
            result = self.pipeline(**gen_kwargs)
            print()  # New line after progress bar

            images = result.images

            logger.info(
                "flux_images_generated",
                count=len(images),
                model=self.model_id,
            )

            # Clear GPU cache after generation
            self.clear_vram()

            return images

        except Exception as e:
            print()  # Clear progress bar line
            logger.error(
                "flux_generation_failed",
                error=str(e),
                model=self.model_id,
            )
            raise

    def clear_vram(self):
        """Clear GPU memory cache to prevent memory leaks."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.debug("flux_cuda_vram_cleared")
        elif torch.backends.mps.is_available():
            torch.mps.empty_cache()
            logger.debug("flux_mps_vram_cleared")

    def unload(self):
        """Unload model from memory and cleanup resources."""
        if self.pipeline:
            logger.info("unloading_flux_model")
            del self.pipeline
            self.pipeline = None

            # Clear GPU cache
            self.clear_vram()

            logger.info("flux_model_unloaded")


def get_flux_model_for_mood(mood: str) -> str:
    """Get the appropriate FLUX model for a given mood.

    Contemplative/Introspective moods use FLUX.1-dev for higher quality.
    Energized/Chaotic moods use FLUX.1-schnell for faster iteration.

    Args:
        mood: The current mood (e.g., "contemplative", "chaotic")

    Returns:
        FLUX model identifier
    """
    # Moods that benefit from higher quality (slower, more detailed)
    quality_moods = {
        "contemplative",
        "introspective",
        "melancholic",
        "serene",
    }

    # Moods that benefit from fast iteration (energetic, experimental)
    fast_moods = {
        "chaotic",
        "energized",
        "rebellious",
        "restless",
        "playful",
        "bold",
    }

    mood_lower = mood.lower()

    if mood_lower in quality_moods:
        return FLUX_DEV
    elif mood_lower in fast_moods:
        return FLUX_SCHNELL
    else:
        # Default to schnell for unknown moods (faster feedback)
        return FLUX_SCHNELL
