"""Inpainting module for fixing image defects."""

from typing import Any, Literal

import torch
from diffusers import DPMSolverMultistepScheduler, StableDiffusionInpaintPipeline
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ImageInpainter:
    """Handles image inpainting (fixing/replacing parts of images)."""

    def __init__(
        self,
        model_id: str = "runwayml/stable-diffusion-inpainting",
        device: Literal["cuda", "mps", "cpu"] = "cuda",
        dtype: torch.dtype = torch.float16,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.pipeline: Any = None

    def load_model(self) -> None:
        """Load the inpainting pipeline."""
        logger.info("loading_inpainter", model=self.model_id)
        try:
            self.pipeline = StableDiffusionInpaintPipeline.from_pretrained(
                self.model_id,
                torch_dtype=self.dtype,
                use_safetensors=True,
                variant="fp16" if self.dtype == torch.float16 else None,
            )

            # Optimizations
            if self.device == "cuda":
                self.pipeline.enable_model_cpu_offload()

            self.pipeline.enable_attention_slicing()

            # Scheduler
            self.pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
                self.pipeline.scheduler.config
            )

            if self.device != "cuda":
                self.pipeline = self.pipeline.to(self.device)

            if self.device == "mps":
                # Fix for MPS VAE issues
                self.pipeline.vae = self.pipeline.vae.to(dtype=torch.float32)

            logger.info("inpainter_loaded")
        except Exception as e:
            logger.error("inpainter_load_failed", error=str(e))
            raise

    def inpaint(
        self,
        image: Image.Image,
        mask: Image.Image,
        prompt: str,
        negative_prompt: str = "",
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        strength: float = 0.75,
    ) -> Image.Image:
        """Inpaint a specific area of the image defined by the mask.

        Args:
            image: Original image
            mask: Black and white mask image (white = inpaint this)
            prompt: What to put in the masked area
            strength: How much to change the masked area (0.0-1.0)
        """
        if not self.pipeline:
            self.load_model()

        if self.pipeline is None:
            raise RuntimeError("Failed to load inpainting pipeline")

        logger.info("inpainting_image", prompt=prompt[:50])

        result: Image.Image = self.pipeline(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image,
            mask_image=mask,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            strength=strength,
        ).images[0]

        return result
