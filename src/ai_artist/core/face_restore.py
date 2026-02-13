"""Face restoration using CodeFormer for fixing distorted/creepy faces.

CodeFormer is a robust blind face restoration algorithm that uses a
Codebook Lookup Transformer to restore degraded faces with high quality.
"""

from pathlib import Path
from typing import Literal

from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)


class FaceRestorer:
    """Restore faces in images using CodeFormer.

    CodeFormer is a practical face restoration algorithm that excels at:
    - Fixing distorted facial features
    - Enhancing facial details
    - Correcting asymmetrical eyes
    - Improving overall face quality

    Uses the codeformer-perceptor package for a clean PIL-based API.
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "cuda",
        fidelity: float = 0.7,
    ):
        """Initialize the face restorer.

        Args:
            model_path: Custom model path (optional, auto-downloads if None)
            device: Device to run on ("cuda", "mps", or "cpu")
            fidelity: Balance between quality and fidelity (0.0-1.0).
                      Lower = higher quality, higher = more faithful to original.
                      Default 0.7 provides good balance.
        """
        self.device = device
        self.model_path = model_path
        self.fidelity = max(0.0, min(1.0, fidelity))
        self.restorer = None
        self._backend: Literal["codeformer-perceptor", "codeformer-pip", None] = None
        logger.info("face_restorer_initialized", device=device, fidelity=self.fidelity)

    def _load_model(self) -> bool:
        """Lazy load CodeFormer model.

        Tries multiple backends in order of preference:
        1. codeformer-perceptor (cleanest API)
        2. codeformer-pip (alternative implementation)
        """
        if self.restorer is not None:
            return True

        # Try codeformer-perceptor first (best API)
        try:
            from codeformer import CodeFormer

            # Initialize model on the appropriate device
            model = CodeFormer()
            if self.device == "cuda":
                model = model.cuda()
            elif self.device == "mps":
                model = model.to("mps")
            # CPU is the default, no action needed

            self.restorer = model
            self._backend = "codeformer-perceptor"
            logger.info("codeformer_model_loaded", backend="codeformer-perceptor")
            return True

        except ImportError:
            logger.debug("codeformer_perceptor_not_available")
        except Exception as e:
            logger.warning("codeformer_perceptor_load_failed", error=str(e))

        # Try codeformer-pip as fallback
        try:
            from codeformer.app import inference_app

            self.restorer = inference_app
            self._backend = "codeformer-pip"
            logger.info("codeformer_model_loaded", backend="codeformer-pip")
            return True

        except ImportError:
            logger.warning(
                "codeformer_not_installed",
                message="Install with: pip install codeformer-perceptor",
                hint="Face restoration will be skipped",
            )
            return False
        except Exception as e:
            logger.error("codeformer_load_failed", error=str(e))
            return False

    def restore(self, image: Image.Image) -> Image.Image:
        """Restore faces in an image.

        Args:
            image: PIL Image to process

        Returns:
            Image with restored faces (or original if no faces/error)
        """
        if not self._load_model():
            return image

        try:
            if self._backend == "codeformer-perceptor":
                return self._restore_with_perceptor(image)
            elif self._backend == "codeformer-pip":
                return self._restore_with_pip(image)
            else:
                logger.warning("no_backend_available")
                return image

        except Exception as e:
            logger.error("face_restoration_failed", error=str(e))
            return image

    def _restore_with_perceptor(self, image: Image.Image) -> Image.Image:
        """Restore using codeformer-perceptor backend."""
        if self.restorer is None:
            return image
        # The codeformer-perceptor model accepts PIL images directly
        # and returns a PIL image
        restored_image = self.restorer(image)

        if restored_image is not None:
            logger.info("faces_restored", backend="codeformer-perceptor")
            return restored_image
        else:
            logger.debug("no_faces_detected")
            return image

    def _restore_with_pip(self, image: Image.Image) -> Image.Image:
        """Restore using codeformer-pip backend."""
        if self.restorer is None:
            return image
        import tempfile

        # codeformer-pip works with file paths
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_in:
            image.save(tmp_in.name)
            tmp_in_path = Path(tmp_in.name)

        try:
            # Run inference - returns output path
            result_path = self.restorer(
                image=str(tmp_in_path),
                background_enhance=False,
                face_upsample=False,
                upscale=1,  # Don't upscale, just restore
                codeformer_fidelity=self.fidelity,
            )

            if result_path and Path(result_path).exists():
                restored_image = Image.open(result_path)
                # Convert to RGB if needed (in case of RGBA)
                if restored_image.mode == "RGBA":
                    restored_image = restored_image.convert("RGB")
                logger.info("faces_restored", backend="codeformer-pip")
                return restored_image
            else:
                logger.debug("no_faces_detected")
                return image

        finally:
            # Clean up temp file
            tmp_in_path.unlink(missing_ok=True)

    def has_faces(self, image: Image.Image) -> bool:
        """Check if image contains faces.

        Args:
            image: PIL Image to check

        Returns:
            True if faces detected
        """
        try:
            import cv2
            import numpy as np

            img_array = np.array(image)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

            # Use OpenCV face detector
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]
            )
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)

            return len(faces) > 0

        except Exception:
            return False
