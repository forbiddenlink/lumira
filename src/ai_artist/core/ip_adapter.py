"""IP-Adapter support for reference image-based style transfer.

IP-Adapter enables generating images that inherit style, composition,
or character from a reference image without retraining.
"""

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import torch
from PIL import Image

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from diffusers import DiffusionPipeline

logger = get_logger(__name__)


# IP-Adapter model configurations
IP_ADAPTER_MODELS = {
    # SD 1.5 models
    "ip-adapter_sd15": {
        "repo": "h94/IP-Adapter",
        "subfolder": "models",
        "weight_name": "ip-adapter_sd15.bin",
        "description": "Standard IP-Adapter for SD 1.5",
    },
    "ip-adapter-plus_sd15": {
        "repo": "h94/IP-Adapter",
        "subfolder": "models",
        "weight_name": "ip-adapter-plus_sd15.bin",
        "description": "Enhanced IP-Adapter with more style transfer",
    },
    "ip-adapter-plus-face_sd15": {
        "repo": "h94/IP-Adapter",
        "subfolder": "models",
        "weight_name": "ip-adapter-plus-face_sd15.bin",
        "description": "Face-focused IP-Adapter for portraits",
    },
    # SDXL models
    "ip-adapter_sdxl": {
        "repo": "h94/IP-Adapter",
        "subfolder": "sdxl_models",
        "weight_name": "ip-adapter_sdxl.bin",
        "description": "Standard IP-Adapter for SDXL",
    },
    "ip-adapter-plus_sdxl": {
        "repo": "h94/IP-Adapter",
        "subfolder": "sdxl_models",
        "weight_name": "ip-adapter-plus_sdxl.bin",
        "description": "Enhanced IP-Adapter for SDXL",
    },
    "ip-adapter-plus-face_sdxl": {
        "repo": "h94/IP-Adapter",
        "subfolder": "sdxl_models",
        "weight_name": "ip-adapter-plus-face_sdxl.bin",
        "description": "Face-focused IP-Adapter for SDXL",
    },
}


class IPAdapterManager:
    """Manages IP-Adapter for reference image conditioning.

    IP-Adapter allows generating images that inherit visual characteristics
    from a reference image, enabling:
    - Style transfer (match artistic style)
    - Character consistency (maintain character appearance)
    - Composition guidance (follow reference layout)

    Example:
        manager = IPAdapterManager()
        manager.load_ip_adapter(pipeline, "ip-adapter_sdxl")
        images = manager.generate_with_reference(
            pipeline=pipeline,
            prompt="a cat in space",
            reference_image=style_image,
            ip_adapter_scale=0.6
        )
    """

    def __init__(self) -> None:
        """Initialize IP-Adapter manager."""
        self._loaded_adapter: str | None = None
        self._image_encoder = None

    def get_available_adapters(
        self, model_type: Literal["sd15", "sdxl"] = "sdxl"
    ) -> list[dict]:
        """Get list of available IP-Adapter models.

        Args:
            model_type: Base model type ("sd15" or "sdxl")

        Returns:
            List of adapter configurations
        """
        suffix = f"_{model_type}"
        return [
            {"name": name, **config}
            for name, config in IP_ADAPTER_MODELS.items()
            if name.endswith(suffix)
        ]

    def detect_model_type(
        self, pipeline: "DiffusionPipeline"
    ) -> Literal["sd15", "sdxl"]:
        """Detect whether pipeline is SD 1.5 or SDXL.

        Args:
            pipeline: The diffusion pipeline

        Returns:
            Model type string
        """
        class_name = pipeline.__class__.__name__
        if "XL" in class_name or "SDXL" in class_name:
            return "sdxl"
        # Check for SDXL UNet dimensions
        if hasattr(pipeline, "unet"):
            in_channels = getattr(pipeline.unet.config, "in_channels", 4)
            if in_channels > 4:
                return "sdxl"
        return "sd15"

    def get_default_adapter(self, model_type: Literal["sd15", "sdxl"] = "sdxl") -> str:
        """Get the default IP-Adapter for a model type.

        Args:
            model_type: Base model type

        Returns:
            Default adapter name
        """
        return f"ip-adapter_{model_type}"

    def load_ip_adapter(
        self,
        pipeline: "DiffusionPipeline",
        adapter_name: str | None = None,
    ) -> None:
        """Load IP-Adapter weights into pipeline.

        Args:
            pipeline: The diffusion pipeline to load adapter into
            adapter_name: Name of the adapter to load (from IP_ADAPTER_MODELS)
                         If None, auto-detects appropriate adapter

        Raises:
            ValueError: If adapter_name is not recognized
            RuntimeError: If loading fails
        """
        # Auto-detect model type and adapter
        model_type = self.detect_model_type(pipeline)

        if adapter_name is None:
            adapter_name = self.get_default_adapter(model_type)
            logger.info(
                "ip_adapter_auto_selected",
                adapter=adapter_name,
                model_type=model_type,
            )

        # Validate adapter exists
        if adapter_name not in IP_ADAPTER_MODELS:
            available = list(IP_ADAPTER_MODELS.keys())
            raise ValueError(
                f"Unknown IP-Adapter: {adapter_name}. Available: {available}"
            )

        # Check model type compatibility
        expected_suffix = f"_{model_type}"
        if not adapter_name.endswith(expected_suffix):
            logger.warning(
                "ip_adapter_model_mismatch",
                adapter=adapter_name,
                expected_type=model_type,
                message="Adapter may not be compatible with pipeline",
            )

        config = IP_ADAPTER_MODELS[adapter_name]

        # Skip if already loaded
        if self._loaded_adapter == adapter_name:
            logger.debug("ip_adapter_already_loaded", adapter=adapter_name)
            return

        logger.info(
            "loading_ip_adapter",
            adapter=adapter_name,
            repo=config["repo"],
            description=config["description"],
        )

        try:
            pipeline_obj = cast(Any, pipeline)
            pipeline_obj.load_ip_adapter(
                config["repo"],
                subfolder=config["subfolder"],
                weight_name=config["weight_name"],
            )
            self._loaded_adapter = adapter_name
            logger.info("ip_adapter_loaded", adapter=adapter_name)
        except Exception as e:
            logger.error("ip_adapter_load_failed", adapter=adapter_name, error=str(e))
            raise RuntimeError(f"Failed to load IP-Adapter: {e}") from e

    def unload_ip_adapter(self, pipeline: "DiffusionPipeline") -> None:
        """Unload IP-Adapter from pipeline.

        Args:
            pipeline: The pipeline to unload adapter from
        """
        if self._loaded_adapter is None:
            return

        try:
            if hasattr(pipeline, "unload_ip_adapter"):
                pipeline.unload_ip_adapter()
                logger.info("ip_adapter_unloaded", adapter=self._loaded_adapter)
            self._loaded_adapter = None
        except Exception as e:
            logger.warning("ip_adapter_unload_failed", error=str(e))

    def set_ip_adapter_scale(
        self,
        pipeline: "DiffusionPipeline",
        scale: float = 0.6,
    ) -> None:
        """Set the IP-Adapter influence scale.

        Args:
            pipeline: The pipeline with loaded adapter
            scale: Influence scale (0.0-1.0)
                   - 0.3-0.6 recommended when combining with text prompt
                   - 0.8-1.0 for strong style transfer
                   - Lower values preserve more of text prompt influence

        Raises:
            ValueError: If scale is out of range
        """
        if not 0.0 <= scale <= 1.0:
            raise ValueError(f"IP-Adapter scale must be 0.0-1.0, got {scale}")

        pipeline_obj = cast(Any, pipeline)
        pipeline_obj.set_ip_adapter_scale(scale)
        logger.debug("ip_adapter_scale_set", scale=scale)

    def prepare_reference_image(
        self,
        image: Image.Image | Path | str,
        target_size: tuple[int, int] | None = None,
    ) -> Image.Image:
        """Prepare a reference image for IP-Adapter.

        Args:
            image: Reference image (PIL Image, path, or URL)
            target_size: Optional (width, height) to resize to

        Returns:
            Prepared PIL Image in RGB mode
        """
        # Load image if path/string provided
        if isinstance(image, str | Path):
            image = Image.open(image)

        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize if target size specified
        if target_size is not None:
            image = image.resize(target_size, Image.Resampling.LANCZOS)

        return image

    def generate_with_reference(
        self,
        pipeline: "DiffusionPipeline",
        prompt: str,
        reference_image: Image.Image | Path | str,
        negative_prompt: str = "",
        ip_adapter_scale: float = 0.6,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        num_images: int = 1,
        seed: int | None = None,
        generator: torch.Generator | None = None,
        **kwargs: Any,
    ) -> list[Image.Image]:
        """Generate images with IP-Adapter conditioning.

        This combines the reference image's visual characteristics with
        the text prompt to generate new images.

        Args:
            pipeline: Loaded pipeline with IP-Adapter
            prompt: Text prompt for generation
            reference_image: Image to use as style/composition reference
            negative_prompt: What to avoid in generation
            ip_adapter_scale: Strength of reference influence (0.0-1.0)
                             0.3-0.6 recommended with text prompts
            width: Output image width
            height: Output image height
            num_inference_steps: Number of denoising steps
            guidance_scale: Text prompt adherence (CFG scale)
            num_images: Number of images to generate
            seed: Random seed for reproducibility
            generator: Optional torch generator
            **kwargs: Additional pipeline arguments

        Returns:
            List of generated PIL images
        """
        # Ensure IP-Adapter is loaded
        if self._loaded_adapter is None:
            self.load_ip_adapter(pipeline)

        # Set the influence scale
        self.set_ip_adapter_scale(pipeline, ip_adapter_scale)

        # Prepare reference image
        ref_image = self.prepare_reference_image(reference_image)

        # Set up generator for reproducibility
        if generator is None and seed is not None:
            device = pipeline.device if hasattr(pipeline, "device") else "cpu"
            generator = torch.Generator(device=device).manual_seed(seed)

        logger.info(
            "generating_with_ip_adapter",
            adapter=self._loaded_adapter,
            scale=ip_adapter_scale,
            prompt=prompt[:100],
            num_images=num_images,
        )

        # Generate with IP-Adapter
        pipeline_obj = cast(Any, pipeline)
        result: Any = pipeline_obj(
            prompt=prompt,
            negative_prompt=negative_prompt,
            ip_adapter_image=ref_image,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            num_images_per_prompt=num_images,
            generator=generator,
            **kwargs,
        )

        images = cast(list[Image.Image], result.images)
        logger.info("ip_adapter_generation_complete", num_images=len(images))

        return images

    def generate_style_variations(
        self,
        pipeline: "DiffusionPipeline",
        reference_image: Image.Image | Path | str,
        prompt: str,
        scales: list[float] | None = None,
        **kwargs: Any,
    ) -> list[tuple[float, Image.Image]]:
        """Generate variations with different IP-Adapter scales.

        Useful for exploring how different influence levels affect output.

        Args:
            pipeline: Loaded pipeline with IP-Adapter
            reference_image: Reference image
            prompt: Text prompt
            scales: List of scales to try (default: [0.2, 0.4, 0.6, 0.8])
            **kwargs: Additional generation arguments

        Returns:
            List of (scale, image) tuples
        """
        if scales is None:
            scales = [0.2, 0.4, 0.6, 0.8]

        results = []
        for scale in scales:
            images = self.generate_with_reference(
                pipeline=pipeline,
                prompt=prompt,
                reference_image=reference_image,
                ip_adapter_scale=scale,
                num_images=1,
                **kwargs,
            )
            if images:
                results.append((scale, images[0]))
                logger.debug("style_variation_generated", scale=scale)

        return results


# Singleton instance for easy access (thread-safe)
_ip_adapter_lock = threading.Lock()
_ip_adapter_manager: IPAdapterManager | None = None


def get_ip_adapter_manager() -> IPAdapterManager:
    """Get the global IP-Adapter manager instance (thread-safe)."""
    global _ip_adapter_manager
    if _ip_adapter_manager is None:
        with _ip_adapter_lock:
            # Double-check pattern for thread safety
            if _ip_adapter_manager is None:
                _ip_adapter_manager = IPAdapterManager()
    return _ip_adapter_manager
