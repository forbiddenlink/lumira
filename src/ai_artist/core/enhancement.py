"""Image enhancement pipeline using Real-ESRGAN and face enhancement.

Provides post-generation enhancement capabilities:
- 4x upscaling with Real-ESRGAN
- Face enhancement with GFPGAN/CodeFormer
- Tile-based processing for memory efficiency
"""

from typing import Any

from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ImageEnhancer:
    """Image enhancement pipeline for upscaling and face enhancement.

    Uses Real-ESRGAN for general upscaling and GFPGAN for face enhancement.
    All models are lazy-loaded to minimize memory usage when not needed.

    Example:
        enhancer = ImageEnhancer(device="cuda")
        upscaled = enhancer.upscale(image, scale=4)
        enhanced = enhancer.full_enhance(image)  # Upscale + face enhance
    """

    def __init__(self, device: str = "cpu"):
        """Initialize the image enhancer.

        Args:
            device: Device to run models on ("cuda", "mps", or "cpu")
        """
        self.device = device

        # Lazy-loaded models
        self._upscaler: Any = None
        self._upscaler_available: bool | None = None

        self._face_enhancer: Any = None
        self._face_enhancer_available: bool | None = None

        logger.info("image_enhancer_initialized", device=device)

    def _load_upscaler(self) -> bool:
        """Lazy load Real-ESRGAN 4x upscaler.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        # Already checked and failed
        if self._upscaler_available is False:
            return False

        # Already loaded
        if self._upscaler is not None:
            return True

        try:
            import torch
            from basicsr.archs.rrdbnet_arch import RRDBNet
            from realesrgan import RealESRGANer

            logger.info("loading_realesrgan_model")

            # Initialize Real-ESRGAN model
            model = RRDBNet(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_block=23,
                num_grow_ch=32,
                scale=4,
            )

            # Determine device for half precision
            half = self.device in ("cuda", "mps") and torch.cuda.is_available()

            self._upscaler = RealESRGANer(
                scale=4,
                model_path="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
                dni_weight=None,
                model=model,
                tile=512,  # Tile size for memory efficiency
                tile_pad=10,
                pre_pad=0,
                half=half,
                device=self.device if self.device != "mps" else "cpu",
            )

            self._upscaler_available = True
            logger.info("realesrgan_model_loaded", device=self.device)
            return True

        except ImportError as e:
            logger.warning(
                "realesrgan_not_installed",
                error=str(e),
                message="Install with: pip install realesrgan basicsr",
            )
            self._upscaler_available = False
            return False
        except Exception as e:
            logger.error("realesrgan_load_failed", error=str(e))
            self._upscaler_available = False
            return False

    def _load_face_enhancer(self) -> bool:
        """Lazy load GFPGAN face enhancer.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        # Already checked and failed
        if self._face_enhancer_available is False:
            return False

        # Already loaded
        if self._face_enhancer is not None:
            return True

        try:
            from gfpgan import GFPGANer

            logger.info("loading_gfpgan_model")

            self._face_enhancer = GFPGANer(
                model_path="https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.3.pth",
                upscale=1,  # We handle upscaling separately
                arch="clean",
                channel_multiplier=2,
                bg_upsampler=None,  # Don't upscale background (use Real-ESRGAN instead)
                device=self.device if self.device != "mps" else "cpu",
            )

            self._face_enhancer_available = True
            logger.info("gfpgan_model_loaded", device=self.device)
            return True

        except ImportError as e:
            logger.warning(
                "gfpgan_not_installed",
                error=str(e),
                message="Install with: pip install gfpgan",
            )
            self._face_enhancer_available = False
            return False
        except Exception as e:
            logger.error("gfpgan_load_failed", error=str(e))
            self._face_enhancer_available = False
            return False

    def upscale(
        self,
        image: Image.Image,
        scale: int = 4,
        tile_size: int = 512,
    ) -> Image.Image:
        """Upscale an image using Real-ESRGAN.

        Uses tile-based processing for memory efficiency on large images.

        Args:
            image: PIL Image to upscale
            scale: Upscale factor (default 4x)
            tile_size: Size of processing tiles (lower = less memory)

        Returns:
            Upscaled PIL Image
        """
        if not self._load_upscaler():
            logger.warning("upscaler_not_available", fallback="pillow_resize")
            # Fallback to Pillow resize
            new_size = (image.width * scale, image.height * scale)
            return image.resize(new_size, Image.Resampling.LANCZOS)

        try:
            import numpy as np

            # Convert PIL to numpy (BGR for opencv compatibility)
            img_array = np.array(image)
            if len(img_array.shape) == 2:  # Grayscale
                img_array = np.stack([img_array] * 3, axis=-1)
            elif img_array.shape[2] == 4:  # RGBA
                img_array = img_array[:, :, :3]

            # RGB to BGR for Real-ESRGAN
            img_bgr = img_array[:, :, ::-1]

            logger.info(
                "upscaling_image",
                original_size=f"{image.width}x{image.height}",
                target_size=f"{image.width * scale}x{image.height * scale}",
                scale=scale,
            )

            # Upscale
            output, _ = self._upscaler.enhance(img_bgr, outscale=scale)

            # BGR to RGB and convert to PIL
            output_rgb = output[:, :, ::-1]
            result = Image.fromarray(output_rgb)

            logger.info(
                "upscaling_complete",
                result_size=f"{result.width}x{result.height}",
            )

            return result

        except Exception as e:
            logger.error("upscaling_failed", error=str(e))
            # Fallback
            new_size = (image.width * scale, image.height * scale)
            return image.resize(new_size, Image.Resampling.LANCZOS)

    def enhance_faces(self, image: Image.Image) -> Image.Image:
        """Enhance faces in an image using GFPGAN.

        Detects and enhances faces while preserving the rest of the image.

        Args:
            image: PIL Image containing faces to enhance

        Returns:
            Image with enhanced faces
        """
        if not self._load_face_enhancer():
            logger.warning("face_enhancer_not_available", fallback="no_enhancement")
            return image

        try:
            import numpy as np

            # Convert PIL to numpy (BGR)
            img_array = np.array(image)
            if len(img_array.shape) == 2:
                img_array = np.stack([img_array] * 3, axis=-1)
            elif img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]

            img_bgr = img_array[:, :, ::-1]

            logger.info(
                "enhancing_faces",
                image_size=f"{image.width}x{image.height}",
            )

            # Enhance faces
            _, _, output = self._face_enhancer.enhance(
                img_bgr,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
            )

            # Convert back to PIL
            if output is not None:
                output_rgb = output[:, :, ::-1]
                result = Image.fromarray(output_rgb)
                logger.info("face_enhancement_complete")
                return result
            else:
                logger.info("no_faces_detected")
                return image

        except Exception as e:
            logger.error("face_enhancement_failed", error=str(e))
            return image

    def full_enhance(
        self,
        image: Image.Image,
        upscale_factor: int = 4,
        enhance_faces: bool = True,
    ) -> Image.Image:
        """Full enhancement pipeline: upscale + face enhancement.

        Order of operations:
        1. Upscale image with Real-ESRGAN
        2. Enhance faces with GFPGAN (optional)

        Args:
            image: PIL Image to enhance
            upscale_factor: Upscale factor (default 4x)
            enhance_faces: Whether to enhance faces (default True)

        Returns:
            Fully enhanced PIL Image
        """
        logger.info(
            "starting_full_enhancement",
            original_size=f"{image.width}x{image.height}",
            upscale_factor=upscale_factor,
            enhance_faces=enhance_faces,
        )

        # Step 1: Upscale
        result = self.upscale(image, scale=upscale_factor)

        # Step 2: Face enhancement (optional)
        if enhance_faces:
            result = self.enhance_faces(result)

        logger.info(
            "full_enhancement_complete",
            final_size=f"{result.width}x{result.height}",
        )

        return result

    def is_available(self) -> dict[str, bool]:
        """Check which enhancement features are available.

        Returns:
            Dict with availability status for each feature
        """
        return {
            "upscaling": self._load_upscaler(),
            "face_enhancement": self._load_face_enhancer(),
        }


# Singleton instance for convenience
_enhancer_instance: ImageEnhancer | None = None


def get_image_enhancer(device: str = "cpu") -> ImageEnhancer:
    """Get or create global image enhancer instance.

    Args:
        device: Device to run on (only used for first creation)

    Returns:
        ImageEnhancer instance
    """
    global _enhancer_instance
    if _enhancer_instance is None:
        _enhancer_instance = ImageEnhancer(device=device)
    return _enhancer_instance
