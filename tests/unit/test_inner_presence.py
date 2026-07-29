"""Presence tests — Lumira should feel like a continuous being, not empty chrome."""

from __future__ import annotations

import pytest

from ai_artist.personality.dialogue import InnerDialogue
from ai_artist.personality.inner_voices import Voice

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_reflect_on_intent_uses_rememberer_and_critic():
    from unittest.mock import AsyncMock, MagicMock

    rememberer = MagicMock()
    rememberer.recall = AsyncMock(
        return_value=MagicMock(
            recent_subjects=["harbor lights"],
            top_styles=[{"name": "oil"}],
            style_blends=[],
            similar_works=[],
        )
    )
    rememberer.format_memory_message = MagicMock(
        return_value="I recall harbor lights from a quieter night."
    )

    critic = MagicMock()
    critic.critique_concept = MagicMock(
        return_value={
            "approved": True,
            "confidence": 0.9,
            "critique": "The harbor idea holds weight — commit to the wet edges.",
            "suggestions": ["soften the horizon"],
        }
    )

    dialogue = InnerDialogue(
        rememberer=rememberer, critic=critic, history_path=None
    )
    await dialogue.reflect_on_intent(
        subject="harbor lights",
        style="oil",
        mood="melancholic",
        reasoning="Tide memory",
    )
    rememberer.recall.assert_awaited()
    critic.critique_concept.assert_called_once()
    critic_turns = [t for t in dialogue.history if t.voice == Voice.CRITIC]
    assert critic_turns
    assert "wet edges" in critic_turns[-1].message
    assert critic_turns[-1].metadata.get("from_critic") is True


@pytest.mark.asyncio
async def test_reflect_on_intent_records_four_voices():
    dialogue = InnerDialogue(history_path=None)
    await dialogue.reflect_on_intent(
        subject="twilight harbor",
        style="oil painting",
        mood="melancholic",
        reasoning="The water remembers what the day forgot.",
        artistic_goals=["quiet longing", "soft edges"],
    )
    voices = [
        t.voice.value if hasattr(t.voice, "value") else str(t.voice)
        for t in dialogue.history
    ]
    assert voices == [
        Voice.REMEMBERER.value,
        Voice.DREAMER.value,
        Voice.CURATOR.value,
        Voice.CRITIC.value,
    ]
    assert any("twilight harbor" in t.message for t in dialogue.history)
    assert dialogue.get_history()  # alias used by AIArtist


@pytest.mark.asyncio
async def test_reflect_on_intent_appends_without_clearing_prior():
    dialogue = InnerDialogue(history_path=None)
    await dialogue.reflect_on_intent(
        subject="one", style="ink", mood="serene", reasoning="first"
    )
    await dialogue.reflect_on_intent(
        subject="two", style="ink", mood="serene", reasoning="second"
    )
    assert len(dialogue.history) == 8
    assert dialogue.history[-1].metadata.get("subject") == "two"


def test_desire_engine_wakes_with_alive_drives():
    from ai_artist.intelligence.desire_engine import DesireEngine

    engine = DesireEngine(persist=False)
    status = engine.get_drive_status()
    assert all(info["intensity"] > 0 for info in status.values())


def test_mood_system_roundtrip_persistence(tmp_path, monkeypatch):
    from ai_artist.personality.moods import Mood, MoodSystem
    import ai_artist.web.lumira_routes as routes

    mood_file = tmp_path / "lumira_mood_state.json"
    monkeypatch.setattr(routes, "_MOOD_STATE_FILE", mood_file)

    system = MoodSystem()
    system.current_mood = Mood.MELANCHOLIC
    system.mood_intensity = 0.82
    system.energy_level = 0.41
    routes._save_mood_system(system)

    restored = routes._load_mood_system()
    assert restored.current_mood == Mood.MELANCHOLIC
    assert restored.mood_intensity == pytest.approx(0.82, abs=0.05)


@pytest.mark.asyncio
async def test_inner_dialogue_singleton_survives_across_lookups(monkeypatch):
    """Studio dialogue must be one mind, not a fresh empty instance per request."""
    import ai_artist.web.lumira_routes as routes

    # Reset process state so we exercise lazy singleton creation
    monkeypatch.setattr(routes, "_lumira_state", None)

    d1 = routes._get_inner_dialogue(session_id="a")
    d2 = routes._get_inner_dialogue(session_id="b")
    assert d1 is d2
    assert d1.critic is not None
    assert d1.rememberer is not None
    assert d1.rememberer.enhanced is not None

    await d1.reflect_on_intent(
        subject="shared mind", style="ink", mood="serene", reasoning="same being"
    )
    assert len(d2.history) >= 4
    assert any("shared mind" in t.message for t in d2.history)


def test_creative_mind_late_binds_mood_and_memory(monkeypatch):
    import ai_artist.intelligence.creative_mind as cm

    monkeypatch.setattr(cm, "_creative_mind", None)
    first = cm.get_creative_mind(mood_system=None, memory_system=None)
    mood = object()
    memory = object()
    second = cm.get_creative_mind(mood_system=mood, memory_system=memory)
    assert first is second
    assert second.mood_system is mood
    assert second.memory_system is memory


@pytest.mark.asyncio
async def test_dialogue_history_persists_across_instances(tmp_path):
    path = tmp_path / "dialogue.json"
    d1 = InnerDialogue(history_path=path)
    await d1.reflect_on_intent(
        subject="persisted thought", style="ink", mood="serene", reasoning="keep me"
    )
    assert path.exists()
    d2 = InnerDialogue(history_path=path)
    assert len(d2.history) >= 4
    assert any("persisted thought" in t.message for t in d2.history)


def test_desire_engine_persists_intensities(tmp_path, monkeypatch):
    from ai_artist.intelligence import desire_engine as de
    from ai_artist.personality import continuity as cont

    path = tmp_path / "desires.json"
    monkeypatch.setattr(cont, "DESIRES_FILE", path)
    monkeypatch.setattr(de, "_desire_engine", None)

    engine = de.DesireEngine()
    engine.drives["novelty"].intensity = 0.77
    engine.save(path)
    engine2 = de.DesireEngine()
    engine2.load(path)
    assert engine2.drives["novelty"].intensity == pytest.approx(0.77, abs=0.01)


def test_should_pair_soundtrack_respects_explicit():
    from ai_artist.personality.continuity import should_pair_soundtrack

    assert should_pair_soundtrack(mood="serene", explicit=True) is True


def test_seed_subject_honored_in_fallback(monkeypatch):
    from ai_artist.intelligence.creative_mind import CreativeMind

    mind = CreativeMind(mood_system=None, memory_system=None, learner=None)
    intent = mind._fallback_decide(
        {"seed_subject": "moonlit pier", "seed_style": "ink wash"}
    )
    assert intent.subject == "moonlit pier"
    assert intent.style == "ink wash"
