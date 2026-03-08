"""Tests for Lumira's CreativeMind — LLM-powered creative reasoning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_artist.intelligence.creative_mind import CreativeIntent, CreativeMind
from ai_artist.personality.moods import Mood

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_mock_mood_system(mood=Mood.SERENE):
    ms = MagicMock()
    ms.current_mood = mood
    ms.mood_intensity = 0.7
    ms.energy_level = 0.6
    ms.get_mood_influence = MagicMock(
        return_value={
            "styles": ["impressionist"],
            "subjects": ["peaceful landscape"],
            "colors": ["soft blue"],
        }
    )
    ms.describe_feeling = MagicMock(return_value="I'm gently held by serene stillness.")
    ms.style_axes = MagicMock()
    ms.style_axes.to_dict = MagicMock(
        return_value={
            "abstraction": 0.3,
            "darkness": 0.2,
            "complexity": 0.5,
            "warmth": 0.6,
            "energy": 0.3,
            "organic": 0.7,
            "surrealism": 0.2,
            "minimalism": 0.4,
            "narrative": 0.5,
            "intimacy": 0.6,
        }
    )
    ms.mood_influences = {
        mood: {
            "styles": ["impressionist"],
            "subjects": ["peaceful landscape"],
            "colors": ["soft blue"],
        }
    }
    return ms


def create_mock_memory():
    mem = MagicMock()
    mem.get_recent_episodes = MagicMock(return_value=[])
    mem.xp = 0
    mem.level = 1
    return mem


def create_mock_learner():
    learner = MagicMock()
    learner.get_learning_stats = MagicMock(
        return_value={
            "total_feedback": 0,
            "models_tracked": 0,
            "top_prompts": [],
        }
    )
    learner.suggest_parameters = MagicMock(return_value={})
    learner.prompt_patterns = {}
    return learner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreativeIntent:
    """Test the CreativeIntent pydantic model."""

    def test_creative_intent_model(self):
        """CreativeIntent validates with required fields and sets defaults."""
        intent = CreativeIntent(
            subject="a cat in space",
            style="digital art",
            mood_alignment="playful curiosity",
            reasoning="Because cats and space are both mysterious.",
            prompt="a cat floating in space, whimsical digital art, masterpiece",
        )
        assert intent.subject == "a cat in space"
        assert intent.style == "digital art"
        assert intent.mood_alignment == "playful curiosity"
        assert intent.reasoning.startswith("Because")
        assert "cat" in intent.prompt
        # Defaults
        assert "blurry" in intent.negative_prompt
        assert intent.artistic_goals == []
        assert intent.thinking_narrative == ""
        assert intent.generation_params == {}
        assert intent.is_user_request is False
        assert intent.user_prompt is None


class TestCreativeMind:
    """Test the CreativeMind class."""

    @pytest.fixture
    def creative_mind(self):
        """Create a CreativeMind with mocked subsystems and no API key."""
        mood = create_mock_mood_system()
        mem = create_mock_memory()
        learner = create_mock_learner()
        with patch.dict("os.environ", {}, clear=False):
            # Ensure no ANTHROPIC_API_KEY leaks in
            import os

            old = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                cm = CreativeMind(
                    mood_system=mood,
                    memory_system=mem,
                    learner=learner,
                    api_key=None,
                )
                yield cm
            finally:
                if old is not None:
                    os.environ["ANTHROPIC_API_KEY"] = old

    def test_creative_mind_initialization(self, creative_mind):
        """CreativeMind initializes with mood_system, memory_system, learner."""
        assert creative_mind.mood_system is not None
        assert creative_mind.memory_system is not None
        assert creative_mind.learner is not None
        assert creative_mind.desire_engine is not None

    def test_creative_mind_has_llm_without_key(self, creative_mind):
        """has_llm is False when no API key is provided."""
        assert creative_mind.has_llm is False

    @pytest.mark.asyncio
    async def test_fallback_decide_returns_creative_intent(self, creative_mind):
        """decide_what_to_create() without LLM returns a well-formed CreativeIntent."""
        intent = await creative_mind.decide_what_to_create()
        assert isinstance(intent, CreativeIntent)
        assert intent.subject
        assert intent.style
        assert intent.mood_alignment
        assert intent.reasoning
        assert intent.prompt
        assert intent.negative_prompt

    @pytest.mark.asyncio
    async def test_fallback_decide_mood_influence(self):
        """The returned intent reflects the current mood."""
        mood_sys = create_mock_mood_system(Mood.CHAOTIC)
        # Add mood_influences for CHAOTIC
        mood_sys.mood_influences = {
            Mood.CHAOTIC: {
                "styles": ["abstract expressionism", "glitch art"],
                "subjects": ["chaos", "energy"],
                "colors": ["clashing neons"],
            }
        }

        with patch.dict("os.environ", {}, clear=False):
            import os

            old = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                cm = CreativeMind(
                    mood_system=mood_sys,
                    memory_system=create_mock_memory(),
                    learner=create_mock_learner(),
                )
                intent = await cm.decide_what_to_create()
            finally:
                if old is not None:
                    os.environ["ANTHROPIC_API_KEY"] = old

        assert isinstance(intent, CreativeIntent)
        # The prompt or mood_alignment should reference the chaotic mood
        lower_prompt = intent.prompt.lower()
        lower_alignment = intent.mood_alignment.lower()
        assert "chaotic" in lower_prompt or "chaotic" in lower_alignment

    def test_mood_generation_params(self):
        """_mood_generation_params returns different params for different moods."""
        for mood_val, expected_low_guidance in [
            (Mood.CHAOTIC, True),
            (Mood.SERENE, False),
        ]:
            mood_sys = create_mock_mood_system(mood_val)
            with patch.dict("os.environ", {}, clear=False):
                import os

                old = os.environ.pop("ANTHROPIC_API_KEY", None)
                try:
                    cm = CreativeMind(mood_system=mood_sys)
                finally:
                    if old is not None:
                        os.environ["ANTHROPIC_API_KEY"] = old

            params = cm._mood_generation_params()
            assert "guidance_scale" in params
            assert "num_inference_steps" in params

            if expected_low_guidance:
                # CHAOTIC guidance_scale should be lower than SERENE's
                assert params["guidance_scale"] < 9.0
            else:
                assert params["guidance_scale"] >= 7.0

    @pytest.mark.asyncio
    async def test_fallback_user_request(self):
        """process_user_request contains the user's input in the prompt."""
        mood_sys = create_mock_mood_system(Mood.SERENE)
        with patch.dict("os.environ", {}, clear=False):
            import os

            old = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                cm = CreativeMind(
                    mood_system=mood_sys,
                    memory_system=create_mock_memory(),
                    learner=create_mock_learner(),
                )
                intent = await cm.process_user_request("a cat in space")
            finally:
                if old is not None:
                    os.environ["ANTHROPIC_API_KEY"] = old

        assert isinstance(intent, CreativeIntent)
        assert "a cat in space" in intent.prompt
        assert intent.is_user_request is True
        assert intent.user_prompt == "a cat in space"
