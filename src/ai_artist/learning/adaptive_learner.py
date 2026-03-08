"""
Adaptive Learning System for Lumira.

Learns from user feedback to improve generation parameters over time.
Uses reinforcement learning principles to optimize:
- Model selection
- Parameter choices (steps, guidance, etc.)
- Style preferences
- Prompt patterns

Author: Lumira AI Artist
Date: February 2026
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class FeedbackSignal(BaseModel):
    """User feedback on generated artwork."""

    artwork_id: str
    user_action: str  # "like", "love", "download", "share", "delete", "skip"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    generation_params: dict[str, Any]
    prompt: str
    model_id: str
    mood: str | None = None


class ParameterScore(BaseModel):
    """Tracks performance of specific parameter combinations."""

    param_combo_hash: str
    total_score: float = 0.0
    num_samples: int = 0
    avg_score: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class AdaptiveLearner:
    """
    Learns from user feedback to optimize generation parameters.

    Uses multi-armed bandit approach with exploration/exploitation balance.
    """

    # Action weights for feedback signals
    ACTION_WEIGHTS = {
        "love": 1.0,
        "like": 0.7,
        "download": 0.9,
        "share": 0.8,
        "skip": -0.3,
        "delete": -1.0,
    }

    # Exploration rate (epsilon-greedy)
    EXPLORATION_RATE = 0.15  # 15% exploration, 85% exploitation

    def __init__(self, storage_path: Path | None = None):
        """Initialize adaptive learner."""
        self.storage_path = storage_path or Path("data/adaptive_learning.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Learning data structures
        self.model_scores: dict[str, ParameterScore] = {}
        self.param_scores: dict[str, ParameterScore] = {}
        self.mood_preferences: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self.prompt_patterns: dict[str, float] = defaultdict(float)

        self._load_state()
        logger.info(
            "adaptive_learner_initialized",
            models_tracked=len(self.model_scores),
            param_combos=len(self.param_scores),
        )

    def record_feedback(self, feedback: FeedbackSignal) -> None:
        """Record user feedback and update learning models."""
        score = self.ACTION_WEIGHTS.get(feedback.user_action, 0.0)

        if score == 0.0:
            logger.debug("unknown_action_ignored", action=feedback.user_action)
            return

        # Update model scores
        self._update_model_score(feedback.model_id, score)

        # Update parameter combination scores
        param_hash = self._hash_params(feedback.generation_params)
        self._update_param_score(param_hash, score, feedback.generation_params)

        # Update mood preferences
        if feedback.mood:
            self._update_mood_preferences(
                feedback.mood, feedback.model_id, feedback.generation_params, score
            )

        # Track successful prompt patterns
        self._update_prompt_patterns(feedback.prompt, score)

        # Persist state
        self._save_state()

        logger.info(
            "feedback_recorded",
            action=feedback.user_action,
            score=score,
            model=feedback.model_id,
        )

    def suggest_model(self, mood: str | None = None) -> str | None:
        """
        Suggest best model based on learned preferences.

        Args:
            mood: Optional mood context for model selection

        Returns:
            Recommended model ID or None if no data
        """
        if not self.model_scores:
            return None

        # Epsilon-greedy: explore vs exploit
        import random

        if random.random() < self.EXPLORATION_RATE:
            # Exploration: random model
            return random.choice(list(self.model_scores.keys()))

        # Exploitation: best performing model
        if mood and mood in self.mood_preferences:
            # Use mood-specific preferences
            mood_prefs = self.mood_preferences[mood]
            if mood_prefs:
                best_model = max(mood_prefs.items(), key=lambda x: x[1])[0]
                logger.debug("mood_based_suggestion", mood=mood, model=best_model)
                return best_model

        # Use global best model
        best_model = max(self.model_scores.items(), key=lambda x: x[1].avg_score)[0]
        logger.debug("global_best_suggestion", model=best_model)
        return best_model

    def suggest_parameters(
        self, base_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Suggest optimal parameters based on learned patterns.

        Args:
            base_params: Starting parameters to optimize

        Returns:
            Optimized parameter dictionary
        """
        if not self.param_scores:
            return base_params or {}

        # Find best performing parameter combination
        best_combo = max(self.param_scores.items(), key=lambda x: x[1].avg_score)

        # Parse stored params
        import ast

        try:
            suggested_params: dict[str, Any] = ast.literal_eval(best_combo[0])
        except (ValueError, SyntaxError):
            return base_params or {}

        # Merge with base params
        if base_params:
            result: dict[str, Any] = base_params.copy()
            result.update(suggested_params)
            return result

        return suggested_params

    def get_learning_stats(self) -> dict[str, Any]:
        """Get statistics about learning progress."""
        if not self.model_scores:
            return {"status": "no_data", "total_feedback": 0}

        total_samples = sum(score.num_samples for score in self.model_scores.values())

        # Find best model
        best_model_entry = max(self.model_scores.items(), key=lambda x: x[1].avg_score)

        # Calculate exploration vs exploitation ratio
        explore_samples = int(total_samples * self.EXPLORATION_RATE)

        return {
            "status": "learning",
            "total_feedback": total_samples,
            "models_tracked": len(self.model_scores),
            "param_combinations": len(self.param_scores),
            "moods_learned": len(self.mood_preferences),
            "best_model": {
                "id": best_model_entry[0],
                "avg_score": round(best_model_entry[1].avg_score, 3),
                "samples": best_model_entry[1].num_samples,
            },
            "exploration_rate": self.EXPLORATION_RATE,
            "exploration_samples": explore_samples,
            "exploitation_samples": total_samples - explore_samples,
        }

    def _update_model_score(self, model_id: str, score: float) -> None:
        """Update running average for model performance."""
        if model_id not in self.model_scores:
            self.model_scores[model_id] = ParameterScore(
                param_combo_hash=model_id,
                total_score=score,
                num_samples=1,
                avg_score=score,
            )
        else:
            model_score = self.model_scores[model_id]
            model_score.total_score += score
            model_score.num_samples += 1
            model_score.avg_score = model_score.total_score / model_score.num_samples
            model_score.last_updated = datetime.utcnow()

    def _update_param_score(
        self, param_hash: str, score: float, params: dict[str, Any]
    ) -> None:
        """Update running average for parameter combinations."""
        if param_hash not in self.param_scores:
            self.param_scores[param_hash] = ParameterScore(
                param_combo_hash=param_hash,
                total_score=score,
                num_samples=1,
                avg_score=score,
            )
        else:
            param_score = self.param_scores[param_hash]
            param_score.total_score += score
            param_score.num_samples += 1
            param_score.avg_score = param_score.total_score / param_score.num_samples
            param_score.last_updated = datetime.utcnow()

    def _update_mood_preferences(
        self, mood: str, model_id: str, params: dict[str, Any], score: float
    ) -> None:
        """Track which models/params work best for each mood."""
        # Update mood-model preferences
        current_score = self.mood_preferences[mood][model_id]
        # Running average
        if current_score == 0.0:
            self.mood_preferences[mood][model_id] = score
        else:
            # Exponential moving average (alpha=0.3)
            self.mood_preferences[mood][model_id] = 0.7 * current_score + 0.3 * score

    def _update_prompt_patterns(self, prompt: str, score: float) -> None:
        """Learn which prompt patterns are successful."""
        # Extract keywords (simple approach - could use NLP)
        keywords = [
            word.lower() for word in prompt.split() if len(word) > 3 and word.isalpha()
        ]

        for keyword in keywords[:10]:  # Limit to first 10 keywords
            current_score = self.prompt_patterns[keyword]
            if current_score == 0.0:
                self.prompt_patterns[keyword] = score
            else:
                # Exponential moving average
                self.prompt_patterns[keyword] = 0.7 * current_score + 0.3 * score

    def _hash_params(self, params: dict[str, Any]) -> str:
        """Create stable hash of parameter combination."""
        # Only hash meaningful generation params
        key_params = {
            k: v
            for k, v in params.items()
            if k
            in ("num_inference_steps", "guidance_scale", "scheduler", "width", "height")
        }
        return str(sorted(key_params.items()))

    def _save_state(self) -> None:
        """Persist learning state to disk."""
        state = {
            "model_scores": {k: v.model_dump() for k, v in self.model_scores.items()},
            "param_scores": {k: v.model_dump() for k, v in self.param_scores.items()},
            "mood_preferences": dict(self.mood_preferences),
            "prompt_patterns": dict(self.prompt_patterns),
            "last_updated": datetime.utcnow().isoformat(),
        }

        try:
            with open(self.storage_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error("failed_to_save_learning_state", error=str(e))

    def _load_state(self) -> None:
        """Load learning state from disk."""
        if not self.storage_path.exists():
            logger.info("no_existing_learning_state", path=str(self.storage_path))
            return

        try:
            with open(self.storage_path) as f:
                state = json.load(f)

            # Restore model scores
            self.model_scores = {
                k: ParameterScore(**v) for k, v in state.get("model_scores", {}).items()
            }

            # Restore param scores
            self.param_scores = {
                k: ParameterScore(**v) for k, v in state.get("param_scores", {}).items()
            }

            # Restore mood preferences
            mood_prefs = state.get("mood_preferences", {})
            self.mood_preferences = defaultdict(lambda: defaultdict(float), mood_prefs)

            # Restore prompt patterns
            self.prompt_patterns = defaultdict(float, state.get("prompt_patterns", {}))

            logger.info(
                "learning_state_loaded",
                models=len(self.model_scores),
                param_combos=len(self.param_scores),
            )

        except Exception as e:
            logger.error("failed_to_load_learning_state", error=str(e))


# Global singleton
_learner_instance: AdaptiveLearner | None = None


def get_adaptive_learner() -> AdaptiveLearner:
    """Get or create global adaptive learner instance."""
    global _learner_instance
    if _learner_instance is None:
        _learner_instance = AdaptiveLearner()
    return _learner_instance
