"""Tests for curator voice composition (no FalkorDB required)."""

from ai_artist.knowledge import get_knowledge_graph, index_artwork_in_knowledge_graph
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


def test_index_creation_links_neighbors_and_curator_cites_them():
    """In-memory graph: shared subject yields neighbors for curator voice."""
    graph = get_knowledge_graph()
    a = "wave4_test_a.png"
    b = "wave4_test_b.png"
    index_artwork_in_knowledge_graph(
        a,
        prompt="moonlit harbor at dusk",
        mood="serene",
        subject="harbor",
        style="ink wash",
    )
    index_artwork_in_knowledge_graph(
        b,
        prompt="quiet harbor lanterns",
        mood="serene",
        subject="harbor",
        style="watercolor",
    )
    neighbors = graph.find_similar_artworks(b, limit=5)
    assert any(n.get("id") == a for n in neighbors)
    note = compose_curator_voice(
        mood="serene",
        prompt="quiet harbor lanterns",
        artwork_id=b,
        subject="harbor",
        style="watercolor",
    )
    assert "harbor" in note.lower() or "neighbor" in note.lower() or "«" in note
