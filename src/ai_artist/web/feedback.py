"""
API endpoints for user feedback and learning.

Allows users to provide feedback on generated artwork,
which feeds into the adaptive learning system.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ai_artist.db.models import GeneratedImage, UserFeedback
from ai_artist.db.session import get_db
from ai_artist.learning import FeedbackSignal, get_adaptive_learner

from .rate_limit import RATE_LIMIT_ENABLED

logger = structlog.get_logger(__name__)

# Feedback writes directly bias the adaptive learner; throttle it in line with
# other public write endpoints (comments 10/min) to prevent preference poisoning.
limiter = Limiter(key_func=get_remote_address, enabled=RATE_LIMIT_ENABLED)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

DbSession = Annotated[Session, Depends(get_db)]


class FeedbackRequest(BaseModel):
    """User feedback submission."""

    artwork_id: str = Field(..., max_length=512)
    action: str = Field(
        ..., max_length=50
    )  # "like", "love", "download", "share", "delete", "skip"
    prompt: str | None = Field(default=None, max_length=2000)
    model_id: str | None = Field(default=None, max_length=200)
    generation_params: dict | None = None
    mood: str | None = Field(default=None, max_length=50)
    session_id: str | None = Field(default=None, max_length=64)


class FeedbackResponse(BaseModel):
    """Feedback submission response."""

    success: bool
    message: str
    learning_stats: dict | None = None


class LearningStatsResponse(BaseModel):
    """Learning system statistics."""

    status: str
    total_feedback: int
    models_tracked: int
    param_combinations: int
    moods_learned: int
    best_model: dict | None = None
    exploration_rate: float = 0.0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


@router.post("/submit", response_model=FeedbackResponse)
@limiter.limit("15/minute")
async def submit_feedback(
    request: Request,
    feedback: FeedbackRequest,
    db: DbSession,
) -> FeedbackResponse:
    """
    Submit user feedback on generated artwork.

    This feedback is used by the adaptive learning system to improve
    future generations based on user preferences.
    """
    try:
        # Validate action
        valid_actions = {"like", "love", "download", "share", "delete", "skip"}
        if feedback.action not in valid_actions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action. Must be one of: {valid_actions}",
            )

        # Create feedback signal for adaptive learner (JSON-based, existing system)
        signal = FeedbackSignal(
            artwork_id=feedback.artwork_id,
            user_action=feedback.action,
            generation_params=feedback.generation_params or {},
            prompt=feedback.prompt or "",
            model_id=feedback.model_id or "unknown",
            mood=feedback.mood,
        )

        learner = get_adaptive_learner()
        learner.record_feedback(signal)

        # Also persist to DB for SQL-queryable analytics
        try:
            # Resolve DB artwork id from filename if possible
            art_db_id = None
            art_row = (
                db.query(GeneratedImage)
                .filter(GeneratedImage.filename == feedback.artwork_id)
                .first()
            )
            if art_row:
                art_db_id = art_row.id

            # Determine signal value from action
            action_values = {
                "love": 1.0,
                "like": 0.8,
                "download": 0.9,
                "share": 0.85,
                "skip": 0.3,
                "delete": 0.0,
            }
            signal_value = action_values.get(feedback.action)

            db_feedback = UserFeedback(
                artwork_id=art_db_id,
                artwork_filename=feedback.artwork_id,
                action=feedback.action,
                signal_value=signal_value,
                generation_params=feedback.generation_params or {},
                mood=feedback.mood,
                session_id=feedback.session_id,
            )
            db.add(db_feedback)
            db.commit()
        except Exception as db_err:
            logger.warning("feedback_db_persist_failed", error=str(db_err))
            db.rollback()

        # Get updated stats
        stats = learner.get_learning_stats()
        taste = learner.get_taste_summary()

        logger.info(
            "feedback_submitted",
            artwork_id=feedback.artwork_id,
            action=feedback.action,
            total_feedback=stats.get("total_feedback", 0),
        )

        # Surface preference shift live to gallery / studio listeners
        try:
            from ai_artist.web.websocket import broadcast_memory_insight

            narrative = taste.get("narrative") or (
                f"Noted your {feedback.action} — adjusting my taste."
            )
            await broadcast_memory_insight(str(narrative), "preference")
        except Exception as ws_err:
            logger.debug("feedback_insight_broadcast_failed", error=str(ws_err))

        return FeedbackResponse(
            success=True,
            message="Feedback recorded successfully. Lumira is learning!",
            learning_stats={**stats, "taste": taste},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("feedback_submission_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback",
        ) from e


@router.get("/taste")
async def get_taste_summary() -> dict:
    """Return a human-readable taste summary for gallery evolution / atelier."""
    try:
        learner = get_adaptive_learner()
        return learner.get_taste_summary()
    except Exception as e:
        logger.error("taste_summary_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve taste summary",
        ) from e


@router.get("/stats", response_model=LearningStatsResponse)
async def get_learning_stats() -> LearningStatsResponse:
    """
    Get current learning system statistics.

    Shows what Lumira has learned from user feedback.
    """
    try:
        learner = get_adaptive_learner()
        stats = learner.get_learning_stats()
        if stats.get("status") == "no_data" or "models_tracked" not in stats:
            return LearningStatsResponse(
                status=str(stats.get("status") or "no_data"),
                total_feedback=int(stats.get("total_feedback") or 0),
                models_tracked=int(stats.get("models_tracked") or 0),
                param_combinations=int(stats.get("param_combinations") or 0),
                moods_learned=int(stats.get("moods_learned") or 0),
                best_model=stats.get("best_model"),
                exploration_rate=float(stats.get("exploration_rate") or 0.0),
            )
        return LearningStatsResponse(**stats)

    except Exception as e:
        logger.error("failed_to_get_stats", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve learning stats",
        ) from e


@router.post("/suggestions")
async def get_suggestions(mood: str | None = None) -> dict[str, Any]:
    """
    Get AI suggestions based on learned preferences.

    Returns recommended model and parameters based on what
    Lumira has learned works best.
    """
    try:
        learner = get_adaptive_learner()

        # Get model suggestion
        suggested_model = learner.suggest_model(mood=mood)

        # Get parameter suggestions
        suggested_params = learner.suggest_parameters()

        return {
            "suggested_model": suggested_model,
            "suggested_params": suggested_params,
            "mood": mood,
            "confidence": "learning" if learner.model_scores else "no_data",
        }

    except Exception as e:
        logger.error("failed_to_get_suggestions", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate suggestions",
        ) from e
