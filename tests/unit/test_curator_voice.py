"""Tests for curator voice composition (no FalkorDB required)."""

from ai_artist.personality.curator_voice import (
    compose_curator_voice,
    curator_voice_payload,
)


def test_compose_curator_voice_mood_style_fallback():
    note = compose_curator_voice(mood="serene", style="ink wash")
    assert "serene" in note.lower()
    assert "ink wash" in note.lower()


def test_compose_curator_voice_minimal_fallback():
    note = compose_curator_voice()
    assert isinstance(note, str)
    assert len(note) > 20


def test_curator_voice_payload_shape():
    payload = curator_voice_payload(mood="bold", prompt="a crimson city")
    assert "curator_note" in payload
    assert payload["mood"] == "bold"
    assert payload["curator_note"]
