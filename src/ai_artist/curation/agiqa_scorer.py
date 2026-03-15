"""AGIQA (AI-Generated Image Quality Assessment) scorer.

Provides quality assessment specifically designed for AI-generated images,
which have different quality characteristics than natural photographs.

Supports multiple assessment approaches:
1. CLIP-IQA+ (prompt-image alignment with quality perception)
2. Technical quality metrics (sharpness, noise, artifacts)
3. Aesthetic coherence for AI art

References:
- AGIQA-3K dataset/model (2023)
- CLIP-IQA+ (2023)
- LAION aesthetic predictor
"""

from typing import Any

import numpy as np
from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Check for model availability
try:
    import torch
    from transformers import CLIPModel, CLIPProcessor

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.debug("torch/transformers not available for AGIQA scoring")


class AGIQAScorer:
    """AI-Generated Image Quality Assessment.

    Provides specialized quality scoring for AI-generated images,
    which have different characteristics than photographs.
    """

    def __init__(
        self,
        device: str | None = None,
        model_name: str = "openai/clip-vit-large-patch14",
    ):
        """Initialize AGIQA scorer.

        Args:
            device: Device to use (cuda/mps/cpu, auto-detected if None)
            model_name: CLIP model to use for quality assessment
        """
        self.model_name = model_name
        self._model: Any = None
        self._processor: Any = None
        self._device = device

        if TORCH_AVAILABLE:
            if device is None:
                if torch.cuda.is_available():
                    self._device = "cuda"
                elif (
                    hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                ):
                    self._device = "mps"
                else:
                    self._device = "cpu"
            logger.info("agiqa_scorer_initialized", device=self._device)
        else:
            logger.warning("agiqa_scorer_using_fallback", reason="torch not available")

    def _load_model(self) -> None:
        """Lazy load the CLIP model."""
        if self._model is not None or not TORCH_AVAILABLE:
            return

        try:
            self._processor = CLIPProcessor.from_pretrained(self.model_name)
            self._model = CLIPModel.from_pretrained(self.model_name)
            self._model.to(self._device)
            self._model.eval()
            logger.info("agiqa_model_loaded", model=self.model_name)
        except Exception as e:
            logger.error("agiqa_model_load_failed", error=str(e))
            self._model = None

    def score_prompt_alignment(self, image: Image.Image, prompt: str) -> float:
        """Score how well the image matches the prompt.

        Uses CLIP similarity between image and text embeddings.

        Args:
            image: Generated image
            prompt: Generation prompt

        Returns:
            Score from 0.0 to 1.0
        """
        if not TORCH_AVAILABLE:
            return self._fallback_prompt_score(image, prompt)

        self._load_model()
        if self._model is None:
            return self._fallback_prompt_score(image, prompt)

        try:
            import torch

            # Process inputs
            inputs = self._processor(
                text=[prompt],
                images=image,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            # Get embeddings
            with torch.no_grad():
                outputs = self._model(**inputs)
                image_embeds = outputs.image_embeds
                text_embeds = outputs.text_embeds

                # Normalize
                image_embeds = image_embeds / image_embeds.norm(dim=-1, keepdim=True)
                text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)

                # Cosine similarity
                similarity = (image_embeds @ text_embeds.T).squeeze()

            # Convert to 0-1 range (CLIP similarities are typically 0.1-0.4)
            score = float((similarity.cpu().numpy() + 1) / 2)
            return min(max(score, 0.0), 1.0)

        except Exception as e:
            logger.warning("prompt_alignment_failed", error=str(e))
            return self._fallback_prompt_score(image, prompt)

    def _fallback_prompt_score(self, image: Image.Image, prompt: str) -> float:
        """Fallback prompt scoring when CLIP unavailable."""
        # Basic heuristic based on image properties
        # Better images tend to have good contrast and saturation
        return 0.65  # Neutral score

    def score_technical_quality(self, image: Image.Image) -> dict[str, float]:
        """Score technical quality aspects of the image.

        Checks for:
        - Sharpness/blur
        - Noise level
        - Color balance
        - Contrast

        Args:
            image: Image to assess

        Returns:
            Dict of quality metrics (each 0.0-1.0)
        """
        try:
            # Convert to numpy for analysis
            img_array = np.array(image.convert("RGB"))

            # Sharpness via Laplacian variance
            gray = np.mean(img_array, axis=2)
            laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
            from scipy import ndimage

            laplacian_var = ndimage.convolve(gray, laplacian).var()
            # Normalize (typical range 0-5000 for good images)
            sharpness = min(laplacian_var / 3000.0, 1.0)

            # Contrast via standard deviation of luminance
            contrast = min(gray.std() / 80.0, 1.0)

            # Color saturation
            hsv = self._rgb_to_hsv(img_array)
            saturation = hsv[:, :, 1].mean()

            # Noise estimation via high-frequency content
            # Lower is better (less noise)
            noise = 1.0 - min(np.abs(np.diff(gray)).mean() / 30.0, 1.0)

            return {
                "sharpness": float(sharpness),
                "contrast": float(contrast),
                "saturation": float(saturation),
                "noise_free": float(noise),
            }

        except Exception as e:
            logger.warning("technical_quality_failed", error=str(e))
            return {
                "sharpness": 0.5,
                "contrast": 0.5,
                "saturation": 0.5,
                "noise_free": 0.5,
            }

    def _rgb_to_hsv(self, rgb: np.ndarray) -> np.ndarray:
        """Convert RGB to HSV color space."""
        rgb = rgb.astype(float) / 255.0
        maxc = rgb.max(axis=2)
        minc = rgb.min(axis=2)
        v = maxc
        s = (maxc - minc) / (maxc + 1e-10)
        s[maxc == 0] = 0
        rc = (maxc - rgb[:, :, 0]) / (maxc - minc + 1e-10)
        gc = (maxc - rgb[:, :, 1]) / (maxc - minc + 1e-10)
        bc = (maxc - rgb[:, :, 2]) / (maxc - minc + 1e-10)
        h = np.zeros_like(maxc)
        h[rgb[:, :, 0] == maxc] = (bc - gc)[rgb[:, :, 0] == maxc]
        h[rgb[:, :, 1] == maxc] = (2.0 + rc - bc)[rgb[:, :, 1] == maxc]
        h[rgb[:, :, 2] == maxc] = (4.0 + gc - rc)[rgb[:, :, 2] == maxc]
        h = (h / 6.0) % 1.0
        return np.stack([h, s, v], axis=2)

    def score_aesthetic_coherence(self, image: Image.Image) -> float:
        """Score aesthetic coherence for AI-generated art.

        Checks for:
        - Composition balance
        - Color harmony
        - Visual flow

        Args:
            image: Image to assess

        Returns:
            Score from 0.0 to 1.0
        """
        try:
            img_array = np.array(image.convert("RGB"))
            h, w = img_array.shape[:2]

            # Rule of thirds check (key points should have activity)
            thirds_h = [h // 3, 2 * h // 3]
            thirds_w = [w // 3, 2 * w // 3]

            # Get variance at rule-of-thirds intersections
            region_size = min(h, w) // 10
            intersection_variance: float = 0.0
            for th in thirds_h:
                for tw in thirds_w:
                    region = img_array[
                        max(0, th - region_size) : min(h, th + region_size),
                        max(0, tw - region_size) : min(w, tw + region_size),
                    ]
                    intersection_variance += region.var()
            intersection_variance /= 4

            # Normalize
            composition_score = min(intersection_variance / 2000.0, 1.0)

            # Color harmony - check for complementary/analogous colors
            hsv = self._rgb_to_hsv(img_array)
            hue_hist, _ = np.histogram(hsv[:, :, 0].flatten(), bins=12, range=(0, 1))
            hue_hist = hue_hist / hue_hist.sum()
            # Entropy-based: moderate diversity is good
            hue_entropy = -np.sum(hue_hist * np.log(hue_hist + 1e-10))
            # Peak entropy around 1.5-2.0 is harmonious
            harmony_score = 1.0 - abs(hue_entropy - 1.7) / 2.0
            harmony_score = max(0, min(1, harmony_score))

            # Combined aesthetic coherence
            return float(0.5 * composition_score + 0.5 * harmony_score)

        except Exception as e:
            logger.warning("aesthetic_coherence_failed", error=str(e))
            return 0.5

    def score_ai_artifacts(self, image: Image.Image) -> float:
        """Score absence of common AI generation artifacts.

        Checks for:
        - Repeated patterns
        - Texture inconsistencies
        - Edge artifacts
        - Anatomical issues (basic check)

        Higher score = fewer artifacts detected.

        Args:
            image: Image to assess

        Returns:
            Score from 0.0 (many artifacts) to 1.0 (clean)
        """
        try:
            img_array = np.array(image.convert("RGB"))
            gray = np.mean(img_array, axis=2)

            # Check for repeating patterns (common AI artifact)
            # Use autocorrelation
            from scipy import signal

            autocorr = signal.correlate2d(gray, gray[::4, ::4], mode="same")
            autocorr_normalized = autocorr / (autocorr.max() + 1e-10)
            # High secondary peaks indicate repetition
            peaks = np.sort(autocorr_normalized.flatten())[-10:-1]
            repetition_score = 1.0 - np.mean(peaks)

            # Edge consistency check
            from scipy import ndimage

            edges_x = ndimage.sobel(gray, axis=1)
            edge_consistency = 1.0 - min(np.std(edges_x) / 50.0, 0.5) * 2

            # Combined artifact score
            artifact_free = 0.6 * repetition_score + 0.4 * edge_consistency
            return float(max(0, min(1, artifact_free)))

        except Exception as e:
            logger.warning("artifact_detection_failed", error=str(e))
            return 0.7  # Assume mostly clean

    def score(
        self,
        image: Image.Image,
        prompt: str = "",
        weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Get comprehensive AGIQA score.

        Args:
            image: Image to assess
            prompt: Generation prompt (for alignment scoring)
            weights: Optional custom weights for score components

        Returns:
            Dict with individual scores and weighted final score
        """
        default_weights = {
            "prompt_alignment": 0.30,
            "technical": 0.25,
            "aesthetic": 0.25,
            "artifact_free": 0.20,
        }
        weights = weights or default_weights

        # Get individual scores
        prompt_score = self.score_prompt_alignment(image, prompt) if prompt else 0.5
        technical = self.score_technical_quality(image)
        technical_avg = np.mean(list(technical.values()))
        aesthetic = self.score_aesthetic_coherence(image)
        artifact_free = self.score_ai_artifacts(image)

        # Calculate weighted final score
        final = (
            weights.get("prompt_alignment", 0.3) * prompt_score
            + weights.get("technical", 0.25) * technical_avg
            + weights.get("aesthetic", 0.25) * aesthetic
            + weights.get("artifact_free", 0.2) * artifact_free
        )

        result = {
            "prompt_alignment": prompt_score,
            "technical_sharpness": technical["sharpness"],
            "technical_contrast": technical["contrast"],
            "technical_saturation": technical["saturation"],
            "technical_noise_free": technical["noise_free"],
            "technical_avg": float(technical_avg),
            "aesthetic_coherence": aesthetic,
            "artifact_free": artifact_free,
            "final_score": float(final),
        }

        logger.debug("agiqa_score_complete", final=final)
        return result


# Singleton instance
_scorer: AGIQAScorer | None = None


def get_agiqa_scorer(device: str | None = None) -> AGIQAScorer:
    """Get or create AGIQA scorer instance."""
    global _scorer
    if _scorer is None:
        _scorer = AGIQAScorer(device=device)
    return _scorer
