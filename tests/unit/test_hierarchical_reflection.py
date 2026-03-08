"""Tests for HierarchicalReflection system."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ai_artist.personality.hierarchical_reflection import (
    ArtistStatement,
    DailyReflection,
    HierarchicalReflection,
    MonthlyInsight,
    SessionReflection,
    WeeklySynthesis,
    generate_period_name,
)


class TestHierarchicalReflection:
    """Tests for the hierarchical reflection system."""

    @pytest.fixture
    def reflection_system(self):
        """Create a reflection system with temporary storage."""
        with TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test_reflections.json"
            yield HierarchicalReflection(storage_path=storage_path)

    def test_initialization(self, reflection_system):
        """System initializes with empty reflections."""
        assert reflection_system.reflections["session"] == []
        assert reflection_system.reflections["daily"] == []
        assert reflection_system.reflections["weekly"] == []
        assert reflection_system.reflections["monthly"] == []
        assert reflection_system.artist_statements == []

    def test_start_session(self, reflection_system):
        """start_session creates a session ID."""
        session_id = reflection_system.start_session()

        assert session_id is not None
        assert len(session_id) == 8
        assert reflection_system._current_session_id == session_id

    def test_record_session_creation(self, reflection_system):
        """record_session_creation tracks creations."""
        reflection_system.start_session()
        reflection_system.record_session_creation({"subject": "ocean", "score": 0.8})
        reflection_system.record_session_creation({"subject": "mountain", "score": 0.7})

        assert len(reflection_system._session_creations) == 2

    def test_record_session_end(self, reflection_system):
        """record_session_end creates a SessionReflection."""
        reflection_system.start_session()

        episodes = [
            {
                "emotional_state": {"mood": "serene"},
                "details": {"subject": "ocean", "score": 0.8, "style": "impressionist"},
            },
            {
                "emotional_state": {"mood": "serene"},
                "details": {"subject": "forest", "score": 0.7, "style": "watercolor"},
            },
        ]

        reflection = reflection_system.record_session_end(episodes=episodes)

        assert isinstance(reflection, SessionReflection)
        assert reflection.creations_count == 2
        assert reflection.dominant_mood == "serene"
        assert reflection.narrative  # Should have narrative text
        assert len(reflection_system.reflections["session"]) == 1

    def test_generate_daily_reflection(self, reflection_system):
        """generate_daily_reflection creates DailyReflection."""
        episodes = [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "emotional_state": {"mood": "energized"},
                "details": {"subject": "cityscape", "score": 0.75, "style": "abstract"},
            },
        ]

        reflection = reflection_system.generate_daily_reflection(episodes=episodes)

        assert isinstance(reflection, DailyReflection)
        assert reflection.date  # Should have date
        assert reflection.growth_notes
        assert reflection.tomorrow_intention
        assert len(reflection_system.reflections["daily"]) == 1

    def test_generate_weekly_synthesis(self, reflection_system):
        """generate_weekly_synthesis creates WeeklySynthesis."""
        episodes = [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "emotional_state": {"mood": "contemplative"},
                "details": {
                    "subject": "landscape",
                    "score": 0.8,
                    "style": "impressionist",
                },
            }
            for _ in range(5)
        ]

        synthesis = reflection_system.generate_weekly_synthesis(episodes=episodes)

        assert isinstance(synthesis, WeeklySynthesis)
        assert synthesis.period_name  # Should have a creative name
        assert synthesis.growth_observations
        assert synthesis.artistic_direction
        assert len(reflection_system.reflections["weekly"]) == 1

    def test_generate_monthly_insight(self, reflection_system):
        """generate_monthly_insight creates MonthlyInsight."""
        episodes = [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "emotional_state": {"mood": "introspective"},
                "details": {"subject": "portrait", "score": 0.7, "style": "realism"},
            }
            for _ in range(10)
        ]

        insight = reflection_system.generate_monthly_insight(episodes=episodes)

        assert isinstance(insight, MonthlyInsight)
        assert insight.period_name
        assert insight.identity_evolution
        assert insight.artistic_vision
        assert len(reflection_system.reflections["monthly"]) == 1

    def test_generate_artist_statement(self, reflection_system):
        """generate_artist_statement creates ArtistStatement."""
        # First create some reflections
        reflection_system.start_session()
        reflection_system.record_session_end(
            episodes=[
                {
                    "emotional_state": {"mood": "bold"},
                    "details": {"subject": "abstract", "score": 0.9},
                }
            ]
        )

        statement = reflection_system.generate_artist_statement()

        assert isinstance(statement, ArtistStatement)
        assert statement.version == 1
        assert statement.identity
        assert statement.philosophy
        assert statement.full_statement
        assert len(reflection_system.artist_statements) == 1

    def test_get_latest_artist_statement(self, reflection_system):
        """get_latest_artist_statement returns most recent."""
        # No statement yet
        assert reflection_system.get_latest_artist_statement() is None

        # Generate one
        reflection_system.generate_artist_statement()
        statement = reflection_system.get_latest_artist_statement()

        assert statement is not None
        assert statement.version == 1

    def test_persistence(self, reflection_system):
        """Reflections persist across system instances."""
        # Create some reflections
        reflection_system.start_session()
        reflection_system.record_session_end(
            episodes=[
                {
                    "emotional_state": {"mood": "serene"},
                    "details": {"subject": "ocean", "score": 0.8},
                }
            ]
        )

        reflection_system.generate_artist_statement()

        # Save and reload
        reflection_system._save_state()

        reflection_system2 = HierarchicalReflection(
            storage_path=reflection_system.storage_path
        )

        assert len(reflection_system2.reflections["session"]) == 1
        assert len(reflection_system2.artist_statements) == 1


class TestPeriodNameGeneration:
    """Tests for period name generation."""

    def test_generate_period_name_weekly(self):
        """generate_period_name creates weekly names."""
        name = generate_period_name("serene", "watercolor", is_weekly=True)

        assert name  # Should produce something
        assert isinstance(name, str)
        # Should have at least 2 words (base name + suffix or style + base name)
        assert len(name.split()) >= 2

    def test_generate_period_name_monthly(self):
        """generate_period_name creates monthly names."""
        name = generate_period_name("melancholic", "oil", is_weekly=False)

        assert name
        assert isinstance(name, str)
        # Should produce a non-empty name with words
        assert len(name.split()) >= 1
