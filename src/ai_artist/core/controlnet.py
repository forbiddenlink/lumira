"""ControlNet helper utilities."""

from collections.abc import Callable
from enum import Enum
from typing import Any, cast

import cv2
import numpy as np
import torch
from diffusers import ControlNetModel
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ControlNetType(str, Enum):
    """Supported ControlNet preprocessor types."""

    CANNY = "canny"
    DEPTH = "depth"
    POSE = "pose"
    LINEART = "lineart"
    SOFTEDGE = "softedge"


# SDXL ControlNet model IDs
SDXL_CONTROLNET_MODELS = {
    ControlNetType.CANNY: "diffusers/controlnet-canny-sdxl-1.0",
    ControlNetType.DEPTH: "diffusers/controlnet-depth-sdxl-1.0",
    # Pose, lineart, and softedge use community models for SDXL
    ControlNetType.POSE: "thibaud/controlnet-openpose-sdxl-1.0",
    ControlNetType.LINEART: "TheMistoAI/MistoLine",
    ControlNetType.SOFTEDGE: "SargeZT/controlnet-sd-xl-1.0-softedge-dexined",
}

# SD 1.5 ControlNet model IDs (for backwards compatibility)
SD15_CONTROLNET_MODELS = {
    ControlNetType.CANNY: "lllyasviel/control_v11p_sd15_canny",
    ControlNetType.DEPTH: "lllyasviel/control_v11f1p_sd15_depth",
    ControlNetType.POSE: "lllyasviel/control_v11p_sd15_openpose",
    ControlNetType.LINEART: "lllyasviel/control_v11p_sd15_lineart",
    ControlNetType.SOFTEDGE: "lllyasviel/control_v11p_sd15_softedge",
}


class ControlNetPreprocessor:
    """Helper for ControlNet image preprocessing.

    Uses lazy loading for controlnet_aux detectors to avoid loading all models at startup.
    """

    # Cache for loaded detectors
    _depth_detector = None
    _pose_detector = None
    _lineart_detector = None
    _softedge_detector = None

    @staticmethod
    def get_canny_image(
        image: Image.Image, low_threshold: int = 100, high_threshold: int = 200
    ) -> Image.Image:
        """Convert a PIL image to a Canny edge map.

        Args:
            image: Input PIL Image
            low_threshold: Canny edge detection low threshold
            high_threshold: Canny edge detection high threshold

        Returns:
            PIL Image with Canny edge detection applied
        """
        try:
            image_np = np.array(image)

            # Ensure 3 channels
            if len(image_np.shape) == 2:
                image_np = cv2.cvtColor(image_np, cv2.COLOR_GRAY2RGB)
            elif image_np.shape[2] == 4:
                image_np = cv2.cvtColor(image_np, cv2.COLOR_RGBA2RGB)

            # Convert to grayscale for Canny
            gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
            canny = cv2.Canny(gray, low_threshold, high_threshold)

            # Convert back to 3-channel image
            canny_3ch = np.stack([canny, canny, canny], axis=2)
            canny_image = Image.fromarray(canny_3ch)

            logger.debug(
                "canny_preprocessing_complete",
                low_threshold=low_threshold,
                high_threshold=high_threshold,
            )
            return canny_image
        except ImportError as e:
            logger.error("opencv_missing", action="install_opencv_python")
            raise RuntimeError(
                "opencv-python is required for ControlNet Canny preprocessing"
            ) from e
        except Exception as e:
            logger.error("canny_preprocessing_failed", error=str(e))
            raise

    @classmethod
    def get_depth_image(cls, image: Image.Image) -> Image.Image:
        """Generate depth map using MiDaS.

        Args:
            image: Input PIL Image

        Returns:
            PIL Image with depth map
        """
        try:
            if cls._depth_detector is None:
                logger.info("loading_depth_detector", model="lllyasviel/Annotators")
                from controlnet_aux import MidasDetector

                cls._depth_detector = MidasDetector.from_pretrained(
                    "lllyasviel/Annotators"
                )

            depth_image = cast(Image.Image, cls._depth_detector(image))
            logger.debug("depth_preprocessing_complete")
            return depth_image
        except ImportError as e:
            logger.error(
                "controlnet_aux_missing",
                action="install controlnet-aux: pip install controlnet-aux",
            )
            raise RuntimeError(
                "controlnet-aux is required for depth preprocessing. "
                "Install with: pip install lumira[controlnet]"
            ) from e
        except Exception as e:
            logger.error("depth_preprocessing_failed", error=str(e))
            raise

    @classmethod
    def get_pose_image(cls, image: Image.Image) -> Image.Image:
        """Generate pose estimation using OpenPose.

        Args:
            image: Input PIL Image

        Returns:
            PIL Image with pose skeleton overlay
        """
        try:
            if cls._pose_detector is None:
                logger.info("loading_pose_detector", model="lllyasviel/Annotators")
                from controlnet_aux import OpenposeDetector

                cls._pose_detector = OpenposeDetector.from_pretrained(
                    "lllyasviel/Annotators"
                )

            pose_image = cast(Image.Image, cls._pose_detector(image))
            logger.debug("pose_preprocessing_complete")
            return pose_image
        except ImportError as e:
            logger.error(
                "controlnet_aux_missing",
                action="install controlnet-aux: pip install controlnet-aux",
            )
            raise RuntimeError(
                "controlnet-aux is required for pose preprocessing. "
                "Install with: pip install lumira[controlnet]"
            ) from e
        except Exception as e:
            logger.error("pose_preprocessing_failed", error=str(e))
            raise

    @classmethod
    def get_lineart_image(cls, image: Image.Image) -> Image.Image:
        """Generate line art.

        Args:
            image: Input PIL Image

        Returns:
            PIL Image with line art extraction
        """
        try:
            if cls._lineart_detector is None:
                logger.info("loading_lineart_detector", model="lllyasviel/Annotators")
                from controlnet_aux import LineartDetector

                cls._lineart_detector = LineartDetector.from_pretrained(
                    "lllyasviel/Annotators"
                )

            lineart_image = cast(Image.Image, cls._lineart_detector(image))
            logger.debug("lineart_preprocessing_complete")
            return lineart_image
        except ImportError as e:
            logger.error(
                "controlnet_aux_missing",
                action="install controlnet-aux: pip install controlnet-aux",
            )
            raise RuntimeError(
                "controlnet-aux is required for lineart preprocessing. "
                "Install with: pip install lumira[controlnet]"
            ) from e
        except Exception as e:
            logger.error("lineart_preprocessing_failed", error=str(e))
            raise

    @classmethod
    def get_softedge_image(cls, image: Image.Image) -> Image.Image:
        """Generate soft edge detection using HED.

        Args:
            image: Input PIL Image

        Returns:
            PIL Image with soft edges
        """
        try:
            if cls._softedge_detector is None:
                logger.info("loading_softedge_detector", model="lllyasviel/Annotators")
                from controlnet_aux import HEDdetector

                cls._softedge_detector = HEDdetector.from_pretrained(
                    "lllyasviel/Annotators"
                )

            softedge_image = cast(Image.Image, cls._softedge_detector(image))
            logger.debug("softedge_preprocessing_complete")
            return softedge_image
        except ImportError as e:
            logger.error(
                "controlnet_aux_missing",
                action="install controlnet-aux: pip install controlnet-aux",
            )
            raise RuntimeError(
                "controlnet-aux is required for softedge preprocessing. "
                "Install with: pip install lumira[controlnet]"
            ) from e
        except Exception as e:
            logger.error("softedge_preprocessing_failed", error=str(e))
            raise

    @classmethod
    def preprocess(
        cls,
        image: Image.Image,
        controlnet_type: ControlNetType | str,
        **kwargs: Any,
    ) -> Image.Image:
        """Preprocess an image using the specified ControlNet type.

        Args:
            image: Input PIL Image
            controlnet_type: Type of preprocessing to apply
            **kwargs: Additional arguments for specific preprocessors

        Returns:
            Preprocessed PIL Image
        """
        if isinstance(controlnet_type, str):
            controlnet_type = ControlNetType(controlnet_type.lower())

        preprocessors: dict[ControlNetType, Callable[..., Image.Image]] = {
            ControlNetType.CANNY: cls.get_canny_image,
            ControlNetType.DEPTH: cls.get_depth_image,
            ControlNetType.POSE: cls.get_pose_image,
            ControlNetType.LINEART: cls.get_lineart_image,
            ControlNetType.SOFTEDGE: cls.get_softedge_image,
        }

        preprocessor = preprocessors.get(controlnet_type)
        if preprocessor is None:
            raise ValueError(f"Unknown ControlNet type: {controlnet_type}")
        preprocessor_fn = cast(Callable[..., Image.Image], preprocessor)

        # Only pass kwargs for methods that accept them (canny)
        if controlnet_type == ControlNetType.CANNY:
            return preprocessor_fn(image, **kwargs)
        return preprocessor_fn(image)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached detectors to free memory."""
        cls._depth_detector = None
        cls._pose_detector = None
        cls._lineart_detector = None
        cls._softedge_detector = None
        logger.info("controlnet_preprocessor_cache_cleared")


class ControlNetLoader:
    """Helper to load ControlNet models."""

    @staticmethod
    def load(
        model_id: str, dtype: torch.dtype = torch.float16, variant: str | None = None
    ) -> ControlNetModel:
        """Load a ControlNet model.

        Args:
            model_id: HuggingFace model ID or local path
            dtype: Model data type (default: float16)
            variant: Model variant (e.g., "fp16")

        Returns:
            Loaded ControlNetModel
        """
        logger.info("loading_controlnet", model=model_id, dtype=str(dtype))

        load_kwargs: dict[str, Any] = {
            "torch_dtype": dtype,
            "use_safetensors": True,
        }
        if variant:
            load_kwargs["variant"] = variant

        return cast(
            ControlNetModel, ControlNetModel.from_pretrained(model_id, **load_kwargs)
        )

    @staticmethod
    def load_multiple(
        model_ids: list[str],
        dtype: torch.dtype = torch.float16,
        variant: str | None = None,
    ) -> list[ControlNetModel]:
        """Load multiple ControlNet models for multi-ControlNet pipelines.

        Args:
            model_ids: List of HuggingFace model IDs
            dtype: Model data type
            variant: Model variant

        Returns:
            List of loaded ControlNetModels
        """
        logger.info("loading_multiple_controlnets", count=len(model_ids))
        controlnets = []
        for model_id in model_ids:
            controlnet = ControlNetLoader.load(model_id, dtype=dtype, variant=variant)
            controlnets.append(controlnet)
        return controlnets

    @staticmethod
    def get_sdxl_model_id(controlnet_type: ControlNetType | str) -> str:
        """Get the SDXL ControlNet model ID for a given type.

        Args:
            controlnet_type: ControlNet type

        Returns:
            HuggingFace model ID for SDXL ControlNet
        """
        if isinstance(controlnet_type, str):
            controlnet_type = ControlNetType(controlnet_type.lower())

        model_id = SDXL_CONTROLNET_MODELS.get(controlnet_type)
        if model_id is None:
            raise ValueError(
                f"No SDXL ControlNet model available for type: {controlnet_type}"
            )
        return model_id

    @staticmethod
    def get_sd15_model_id(controlnet_type: ControlNetType | str) -> str:
        """Get the SD 1.5 ControlNet model ID for a given type.

        Args:
            controlnet_type: ControlNet type

        Returns:
            HuggingFace model ID for SD 1.5 ControlNet
        """
        if isinstance(controlnet_type, str):
            controlnet_type = ControlNetType(controlnet_type.lower())

        model_id = SD15_CONTROLNET_MODELS.get(controlnet_type)
        if model_id is None:
            raise ValueError(
                f"No SD 1.5 ControlNet model available for type: {controlnet_type}"
            )
        return model_id
