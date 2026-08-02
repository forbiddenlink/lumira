"""Tests for AdaptiveLearner and RLAIF functionality."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ai_artist.learning.adaptive_learner import AdaptiveLearner, FeedbackSignal


class TestRLAIF:
    """Tests for RLAIF (Critic-Informed Learning) functionality."""

    @pytest.fixture
    def learner(self):
        """Create a learner with temporary storage."""
        with TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test_learning.json"
            yield AdaptiveLearner(storage_path=storage_path)

    def test_feedback_signal_has_source(self):
        """FeedbackSignal includes source field."""
        signal = FeedbackSignal(
            artwork_id="art1",
            user_action="like",
            generation_params={"steps": 30},
            prompt="test prompt",
            model_id="test-model",
            source="critic",
        )
        assert signal.source == "critic"

    def test_user_feedback_full_weight(self, learner):
        """User feedback is applied at full weight."""
        feedback = FeedbackSignal(
            artwork_id="art1",
            user_action="like",
            generation_params={"steps": 30},
            prompt="test prompt",
            model_id="test-model",
            source="user",
        )

        learner.record_feedback(feedback)

        # Check that model score was recorded
        assert "test-model" in learner.model_scores
        # Like = 0.7 * user_weight(1.0) = 0.7
        assert learner.model_scores["test-model"].avg_score == pytest.approx(
            0.7, rel=0.1
        )

    def test_critic_feedback_reduced_weight(self, learner):
        """Critic feedback is applied at reduced weight."""
        feedback = FeedbackSignal(
            artwork_id="art1",
            user_action="like",
            generation_params={"steps": 30},
            prompt="test prompt",
            model_id="test-model",
            source="critic",
        )

        learner.record_feedback(feedback)

        # Like = 0.7 * critic_weight(0.3) * reliability(0.5) = 0.105
        assert "test-model" in learner.model_scores
        assert learner.model_scores["test-model"].avg_score < 0.2  # Much less than user

    def test_track_alignment_updates_reliability(self, learner):
        """Tracking critic-user alignment updates critic reliability."""
        initial_reliability = learner._critic_reliability

        # Track perfect alignment
        learner.track_alignment("art1", critic_score=0.8, user_score=0.8)
        learner.track_alignment("art2", critic_score=0.7, user_score=0.7)
        learner.track_alignment("art3", critic_score=0.9, user_score=0.9)

        # Reliability should increase with good alignment
        assert learner._critic_reliability > initial_reliability

    def test_track_alignment_misalignment_reduces_reliability(self, learner):
        """Poor alignment reduces critic reliability."""
        # Start with some good alignment
        learner.track_alignment("art1", critic_score=0.8, user_score=0.8)
        good_reliability = learner._critic_reliability

        # Now add misaligned feedback
        learner.track_alignment("art2", critic_score=0.9, user_score=0.2)
        learner.track_alignment("art3", critic_score=0.1, user_score=0.8)

        # Reliability should decrease
        assert learner._critic_reliability < good_reliability

    def test_record_critic_evaluation(self, learner):
        """record_critic_evaluation creates appropriate feedback."""
        critic_analysis = {
            "overall_score": 0.85,  # High score should map to "like" or "love"
        }

        learner.record_critic_evaluation(
            artwork_id="art1",
            critic_analysis=critic_analysis,
            params={"steps": 30},
            prompt="test prompt",
            model_id="test-model",
        )

        # Should have recorded feedback
        assert "test-model" in learner.model_scores

    def test_neutral_critic_scores_ignored(self, learner):
        """Critic scores between 0.45-0.7 don't create feedback."""
        critic_analysis = {
            "overall_score": 0.55,  # Neutral
        }

        learner.record_critic_evaluation(
            artwork_id="art1",
            critic_analysis=critic_analysis,
            params={"steps": 30},
            prompt="test prompt",
            model_id="test-model",
        )

        # Should NOT have recorded feedback for neutral score
        assert "test-model" not in learner.model_scores

    def test_get_critic_reliability(self, learner):
        """get_critic_reliability returns current value."""
        reliability = learner.get_critic_reliability()
        assert 0 <= reliability <= 1

    def test_convert_user_action_to_score(self, learner):
        """convert_user_action_to_score normalizes to 0-1."""
        love_score = learner.convert_user_action_to_score("love")
        like_score = learner.convert_user_action_to_score("like")
        delete_score = learner.convert_user_action_to_score("delete")

        # love = 1.0 -> (1+1)/2 = 1.0
        # like = 0.7 -> (0.7+1)/2 = 0.85
        # delete = -1.0 -> (-1+1)/2 = 0.0
        assert love_score == pytest.approx(1.0)
        assert like_score == pytest.approx(0.85)
        assert delete_score == pytest.approx(0.0)

    def test_learning_stats_includes_critic_reliability(self, learner):
        """get_learning_stats includes critic reliability."""
        # Record some feedback so we have data
        feedback = FeedbackSignal(
            artwork_id="art1",
            user_action="like",
            generation_params={"steps": 30},
            prompt="test prompt",
            model_id="test-model",
        )
        learner.record_feedback(feedback)

        stats = learner.get_learning_stats()
        assert "critic_reliability" in stats
        assert "alignment_samples" in stats

    def test_alignment_history_persistence(self, learner):
        """Alignment history is persisted and loaded."""
        learner.track_alignment("art1", critic_score=0.8, user_score=0.8)
        learner.track_alignment("art2", critic_score=0.7, user_score=0.7)

        # Save state
        learner._save_state()

        # Create new learner with same storage
        learner2 = AdaptiveLearner(storage_path=learner.storage_path)

        assert len(learner2.alignment_history) == 2
        assert learner2._critic_reliability == pytest.approx(
            learner._critic_reliability, rel=0.01
        )


class TestSuggestParameters:
    """Param-hash keys are str(sorted(items)) — must round-trip to a dict."""

    @pytest.fixture
    def learner(self):
        with TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test_learning.json"
            yield AdaptiveLearner(storage_path=storage_path)

    def test_suggest_parameters_returns_dict_not_list(self, learner):
        feedback = FeedbackSignal(
            artwork_id="art1",
            user_action="like",
            generation_params={
                "num_inference_steps": 40,
                "guidance_scale": 7.5,
                "width": 768,
                "height": 768,
            },
            prompt="misty harbor",
            model_id="test-model",
            source="user",
        )
        learner.record_feedback(feedback)

        suggested = learner.suggest_parameters()
        assert isinstance(suggested, dict)
        assert suggested["num_inference_steps"] == 40
        assert suggested["guidance_scale"] == 7.5
        # Must support .items() (creative_mind context builder)
        assert "guidance_scale=7.5" in ", ".join(
            f"{k}={v}" for k, v in suggested.items()
        )

    def test_parse_param_hash_list_of_pairs(self):
        raw = "[('guidance_scale', 7.5), ('height', 768), ('num_inference_steps', 40), ('width', 768)]"
        parsed = AdaptiveLearner._parse_param_hash(raw)
        assert parsed == {
            "guidance_scale": 7.5,
            "height": 768,
            "num_inference_steps": 40,
            "width": 768,
        }

    def test_parse_param_hash_dict_form(self):
        parsed = AdaptiveLearner._parse_param_hash("{'width': 512, 'height': 512}")
        assert parsed == {"width": 512, "height": 512}
