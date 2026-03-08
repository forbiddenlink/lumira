"""
Ensemble curation using multiple models for better quality assessment.

Uses voting from multiple evaluation models to get more robust
quality scores and reduce bias from any single model.

Includes:
- CLIP-based prompt alignment
- LAION aesthetic predictor
- AGIQA (AI-Generated Image Quality Assessment) for AI-specific quality
"""

from dataclasses import dataclass, field

import structlog
from PIL import Image

from ai_artist.utils.config import Config

from .agiqa_scorer import get_agiqa_scorer

logger = structlog.get_logger(__name__)


@dataclass
class EnsembleVote:
    """Votes from ensemble of evaluation models."""

    clip_scores: list[float]
    aesthetic_scores: list[float]
    avg_clip: float
    avg_aesthetic: float
    consensus_strength: float  # 0-1, how much models agree
    final_score: float
    # AGIQA-specific scores (AI-generated image quality)
    agiqa_scores: dict = field(default_factory=dict)


class EnsembleCurator:
    """
    Multi-model ensemble for robust quality assessment.

    Uses multiple evaluation approaches and voting to reduce
    bias and get more reliable quality scores.
    """

    def __init__(self, config: Config):
        """Initialize ensemble curator."""
        self.config = config
        logger.info("ensemble_curator_initialized")

    async def evaluate_with_ensemble(
        self, image: Image.Image, prompt: str, use_agiqa: bool = True
    ) -> EnsembleVote:
        """
        Evaluate image quality using ensemble of models.

        Args:
            image: Image to evaluate
            prompt: Generation prompt
            use_agiqa: Whether to include AGIQA scoring (recommended for AI art)

        Returns:
            Ensemble voting results
        """
        # Import curator for individual evaluations
        from ai_artist.curation.curator import ImageCurator

        curator = ImageCurator(self.config.model.base_model)

        # Get evaluation from primary curator
        primary_metrics = curator.evaluate(image, prompt)

        # CLIP and aesthetic scores from primary
        clip_scores = [primary_metrics.clip_score]
        aesthetic_scores = [primary_metrics.aesthetic_score]

        # AGIQA scoring for AI-generated image quality
        agiqa_scores = {}
        agiqa_final = 0.0
        if use_agiqa:
            try:
                agiqa_scorer = get_agiqa_scorer()
                agiqa_scores = agiqa_scorer.score(image, prompt)
                agiqa_final = agiqa_scores.get("final_score", 0.0)
            except Exception as e:
                logger.warning("agiqa_scoring_failed", error=str(e))

        # Calculate consensus
        # With AGIQA, we have more signals to compare
        if agiqa_scores:
            scores = [primary_metrics.clip_score, primary_metrics.aesthetic_score, agiqa_final]
            mean_score = sum(scores) / len(scores)
            variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
            consensus = max(0, 1.0 - (variance ** 0.5) * 2)  # Lower variance = higher consensus
        else:
            consensus = 1.0

        # Average scores
        avg_clip = sum(clip_scores) / len(clip_scores)
        avg_aesthetic = sum(aesthetic_scores) / len(aesthetic_scores)

        # Weighted final score (adjusted for AGIQA)
        if agiqa_scores:
            # AGIQA-enhanced weighting:
            # 40% CLIP alignment, 25% aesthetic, 35% AGIQA (AI-specific quality)
            final_score = 0.40 * avg_clip + 0.25 * avg_aesthetic + 0.35 * agiqa_final
        else:
            # Fallback to original weighting
            final_score = 0.6 * avg_clip + 0.4 * avg_aesthetic

        vote = EnsembleVote(
            clip_scores=clip_scores,
            aesthetic_scores=aesthetic_scores,
            avg_clip=avg_clip,
            avg_aesthetic=avg_aesthetic,
            consensus_strength=consensus,
            final_score=final_score,
            agiqa_scores=agiqa_scores,
        )

        logger.debug(
            "ensemble_evaluation_complete",
            final_score=final_score,
            consensus=consensus,
            agiqa_enabled=bool(agiqa_scores),
        )

        return vote

    async def evaluate_batch_with_ensemble(
        self, images: list[Image.Image], prompt: str
    ) -> list[EnsembleVote]:
        """
        Batch evaluate multiple images with ensemble.

        Args:
            images: Images to evaluate
            prompt: Generation prompt

        Returns:
            List of ensemble votes
        """
        from ai_artist.curation.curator import ImageCurator

        curator = ImageCurator(self.config.model.base_model)

        # Use batch evaluation for speed
        metrics_list = curator.evaluate_batch(images, prompt)

        # Convert to ensemble votes
        votes = []
        for metrics in metrics_list:
            vote = EnsembleVote(
                clip_scores=[metrics.clip_score],
                aesthetic_scores=[metrics.aesthetic_score],
                avg_clip=metrics.clip_score,
                avg_aesthetic=metrics.aesthetic_score,
                consensus_strength=1.0,  # Single model
                final_score=0.6 * metrics.clip_score + 0.4 * metrics.aesthetic_score,
            )
            votes.append(vote)

        logger.info("batch_ensemble_evaluation_complete", count=len(images))
        return votes

    def rank_by_ensemble(
        self, images: list[Image.Image], votes: list[EnsembleVote]
    ) -> list[tuple[Image.Image, EnsembleVote]]:
        """
        Rank images by ensemble voting results.

        Args:
            images: Images to rank
            votes: Corresponding ensemble votes

        Returns:
            List of (image, vote) tuples sorted by quality
        """
        paired = list(zip(images, votes, strict=False))
        # Sort by final score (highest first)
        ranked = sorted(paired, key=lambda x: x[1].final_score, reverse=True)

        logger.debug(
            "ensemble_ranking_complete",
            top_score=ranked[0][1].final_score if ranked else 0,
        )

        return ranked
