"""Image upscaling using Stable Diffusion x4 Upscaler."""

from typing import Any, Literal

import torch
from diffusers import StableDiffusionUpscalePipeline
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ImageUpscaler:
    """Handles image upscaling using diffusion models."""

    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-x4-upscaler",
        device: Literal["cuda", "mps", "cpu"] = "cuda",
        dtype: torch.dtype = torch.float16,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.pipeline: Any = None

    def load_model(self) -> None:
        """Load the upscaling pipeline."""
        if self.pipeline is not None:
            return

        logger.info("loading_upscaler", model=self.model_id)

        try:
            self.pipeline = StableDiffusionUpscalePipeline.from_pretrained(
                self.model_id,
                torch_dtype=self.dtype,
                variant="fp16" if self.dtype == torch.float16 else None,
            )

            if self.device == "cuda":
                self.pipeline.enable_model_cpu_offload()
            elif self.device != "cuda":
                self.pipeline = self.pipeline.to(self.device)

            # Optimizations
            self.pipeline.enable_attention_slicing()
            if hasattr(self.pipeline, "enable_vae_slicing"):
                self.pipeline.enable_vae_slicing()

            logger.info("upscaler_loaded")
        except Exception as e:
            logger.error("upscaler_load_failed", error=str(e))
            raise

    def upscale(
        self,
        image: Image.Image,
        prompt: str,
        num_inference_steps: int = 20,
        guidance_scale: float = 9.0,
        noise_level: int = 20,
    ) -> Image.Image:
        """Upscale an image by 4x.

        Args:
            image: Input low-res image
            prompt: Text description to guide hallucination of details
            noise_level: 0-100, how much noise to add (higher = more creative/different)
        """
        if not self.pipeline:
            self.load_model()

        # Assert pipeline is loaded after load_model()
        assert self.pipeline is not None, "Pipeline failed to load"

        logger.info("upscaling_image", size=image.size)

        try:
            # Ensure proper mode
            if image.mode != "RGB":
                image = image.convert("RGB")

            # SD x4 Upscaler usually takes low-res images.
            # If image is already large, resizing might be needed or chunking.
            # But the model creates 4x output.

            result: Image.Image = self.pipeline(
                prompt=prompt,
                image=image,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                noise_level=noise_level,
            ).images[0]

            logger.info("image_upscaled", new_size=result.size)
            return result
        except Exception as e:
            logger.error("upscaling_failed", error=str(e))
            raise

    def unload(self) -> None:
        """Unload model to free memory."""
        if self.pipeline:
            del self.pipeline
            self.pipeline = None
            if self.device == "cuda":
                torch.cuda.empty_cache()
            elif self.device == "mps":
                torch.mps.empty_cache()
