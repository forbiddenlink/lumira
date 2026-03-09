"""Tests for vector memory."""

import pytest

from ai_artist.personality.vector_memory import VectorMemory


class TestVectorMemory:
    """Test the VectorMemory class."""

    @pytest.fixture
    def memory(self, tmp_path):
        """Create a vector memory with temporary storage."""
        return VectorMemory(persist_dir=tmp_path / "vector_memory")

    def test_initialization(self, memory):
        """Test vector memory initializes successfully."""
        assert memory is not None
        stats = memory.get_stats()
        assert stats["creations_count"] == 0
        assert stats["reflections_count"] == 0

    def test_add_creation(self, memory):
        """Test adding a creation to vector memory."""
        memory.add_creation(
            creation_id="test-001",
            prompt="A beautiful sunset over mountains",
            subject="sunset",
            style="impressionist",
            mood="serene",
            reasoning="Wanted to capture peaceful evening light",
        )

        stats = memory.get_stats()
        assert stats["creations_count"] == 1

    def test_search_creations(self, memory):
        """Test semantic search over creations."""
        # Add some creations
        memory.add_creation(
            creation_id="001",
            prompt="A beautiful sunset over mountains with golden light",
            subject="sunset",
            style="impressionist",
            mood="serene",
        )
        memory.add_creation(
            creation_id="002",
            prompt="A dark stormy sea with crashing waves",
            subject="ocean",
            style="dramatic",
            mood="chaotic",
        )
        memory.add_creation(
            creation_id="003",
            prompt="A peaceful garden with blooming flowers",
            subject="garden",
            style="watercolor",
            mood="serene",
        )

        # Search for sunset-related
        results = memory.search_creations("evening sky with warm colors")
        assert len(results) > 0
        # Sunset should be most relevant
        assert results[0]["metadata"]["subject"] == "sunset"

    def test_search_with_mood_filter(self, memory):
        """Test search with mood filter."""
        memory.add_creation(
            creation_id="001",
            prompt="Calm waters",
            subject="lake",
            style="minimal",
            mood="serene",
        )
        memory.add_creation(
            creation_id="002",
            prompt="Violent storm",
            subject="storm",
            style="dramatic",
            mood="chaotic",
        )

        # Filter by mood
        results = memory.search_creations(
            "nature scene",
            mood_filter="serene",
        )
        assert len(results) == 1
        assert results[0]["metadata"]["mood"] == "serene"

    def test_add_reflection(self, memory):
        """Test adding a reflection."""
        memory.add_reflection(
            reflection_id="ref-001",
            content="Today I explored the interplay of light and shadow.",
            reflection_type="daily",
            themes=["light", "shadow", "exploration"],
        )

        stats = memory.get_stats()
        assert stats["reflections_count"] == 1

    def test_search_reflections(self, memory):
        """Test searching reflections."""
        memory.add_reflection(
            reflection_id="ref-001",
            content="I discovered that warm colors evoke nostalgia.",
            reflection_type="daily",
            themes=["color", "emotion"],
        )
        memory.add_reflection(
            reflection_id="ref-002",
            content="Abstract forms allow for personal interpretation.",
            reflection_type="weekly",
            themes=["abstraction", "interpretation"],
        )

        results = memory.search_reflections("feelings and colors")
        assert len(results) > 0

    def test_find_similar_to_creation(self, memory):
        """Test finding similar creations."""
        memory.add_creation(
            creation_id="001",
            prompt="Mountain sunset with purple sky",
            subject="mountains",
            style="romantic",
            mood="serene",
        )
        memory.add_creation(
            creation_id="002",
            prompt="Ocean sunrise with pink clouds",
            subject="ocean",
            style="romantic",
            mood="peaceful",
        )
        memory.add_creation(
            creation_id="003",
            prompt="Dark forest with fog",
            subject="forest",
            style="gothic",
            mood="mysterious",
        )

        # Find similar to sunset
        similar = memory.find_similar_to_creation("001", n_results=2)
        assert len(similar) <= 2
        # Should not include the original
        assert all(r["id"] != "001" for r in similar)

    def test_get_mood_themes(self, memory):
        """Test getting themes for a mood."""
        memory.add_creation(
            creation_id="001",
            prompt="Calm lake",
            subject="lake",
            style="minimal",
            mood="serene",
        )
        memory.add_creation(
            creation_id="002",
            prompt="Peaceful meadow",
            subject="meadow",
            style="pastoral",
            mood="serene",
        )

        themes = memory.get_mood_themes("serene")
        assert "lake" in themes or "meadow" in themes

    def test_upsert_same_id(self, memory):
        """Test that upserting with same ID updates the entry."""
        memory.add_creation(
            creation_id="001",
            prompt="Original prompt",
            subject="original",
            style="style1",
            mood="serene",
        )

        memory.add_creation(
            creation_id="001",
            prompt="Updated prompt",
            subject="updated",
            style="style2",
            mood="chaotic",
        )

        # Should still be only 1 entry
        stats = memory.get_stats()
        assert stats["creations_count"] == 1

        # Search should find updated content
        results = memory.search_creations("Updated")
        assert len(results) > 0
        assert results[0]["metadata"]["subject"] == "updated"
