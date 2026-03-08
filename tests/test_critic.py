"""Tests for Lumira's critique system."""

from ai_artist.personality.critic import ArtistCritic
from ai_artist.personality.moods import MoodSystem


class TestArtistCritic:
    """Test the ArtistCritic class."""

    def test_critic_initialization(self):
        """Test critic initializes with personality."""
        critic = ArtistCritic()
        assert critic.name == "Inner Critic"
        assert "strictness" in critic.personality
        assert 0 <= critic.personality["strictness"] <= 1

    def test_critic_custom_name(self):
        """Test critic with custom name."""
        critic = ArtistCritic(name="Test Critic")
        assert critic.name == "Test Critic"

    def test_critique_concept_returns_required_fields(self):
        """Test critique returns all required fields."""
        critic = ArtistCritic()
        concept = {
            "subject": "sunset",
            "mood": "serene",
            "style": "impressionist",
            "colors": ["orange", "pink"],
        }
        artist_state = {
            "mood": "serene",
            "energy": 0.7,
            "recent_subjects": [],
        }

        result = critic.critique_concept(concept, artist_state)

        assert "approved" in result
        assert "confidence" in result
        assert "critique" in result
        assert "analysis" in result
        assert isinstance(result["approved"], bool)
        assert 0 <= result["confidence"] <= 1

    def test_critique_penalizes_repeated_subjects(self):
        """Test that repeating subjects lowers novelty score."""
        critic = ArtistCritic()
        concept = {
            "subject": "ocean",
            "mood": "serene",
            "style": "minimalist",
            "colors": ["blue"],
        }

        # First with no recent subjects
        state_fresh = {"mood": "serene", "energy": 0.5, "recent_subjects": []}
        result_fresh = critic.critique_concept(concept, state_fresh)

        # Then with ocean in recent subjects
        state_repeat = {"mood": "serene", "energy": 0.5, "recent_subjects": ["ocean"]}
        result_repeat = critic.critique_concept(concept, state_repeat)

        # Novelty should be lower for repeat
        assert (
            result_repeat["analysis"]["novelty_score"]
            < result_fresh["analysis"]["novelty_score"]
        )

    def test_mood_style_alignment_scoring(self):
        """Test that matching mood-style pairs score higher."""
        critic = ArtistCritic()

        # Good pairing: serene + minimalist
        good_concept = {
            "subject": "calm lake",
            "mood": "serene",
            "style": "minimalist",
            "colors": ["blue"],
        }

        state = {"mood": "serene", "energy": 0.5, "recent_subjects": []}
        result = critic.critique_concept(good_concept, state)

        # Should have high mood alignment
        assert result["analysis"]["mood_alignment"] >= 0.5

    def test_personality_description(self):
        """Test personality description generation."""
        critic = ArtistCritic()
        description = critic.get_personality_description()

        assert isinstance(description, str)
        assert len(description) > 10

    def test_critique_handles_empty_colors(self):
        """Test critique handles missing colors gracefully."""
        critic = ArtistCritic()
        concept = {
            "subject": "abstract",
            "mood": "chaotic",
            "style": "abstract",
            "colors": [],
        }
        state = {"mood": "chaotic", "energy": 0.8, "recent_subjects": []}

        result = critic.critique_concept(concept, state)
        assert "color_harmony" in result["analysis"]


class TestMoodSystemIntegration:
    """Test MoodSystem methods used by critic."""

    def test_get_mood_style(self):
        """Test mood system provides style."""
        mood_system = MoodSystem()
        style = mood_system.get_mood_style()
        assert isinstance(style, str)
        assert len(style) > 0

    def test_get_mood_colors(self):
        """Test mood system provides colors."""
        mood_system = MoodSystem()
        colors = mood_system.get_mood_colors()
        assert isinstance(colors, list)
        assert len(colors) > 0
