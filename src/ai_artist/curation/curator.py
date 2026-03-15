"""Automated image curation using CLIP and LAION aesthetic predictor."""

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Default model for aesthetic prediction
AESTHETIC_MODEL_ID = "shunk031/aesthetics-predictor-v2-sac-logos-ava1-l14-linearMSE"


def is_black_or_blank(image: Image.Image, threshold: float = 0.02) -> tuple[bool, str]:
    """Detect if an image is black, blank, or contains NaN values.

    Args:
        image: PIL Image to check
        threshold: Maximum allowed mean pixel value ratio for "black" detection (0-1)

    Returns:
        Tuple of (is_invalid, reason) where is_invalid is True if image should be rejected
    """
    try:
        arr = np.array(image)

        # Check for NaN values (common MPS issue)
        if np.isnan(arr).any():
            logger.warning("detected_nan_image", has_nan=True)
            return True, "contains_nan_values"

        # Check for completely black image (max value is 0 or very low)
        if arr.max() == 0:
            logger.warning("detected_black_image", max_value=0)
            return True, "completely_black"

        # Check for nearly black image (mean is very low)
        mean_value = arr.mean() / 255.0  # Normalize to 0-1
        if mean_value < threshold:
            logger.warning("detected_nearly_black_image", mean_normalized=mean_value)
            return True, "nearly_black"

        # Check for uniform color (no variation - likely failed generation)
        std_value = arr.std()
        if std_value < 1.0:  # Very low standard deviation
            logger.warning("detected_uniform_image", std=std_value)
            return True, "uniform_color"

        # Check for mostly white/blown out
        white_ratio = np.sum(arr > 250) / arr.size
        if white_ratio > 0.95:
            logger.warning("detected_blown_out_image", white_ratio=white_ratio)
            return True, "blown_out"

        return False, "valid"

    except Exception as e:
        logger.error("image_validation_failed", error=str(e))
        return True, f"validation_error: {e}"


@dataclass
class QualityMetrics:
    """Image quality metrics."""

    aesthetic_score: float
    clip_score: float
    technical_score: float

    @property
    def overall_score(self) -> float:
        """Weighted average."""
        return (
            self.aesthetic_score * 0.5
            + self.clip_score * 0.3
            + self.technical_score * 0.2
        )


class ImageCurator:
    """CLIP-based image curation with LAION aesthetic scoring."""

    def __init__(self, device: str = "cuda", aesthetic_model_id: str | None = None):
        self.device = device
        # Note: CLIP loading is deferred to avoid import errors if not installed yet
        self.model = None
        self.preprocess = None
        # Aesthetic predictor (lazy loaded)
        self._aesthetic_model: Any = None
        self._aesthetic_processor: Any = None
        self._aesthetic_model_id = aesthetic_model_id or AESTHETIC_MODEL_ID
        self._aesthetic_available: bool | None = None  # None = not checked yet
        logger.info("curator_initialized", device=device)

    def _load_clip(self):
        """Lazy load CLIP model."""
        if self.model is None:
            try:
                import clip

                self.model, self.preprocess = clip.load("ViT-L/14", device=self.device)
                logger.info("clip_model_loaded")
            except ImportError:
                logger.warning(
                    "clip_not_installed",
                    message="Install with: pip install git+https://github.com/openai/CLIP.git",
                )
                # Don't raise - allow graceful degradation
                return False
        return True

    def _load_aesthetic_model(self) -> bool:
        """Lazy load LAION aesthetic predictor model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        # Already checked and failed
        if self._aesthetic_available is False:
            return False

        # Already loaded
        if self._aesthetic_model is not None:
            return True

        try:
            from importlib.util import find_spec

            # Check if torch is available without importing
            if find_spec("torch") is None:
                raise ImportError("torch not available")

            import torch  # noqa: F401
            from aesthetics_predictor import AestheticsPredictorV2Linear
            from transformers import CLIPProcessor

            logger.info(
                "loading_aesthetic_model",
                model_id=self._aesthetic_model_id,
            )

            self._aesthetic_model = AestheticsPredictorV2Linear.from_pretrained(
                self._aesthetic_model_id
            )
            self._aesthetic_processor = CLIPProcessor.from_pretrained(
                self._aesthetic_model_id
            )

            # Move model to device and set to evaluation mode
            self._aesthetic_model = self._aesthetic_model.to(self.device)
            self._aesthetic_model.train(False)  # Sets model to evaluation mode

            self._aesthetic_available = True
            logger.info(
                "aesthetic_model_loaded",
                model_id=self._aesthetic_model_id,
                device=self.device,
            )
            return True

        except ImportError as e:
            logger.warning(
                "aesthetic_predictor_not_installed",
                error=str(e),
                message="Install with: pip install simple-aesthetics-predictor transformers",
            )
            self._aesthetic_available = False
            return False
        except Exception as e:
            logger.error(
                "aesthetic_model_load_failed",
                error=str(e),
                model_id=self._aesthetic_model_id,
            )
            self._aesthetic_available = False
            return False

    def evaluate(self, image: Image.Image, prompt: str) -> QualityMetrics:
        """Evaluate image quality."""
        # Load CLIP if not already loaded - if it fails, return default scores
        if self.model is None and not self._load_clip():
            return QualityMetrics(
                aesthetic_score=0.5,
                clip_score=0.5,
                technical_score=0.5,
            )

        # CLIP score (text-image alignment)
        clip_score = self._compute_clip_score(image, prompt)

        # Aesthetic score (placeholder - implement with aesthetic predictor)
        aesthetic_score = self._estimate_aesthetic(image)

        # Technical score (resolution, sharpness)
        technical_score = self._compute_technical_score(image)

        metrics = QualityMetrics(
            aesthetic_score=aesthetic_score,
            clip_score=clip_score,
            technical_score=technical_score,
        )

        logger.info(
            "image_evaluated",
            overall=round(metrics.overall_score, 2),
            aesthetic=round(aesthetic_score, 2),
            clip=round(clip_score, 2),
        )

        return metrics

    def evaluate_batch(
        self,
        images: list[Image.Image],
        prompt: str,
    ) -> list[QualityMetrics]:
        """Evaluate multiple images in a single batch (faster).

        Processes all images in one GPU pass for CLIP and aesthetic scoring,
        providing 2-3x speedup compared to sequential evaluation.

        Args:
            images: List of PIL Images to evaluate
            prompt: Generation prompt for CLIP scoring

        Returns:
            List of QualityMetrics, one per image
        """
        if not images:
            return []

        # Load CLIP if not already loaded
        if self.model is None and not self._load_clip():
            # Return default scores for all images
            return [
                QualityMetrics(
                    aesthetic_score=0.5,
                    clip_score=0.5,
                    technical_score=0.5,
                )
                for _ in images
            ]

        # Batch compute CLIP scores
        clip_scores = self._compute_clip_scores_batch(images, prompt)

        # Batch compute aesthetic scores
        aesthetic_scores = self._estimate_aesthetic_batch(images)

        # Compute technical scores (CPU-bound, can stay sequential)
        technical_scores = [self._compute_technical_score(img) for img in images]

        # Combine into metrics
        results = [
            QualityMetrics(
                aesthetic_score=aes,
                clip_score=clip,
                technical_score=tech,
            )
            for aes, clip, tech in zip(
                aesthetic_scores, clip_scores, technical_scores, strict=False
            )
        ]

        logger.info(
            "batch_evaluated",
            num_images=len(images),
            avg_overall=round(sum(m.overall_score for m in results) / len(results), 2),
        )

        return results

    def _compute_clip_scores_batch(
        self,
        images: list[Image.Image],
        prompt: str,
    ) -> list[float]:
        """Compute CLIP scores for multiple images in one forward pass.

        Args:
            images: Images to score
            prompt: Text prompt

        Returns:
            List of CLIP similarity scores
        """
        import clip
        import torch

        assert self.model is not None and self.preprocess is not None

        with torch.no_grad():
            # Stack images into batch tensor
            image_tensors = torch.stack([self.preprocess(img) for img in images]).to(
                self.device
            )

            # Tokenize prompt once
            text_token = clip.tokenize([prompt]).to(self.device)

            # Single forward pass for all images
            image_features = self.model.encode_image(image_tensors)
            text_features = self.model.encode_text(text_token)

            # Normalize
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            # Compute similarities for all images at once
            similarities = (image_features @ text_features.T).squeeze()

        # Convert to list and clip to [0, 1]
        if len(images) == 1:
            return [float(max(0.0, similarities.item()))]
        return [float(max(0.0, s.item())) for s in similarities]

    def _estimate_aesthetic_batch(
        self,
        images: list[Image.Image],
    ) -> list[float]:
        """Estimate aesthetic scores for multiple images in batch.

        Args:
            images: Images to score

        Returns:
            List of aesthetic scores (0-1 range)
        """
        # Try to load aesthetic model
        if not self._load_aesthetic_model():
            # Fall back to heuristic for all images
            return [self._estimate_aesthetic_heuristic(img) for img in images]

        try:
            import torch

            assert self._aesthetic_model is not None
            assert self._aesthetic_processor is not None

            # Process all images in batch
            inputs = self._aesthetic_processor(images=images, return_tensors="pt")

            with torch.no_grad():
                # Single forward pass for all images
                outputs = self._aesthetic_model(**inputs)
                scores = outputs.logits.squeeze()

            # Normalize from 1-10 scale to 0-1
            if len(images) == 1:
                normalized = [(scores.item() - 1.0) / 9.0]
            else:
                normalized = [(s.item() - 1.0) / 9.0 for s in scores]

            # Clip to valid range
            return [max(0.0, min(1.0, score)) for score in normalized]

        except Exception as e:
            logger.warning(
                "batch_aesthetic_scoring_failed",
                error=str(e),
                falling_back=True,
            )
            # Fall back to heuristic
            return [self._estimate_aesthetic_heuristic(img) for img in images]

    def _compute_clip_score(self, image: Image.Image, prompt: str) -> float:
        """Compute CLIP similarity score."""
        import clip
        import torch

        assert self.model is not None and self.preprocess is not None
        with torch.no_grad():
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
            text_token = clip.tokenize([prompt]).to(self.device)

            image_features = self.model.encode_image(image_tensor)
            text_features = self.model.encode_text(text_token)

            # Normalize features
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            # Compute similarity
            similarity = (image_features @ text_features.T).item()

        return float(max(0.0, similarity))  # Clip to [0, 1]

    def _estimate_aesthetic(self, image: Image.Image) -> float:
        """Estimate aesthetic score using LAION aesthetic predictor.

        Uses the LAION aesthetic predictor V2 model to score images on a 1-10 scale,
        then normalizes to 0-1 range. Falls back to heuristic scoring if the model
        is not available.

        Args:
            image: PIL Image to score.

        Returns:
            Aesthetic score in range 0-1.
        """
        # Try to use the LAION aesthetic predictor
        if self._load_aesthetic_model():
            try:
                return self._compute_aesthetic_score(image)
            except Exception as e:
                logger.warning(
                    "aesthetic_prediction_failed",
                    error=str(e),
                    fallback="heuristic",
                )

        # Fallback to heuristic scoring
        return self._estimate_aesthetic_heuristic(image)

    def _compute_aesthetic_score(self, image: Image.Image) -> float:
        """Compute aesthetic score using the LAION model.

        Args:
            image: PIL Image to score.

        Returns:
            Normalized aesthetic score (0-1).
        """
        import torch

        assert self._aesthetic_model is not None
        assert self._aesthetic_processor is not None

        # Ensure image is RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Preprocess the image
        inputs = self._aesthetic_processor(images=image, return_tensors="pt")

        # Move inputs to the same device as model
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Run inference
        with torch.no_grad():
            outputs = self._aesthetic_model(**inputs)
            # Model outputs logits in range ~1-10
            raw_score = outputs.logits.item()

        # Normalize from 1-10 scale to 0-1
        # Scores below 4 are generally considered low quality
        # Scores above 7 are considered high quality
        normalized_score = (raw_score - 1.0) / 9.0  # Map 1-10 to 0-1
        normalized_score = max(0.0, min(1.0, normalized_score))  # Clamp

        logger.debug(
            "aesthetic_score_computed",
            raw_score=round(raw_score, 2),
            normalized_score=round(normalized_score, 3),
        )

        return float(normalized_score)

    def _estimate_aesthetic_heuristic(self, image: Image.Image) -> float:
        """Fallback heuristic aesthetic scoring when model is unavailable.

        Combines multiple image quality signals:
        - Aspect ratio preference (40%)
        - Contrast/dynamic range (30%)
        - Color saturation (30%)

        Args:
            image: PIL Image to score.

        Returns:
            Heuristic aesthetic score in range 0-1.
        """
        try:
            img_array = np.array(image.convert("RGB"))

            # 1. Aspect ratio score (prefer ratios close to golden ratio or square)
            width, height = image.size
            aspect = max(width, height) / max(min(width, height), 1)
            golden_ratio = 1.618
            # Score how close to golden ratio or square (1.0)
            aspect_score = (
                1.0 - min(abs(aspect - golden_ratio), abs(aspect - 1.0)) / 2.0
            )
            aspect_score = max(0.0, min(1.0, aspect_score))

            # 2. Contrast score (standard deviation of luminance)
            luminance = (
                0.299 * img_array[:, :, 0]
                + 0.587 * img_array[:, :, 1]
                + 0.114 * img_array[:, :, 2]
            )
            contrast = luminance.std() / 128.0  # Normalize by half the max value
            contrast_score = min(1.0, contrast)

            # 3. Color saturation score
            # Convert to HSV-like saturation without opencv
            r, g, b = (
                img_array[:, :, 0].astype(np.float32),
                img_array[:, :, 1].astype(np.float32),
                img_array[:, :, 2].astype(np.float32),
            )
            max_rgb = np.maximum(np.maximum(r, g), b)
            min_rgb = np.minimum(np.minimum(r, g), b)
            # Saturation = (max - min) / max, avoiding division by zero
            # Use epsilon to prevent division warning on black pixels
            saturation = (max_rgb - min_rgb) / np.maximum(max_rgb, 1e-7)
            saturation_score = float(saturation.mean())

            # Weighted combination
            aesthetic_score = (
                aspect_score * 0.4 + contrast_score * 0.3 + saturation_score * 0.3
            )

            logger.debug(
                "heuristic_aesthetic_score",
                aspect_score=round(aspect_score, 3),
                contrast_score=round(contrast_score, 3),
                saturation_score=round(saturation_score, 3),
                total=round(aesthetic_score, 3),
            )

            return float(aesthetic_score)

        except Exception as e:
            logger.error("heuristic_aesthetic_failed", error=str(e))
            # Ultimate fallback: moderate score based on aspect ratio
            width, height = image.size
            aspect_ratio = min(width, height) / max(width, height)
            return float(0.5 + (aspect_ratio * 0.3))

    def _detect_blur(self, image: Image.Image) -> float:
        """Detect image blur using Laplacian variance.

        Returns:
            float: Blur score (0-1, higher is sharper)
        """
        try:
            import cv2

            # Convert PIL to numpy array (grayscale for blur detection)
            img_array = np.array(image.convert("L"))

            # Calculate Laplacian variance
            laplacian = cv2.Laplacian(img_array, cv2.CV_64F)
            variance = laplacian.var()

            # Normalize: >100 is sharp, <50 is blurry
            # Scale to 0-1 range
            blur_score = min(variance / 100.0, 1.0)

            logger.debug(
                "blur_detection",
                variance=variance,
                score=blur_score,
                assessment=(
                    "sharp"
                    if blur_score > 0.7
                    else "moderate" if blur_score > 0.5 else "blurry"
                ),
            )

            return float(blur_score)
        except ImportError:
            logger.warning(
                "opencv_not_installed",
                message="Install opencv-python for blur detection",
            )
            return 0.8  # Default to moderate score if opencv not available
        except Exception as e:
            logger.error("blur_detection_failed", error=str(e))
            return 0.8

    def _detect_artifacts(self, image: Image.Image) -> float:
        """Detect compression artifacts and anomalies.

        Returns:
            float: Artifact score (0-1, higher is better/fewer artifacts)
        """
        try:
            img_array = np.array(image)

            # Check for extreme values (blown highlights/crushed shadows)
            # Images with >30% extreme pixels likely have issues
            extremes = np.sum((img_array < 10) | (img_array > 245))
            extreme_ratio = float(extremes) / float(img_array.size)

            # Check for color diversity (banding/posterization detection)
            # More unique colors = better (less banding)
            unique_colors = len(
                np.unique(img_array.reshape(-1, img_array.shape[-1]), axis=0)
            )
            total_pixels = img_array.shape[0] * img_array.shape[1]
            color_diversity = min(
                float(unique_colors) / float(total_pixels * 0.1), 1.0
            )  # Expect 10% unique

            # Combine metrics (penalize extremes and low diversity)
            artifact_score = (
                1.0 - min(extreme_ratio * 3, 1.0)
            ) * 0.5 + color_diversity * 0.5

            logger.debug(
                "artifact_detection",
                extreme_ratio=extreme_ratio,
                color_diversity=color_diversity,
                unique_colors=unique_colors,
                score=artifact_score,
                assessment=(
                    "clean"
                    if artifact_score > 0.7
                    else "moderate" if artifact_score > 0.5 else "artifacts"
                ),
            )

            return float(artifact_score)
        except Exception as e:
            logger.error("artifact_detection_failed", error=str(e))
            return 0.8  # Default to moderate score on error

    def _compute_technical_score(self, image: Image.Image) -> float:
        """Compute technical quality score with blur and artifact detection.

        Combines multiple technical metrics:
        - Resolution quality (40%)
        - Sharpness/blur (40%)
        - Artifact detection (20%)
        """
        # Check resolution
        width, height = image.size
        resolution = width * height
        resolution_score = min(1.0, resolution / (1024 * 1024))

        # Detect blur
        blur_score = self._detect_blur(image)

        # Detect artifacts
        artifact_score = self._detect_artifacts(image)

        # Weighted combination
        technical_score = (
            resolution_score * 0.4 + blur_score * 0.4 + artifact_score * 0.2
        )

        logger.debug(
            "technical_score_calculated",
            resolution=resolution_score,
            blur=blur_score,
            artifacts=artifact_score,
            total=technical_score,
        )

        return float(technical_score)

    def should_keep(self, metrics: QualityMetrics, threshold: float = 0.6) -> bool:
        """Determine if image should be kept."""
        return metrics.overall_score >= threshold
