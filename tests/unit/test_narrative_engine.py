"""Tests for NarrativeEngine and ThematicSeries."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from ai_artist.intelligence.narrative_engine import (
    NarrativeEngine,
    ThematicSeries,
    generate_mood_arc,
    generate_series_title,
    generate_variations,
    generate_visual_threads,
)


class TestThematicSeries:
    """Tests for ThematicSeries model."""

    def test_series_creation(self):
        """ThematicSeries can be created with defaults."""
        series = ThematicSeries(
            title="Ocean Studies",
            theme="ocean",
        )

        assert series.series_id  # Auto-generated
        assert series.title == "Ocean Studies"
        assert series.theme == "ocean"
        assert series.planned_count == 5
        assert series.status == "active"
        assert len(series.completed_works) == 0

    def test_series_with_all_fields(self):
        """ThematicSeries accepts all configuration."""
        series = ThematicSeries(
            title="Mountain Studies",
            theme="mountain",
            planned_count=4,
            visual_threads=["warm tones", "layered depth"],
            variations=["different times of day", "varying perspectives"],
            mood_arc=["serene", "contemplative", "bold"],
        )

        assert series.planned_count == 4
        assert len(series.visual_threads) == 2
        assert len(series.variations) == 2
        assert len(series.mood_arc) == 3


class TestNarrativeEngine:
    """Tests for NarrativeEngine functionality."""

    @pytest.fixture
    def engine(self):
        """Create engine with temporary storage."""
        with TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test_series.json"
            yield NarrativeEngine(storage_path=storage_path)

    @pytest.fixture
    def mock_mood_system(self):
        """Create mock mood system."""
        mood = MagicMock()
        mood.current_mood.value = "serene"
        mood.mood_intensity = 0.8
        return mood

    def test_should_start_series_high_quality(self, engine):
        """High-quality creation can start a series."""
        creation = {
            "details": {
                "subject": "ocean",
                "score": 0.85,  # Above threshold
            },
            "emotional_state": {"mood": "serene"},
        }

        # Add mood system with high intensity
        engine.mood_system = MagicMock()
        engine.mood_system.mood_intensity = 0.8

        # May or may not trigger due to random chance
        result = engine.should_start_series(creation)
        assert isinstance(result, bool)

    def test_should_start_series_low_quality(self, engine):
        """Low-quality creation doesn't start series."""
        creation = {
            "details": {
                "subject": "ocean",
                "score": 0.4,  # Below threshold
            },
            "emotional_state": {"mood": "serene"},
        }

        result = engine.should_start_series(creation)
        assert result is False

    def test_should_start_series_too_many_active(self, engine):
        """Too many active series prevents new ones."""
        # Create 3 active series
        for i in range(3):
            engine.active_series.append(
                ThematicSeries(
                    title=f"Series {i}",
                    theme=f"theme{i}",
                )
            )

        creation = {
            "details": {"subject": "unique", "score": 0.9},
            "emotional_state": {"mood": "bold"},
        }

        result = engine.should_start_series(creation)
        assert result is False

    def test_create_series(self, engine):
        """create_series creates a ThematicSeries."""
        seed = {
            "id": "art123",
            "details": {"subject": "forest", "style": "impressionist", "score": 0.85},
            "emotional_state": {"mood": "contemplative"},
        }

        series = engine.create_series(seed)

        assert isinstance(series, ThematicSeries)
        assert series.theme == "forest"
        assert "art123" in series.completed_works
        assert len(series.visual_threads) > 0
        assert len(series.variations) > 0
        assert len(series.mood_arc) > 0
        assert series in engine.active_series

    def test_get_series_continuation_desire(self, engine):
        """get_series_continuation_desire returns desire for active series."""
        # Create a series with work remaining
        series = ThematicSeries(
            title="Ocean Studies",
            theme="ocean",
            planned_count=4,
            visual_threads=["blue tones"],
            variations=["different times"],
            mood_arc=["serene", "contemplative"],
        )
        series.completed_works = ["art1"]
        engine.active_series.append(series)

        desire = engine.get_series_continuation_desire()

        assert desire is not None
        assert desire.drive_name == "series_continuation"
        assert "ocean" in desire.subject_suggestion.lower()
        assert "Ocean Studies" in desire.theme
        assert desire.urgency > 0

    def test_get_series_continuation_desire_no_active(self, engine):
        """Returns None when no active series."""
        desire = engine.get_series_continuation_desire()
        assert desire is None

    def test_complete_series_work(self, engine):
        """complete_series_work records artwork in series."""
        series = ThematicSeries(
            title="Test Series",
            theme="test",
            planned_count=3,
        )
        series.completed_works = ["art1"]
        engine.active_series.append(series)

        result = engine.complete_series_work(series.series_id, "art2")

        assert result is True
        assert "art2" in series.completed_works
        assert len(series.completed_works) == 2

    def test_complete_series_work_finishes_series(self, engine):
        """Completing final work moves series to completed."""
        series = ThematicSeries(
            title="Almost Done",
            theme="test",
            planned_count=2,
        )
        series.completed_works = ["art1"]
        engine.active_series.append(series)

        engine.complete_series_work(series.series_id, "art2")

        # Series should be complete
        assert series.status == "completed"
        assert series not in engine.active_series
        assert series in engine.completed_series

    def test_abandon_series(self, engine):
        """abandon_series marks series as abandoned."""
        series = ThematicSeries(
            title="Abandoned Dreams",
            theme="test",
        )
        engine.active_series.append(series)

        result = engine.abandon_series(series.series_id)

        assert result is True
        assert series.status == "abandoned"
        assert series not in engine.active_series
        assert series in engine.completed_series

    def test_get_series_status(self, engine):
        """get_series_status returns summary."""
        series = ThematicSeries(title="Active", theme="test")
        series.completed_works = ["art1"]
        engine.active_series.append(series)

        status = engine.get_series_status()

        assert "active" in status
        assert len(status["active"]) == 1
        assert status["active"][0]["title"] == "Active"
        assert "completed_count" in status
        assert "abandoned_count" in status

    def test_persistence(self, engine):
        """Series persist across engine instances."""
        series = ThematicSeries(
            title="Persistent Series",
            theme="persistence",
        )
        engine.active_series.append(series)
        engine._save_state()

        # Load in new engine
        engine2 = NarrativeEngine(storage_path=engine.storage_path)

        assert len(engine2.active_series) == 1
        assert engine2.active_series[0].title == "Persistent Series"


class TestSeriesGeneration:
    """Tests for series generation helpers."""

    def test_generate_series_title(self):
        """generate_series_title creates evocative names."""
        title = generate_series_title("ocean", "watercolor", "serene")

        assert title
        assert isinstance(title, str)

    def test_generate_visual_threads(self):
        """generate_visual_threads creates thread list."""
        seed = {
            "details": {"subject": "mountain", "style": "impressionist"},
        }

        threads = generate_visual_threads(seed)

        assert len(threads) >= 2
        assert all(isinstance(t, str) for t in threads)

    def test_generate_variations(self):
        """generate_variations creates variation list."""
        variations = generate_variations("forest", "contemplative")

        assert len(variations) >= 3
        assert all(isinstance(v, str) for v in variations)

    def test_generate_mood_arc(self):
        """generate_mood_arc creates coherent arc."""
        arc = generate_mood_arc("serene", 5)

        assert len(arc) == 5
        assert arc[0] == "serene"
        # All should be valid mood names
        valid_moods = {
            "serene",
            "melancholic",
            "energized",
            "chaotic",
            "contemplative",
            "playful",
            "bold",
            "rebellious",
            "restless",
            "introspective",
        }
        assert all(m in valid_moods for m in arc)
