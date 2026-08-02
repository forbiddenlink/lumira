"""Tests for Inner Dialogue system."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_artist.memory.graph_memory import MemoryContext
from ai_artist.personality.dialogue import InnerDialogue
from ai_artist.personality.inner_voices import (
    Concept,
    Curator,
    DialogueTurn,
    Dreamer,
    Rememberer,
    Voice,
)


class TestVoice:
    """Tests for Voice enum."""

    def test_voice_values(self):
        """Test all four voices are defined."""
        assert Voice.DREAMER.value == "dreamer"
        assert Voice.CRITIC.value == "critic"
        assert Voice.CURATOR.value == "curator"
        assert Voice.REMEMBERER.value == "rememberer"


class TestConcept:
    """Tests for Concept dataclass."""

    def test_concept_defaults(self):
        """Test concept with minimal fields."""
        concept = Concept(subject="test subject")
        assert concept.subject == "test subject"
        assert concept.mood_blend == {}
        assert concept.style_blend == {}
        assert concept.colors == []
        assert concept.prompt == ""
        assert concept.approved is False

    def test_concept_full(self):
        """Test concept with all fields."""
        concept = Concept(
            subject="mountain landscape",
            mood_blend={"serene": 0.8, "contemplative": 0.2},
            style_blend={"impressionist": 0.6, "atmospheric": 0.4},
            colors=["blue", "gold"],
            prompt="mountain landscape in impressionist style",
            reasoning="I was drawn to the contrast",
            approved=True,
            confidence=0.85,
        )
        assert concept.subject == "mountain landscape"
        assert concept.mood_blend["serene"] == pytest.approx(0.8)
        assert concept.approved is True

    def test_concept_to_dict(self):
        """Test concept serialization."""
        concept = Concept(
            subject="test",
            mood_blend={"calm": 1.0},
            approved=True,
        )
        d = concept.to_dict()
        assert d["subject"] == "test"
        assert d["mood_blend"] == {"calm": 1.0}
        assert d["approved"] is True


class TestDialogueTurn:
    """Tests for DialogueTurn dataclass."""

    def test_dialogue_turn_creation(self):
        """Test creating a dialogue turn."""
        turn = DialogueTurn(
            voice=Voice.DREAMER,
            message="What if we tried something bold?",
        )
        assert turn.voice == Voice.DREAMER
        assert "bold" in turn.message
        assert turn.timestamp is not None

    def test_dialogue_turn_to_dict(self):
        """Test dialogue turn serialization."""
        turn = DialogueTurn(
            voice=Voice.CRITIC,
            message="This needs more depth.",
            metadata={"score": 0.6},
        )
        d = turn.to_dict()
        assert d["voice"] == "critic"
        assert d["message"] == "This needs more depth."
        assert d["metadata"]["score"] == pytest.approx(0.6)


class TestDreamer:
    """Tests for Dreamer voice."""

    @pytest.fixture
    def dreamer(self):
        """Create a Dreamer instance."""
        return Dreamer(temperature=0.7)

    @pytest.mark.asyncio
    async def test_imagine_generates_ideas(self, dreamer):
        """Test that imagine generates the requested number of ideas."""
        ideas = await dreamer.imagine(mood="contemplative", count=3)
        assert len(ideas) == 3
        for idea in ideas:
            assert isinstance(idea, Concept)
            assert idea.subject != ""

    @pytest.mark.asyncio
    async def test_imagine_respects_mood(self, dreamer):
        """Test that ideas reflect the current mood."""
        # imagine() draws `count` subjects at random per mood, so two independent
        # 5-draws can fully overlap by chance (union == count -> a valid but rare
        # outcome). Retry a few times and assert mood-driven divergence appears at
        # least once, rather than hard-failing the occasional all-overlap draw.
        diverged = False
        for _ in range(4):
            contemplative_ideas = await dreamer.imagine(mood="contemplative", count=5)
            playful_ideas = await dreamer.imagine(mood="playful", count=5)
            contemp_subjects = {i.subject for i in contemplative_ideas}
            playful_subjects = {i.subject for i in playful_ideas}
            if len(contemp_subjects | playful_subjects) > len(contemp_subjects):
                diverged = True
                break

        assert diverged, "different moods should produce diverging subjects"

    @pytest.mark.asyncio
    async def test_imagine_with_context(self, dreamer):
        """Test that context influences idea generation."""
        context = MemoryContext(
            top_styles=[{"name": "zen", "avg_score": 0.9}],
            mood_pairs=[],
            similar_works=[],
            recent_work=[],
            recent_subjects=["mountain", "river"],  # Should avoid these
            style_blends=[],
        )

        ideas = await dreamer.imagine(
            mood="serene",
            context=context,
            count=3,
        )

        # Ideas should exist
        assert len(ideas) == 3

    @pytest.mark.asyncio
    async def test_refine_modifies_concept(self, dreamer):
        """Test that refine changes the concept based on feedback."""
        original = Concept(
            subject="simple landscape",
            mood_blend={"serene": 1.0},
            style_blend={"minimalist": 1.0},
        )

        refined = await dreamer.refine(original, "Make it bolder and more dramatic")

        # Should have been modified
        assert (
            refined.subject != original.subject
            or refined.style_blend != original.style_blend
        )
        assert "dramatic" in refined.style_blend or "bold" in refined.reasoning.lower()


class TestCurator:
    """Tests for Curator voice."""

    @pytest.fixture
    def curator(self):
        """Create a Curator instance."""
        return Curator(variety_weight=0.6)

    @pytest.mark.asyncio
    async def test_filter_ranks_ideas(self, curator):
        """Test that filter sorts ideas by score."""
        ideas = [
            Concept(subject="boring same thing", mood_blend={"calm": 1.0}),
            Concept(subject="exciting new concept", mood_blend={"euphoric": 0.9}),
            Concept(subject="another same thing", mood_blend={"calm": 1.0}),
        ]

        recent_work = [
            {"prompt": "same thing variation", "styles": ["minimalist"]},
        ]

        filtered = await curator.filter(ideas, recent_work)

        # Should still have all ideas
        assert len(filtered) == 3

        # "Exciting new concept" should score higher due to novelty
        subjects = [c.subject for c in filtered]
        assert "exciting new concept" in subjects

    @pytest.mark.asyncio
    async def test_filter_empty_ideas(self, curator):
        """Test filter handles empty input."""
        filtered = await curator.filter([], [])
        assert filtered == []

    def test_get_feedback_repetition(self, curator):
        """Test feedback identifies repetition."""
        concept = Concept(subject="mountain landscape")
        recent = [
            {"prompt": "mountain view at sunset"},
            {"prompt": "ocean waves"},
        ]

        feedback = curator.get_feedback(concept, recent)
        assert "similar" in feedback.lower() or "fresh" in feedback.lower()

    def test_get_feedback_unique(self, curator):
        """Test feedback approves unique concepts."""
        concept = Concept(subject="cosmic nebula")
        recent = [
            {"prompt": "mountain view"},
            {"prompt": "ocean waves"},
        ]

        feedback = curator.get_feedback(concept, recent)
        # Should be positive since it's different
        assert "fresh" in feedback.lower() or "approve" in feedback.lower()


class TestRememberer:
    """Tests for Rememberer voice."""

    @pytest.fixture
    def rememberer(self):
        """Create a Rememberer with no backends."""
        return Rememberer()

    @pytest.mark.asyncio
    async def test_recall_empty(self, rememberer):
        """Test recall returns empty context when no backends."""
        context = await rememberer.recall(mood="contemplative")

        assert isinstance(context, MemoryContext)
        assert context.top_styles == []
        assert context.recent_work == []

    @pytest.mark.asyncio
    async def test_recall_with_mock_graph(self):
        """Test recall uses graph memory when available."""
        mock_graph = AsyncMock()
        mock_context = MemoryContext(
            top_styles=[{"name": "impressionist", "avg_score": 0.85}],
            mood_pairs=[],
            similar_works=[],
            recent_work=[{"id": "1", "prompt": "test"}],
            recent_subjects=["test"],
            style_blends=[],
        )
        mock_graph.get_context_for_creation = AsyncMock(return_value=mock_context)

        rememberer = Rememberer(graph_memory=mock_graph)
        context = await rememberer.recall(mood="serene")

        assert len(context.top_styles) == 1
        assert context.top_styles[0]["name"] == "impressionist"

    def test_format_memory_message_with_styles(self, rememberer):
        """Test formatting memory as natural language."""
        context = MemoryContext(
            top_styles=[{"name": "zen"}, {"name": "minimalist"}],
            mood_pairs=[],
            similar_works=[],
            recent_work=[],
            recent_subjects=[],
            style_blends=[],
        )

        message = rememberer.format_memory_message(context)
        assert "zen" in message
        assert "minimalist" in message

    def test_format_memory_message_empty(self, rememberer):
        """Test formatting when no memories available."""
        context = MemoryContext(
            top_styles=[],
            mood_pairs=[],
            similar_works=[],
            recent_work=[],
            recent_subjects=[],
            style_blends=[],
        )

        message = rememberer.format_memory_message(context)
        assert "fresh start" in message.lower() or "no specific" in message.lower()


class TestInnerDialogue:
    """Tests for InnerDialogue orchestrator."""

    @pytest.fixture
    def dialogue(self):
        """Create an InnerDialogue with default voices."""
        return InnerDialogue()

    @pytest.mark.asyncio
    async def test_deliberate_produces_concept(self, dialogue):
        """Test that deliberate returns an approved concept."""
        concept = await dialogue.deliberate(mood="contemplative")

        assert isinstance(concept, Concept)
        assert concept.subject != ""
        assert concept.approved is True
        assert concept.prompt != ""

    @pytest.mark.asyncio
    async def test_deliberate_records_history(self, dialogue):
        """Test that deliberate records dialogue history."""
        await dialogue.deliberate(mood="playful")

        history = dialogue.get_dialogue_history()
        assert len(history) > 0

        # Should have turns from multiple voices
        voices = {turn["voice"] for turn in history}
        assert "rememberer" in voices
        assert "dreamer" in voices
        assert "curator" in voices

    @pytest.mark.asyncio
    async def test_deliberate_with_theme(self, dialogue):
        """Test deliberate with a theme suggestion."""
        concept = await dialogue.deliberate(
            mood="melancholic",
            theme="autumn leaves",
        )

        assert concept.approved is True
        # Theme might influence the concept (not guaranteed due to randomness)

    @pytest.mark.asyncio
    async def test_deliberate_with_callback(self):
        """Test that on_turn callback is invoked."""
        turns_received = []

        async def on_turn(turn):
            await asyncio.sleep(0)
            turns_received.append(turn)

        dialogue = InnerDialogue(on_turn=on_turn)
        await dialogue.deliberate(mood="serene")

        assert len(turns_received) > 0
        assert all(isinstance(t, DialogueTurn) for t in turns_received)

    @pytest.mark.asyncio
    async def test_deliberate_with_critic(self):
        """Test deliberate with a mock critic."""
        mock_critic = MagicMock()
        mock_critic.critique_concept.return_value = {
            "approved": True,
            "confidence": 0.8,
            "critique": "This concept has merit.",
            "suggestions": [],
        }

        dialogue = InnerDialogue(critic=mock_critic)
        concept = await dialogue.deliberate(mood="curious")

        assert concept.approved is True
        assert concept.confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_deliberate_refinement_loop(self):
        """Test that refinement happens when critic rejects."""
        mock_critic = MagicMock()

        # First call rejects, second approves
        mock_critic.critique_concept.side_effect = [
            {
                "approved": False,
                "confidence": 0.4,
                "critique": "Needs more boldness.",
                "suggestions": ["Add contrast"],
            },
            {
                "approved": True,
                "confidence": 0.75,
                "critique": "Better, I approve.",
                "suggestions": [],
            },
        ]

        dialogue = InnerDialogue(critic=mock_critic)
        concept = await dialogue.deliberate(mood="rebellious")

        assert concept.approved is True
        # Critic should have been called twice
        assert mock_critic.critique_concept.call_count == 2

    def test_get_dialogue_narrative(self, dialogue):
        """Test narrative formatting."""
        # Add some test turns
        dialogue.history = [
            DialogueTurn(voice=Voice.REMEMBERER, message="I recall..."),
            DialogueTurn(voice=Voice.DREAMER, message="What if..."),
        ]

        narrative = dialogue.get_dialogue_narrative()
        assert "[Rememberer]" in narrative
        assert "[Dreamer]" in narrative
        assert "I recall" in narrative

    def test_clear_history(self, dialogue):
        """Test history clearing."""
        dialogue.history = [
            DialogueTurn(voice=Voice.CRITIC, message="test"),
        ]

        dialogue.clear_history()
        assert dialogue.history == []

    @pytest.mark.asyncio
    async def test_max_iterations_respected(self):
        """Test that max iterations is respected."""
        mock_critic = MagicMock()
        # Always reject
        mock_critic.critique_concept.return_value = {
            "approved": False,
            "confidence": 0.3,
            "critique": "Not good enough.",
            "suggestions": [],
        }

        dialogue = InnerDialogue(critic=mock_critic)
        concept = await dialogue.deliberate(mood="anxious")

        # Should still return (forced approval)
        assert concept.approved is True
        assert concept.confidence == pytest.approx(0.5)  # Forced approval confidence

        # Should not exceed MAX_ITERATIONS
        assert mock_critic.critique_concept.call_count <= InnerDialogue.MAX_ITERATIONS
