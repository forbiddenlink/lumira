"""Image generation using Replicate cloud API.

Uses Replicate's hosted models for fast, GPU-free image generation.
Supports SDXL, FLUX, and other models available on Replicate.
"""

import io
import os
from typing import Any, Literal

import httpx
import replicate
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Popular Replicate models
REPLICATE_MODELS = {
    # SDXL models
    "sdxl": "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
    "dreamshaper": "cjwbw/dreamshaper-xl-v2-turbo:0a1710e0187b01a255c57571dac757571241127397f37fc97d90f18460fc3383",
    # FLUX 1.x models
    "flux-schnell": "black-forest-labs/flux-schnell",
    "flux-dev": "black-forest-labs/flux-dev",
    "flux-pro": "black-forest-labs/flux-1.1-pro",
    "flux-pro-ultra": "black-forest-labs/flux-1.1-pro-ultra",  # 4MP, enhanced photorealism
    # FLUX 2.x models (Nov 2025, 32B params - state of the art)
    "flux2-pro": "black-forest-labs/flux-2-pro",  # Production balanced (6s, $0.015)
    "flux2-dev": "black-forest-labs/flux-2-dev",  # Fast & cheap (2.5s, $0.012/MP)
    "flux2-flex": "black-forest-labs/flux-2-flex",  # Max quality (22s, $0.06/MP)
    "flux2-max": "black-forest-labs/flux-2-max",  # Premium quality
    # FLUX control models
    "flux-canny": "black-forest-labs/flux-canny-pro",  # Edge-guided generation
    "flux-depth": "black-forest-labs/flux-depth-pro",  # Depth-guided generation
    "flux-fill": "black-forest-labs/flux-fill-pro",  # Inpainting
    "flux-redux": "black-forest-labs/flux-redux-dev",  # Image variations
}

# Default to FLUX 2 Pro for best quality/speed balance
DEFAULT_MODEL = "flux2-pro"

# Daily spend backstop for the metered Replicate API. Counts images generated
# per UTC day across this process; refuses new calls once the cap is hit so a
# scripted caller cannot run up an unbounded bill. 0 disables. Configure via
# LUMIRA_REPLICATE_DAILY_MAX_IMAGES.
_spend_day: str | None = None
_spend_count = 0


def _check_replicate_budget(num_images: int) -> None:
    """Enforce the per-day Replicate image budget; raise if exceeded."""
    global _spend_day, _spend_count
    cap = int(os.getenv("LUMIRA_REPLICATE_DAILY_MAX_IMAGES", "200"))
    if cap <= 0:
        return
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if today != _spend_day:
        _spend_day = today
        _spend_count = 0
    if _spend_count + num_images > cap:
        logger.error(
            "replicate_budget_exceeded",
            used=_spend_count,
            requested=num_images,
            daily_cap=cap,
        )
        raise RuntimeError(
            f"Replicate daily image budget exceeded ({_spend_count}/{cap}). "
            "Raise LUMIRA_REPLICATE_DAILY_MAX_IMAGES or wait for the daily reset."
        )
    _spend_count += num_images


class ReplicateGenerator:
    """Image generator using Replicate cloud API.

    Provides a compatible interface with ImageGenerator for seamless integration.
    Uses your REPLICATE_API_TOKEN environment variable for authentication.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        device: Literal[
            "cuda", "mps", "cpu"
        ] = "cpu",  # Ignored, runs on Replicate's GPUs
        dtype=None,  # Ignored, for compatibility
    ):
        """Initialize Replicate generator.

        Args:
            model_id: Model to use - can be a key from REPLICATE_MODELS or a full Replicate model ID
            device: Ignored (Replicate runs on cloud GPUs)
            dtype: Ignored (for compatibility with ImageGenerator)
        """
        # Resolve model ID
        if model_id in REPLICATE_MODELS:
            self.model_id = REPLICATE_MODELS[model_id]
        elif self._is_replicate_model(model_id):
            # It's a valid Replicate model ID format
            self.model_id = model_id
        else:
            # Default to flux-schnell for HuggingFace or unknown models
            logger.info(
                "using_default_replicate_model",
                requested=model_id,
                using=DEFAULT_MODEL,
                reason="Model appears to be HuggingFace format, using Replicate default",
            )
            self.model_id = REPLICATE_MODELS[DEFAULT_MODEL]

        self.model_name = model_id
        self._client = None

        # Check for API token
        self.api_token = os.environ.get("REPLICATE_API_TOKEN")
        if not self.api_token:
            logger.warning(
                "replicate_token_missing",
                message="REPLICATE_API_TOKEN not set. Generation will fail.",
            )

    def load_model(self) -> None:
        """Initialize the Replicate client.

        Unlike local generators, no model download is needed.
        This just validates the API token.
        """
        if not self.api_token:
            raise ValueError(
                "REPLICATE_API_TOKEN environment variable not set. "
                "Get your token at https://replicate.com/account/api-tokens"
            )

        # The replicate library uses the env var automatically
        logger.info("replicate_ready", model=self.model_name)

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        num_images: int = 1,
        seed: int | None = None,
        on_progress=None,  # Not supported by Replicate API
        lora_url: str | None = None,
        lora_scale: float = 1.0,
        **kwargs: Any,  # Tolerate backend-agnostic caller params (e.g. use_refiner)
    ) -> list[Image.Image]:
        """Generate images using Replicate API.

        Args:
            prompt: Text prompt describing the image
            negative_prompt: Things to avoid (supported by SDXL models)
            width: Image width (typically 512-1024)
            height: Image height (typically 512-1024)
            num_inference_steps: Number of denoising steps
            guidance_scale: How closely to follow the prompt (7.5 typical)
            num_images: Number of images to generate
            seed: Random seed for reproducibility
            on_progress: Callback for progress updates (not supported)
            lora_url: URL to LoRA weights file (e.g., from Replicate training)
            lora_scale: LoRA influence strength (0.0-1.0, default 1.0)

        Returns:
            List of PIL Image objects
        """
        if not self.api_token:
            raise ValueError("REPLICATE_API_TOKEN not set")

        _check_replicate_budget(num_images)

        logger.info(
            "replicate_generation_start",
            model=self.model_name,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
            width=width,
            height=height,
        )

        # Build input based on model type (check actual model_id, not original model_name)
        is_flux_model = "flux" in self.model_id.lower()
        is_flux_schnell = "schnell" in self.model_id.lower()
        is_flux2 = (
            "flux-2" in self.model_id.lower() or "flux2" in self.model_name.lower()
        )

        if is_flux_model:
            # FLUX models use different parameters
            input_params = {
                "prompt": prompt,
                "num_outputs": num_images,
                "aspect_ratio": self._get_aspect_ratio(width, height),
                "output_format": "png",
                "output_quality": 90,
            }

            if is_flux2:
                # FLUX 2.x models (32B params, Nov 2025)
                # Support higher steps and have better prompt understanding
                input_params["num_inference_steps"] = min(num_inference_steps, 50)
                input_params["guidance"] = guidance_scale
                # FLUX 2 supports safety tolerance (1-5, higher = more permissive)
                input_params["safety_tolerance"] = 3
                # Enable raw mode for photorealistic outputs
                if "ultra" in self.model_id.lower() or "max" in self.model_id.lower():
                    input_params["raw"] = True
            elif is_flux_schnell:
                # FLUX schnell only accepts up to 4 steps
                input_params["num_inference_steps"] = min(num_inference_steps, 4)
            else:
                # FLUX 1.x dev/pro models
                input_params["num_inference_steps"] = min(num_inference_steps, 50)
                input_params["guidance"] = guidance_scale

            if seed is not None:
                input_params["seed"] = seed

            # Add LoRA support for FLUX models
            if lora_url:
                input_params["hf_lora"] = lora_url
                input_params["lora_scale"] = lora_scale
                logger.info(
                    "using_lora",
                    lora_url=lora_url[:50] + "..." if len(lora_url) > 50 else lora_url,
                    scale=lora_scale,
                )
        else:
            # SDXL and other models
            input_params = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "num_outputs": num_images,
            }
            if seed is not None:
                input_params["seed"] = seed

        try:
            # Run the model
            output = replicate.run(self.model_id, input=input_params)

            # Handle different output formats
            images: list[Image.Image] = []

            # Output can be a list of URLs or FileOutput objects
            urls = output if isinstance(output, list) else [output]

            for url in urls:
                # Handle FileOutput objects
                if hasattr(url, "url"):
                    url = url.url
                elif hasattr(url, "read"):
                    # It's a file-like object
                    img = Image.open(url)
                    images.append(img)
                    continue

                # Download the image
                response = httpx.get(str(url), timeout=60.0)
                response.raise_for_status()
                img = Image.open(io.BytesIO(response.content))
                images.append(img)

            logger.info("replicate_generation_complete", num_images=len(images))
            return images

        except replicate.exceptions.ReplicateError as e:
            logger.error("replicate_api_error", error=str(e))
            raise RuntimeError(f"Replicate API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("replicate_download_error", error=str(e))
            raise RuntimeError(f"Failed to download generated image: {e}") from e

    def generate_img2img(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str = "",
        strength: float = 0.75,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        seed: int | None = None,
    ) -> list[Image.Image]:
        """Generate image-to-image variations using Replicate.

        Args:
            image: Source image to transform
            prompt: Text prompt for the transformation
            negative_prompt: Things to avoid
            strength: How much to change (0.0 = no change, 1.0 = complete change)
            num_inference_steps: Denoising steps
            guidance_scale: Prompt adherence
            seed: Random seed

        Returns:
            List of transformed images
        """
        # Save image to a temporary buffer
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        # Use SDXL img2img model
        img2img_model = "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"

        input_params = {
            "image": buffer,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "prompt_strength": strength,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "num_outputs": 1,
        }
        if seed is not None:
            input_params["seed"] = seed

        try:
            output = replicate.run(img2img_model, input=input_params)

            images: list[Image.Image] = []
            urls = output if isinstance(output, list) else [output]

            for url in urls:
                if hasattr(url, "url"):
                    url = url.url
                response = httpx.get(str(url), timeout=60.0)
                response.raise_for_status()
                img = Image.open(io.BytesIO(response.content))
                images.append(img)

            return images

        except Exception as e:
            logger.error("replicate_img2img_error", error=str(e))
            raise RuntimeError(f"Replicate img2img error: {e}") from e

    def _is_replicate_model(self, model_id: str) -> bool:
        """Check if a model ID looks like a valid Replicate model.

        Replicate models look like:
        - owner/model-name (no version)
        - owner/model-name:version-hash

        HuggingFace models look like:
        - owner/model-name (similar but different ecosystem)

        We check for known Replicate owners/patterns.
        """
        if not model_id or "/" not in model_id:
            return False

        # Known Replicate model owners
        replicate_owners = {
            "stability-ai",
            "black-forest-labs",
            "cjwbw",
            "lucataco",
            "fofr",
            "replicate",
            "meta",
            "bytedance",
        }

        owner = model_id.split("/")[0].lower()
        if owner in replicate_owners:
            return True

        # Check for version hash pattern (indicates Replicate)
        return ":" in model_id

    def _get_aspect_ratio(self, width: int, height: int) -> str:
        """Convert dimensions to FLUX aspect ratio string."""
        ratio = width / height

        # Map to supported FLUX aspect ratios
        if ratio > 1.7:
            return "16:9"
        elif ratio > 1.4:
            return "3:2"
        elif ratio > 1.2:
            return "4:3"
        elif ratio > 0.9:
            return "1:1"
        elif ratio > 0.7:
            return "3:4"
        elif ratio > 0.55:
            return "2:3"
        else:
            return "9:16"

    def cleanup(self) -> None:
        """Clean up resources. No-op for Replicate."""
        pass

    def unload(self) -> None:
        """Release resources. Alias of cleanup for backend-interface parity."""
        self.cleanup()

    def clear_vram(self) -> None:
        """Clear VRAM. No-op for Replicate (runs on cloud)."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
        return False
