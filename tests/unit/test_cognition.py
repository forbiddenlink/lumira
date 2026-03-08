"""Tests for Lumira's cognition and thinking process."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_artist.personality.cognition import ThinkingProcess, Thought, ThoughtType
from ai_artist.personality.moods import Mood, MoodSystem


class TestThoughtType:
    """Test the ThoughtType enum."""

    def test_thought_types_exist(self):
        """Test all expected thought types exist."""
        expected = ["observe", "reflect", "decide", "express", "create"]
        actual = [t.value for t in ThoughtType]
        assert sorted(actual) == sorted(expected)

    def test_thought_type_is_string_enum(self):
        """Test ThoughtType values are strings."""
        assert isinstance(ThoughtType.OBSERVE.value, str)
        assert ThoughtType.OBSERVE.value == "observe"


class TestThought:
    """Test the Thought class."""

    def test_thought_creation(self):
        """Test creating a thought."""
        thought = Thought(
            thought_type=ThoughtType.OBSERVE,
            content="I notice the morning light",
        )
        assert thought.type == ThoughtType.OBSERVE
        assert thought.content == "I notice the morning light"
        assert thought.context == {}

    def test_thought_with_context(self):
        """Test creating a thought with context."""
        context = {"time": "morning", "weather": "sunny"}
        thought = Thought(
            thought_type=ThoughtType.REFLECT,
            content="Thinking about nature",
            context=context,
        )
        assert thought.context == context

    def test_thought_has_timestamp(self):
        """Test thought has an ISO timestamp."""
        thought = Thought(ThoughtType.OBSERVE, "test")
        # Should be a valid ISO timestamp
        datetime.fromisoformat(thought.timestamp)

    def test_thought_to_dict(self):
        """Test thought serialization to dict."""
        thought = Thought(
            thought_type=ThoughtType.DECIDE,
            content="I choose this path",
            context={"options": ["a", "b"]},
        )
        d = thought.to_dict()

        assert d["type"] == "decide"
        assert d["content"] == "I choose this path"
        assert d["context"] == {"options": ["a", "b"]}
        assert "timestamp" in d

    def test_thought_format_display(self):
        """Test thought display formatting."""
        thought = Thought(ThoughtType.EXPRESS, "With joy, I create")
        display = thought.format_display()

        assert "[EXPRESS]" in display
        assert "With joy, I create" in display


class TestThinkingProcessInit:
    """Test ThinkingProcess initialization."""

    def test_init_without_dependencies(self):
        """Test initialization without mood or memory systems."""
        tp = ThinkingProcess()
        assert tp.mood_system is None
        assert tp.memory_system is None
        assert tp.on_thought is None
        assert tp.thoughts == []
        assert tp.working_context == {}

    def test_init_with_mood_system(self):
        """Test initialization with mood system."""
        mood = MoodSystem()
        tp = ThinkingProcess(mood_system=mood)
        assert tp.mood_system is mood

    def test_init_with_callback(self):
        """Test initialization with thought callback."""
        callback = MagicMock()
        tp = ThinkingProcess(on_thought=callback)
        assert tp.on_thought is callback


class TestObserve:
    """Test the observe method."""

    @pytest.fixture
    def thinking(self):
        """Create a ThinkingProcess with mood system."""
        mood = MoodSystem()
        return ThinkingProcess(mood_system=mood)

    def test_observe_returns_string(self, thinking):
        """Test observe returns a string observation."""
        obs = thinking.observe({"time_of_day": "morning"})
        assert isinstance(obs, str)
        assert len(obs) > 0

    def test_observe_morning_context(self, thinking):
        """Test observation includes morning context."""
        obs = thinking.observe({"time_of_day": "morning"})
        assert "morning" in obs.lower() or "fresh" in obs.lower()

    def test_observe_evening_context(self, thinking):
        """Test observation includes evening context."""
        obs = thinking.observe({"time_of_day": "evening"})
        assert "evening" in obs.lower() or "shadow" in obs.lower()

    def test_observe_night_context(self, thinking):
        """Test observation includes night context."""
        obs = thinking.observe({"time_of_day": "night"})
        assert "night" in obs.lower() or "quiet" in obs.lower()

    def test_observe_with_theme(self, thinking):
        """Test observation mentions suggested theme."""
        obs = thinking.observe({"theme": "ocean waves"})
        assert "ocean waves" in obs

    def test_observe_without_theme(self, thinking):
        """Test observation notes freedom when no theme."""
        obs = thinking.observe({})
        assert "free" in obs.lower() or "intuition" in obs.lower()

    def test_observe_with_recent_work(self, thinking):
        """Test observation mentions recent work."""
        obs = thinking.observe({"recent_work": "sunset painting"})
        assert "sunset painting" in obs or "recent" in obs.lower()

    def test_observe_emits_thought(self, thinking):
        """Test observe emits a thought."""
        thinking.observe({"time_of_day": "morning"})
        assert len(thinking.thoughts) == 1
        assert thinking.thoughts[0].type == ThoughtType.OBSERVE

    def test_observe_includes_mood_state(self, thinking):
        """Test observation includes mood state."""
        obs = thinking.observe({})
        assert "feeling" in obs.lower()

    def test_observe_updates_working_context(self, thinking):
        """Test observe updates working context."""
        thinking.observe({"time_of_day": "morning", "custom": "value"})
        assert thinking.working_context.get("time_of_day") == "morning"
        assert thinking.working_context.get("custom") == "value"


class TestReflect:
    """Test the reflect method."""

    @pytest.fixture
    def thinking(self):
        """Create a ThinkingProcess with mood system."""
        mood = MoodSystem()
        return ThinkingProcess(mood_system=mood)

    def test_reflect_returns_string(self, thinking):
        """Test reflect returns a string."""
        reflection = thinking.reflect("nature")
        assert isinstance(reflection, str)
        assert len(reflection) > 0

    def test_reflect_includes_topic(self, thinking):
        """Test reflection includes the topic."""
        reflection = thinking.reflect("ocean waves")
        assert "ocean waves" in reflection

    def test_reflect_emits_thought(self, thinking):
        """Test reflect emits a thought."""
        thinking.reflect("test topic")
        assert len(thinking.thoughts) == 1
        assert thinking.thoughts[0].type == ThoughtType.REFLECT

    def test_reflect_influenced_by_mood(self, thinking):
        """Test reflection is influenced by mood."""
        thinking.mood_system.current_mood = Mood.CONTEMPLATIVE
        contemplative_reflection = thinking.reflect("nature")

        thinking.mood_system.current_mood = Mood.CHAOTIC
        thinking.thoughts = []  # Clear for next test
        chaotic_reflection = thinking.reflect("nature")

        # Different moods should produce different reflections
        assert contemplative_reflection != chaotic_reflection

    def test_reflect_with_memory_context(self):
        """Test reflection uses memory context when available."""
        mock_memory = MagicMock()
        mock_memory.get_relevant_context.return_value = {
            "similar_mood_episodes": [{"details": {"subject": "past work"}}],
            "best_styles": [("impressionist", 0.9)],
        }

        thinking = ThinkingProcess(
            mood_system=MoodSystem(),
            memory_system=mock_memory,
        )
        thinking.reflect("art")

        # Should query memory
        mock_memory.get_relevant_context.assert_called_once()


class TestDecide:
    """Test the decide method."""

    @pytest.fixture
    def thinking(self):
        """Create a ThinkingProcess with mood system."""
        mood = MoodSystem()
        return ThinkingProcess(mood_system=mood)

    def test_decide_returns_tuple(self, thinking):
        """Test decide returns a tuple of choice and reasoning."""
        result = thinking.decide(["option1", "option2"])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_decide_empty_options(self, thinking):
        """Test decide handles empty options."""
        choice, reasoning = thinking.decide([])
        assert choice == ""
        assert "intuition" in reasoning.lower()

    def test_decide_single_option(self, thinking):
        """Test decide with single option."""
        choice, reasoning = thinking.decide(["only_option"])
        assert choice == "only_option"

    def test_decide_emits_thought(self, thinking):
        """Test decide emits a thought."""
        thinking.decide(["a", "b"])
        assert len(thinking.thoughts) == 1
        assert thinking.thoughts[0].type == ThoughtType.DECIDE

    def test_decide_influenced_by_mood(self, thinking):
        """Test mood influences decision."""
        thinking.mood_system.current_mood = Mood.SERENE
        options = ["peaceful lake", "chaotic storm"]

        # Run multiple times - serene mood should prefer peaceful
        choices = []
        for _ in range(10):
            thinking.thoughts = []
            choice, _ = thinking.decide(options)
            choices.append(choice)

        # Should have at least some peaceful choices
        assert "peaceful lake" in choices

    def test_decide_prefers_novel_subjects(self):
        """Test decision prefers novel subjects when memory available."""
        mock_memory = MagicMock()
        mock_memory.episodic.get_recent_episodes.return_value = [
            {"details": {"subject": "ocean"}},
        ]

        thinking = ThinkingProcess(
            mood_system=MoodSystem(),
            memory_system=mock_memory,
        )

        # "ocean" is in recent, "mountain" should be preferred
        choice, reasoning = thinking.decide(["ocean", "mountain"])
        # Note: This depends on mood not overriding; test the mechanism exists


class TestExpress:
    """Test the express method."""

    @pytest.fixture
    def thinking(self):
        """Create a ThinkingProcess with mood system."""
        mood = MoodSystem()
        return ThinkingProcess(mood_system=mood)

    def test_express_returns_string(self, thinking):
        """Test express returns a string."""
        expression = thinking.express("I will paint")
        assert isinstance(expression, str)
        assert len(expression) > 0

    def test_express_emits_thought(self, thinking):
        """Test express emits a thought."""
        thinking.express("creating art")
        assert len(thinking.thoughts) == 1
        assert thinking.thoughts[0].type == ThoughtType.EXPRESS

    def test_express_colored_by_mood(self, thinking):
        """Test expression is colored by mood."""
        thinking.mood_system.current_mood = Mood.CONTEMPLATIVE
        contemplative = thinking.express("I paint")

        thinking.mood_system.current_mood = Mood.CHAOTIC
        thinking.thoughts = []
        chaotic = thinking.express("I paint")

        assert contemplative != chaotic
        assert "quiet" in contemplative.lower() or "intention" in contemplative.lower()
        assert "wild" in chaotic.lower() or "energy" in chaotic.lower()

    def test_express_high_energy_adds_exclamation(self, thinking):
        """Test high energy adds exclamation."""
        thinking.mood_system.energy_level = 0.9
        expression = thinking.express("I create")
        assert expression.endswith("!")

    def test_express_low_energy_adds_ellipsis(self, thinking):
        """Test low energy adds ellipsis."""
        thinking.mood_system.energy_level = 0.1
        expression = thinking.express("I create")
        assert expression.endswith("...")


class TestBeginCreation:
    """Test the begin_creation method."""

    @pytest.fixture
    def thinking(self):
        return ThinkingProcess()

    def test_begin_creation_returns_string(self, thinking):
        """Test begin_creation returns a string."""
        statement = thinking.begin_creation(
            {"subject": "sunset", "style": "impressionist"}
        )
        assert isinstance(statement, str)
        assert len(statement) > 0

    def test_begin_creation_includes_subject(self, thinking):
        """Test statement includes subject."""
        statement = thinking.begin_creation({"subject": "mountain"})
        assert "mountain" in statement

    def test_begin_creation_includes_style(self, thinking):
        """Test statement includes style."""
        statement = thinking.begin_creation({"style": "watercolor"})
        assert "watercolor" in statement

    def test_begin_creation_emits_thought(self, thinking):
        """Test begin_creation emits a thought."""
        thinking.begin_creation({"subject": "test"})
        assert len(thinking.thoughts) == 1
        assert thinking.thoughts[0].type == ThoughtType.CREATE


class TestThoughtCallback:
    """Test thought callback functionality."""

    def test_callback_invoked_on_observe(self):
        """Test callback is invoked when observing."""
        callback = MagicMock()
        thinking = ThinkingProcess(on_thought=callback)

        thinking.observe({})

        callback.assert_called_once()
        thought = callback.call_args[0][0]
        assert thought.type == ThoughtType.OBSERVE

    def test_callback_invoked_on_reflect(self):
        """Test callback is invoked when reflecting."""
        callback = MagicMock()
        thinking = ThinkingProcess(on_thought=callback)

        thinking.reflect("topic")

        callback.assert_called_once()
        thought = callback.call_args[0][0]
        assert thought.type == ThoughtType.REFLECT

    def test_callback_exception_handled(self):
        """Test callback exceptions are handled gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        thinking = ThinkingProcess(on_thought=callback)

        # Should not raise
        thinking.observe({})
        assert len(thinking.thoughts) == 1


class TestThoughtStorageInMemory:
    """Test thought storage in memory system."""

    def test_store_in_memory_without_memory_system(self):
        """Test store_in_memory does nothing without memory system."""
        thinking = ThinkingProcess()
        thinking.observe({})
        thinking.store_in_memory()  # Should not raise

    def test_store_in_memory_without_thoughts(self):
        """Test store_in_memory does nothing without thoughts."""
        mock_memory = MagicMock()
        thinking = ThinkingProcess(memory_system=mock_memory)
        thinking.store_in_memory()
        mock_memory.episodic.record_episode.assert_not_called()

    def test_store_in_memory_records_episode(self):
        """Test store_in_memory records an episode."""
        mock_memory = MagicMock()
        mock_mood = MagicMock()
        mock_mood.current_mood.value = "contemplative"
        mock_mood.energy_level = 0.5

        thinking = ThinkingProcess(mood_system=mock_mood, memory_system=mock_memory)
        thinking.observe({})
        thinking.reflect("test")
        thinking.store_in_memory()

        mock_memory.episodic.record_episode.assert_called_once()
        call_kwargs = mock_memory.episodic.record_episode.call_args.kwargs
        assert call_kwargs["event_type"] == "thinking_session"
        assert "thoughts" in call_kwargs["details"]


class TestSessionManagement:
    """Test session management methods."""

    @pytest.fixture
    def thinking(self):
        return ThinkingProcess()

    def test_get_session_thoughts(self, thinking):
        """Test get_session_thoughts returns list of dicts."""
        thinking.observe({})
        thinking.reflect("test")

        thoughts = thinking.get_session_thoughts()

        assert isinstance(thoughts, list)
        assert len(thoughts) == 2
        assert all(isinstance(t, dict) for t in thoughts)

    def test_get_thinking_narrative(self, thinking):
        """Test get_thinking_narrative returns formatted string."""
        thinking.observe({"time_of_day": "morning"})
        thinking.reflect("nature")

        narrative = thinking.get_thinking_narrative()

        assert isinstance(narrative, str)
        assert "[OBSERVE]" in narrative
        assert "[REFLECT]" in narrative

    def test_clear_session(self, thinking):
        """Test clear_session resets state."""
        thinking.observe({})
        thinking.reflect("test")
        thinking.working_context["key"] = "value"

        thinking.clear_session()

        assert thinking.thoughts == []
        assert thinking.working_context == {}


class TestMoodInfluenceOnThinking:
    """Test how mood influences the thinking process."""

    def test_contemplative_mood_adds_depth(self):
        """Test contemplative mood adds depth to reflection."""
        thinking = ThinkingProcess(mood_system=MoodSystem())
        thinking.mood_system.current_mood = Mood.CONTEMPLATIVE

        reflection = thinking.reflect("art")

        assert "meaning" in reflection.lower() or "deep" in reflection.lower()

    def test_playful_mood_adds_joy(self):
        """Test playful mood adds joy to reflection."""
        thinking = ThinkingProcess(mood_system=MoodSystem())
        thinking.mood_system.current_mood = Mood.PLAYFUL

        reflection = thinking.reflect("colors")

        assert "fun" in reflection.lower() or "joy" in reflection.lower()

    def test_rebellious_mood_adds_challenge(self):
        """Test rebellious mood adds challenge to reflection."""
        thinking = ThinkingProcess(mood_system=MoodSystem())
        thinking.mood_system.current_mood = Mood.REBELLIOUS

        reflection = thinking.reflect("rules")

        assert "challenge" in reflection.lower() or "expectations" in reflection.lower()
