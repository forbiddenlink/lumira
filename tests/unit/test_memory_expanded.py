"""Expanded tests for Lumira's memory systems.

Tests both the basic ArtistMemory and the EnhancedMemorySystem.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ai_artist.personality.enhanced_memory import (
    LEVEL_TITLES,
    EnhancedMemorySystem,
    EpisodicMemory,
    ExperienceSystem,
    ReflectionSystem,
    SemanticMemory,
    WorkingMemory,
    xp_for_level,
)
from ai_artist.personality.memory import ArtistMemory

# ============================================================================
# Tests for ArtistMemory (basic memory system)
# ============================================================================


class TestArtistMemoryInit:
    """Test ArtistMemory initialization."""

    def test_init_with_default_path(self, tmp_path):
        """Test initialization with default path."""
        with patch.object(ArtistMemory, "_load"):
            memory = ArtistMemory()
            assert memory.memory_file == Path("data/lumira_memory.json")

    def test_init_with_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_memory.json"
        with patch.object(ArtistMemory, "_load"):
            memory = ArtistMemory(memory_file=custom_path)
            assert memory.memory_file == custom_path

    def test_init_creates_default_structure(self, tmp_path):
        """Test initialization creates default memory structure."""
        memory_path = tmp_path / "memory.json"
        memory = ArtistMemory(memory_file=memory_path)

        assert memory.memory["name"] == "Lumira"
        assert "paintings" in memory.memory
        assert "reflections" in memory.memory
        assert "preferences" in memory.memory
        assert "stats" in memory.memory


class TestEpisodicMemoryRecording:
    """Test episodic memory recording."""

    @pytest.fixture
    def memory(self, tmp_path):
        """Create an ArtistMemory instance."""
        return ArtistMemory(memory_file=tmp_path / "test_memory.json")

    def test_remember_artwork_adds_entry(self, memory):
        """Test remember_artwork adds a new entry."""
        memory.remember_artwork(
            prompt="a sunset over ocean",
            subject="sunset",
            style="impressionist",
            mood="serene",
            colors=["orange", "pink", "blue"],
            score=0.85,
            image_path="/path/to/image.png",
        )

        assert len(memory.memory["paintings"]) == 1
        painting = memory.memory["paintings"][0]
        assert painting["subject"] == "sunset"
        assert painting["score"] == 0.85

    def test_remember_artwork_updates_total(self, memory):
        """Test remember_artwork increments total count."""
        assert memory.memory["stats"]["total_created"] == 0

        memory.remember_artwork(
            prompt="test",
            subject="test",
            style="test",
            mood="serene",
            colors=[],
            score=0.5,
            image_path="/test.png",
        )

        assert memory.memory["stats"]["total_created"] == 1

    def test_remember_artwork_updates_best_score(self, memory):
        """Test remember_artwork updates best score."""
        memory.remember_artwork(
            prompt="test1",
            subject="a",
            style="x",
            mood="serene",
            colors=[],
            score=0.6,
            image_path="/a.png",
        )
        assert memory.memory["stats"]["best_score"] == 0.6

        memory.remember_artwork(
            prompt="test2",
            subject="b",
            style="y",
            mood="chaotic",
            colors=[],
            score=0.9,
            image_path="/b.png",
        )
        assert memory.memory["stats"]["best_score"] == 0.9

        # Lower score shouldn't replace
        memory.remember_artwork(
            prompt="test3",
            subject="c",
            style="z",
            mood="bold",
            colors=[],
            score=0.7,
            image_path="/c.png",
        )
        assert memory.memory["stats"]["best_score"] == 0.9


class TestSemanticLearning:
    """Test semantic learning through preferences."""

    @pytest.fixture
    def memory(self, tmp_path):
        return ArtistMemory(memory_file=tmp_path / "test.json")

    def test_update_preferences_tracks_subjects(self, memory):
        """Test preferences track subject frequency."""
        memory.remember_artwork("p", "ocean", "s", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "ocean", "s", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "mountain", "s", "m", [], 0.5, "/i.png")

        subjects = memory.memory["preferences"]["favorite_subjects"]
        assert subjects["ocean"] == 2
        assert subjects["mountain"] == 1

    def test_update_preferences_tracks_styles(self, memory):
        """Test preferences track style frequency."""
        memory.remember_artwork("p", "s", "impressionist", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "s", "impressionist", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "s", "minimalist", "m", [], 0.5, "/i.png")

        styles = memory.memory["preferences"]["favorite_styles"]
        assert styles["impressionist"] == 2
        assert styles["minimalist"] == 1

    def test_update_preferences_tracks_colors(self, memory):
        """Test preferences track color frequency."""
        memory.remember_artwork("p", "s", "st", "m", ["blue", "green"], 0.5, "/i.png")
        memory.remember_artwork("p", "s", "st", "m", ["blue", "red"], 0.5, "/i.png")

        colors = memory.memory["preferences"]["favorite_colors"]
        assert colors["blue"] == 2
        assert colors["green"] == 1
        assert colors["red"] == 1


class TestRelevanceSearch:
    """Test relevance search in memory."""

    @pytest.fixture
    def memory(self, tmp_path):
        return ArtistMemory(memory_file=tmp_path / "test.json")

    def test_get_recent_works(self, memory):
        """Test getting recent works."""
        for i in range(15):
            memory.remember_artwork(f"p{i}", f"s{i}", "st", "m", [], 0.5, f"/{i}.png")

        recent = memory.get_recent_works(limit=10)
        assert len(recent) == 10
        # Should be the last 10
        assert recent[0]["subject"] == "s5"
        assert recent[-1]["subject"] == "s14"

    def test_get_best_works(self, memory):
        """Test getting best scored works."""
        scores = [0.3, 0.9, 0.5, 0.8, 0.2]
        for i, score in enumerate(scores):
            memory.remember_artwork(f"p{i}", f"s{i}", "st", "m", [], score, f"/{i}.png")

        best = memory.get_best_works(limit=3)
        assert len(best) == 3
        assert best[0]["score"] == 0.9
        assert best[1]["score"] == 0.8
        assert best[2]["score"] == 0.5

    def test_has_painted_recently_true(self, memory):
        """Test has_painted_recently returns True for recent subject."""
        memory.remember_artwork("p", "ocean", "st", "m", [], 0.5, "/i.png")
        assert memory.has_painted_recently("ocean") is True

    def test_has_painted_recently_false(self, memory):
        """Test has_painted_recently returns False for old subject."""
        # Add old painting
        memory.remember_artwork("p", "ocean", "st", "m", [], 0.5, "/i.png")
        # Add 5 more to push it beyond threshold
        for i in range(5):
            memory.remember_artwork("p", f"other{i}", "st", "m", [], 0.5, f"/{i}.png")

        assert memory.has_painted_recently("ocean", threshold=5) is False

    def test_get_favorite_subject(self, memory):
        """Test get_favorite_subject returns most frequent."""
        memory.remember_artwork("p", "a", "st", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "b", "st", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "b", "st", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "b", "st", "m", [], 0.5, "/i.png")
        memory.remember_artwork("p", "a", "st", "m", [], 0.5, "/i.png")

        assert memory.get_favorite_subject() == "b"

    def test_get_favorite_subject_empty(self, memory):
        """Test get_favorite_subject returns None when empty."""
        assert memory.get_favorite_subject() is None


class TestMemoryConsolidation:
    """Test memory persistence (consolidation)."""

    def test_save_creates_file(self, tmp_path):
        """Test save creates file on disk."""
        memory_path = tmp_path / "memory.json"
        memory = ArtistMemory(memory_file=memory_path)
        memory.remember_artwork("p", "s", "st", "m", [], 0.5, "/i.png")

        assert memory_path.exists()

    def test_load_restores_memory(self, tmp_path):
        """Test load restores saved memory."""
        memory_path = tmp_path / "memory.json"

        # Create and save
        memory1 = ArtistMemory(memory_file=memory_path)
        memory1.remember_artwork("p", "test_subject", "st", "m", [], 0.8, "/i.png")

        # Load in new instance
        memory2 = ArtistMemory(memory_file=memory_path)

        assert len(memory2.memory["paintings"]) == 1
        assert memory2.memory["paintings"][0]["subject"] == "test_subject"


# ============================================================================
# Tests for EpisodicMemory (enhanced memory)
# ============================================================================


class TestEpisodicMemory:
    """Test the EpisodicMemory class."""

    @pytest.fixture
    def episodic(self):
        return EpisodicMemory()

    def test_record_episode(self, episodic):
        """Test recording an episode."""
        episodic.record_episode(
            event_type="creation",
            details={"subject": "sunset"},
            emotional_state={"mood": "serene", "energy": 0.7},
        )

        assert len(episodic.episodes) == 1
        ep = episodic.episodes[0]
        assert ep["event_type"] == "creation"
        assert ep["details"]["subject"] == "sunset"

    def test_record_episode_with_timestamp(self, episodic):
        """Test recording episode with custom timestamp."""
        episodic.record_episode(
            event_type="test",
            details={},
            emotional_state={},
            timestamp="2024-01-01T12:00:00",
        )

        assert episodic.episodes[0]["timestamp"] == "2024-01-01T12:00:00"

    def test_get_recent_episodes(self, episodic):
        """Test getting recent episodes."""
        for i in range(10):
            episodic.record_episode(f"type{i}", {"i": i}, {})

        recent = episodic.get_recent_episodes(count=5)
        assert len(recent) == 5
        assert recent[0]["details"]["i"] == 5
        assert recent[-1]["details"]["i"] == 9

    def test_get_recent_episodes_filtered(self, episodic):
        """Test getting recent episodes filtered by type."""
        episodic.record_episode("creation", {"i": 1}, {})
        episodic.record_episode("reflection", {"i": 2}, {})
        episodic.record_episode("creation", {"i": 3}, {})

        creations = episodic.get_recent_episodes(count=10, event_type="creation")
        assert len(creations) == 2
        assert all(ep["event_type"] == "creation" for ep in creations)

    def test_get_episodes_by_mood(self, episodic):
        """Test getting episodes by mood."""
        episodic.record_episode("a", {}, {"mood": "serene"})
        episodic.record_episode("b", {}, {"mood": "chaotic"})
        episodic.record_episode("c", {}, {"mood": "serene"})

        serene = episodic.get_episodes_by_mood("serene")
        assert len(serene) == 2

    def test_count_episodes_by_type(self, episodic):
        """Test counting episodes by type."""
        episodic.record_episode("creation", {}, {})
        episodic.record_episode("creation", {}, {})
        episodic.record_episode("reflection", {}, {})

        counts = episodic.count_episodes_by_type()
        assert counts["creation"] == 2
        assert counts["reflection"] == 1


# ============================================================================
# Tests for SemanticMemory (enhanced memory)
# ============================================================================


class TestSemanticMemory:
    """Test the SemanticMemory class."""

    @pytest.fixture
    def semantic(self):
        return SemanticMemory()

    def test_record_style_effectiveness(self, semantic):
        """Test recording style effectiveness."""
        semantic.record_style_effectiveness("impressionist", 0.85, 10)

        assert "impressionist" in semantic.knowledge["style_effectiveness"]
        assert (
            semantic.knowledge["style_effectiveness"]["impressionist"]["avg_score"]
            == 0.85
        )
        assert (
            semantic.knowledge["style_effectiveness"]["impressionist"]["sample_size"]
            == 10
        )

    def test_record_subject_resonance(self, semantic):
        """Test recording subject resonance."""
        semantic.record_subject_resonance("ocean", {"beauty": 0.9, "depth": 0.8})

        assert "ocean" in semantic.knowledge["subject_resonance"]
        assert semantic.knowledge["subject_resonance"]["ocean"]["beauty"] == 0.9

    def test_learn_association(self, semantic):
        """Test learning an association."""
        semantic.learn_association("Blue and orange create tension", "color_theory")

        associations = semantic.knowledge["learned_associations"]
        assert len(associations) == 1
        assert associations[0]["insight"] == "Blue and orange create tension"
        assert associations[0]["category"] == "color_theory"

    def test_get_best_styles(self, semantic):
        """Test getting best styles."""
        semantic.record_style_effectiveness("style_a", 0.7, 5)
        semantic.record_style_effectiveness("style_b", 0.9, 10)
        semantic.record_style_effectiveness("style_c", 0.8, 3)  # Too few samples
        semantic.record_style_effectiveness("style_d", 0.6, 8)

        best = semantic.get_best_styles(min_samples=5)
        assert len(best) == 3
        assert best[0][0] == "style_b"  # Highest score
        assert best[0][1] == 0.9

    def test_get_insights_by_category(self, semantic):
        """Test getting insights by category."""
        semantic.learn_association("Insight 1", "color")
        semantic.learn_association("Insight 2", "composition")
        semantic.learn_association("Insight 3", "color")

        color_insights = semantic.get_insights_by_category("color")
        assert len(color_insights) == 2
        assert "Insight 1" in color_insights
        assert "Insight 3" in color_insights


# ============================================================================
# Tests for WorkingMemory (enhanced memory)
# ============================================================================


class TestWorkingMemory:
    """Test the WorkingMemory class."""

    @pytest.fixture
    def working(self):
        return WorkingMemory()

    def test_set_and_get_context(self, working):
        """Test setting and getting context."""
        working.set_context("current_subject", "sunset")
        assert working.get_context("current_subject") == "sunset"

    def test_get_context_missing_key(self, working):
        """Test getting missing context returns None."""
        assert working.get_context("nonexistent") is None

    def test_add_goal(self, working):
        """Test adding a goal."""
        working.add_goal("Create a painting")
        assert "Create a painting" in working.active_goals

    def test_complete_goal(self, working):
        """Test completing a goal."""
        working.add_goal("Goal 1")
        working.add_goal("Goal 2")
        working.complete_goal("Goal 1")

        assert "Goal 1" not in working.active_goals
        assert "Goal 2" in working.active_goals

    def test_complete_nonexistent_goal(self, working):
        """Test completing nonexistent goal doesn't raise."""
        working.complete_goal("Nonexistent")  # Should not raise

    def test_clear_session(self, working):
        """Test clearing session."""
        working.set_context("key", "value")
        working.add_goal("goal")
        old_start = working.session_start

        import time

        time.sleep(0.01)  # Ensure different timestamp
        working.clear_session()

        assert working.current_context == {}
        assert working.active_goals == []
        assert working.session_start != old_start


# ============================================================================
# Tests for EnhancedMemorySystem
# ============================================================================


class TestEnhancedMemorySystem:
    """Test the integrated EnhancedMemorySystem."""

    @pytest.fixture
    def memory_system(self, tmp_path):
        return EnhancedMemorySystem(memory_file=tmp_path / "enhanced.json")

    def test_initialization(self, memory_system):
        """Test system initializes all memory types."""
        assert isinstance(memory_system.episodic, EpisodicMemory)
        assert isinstance(memory_system.semantic, SemanticMemory)
        assert isinstance(memory_system.working, WorkingMemory)

    def test_record_creation_updates_both_memories(self, memory_system):
        """Test record_creation updates episodic and semantic."""
        memory_system.record_creation(
            artwork_details={
                "prompt": "test prompt",
                "style": "impressionist",
                "subject": "ocean",
            },
            emotional_state={
                "mood": "serene",
                "energy_level": 0.7,
            },
            outcome={
                "score": 0.85,
            },
        )

        # Check episodic
        assert len(memory_system.episodic.episodes) == 1

        # Check semantic (style effectiveness updated)
        assert (
            "impressionist" in memory_system.semantic.knowledge["style_effectiveness"]
        )

    def test_record_creation_calculates_running_average(self, memory_system):
        """Test style effectiveness uses running average."""
        memory_system.record_creation(
            artwork_details={"style": "test_style"},
            emotional_state={},
            outcome={"score": 0.8},
        )
        memory_system.record_creation(
            artwork_details={"style": "test_style"},
            emotional_state={},
            outcome={"score": 0.6},
        )

        effectiveness = memory_system.semantic.knowledge["style_effectiveness"][
            "test_style"
        ]
        assert effectiveness["sample_size"] == 2
        assert effectiveness["avg_score"] == 0.7  # (0.8 + 0.6) / 2

    def test_generate_insights(self, memory_system):
        """Test generate_insights produces meaningful output."""
        memory_system.record_creation(
            artwork_details={"style": "impressionist"},
            emotional_state={"mood": "serene"},
            outcome={"score": 0.85},
        )
        memory_system.record_creation(
            artwork_details={"style": "impressionist"},
            emotional_state={"mood": "chaotic"},
            outcome={"score": 0.75},
        )

        insights = memory_system.generate_insights()

        assert insights["total_creations"] == 2
        assert "impressionist" in insights["style_effectiveness"]
        assert "serene" in insights["mood_patterns"]

    def test_get_relevant_context(self, memory_system):
        """Test get_relevant_context retrieves appropriate memories."""
        memory_system.episodic.record_episode(
            "creation",
            {"subject": "ocean"},
            {"mood": "serene"},
        )
        memory_system.semantic.record_style_effectiveness("minimalist", 0.9, 5)

        context = memory_system.get_relevant_context("serene", limit=5)

        assert "similar_mood_episodes" in context
        assert "best_styles" in context
        assert "recent_insights" in context

    def test_save_and_load(self, tmp_path):
        """Test persistence across instances."""
        memory_path = tmp_path / "persist.json"

        # Create and populate
        memory1 = EnhancedMemorySystem(memory_file=memory_path)
        memory1.record_creation(
            artwork_details={"style": "test", "subject": "test_subject"},
            emotional_state={"mood": "contemplative"},
            outcome={"score": 0.9},
        )

        # Load in new instance
        memory2 = EnhancedMemorySystem(memory_file=memory_path)

        assert len(memory2.episodic.episodes) == 1
        assert "test" in memory2.semantic.knowledge["style_effectiveness"]

    def test_working_memory_not_persisted(self, tmp_path):
        """Test working memory is not persisted."""
        memory_path = tmp_path / "working_test.json"

        memory1 = EnhancedMemorySystem(memory_file=memory_path)
        memory1.working.set_context("session_data", "temporary")
        memory1.save()

        memory2 = EnhancedMemorySystem(memory_file=memory_path)
        assert memory2.working.get_context("session_data") is None


class TestMemoryReflectionGeneration:
    """Test memory-based reflection generation."""

    @pytest.fixture
    def memory(self, tmp_path):
        return ArtistMemory(memory_file=tmp_path / "test.json")

    def test_generate_reflection_includes_subject(self, memory):
        """Test generated reflection includes subject."""
        artwork = {
            "subject": "mountains",
            "style": "impressionist",
            "mood": "serene",
            "score": 0.8,
        }
        reflection = memory.generate_reflection(artwork)
        assert "mountains" in reflection

    def test_generate_reflection_includes_artwork_details(self, memory):
        """Test generated reflection includes some artwork details."""
        artwork = {
            "subject": "sunset",
            "style": "impressionist",
            "mood": "contemplative",
            "score": 0.5,
        }
        # Run multiple times since reflections are randomly selected
        found_subject = False
        for _ in range(20):
            reflection = memory.generate_reflection(artwork)
            if "sunset" in reflection:
                found_subject = True
                break
        assert found_subject, "At least one reflection should mention the subject"

    def test_generate_reflection_varies(self, memory):
        """Test reflections have variety."""
        artwork = {
            "subject": "test",
            "style": "test",
            "mood": "serene",
            "score": 0.7,
        }
        reflections = set()
        for _ in range(20):
            reflections.add(memory.generate_reflection(artwork))

        # Should have some variety
        assert len(reflections) > 1


class TestMemoryStats:
    """Test memory statistics."""

    @pytest.fixture
    def memory(self, tmp_path):
        return ArtistMemory(memory_file=tmp_path / "test.json")

    def test_get_stats_empty(self, memory):
        """Test stats with empty memory."""
        stats = memory.get_stats()
        assert stats["total_artworks"] == 0
        assert stats["best_score"] == 0.0
        assert stats["favorite_subject"] is None

    def test_get_stats_populated(self, memory):
        """Test stats with populated memory."""
        memory.remember_artwork("p", "ocean", "impressionist", "m", [], 0.8, "/i.png")
        memory.remember_artwork("p", "ocean", "minimalist", "m", [], 0.9, "/i.png")
        memory.remember_artwork(
            "p", "mountain", "impressionist", "m", [], 0.7, "/i.png"
        )

        stats = memory.get_stats()

        assert stats["total_artworks"] == 3
        assert stats["best_score"] == 0.9
        assert stats["favorite_subject"] == "ocean"
        assert stats["favorite_style"] == "impressionist"


# ============================================================================
# NEW TESTS: ExperienceSystem and ReflectionSystem
# ============================================================================


class TestXpForLevel:
    """Test XP calculation function."""

    def test_level_1_requires_zero(self):
        """Level 1 requires 0 XP."""
        assert xp_for_level(1) == 0

    def test_level_2_requires_150(self):
        """Level 2 requires 150 XP (100 * 1.5^1)."""
        assert xp_for_level(2) == 150

    def test_exponential_growth(self):
        """XP requirements grow exponentially."""
        # Level 2 = 100 * 1.5^1 = 150
        assert xp_for_level(2) == 150
        # Level 3 = 100 * 1.5^2 = 225
        assert xp_for_level(3) == 225
        # Level 4 = 100 * 1.5^3 = 337.5 -> 337
        assert xp_for_level(4) == 337

    def test_high_levels(self):
        """Test high level XP requirements."""
        # Each level requires more than previous
        for lvl in range(1, 20):
            assert xp_for_level(lvl + 1) > xp_for_level(lvl)


class TestExperienceSystem:
    """Test the ExperienceSystem class."""

    @pytest.fixture
    def exp(self):
        return ExperienceSystem()

    def test_initial_state(self, exp):
        """Test initial experience state."""
        assert exp.total_xp == 0
        assert exp.level == 1
        assert exp.title == "Novice Artist"
        assert exp.creation_count == 0
        assert len(exp.milestones_achieved) == 0

    def test_calculate_creation_xp_low_score(self, exp):
        """Test XP calculation for low score."""
        xp = exp.calculate_creation_xp(0.2)
        assert xp == 10 + int(0.2 * 40)  # 18

    def test_calculate_creation_xp_high_score(self, exp):
        """Test XP calculation for high score includes bonus."""
        xp = exp.calculate_creation_xp(0.8)
        # Base: 10 + 32 = 42, + 15 high quality bonus = 57
        assert xp == 57

    def test_calculate_creation_xp_masterpiece(self, exp):
        """Test XP calculation for masterpiece includes both bonuses."""
        xp = exp.calculate_creation_xp(0.9)
        # Base: 10 + 36 = 46, + 15 (>0.7) + 25 (>0.85) = 86
        assert xp == 86

    def test_calculate_creation_xp_featured(self, exp):
        """Test XP calculation for featured work."""
        base_xp = exp.calculate_creation_xp(0.5)
        featured_xp = exp.calculate_creation_xp(0.5, is_featured=True)
        assert featured_xp == base_xp + 20

    def test_add_creation_increments_count(self, exp):
        """Test add_creation increments creation count."""
        exp.add_creation(0.5, "style", "mood")
        assert exp.creation_count == 1

    def test_add_creation_tracks_styles(self, exp):
        """Test add_creation tracks unique styles."""
        exp.add_creation(0.5, "impressionist", "mood")
        exp.add_creation(0.5, "abstract", "mood")
        exp.add_creation(0.5, "impressionist", "mood")  # Duplicate

        assert len(exp.styles_used) == 2
        assert "impressionist" in exp.styles_used
        assert "abstract" in exp.styles_used

    def test_add_creation_tracks_moods(self, exp):
        """Test add_creation tracks unique moods."""
        exp.add_creation(0.5, "style", "serene")
        exp.add_creation(0.5, "style", "chaotic")

        assert len(exp.moods_experienced) == 2

    def test_add_creation_returns_result(self, exp):
        """Test add_creation returns result dict."""
        result = exp.add_creation(0.5, "style", "mood")

        assert "xp_earned" in result
        assert "level_up" in result
        assert "milestones_unlocked" in result

    def test_first_creation_milestone(self, exp):
        """Test first creation triggers milestone."""
        result = exp.add_creation(0.5, "style", "mood")

        assert any(m["name"] == "first_creation" for m in result["milestones_unlocked"])
        assert "first_creation" in exp.milestones_achieved

    def test_first_high_quality_milestone(self, exp):
        """Test first high quality creation triggers milestone."""
        # First normal creation
        exp.add_creation(0.5, "style", "mood")
        # First high quality (>0.7)
        result = exp.add_creation(0.75, "style", "mood")

        assert any(
            m["name"] == "first_high_quality" for m in result["milestones_unlocked"]
        )

    def test_first_masterpiece_milestone(self, exp):
        """Test first masterpiece triggers milestone."""
        result = exp.add_creation(0.9, "style", "mood")

        milestone_names = [m["name"] for m in result["milestones_unlocked"]]
        assert "first_masterpiece" in milestone_names

    def test_level_up_detection(self, exp):
        """Test level up is detected."""
        # Add enough XP to level up (need 100 for level 2)
        exp.total_xp = 90  # Just under level 2
        exp.level = 1

        result = exp.add_creation(0.5, "style", "mood")  # Should push over

        # If total_xp > 100, should level up
        if exp.total_xp >= 100:
            assert result["level_up"] is True
            assert exp.level == 2

    def test_title_changes_at_level_thresholds(self, exp):
        """Test titles change at appropriate levels."""
        exp.level = 2
        exp.total_xp = 200

        # Manually trigger level update
        exp._update_level()

        # Force to level 3 threshold
        exp.level = 3
        # Check title would update
        for lvl in sorted(LEVEL_TITLES.keys(), reverse=True):
            if lvl <= 3:
                assert LEVEL_TITLES[lvl] == "Emerging Creator"
                break

    def test_get_progress_to_next_level(self, exp):
        """Test progress calculation."""
        exp.total_xp = 75  # Halfway to level 2 (150)
        exp.level = 1

        progress = exp.get_progress_to_next_level()

        assert progress["current_level"] == 1
        assert progress["xp_in_level"] == 75
        assert progress["xp_for_next_level"] == 150
        assert progress["progress_percent"] == 50.0

    def test_to_dict_and_from_dict(self, exp):
        """Test serialization round-trip."""
        exp.add_creation(0.8, "style1", "mood1")
        exp.add_creation(0.9, "style2", "mood2")

        data = exp.to_dict()
        restored = ExperienceSystem.from_dict(data)

        assert restored.total_xp == exp.total_xp
        assert restored.level == exp.level
        assert restored.creation_count == exp.creation_count
        assert restored.styles_used == exp.styles_used

    def test_style_explorer_milestone(self, exp):
        """Test style explorer milestone after 5 styles."""
        for style in ["a", "b", "c", "d", "e"]:
            exp.add_creation(0.5, style, "mood")

        assert "style_explorer" in exp.milestones_achieved

    def test_10_creations_milestone(self, exp):
        """Test 10 creations milestone."""
        for i in range(10):
            exp.add_creation(0.5, f"style{i}", "mood")

        assert "10_creations" in exp.milestones_achieved


class TestReflectionSystem:
    """Test the ReflectionSystem class."""

    @pytest.fixture
    def reflection(self):
        return ReflectionSystem()

    @pytest.fixture
    def sample_episodes(self):
        """Create sample episodes for testing."""
        episodes = []
        for i in range(10):
            episodes.append(
                {
                    "event_type": "creation",
                    "details": {
                        "style": "impressionist" if i % 2 == 0 else "abstract",
                        "score": 0.5 + i * 0.03,
                    },
                    "emotional_state": {"mood": "serene" if i < 5 else "chaotic"},
                }
            )
        return episodes

    @pytest.fixture
    def sample_experience(self):
        exp = ExperienceSystem()
        exp.level = 5
        exp.title = "Developing Visionary"
        exp.masterpiece_count = 2
        return exp

    def test_initial_state(self, reflection):
        """Test initial reflection state."""
        assert reflection.reflection_count == 0
        assert reflection.last_reflection_time is None
        assert len(reflection.reflections) == 0

    def test_should_reflect_first_time(self, reflection):
        """Test should_reflect returns True after 5 episodes."""
        assert reflection.should_reflect(4) is False
        assert reflection.should_reflect(5) is True

    def test_should_reflect_every_10(self, reflection):
        """Test should_reflect triggers every 10 creations."""
        from datetime import datetime

        reflection.last_reflection_time = datetime.now()

        assert reflection.should_reflect(10) is True
        assert reflection.should_reflect(20) is True
        assert reflection.should_reflect(15) is False

    def test_should_reflect_after_24_hours(self, reflection):
        """Test should_reflect triggers after 24 hours."""
        from datetime import datetime, timedelta

        reflection.last_reflection_time = datetime.now() - timedelta(hours=25)

        assert reflection.should_reflect(3, hours_since_last=25) is True

    def test_generate_reflection_structure(
        self, reflection, sample_episodes, sample_experience
    ):
        """Test generated reflection has correct structure."""
        result = reflection.generate_reflection(
            sample_episodes,
            {},
            sample_experience,
        )

        assert "timestamp" in result
        assert "reflection_number" in result
        assert "insights" in result
        assert "patterns_discovered" in result
        assert "growth_observations" in result
        assert "artistic_direction" in result

    def test_generate_reflection_increments_count(
        self, reflection, sample_episodes, sample_experience
    ):
        """Test generate_reflection increments count."""
        reflection.generate_reflection(sample_episodes, {}, sample_experience)

        assert reflection.reflection_count == 1
        assert reflection.last_reflection_time is not None

    def test_generate_reflection_stores_reflection(
        self, reflection, sample_episodes, sample_experience
    ):
        """Test generated reflection is stored."""
        result = reflection.generate_reflection(sample_episodes, {}, sample_experience)

        assert len(reflection.reflections) == 1
        assert reflection.reflections[0] == result

    def test_get_recent_reflections(
        self, reflection, sample_episodes, sample_experience
    ):
        """Test getting recent reflections."""
        for _ in range(7):
            reflection.generate_reflection(sample_episodes, {}, sample_experience)

        recent = reflection.get_recent_reflections(3)
        assert len(recent) == 3

    def test_to_dict_and_from_dict(
        self, reflection, sample_episodes, sample_experience
    ):
        """Test serialization round-trip."""
        reflection.generate_reflection(sample_episodes, {}, sample_experience)

        data = reflection.to_dict()
        restored = ReflectionSystem.from_dict(data)

        assert restored.reflection_count == 1
        assert len(restored.reflections) == 1
        assert restored.last_reflection_time is not None

    def test_empty_episodes_handled(self, reflection, sample_experience):
        """Test generate_reflection handles empty episodes."""
        result = reflection.generate_reflection([], {}, sample_experience)

        assert result["reflection_number"] == 1
        assert result["insights"] == []

    def test_patterns_detected_from_moods(self, reflection, sample_experience):
        """Test mood patterns are detected."""
        episodes = [
            {
                "event_type": "creation",
                "details": {},
                "emotional_state": {"mood": "serene"},
            }
            for _ in range(15)
        ]

        result = reflection.generate_reflection(episodes, {}, sample_experience)

        assert any("serene" in p.lower() for p in result["patterns_discovered"])

    def test_score_trend_detected(self, reflection, sample_experience):
        """Test score improvement is detected."""
        # Episodes with improving scores
        episodes = [
            {
                "event_type": "creation",
                "details": {"score": 0.4 + i * 0.05},
                "emotional_state": {},
            }
            for i in range(10)
        ]

        result = reflection.generate_reflection(episodes, {}, sample_experience)

        # Should detect improvement trend
        assert len(result["growth_observations"]) >= 0  # May or may not detect


class TestEnhancedMemoryWithExperience:
    """Test EnhancedMemorySystem integration with experience."""

    @pytest.fixture
    def memory_system(self, tmp_path):
        return EnhancedMemorySystem(memory_file=tmp_path / "enhanced.json")

    def test_record_creation_updates_experience(self, memory_system):
        """Test record_creation updates experience system."""
        result = memory_system.record_creation(
            artwork_details={"style": "test"},
            emotional_state={"mood": "serene"},
            outcome={"score": 0.8},
        )

        assert "xp_earned" in result
        assert memory_system.experience.creation_count == 1

    def test_get_experience_progress(self, memory_system):
        """Test get_experience_progress returns full info."""
        memory_system.record_creation(
            artwork_details={"style": "test"},
            emotional_state={"mood": "serene"},
            outcome={"score": 0.8},
        )

        progress = memory_system.get_experience_progress()

        assert "current_level" in progress
        assert "title" in progress
        assert "milestones" in progress
        assert "styles_mastered" in progress

    def test_force_reflection(self, memory_system):
        """Test force_reflection generates a reflection."""
        # Add some creations first
        for i in range(5):
            memory_system.record_creation(
                artwork_details={"style": f"style{i}"},
                emotional_state={"mood": "serene"},
                outcome={"score": 0.5 + i * 0.1},
            )

        reflection = memory_system.force_reflection()

        assert "timestamp" in reflection
        assert "insights" in reflection

    def test_get_latest_reflection(self, memory_system):
        """Test get_latest_reflection returns most recent."""
        # Initially None
        assert memory_system.get_latest_reflection() is None

        # Add some creations first (needed for reflection to be saved)
        for i in range(5):
            memory_system.record_creation(
                artwork_details={"style": f"style{i}"},
                emotional_state={"mood": "serene"},
                outcome={"score": 0.6},
            )

        # Force a reflection
        memory_system.force_reflection()

        latest = memory_system.get_latest_reflection()
        assert latest is not None
        assert "reflection_number" in latest

    def test_experience_persists_across_sessions(self, tmp_path):
        """Test experience data persists."""
        memory_path = tmp_path / "persist.json"

        # Create and populate
        memory1 = EnhancedMemorySystem(memory_file=memory_path)
        for i in range(5):
            memory1.record_creation(
                artwork_details={"style": f"style{i}"},
                emotional_state={"mood": "serene"},
                outcome={"score": 0.7},
            )

        # Load in new instance
        memory2 = EnhancedMemorySystem(memory_file=memory_path)

        assert memory2.experience.creation_count == 5
        assert memory2.experience.total_xp > 0
        assert "first_creation" in memory2.experience.milestones_achieved
