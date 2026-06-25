"""Tests for metadata normalization helpers."""

from ai_artist.utils.metadata_helpers import (
    enrich_generation_metadata,
    enrich_sidecar_metadata,
    extract_mood_from_sidecar,
    normalize_mood,
)


def test_normalize_mood_lowercase():
    assert normalize_mood("playful") == "playful"


def test_normalize_mood_uppercase_enum():
    assert normalize_mood("MELANCHOLIC") == "melancholic"


def test_normalize_mood_invalid():
    assert normalize_mood("euphoric") is None
    assert normalize_mood("") is None


def test_extract_mood_from_nested_metadata():
    sidecar = {"metadata": {"mood": "serene", "style": "watercolor"}}
    assert extract_mood_from_sidecar(sidecar) == "serene"


def test_extract_mood_from_lumira_state():
    sidecar = {"lumira_state": {"mood": "bold"}}
    assert extract_mood_from_sidecar(sidecar) == "bold"


def test_extract_mood_from_status_fallback():
    sidecar = {"status": "restless"}
    assert extract_mood_from_sidecar(sidecar) == "restless"


def test_enrich_generation_metadata_uses_status():
    result = enrich_generation_metadata({}, status="chaotic")
    assert result["mood"] == "chaotic"


def test_enrich_sidecar_metadata():
    sidecar = {
        "metadata": {"style": "abstract"},
        "lumira_state": {"mood": "introspective"},
        "reflection": "A quiet moment",
    }
    result = enrich_sidecar_metadata(sidecar)
    assert result["mood"] == "introspective"
    assert result["style"] == "abstract"
    assert result["reflection"] == "A quiet moment"
