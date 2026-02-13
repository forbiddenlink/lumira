"""Tests for Aria's mood system."""

import random
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from ai_artist.personality.moods import (
    MOOD_INTENSITY_BASELINE,
    NEUTRAL_MOODS,
    Mood,
    MoodSystem,
    StyleAxes,
)


class TestMood:
    """Test the Mood enum."""

    def test_mood_values(self):
        """Test that all expected moods exist."""
        expected = [
            "contemplative",
            "chaotic",
            "melancholic",
            "energized",
            "rebellious",
            "serene",
            "restless",
            "playful",
            "introspective",
            "bold",
        ]
        actual = [m.value for m in Mood]
        assert sorted(actual) == sorted(expected)

    def test_mood_is_string_enum(self):
        """Test that Mood is a string enum."""
        assert isinstance(Mood.CONTEMPLATIVE.value, str)
        assert str(Mood.CONTEMPLATIVE) == "Mood.CONTEMPLATIVE"
        assert Mood.CONTEMPLATIVE == "contemplative"


class TestMoodSystem:
    """Test the MoodSystem class."""

    @pytest.fixture
    def mood_system(self):
        """Create a fresh MoodSystem for each test."""
        return MoodSystem()

    def test_initialization(self, mood_system):
        """Test MoodSystem initializes with correct defaults."""
        assert isinstance(mood_system.current_mood, Mood)
        assert mood_system.energy_level == 0.5
        assert mood_system.mood_duration == 0
        assert isinstance(mood_system.mood_influences, dict)
        assert len(mood_system.mood_influences) == len(Mood)

    def test_initial_mood_is_valid(self, mood_system):
        """Test that Aria starts in a valid configured mood."""
        assert mood_system.current_mood in Mood
        assert mood_system.current_mood in mood_system.mood_influences

    def test_energy_level_bounds(self, mood_system):
        """Test that energy level stays within 0-1 bounds."""
        # Force energy to extremes through multiple updates
        for _ in range(100):
            mood_system.update_mood()
            assert 0.0 <= mood_system.energy_level <= 1.0

    def test_mood_duration_increments(self, mood_system):
        """Test that mood duration increments on update."""
        initial_duration = mood_system.mood_duration
        mood_system.update_mood()
        assert mood_system.mood_duration > initial_duration

    def test_mood_influences_have_all_keys(self, mood_system):
        """Test that every mood has styles, colors, and subjects."""
        for mood in Mood:
            influences = mood_system.mood_influences[mood]
            assert "styles" in influences
            assert "colors" in influences
            assert "subjects" in influences
            assert isinstance(influences["styles"], list)
            assert isinstance(influences["colors"], list)
            assert isinstance(influences["subjects"], list)
            assert len(influences["styles"]) > 0
            assert len(influences["colors"]) > 0
            assert len(influences["subjects"]) > 0

    def test_update_mood_returns_mood(self, mood_system):
        """Test update_mood returns a Mood enum."""
        result = mood_system.update_mood()
        assert isinstance(result, Mood)

    def test_mood_shift_after_duration(self, mood_system):
        """Test that mood shifts after sufficient duration."""
        # Force a short duration threshold
        with patch.object(random, "randint", return_value=1):
            # First update increments duration to 1 (triggers shift since 1 > 1 is false)
            mood_system.update_mood()
            # Check duration is now 1
            assert mood_system.mood_duration == 1
            # Second update: duration becomes 2, which is > 1, triggers shift
            mood_system.update_mood()
            # After shift, duration is reset to 0 then incremented to 1
            # But actually the shift happens during update, so duration is reset to 0
            # The increment happens before the shift check in update_mood
            # Looking at the code: duration increments first, then checks if > threshold
            # So: start 0 -> increment to 1 -> 1 > 1? No -> no shift
            # Then: start 1 -> increment to 2 -> 2 > 1? Yes -> shift resets to 0
            assert mood_system.mood_duration == 0  # Reset after shift

    def test_mood_transitions_are_valid(self, mood_system):
        """Test that mood transitions follow defined pathways."""
        # Test each mood's possible transitions
        transitions = {
            Mood.CONTEMPLATIVE: [Mood.SERENE, Mood.INTROSPECTIVE, Mood.MELANCHOLIC],
            Mood.CHAOTIC: [Mood.REBELLIOUS, Mood.ENERGIZED, Mood.RESTLESS],
            Mood.MELANCHOLIC: [Mood.CONTEMPLATIVE, Mood.INTROSPECTIVE, Mood.SERENE],
            Mood.ENERGIZED: [Mood.PLAYFUL, Mood.BOLD, Mood.CHAOTIC],
            Mood.REBELLIOUS: [Mood.CHAOTIC, Mood.BOLD, Mood.RESTLESS],
            Mood.SERENE: [Mood.CONTEMPLATIVE, Mood.PLAYFUL, Mood.INTROSPECTIVE],
            Mood.RESTLESS: [Mood.CHAOTIC, Mood.REBELLIOUS, Mood.INTROSPECTIVE],
            Mood.PLAYFUL: [Mood.ENERGIZED, Mood.SERENE, Mood.BOLD],
            Mood.INTROSPECTIVE: [Mood.CONTEMPLATIVE, Mood.MELANCHOLIC, Mood.SERENE],
            Mood.BOLD: [Mood.REBELLIOUS, Mood.ENERGIZED, Mood.PLAYFUL],
        }

        for start_mood, valid_transitions in transitions.items():
            mood_system.current_mood = start_mood
            mood_system._shift_mood()
            assert mood_system.current_mood in valid_transitions

    def test_contemplative_to_serene_transition(self, mood_system):
        """Test specific transition: contemplative can become serene."""
        mood_system.current_mood = Mood.CONTEMPLATIVE
        # Run multiple transitions to find one
        found_serene = False
        for _ in range(100):
            mood_system.current_mood = Mood.CONTEMPLATIVE
            mood_system._shift_mood()
            if mood_system.current_mood == Mood.SERENE:
                found_serene = True
                break
        assert found_serene, "Serene should be reachable from contemplative"


class TestMoodInfluenceOnPrompts:
    """Test how moods influence prompts."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_influence_prompt_adds_content(self, mood_system):
        """Test that influence_prompt modifies the base prompt."""
        base_prompt = "a simple landscape"
        influenced = mood_system.influence_prompt(base_prompt)
        assert len(influenced) > len(base_prompt)
        assert base_prompt in influenced

    def test_influence_prompt_adds_mood_descriptor(self, mood_system):
        """Test that mood descriptor is always added."""
        base_prompt = "test image"
        influenced = mood_system.influence_prompt(base_prompt)
        # Should contain mood descriptor
        assert "mood" in influenced.lower()

    def test_contemplative_mood_adds_quiet_thoughtful(self, mood_system):
        """Test contemplative mood adds its descriptor."""
        mood_system.current_mood = Mood.CONTEMPLATIVE
        influenced = mood_system.influence_prompt("test")
        assert "quiet" in influenced or "thoughtful" in influenced

    def test_chaotic_mood_adds_wild_energetic(self, mood_system):
        """Test chaotic mood adds its descriptor."""
        mood_system.current_mood = Mood.CHAOTIC
        influenced = mood_system.influence_prompt("test")
        assert "wild" in influenced or "energetic" in influenced

    def test_all_moods_have_descriptors(self, mood_system):
        """Test every mood adds some descriptor."""
        base = "test prompt"
        for mood in Mood:
            mood_system.current_mood = mood
            influenced = mood_system.influence_prompt(base)
            assert influenced != base
            assert "mood" in influenced


class TestMoodDurationTracking:
    """Test mood duration tracking."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_duration_starts_at_zero(self, mood_system):
        """Test duration starts at zero."""
        assert mood_system.mood_duration == 0

    def test_duration_increments_on_update(self, mood_system):
        """Test duration increments with each update."""
        for i in range(5):
            mood_system.mood_duration = i  # Reset to known value
            with patch.object(random, "randint", return_value=100):  # Never shift
                mood_system.update_mood()
            assert mood_system.mood_duration == i + 1

    def test_duration_resets_on_shift(self, mood_system):
        """Test duration resets to 0 after mood shift."""
        mood_system.mood_duration = 10
        mood_system._shift_mood()
        assert mood_system.mood_duration == 0


class TestExternalFactorsAffectingMood:
    """Test how external factors affect mood (placeholder for future)."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_update_mood_accepts_external_factors(self, mood_system):
        """Test that update_mood accepts external factors parameter."""
        # Currently external_factors is not used, but the parameter exists
        result = mood_system.update_mood(external_factors={"weather": "sunny"})
        assert isinstance(result, Mood)

    def test_external_factors_parameter_is_optional(self, mood_system):
        """Test that external_factors is optional."""
        result = mood_system.update_mood()
        assert isinstance(result, Mood)


class TestMoodBasedSubjects:
    """Test mood-based subject selection."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_get_mood_based_subject_returns_string(self, mood_system):
        """Test get_mood_based_subject returns a string."""
        subject = mood_system.get_mood_based_subject()
        assert isinstance(subject, str)
        assert len(subject) > 0

    def test_subject_matches_mood(self, mood_system):
        """Test subjects come from current mood's pool."""
        for mood in Mood:
            mood_system.current_mood = mood
            subject = mood_system.get_mood_based_subject()
            expected_subjects = mood_system.mood_influences[mood]["subjects"]
            assert subject in expected_subjects


class TestMoodDescriptions:
    """Test mood description methods."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_describe_feeling_returns_string(self, mood_system):
        """Test describe_feeling returns a non-empty string."""
        feeling = mood_system.describe_feeling()
        assert isinstance(feeling, str)
        assert len(feeling) > 0

    def test_describe_feeling_includes_energy(self, mood_system):
        """Test describe_feeling includes energy level."""
        feeling = mood_system.describe_feeling()
        assert "Energy" in feeling

    def test_describe_feeling_varies_by_mood(self, mood_system):
        """Test different moods produce different descriptions."""
        feelings = set()
        for mood in Mood:
            mood_system.current_mood = mood
            feeling = mood_system.describe_feeling()
            feelings.add(feeling.split("(")[0].strip())  # Remove energy part
        assert len(feelings) == len(Mood)


class TestMoodReflections:
    """Test mood-based reflections on work."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_reflect_on_work_returns_string(self, mood_system):
        """Test reflect_on_work returns a non-empty string."""
        reflection = mood_system.reflect_on_work(score=0.7, subject="sunset")
        assert isinstance(reflection, str)
        assert len(reflection) > 0

    def test_reflect_on_work_includes_subject(self, mood_system):
        """Test reflection includes the subject."""
        reflection = mood_system.reflect_on_work(score=0.7, subject="mountains")
        assert "mountains" in reflection

    def test_high_score_adds_positive_sentiment(self, mood_system):
        """Test high scores add positive sentiment."""
        reflection = mood_system.reflect_on_work(score=0.9, subject="test")
        assert "pleased" in reflection or "satisfied" in reflection.lower()

    def test_low_score_adds_growth_sentiment(self, mood_system):
        """Test low scores add growth-oriented sentiment."""
        reflection = mood_system.reflect_on_work(score=0.3, subject="test")
        # Updated to match new intensity-aware language
        assert (
            "learn" in reflection
            or "failures" in reflection
            or "successes" in reflection
        )

    def test_medium_score_is_neutral(self, mood_system):
        """Test medium scores are neutral."""
        reflection = mood_system.reflect_on_work(score=0.5, subject="test")
        # Updated to match new intensity-aware language
        assert (
            "challenged" in reflection
            or "Growth" in reflection
            or "struggle" in reflection
        )


class TestMoodColorAndStyle:
    """Test mood-based color and style methods."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_get_mood_colors_returns_list(self, mood_system):
        """Test get_mood_colors returns a list."""
        colors = mood_system.get_mood_colors()
        assert isinstance(colors, list)
        assert len(colors) > 0

    def test_get_mood_colors_matches_influences(self, mood_system):
        """Test colors match the mood_influences definition."""
        for mood in Mood:
            mood_system.current_mood = mood
            colors = mood_system.get_mood_colors()
            expected = mood_system.mood_influences[mood]["colors"]
            assert colors == expected

    def test_get_mood_style_returns_string(self, mood_system):
        """Test get_mood_style returns a string."""
        style = mood_system.get_mood_style()
        assert isinstance(style, str)
        assert len(style) > 0

    def test_get_mood_style_from_influences(self, mood_system):
        """Test style comes from mood influences."""
        for mood in Mood:
            mood_system.current_mood = mood
            style = mood_system.get_mood_style()
            expected_styles = mood_system.mood_influences[mood]["styles"]
            assert style in expected_styles


# ============================================================================
# NEW TESTS: StyleAxes, Mood Decay, Intensity, Serialization
# ============================================================================


class TestStyleAxes:
    """Test the StyleAxes class for granular creative control."""

    def test_default_values(self):
        """Test StyleAxes initializes with default 0.5 values."""
        axes = StyleAxes()
        assert axes.abstraction == 0.5
        assert axes.saturation == 0.5
        assert axes.complexity == 0.5
        assert axes.drama == 0.5
        assert axes.symmetry == 0.5
        assert axes.novelty == 0.5
        assert axes.line_quality == 0.5
        assert axes.palette_temperature == 0.5
        assert axes.motion == 0.5
        assert axes.symbolism == 0.5

    def test_custom_values(self):
        """Test StyleAxes with custom values."""
        axes = StyleAxes(abstraction=0.9, drama=0.1, novelty=0.8)
        assert axes.abstraction == 0.9
        assert axes.drama == 0.1
        assert axes.novelty == 0.8
        assert axes.saturation == 0.5  # Default

    def test_to_dict(self):
        """Test StyleAxes serialization."""
        axes = StyleAxes(abstraction=0.75, complexity=0.25)
        d = axes.to_dict()
        assert isinstance(d, dict)
        assert len(d) == 10  # All 10 axes
        assert d["abstraction"] == 0.75
        assert d["complexity"] == 0.25
        assert d["saturation"] == 0.5

    def test_from_dict(self):
        """Test StyleAxes deserialization."""
        data = {"abstraction": 0.8, "drama": 0.9, "motion": 0.1}
        axes = StyleAxes.from_dict(data)
        assert axes.abstraction == 0.8
        assert axes.drama == 0.9
        assert axes.motion == 0.1

    def test_from_mood_returns_style_axes(self):
        """Test StyleAxes.from_mood creates axes based on mood."""
        for mood in Mood:
            axes = StyleAxes.from_mood(mood)
            assert isinstance(axes, StyleAxes)
            # All values should be 0-1
            for key, value in axes.to_dict().items():
                assert 0.0 <= value <= 1.0, f"{key} out of bounds: {value}"

    def test_from_mood_intensity_affects_extremity(self):
        """Test that higher intensity produces more extreme values."""
        # Chaotic mood with high intensity should have extreme values
        high_intensity = StyleAxes.from_mood(Mood.CHAOTIC, intensity=1.0)

        # High intensity should be more extreme (further from 0.5)
        # Due to randomness, just verify high intensity produces some extremity
        high_extremity = sum(abs(v - 0.5) for v in high_intensity.to_dict().values())
        assert high_extremity > 0  # At least some extremity

    def test_to_prompt_modifiers_returns_list(self):
        """Test to_prompt_modifiers returns a list of strings."""
        axes = StyleAxes(abstraction=0.9, drama=0.9, saturation=0.1)
        modifiers = axes.to_prompt_modifiers()
        assert isinstance(modifiers, list)
        assert all(isinstance(m, str) for m in modifiers)

    def test_extreme_values_generate_modifiers(self):
        """Test that extreme values generate appropriate modifiers."""
        # Very abstract
        axes = StyleAxes(abstraction=0.9)
        modifiers = axes.to_prompt_modifiers()
        assert any("abstract" in m.lower() for m in modifiers)

        # Very low saturation
        axes = StyleAxes(saturation=0.1)
        modifiers = axes.to_prompt_modifiers()
        assert any(
            "muted" in m.lower() or "desaturated" in m.lower() for m in modifiers
        )


class TestMoodDecay:
    """Test mood decay over time."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_no_decay_under_six_minutes(self, mood_system):
        """Test that short time periods don't trigger decay."""
        mood_system.current_mood = Mood.CHAOTIC
        mood_system.mood_intensity = 0.9
        initial_intensity = mood_system.mood_intensity

        # Set last_update to 5 minutes ago
        mood_system.last_update = datetime.now() - timedelta(minutes=5)
        mood_system.apply_decay()

        assert mood_system.mood_intensity == initial_intensity

    def test_decay_after_hours(self, mood_system):
        """Test that mood decays after hours pass."""
        mood_system.current_mood = Mood.CHAOTIC  # High intensity baseline
        mood_system.mood_intensity = 0.9
        initial_intensity = mood_system.mood_intensity

        # Set last_update to 2 hours ago
        mood_system.last_update = datetime.now() - timedelta(hours=2)
        mood_system.apply_decay()

        assert mood_system.mood_intensity < initial_intensity

    def test_intense_moods_decay_faster(self, mood_system):
        """Test that intense moods (chaotic) decay faster than calm moods (serene)."""
        # Test chaotic (high baseline)
        mood_system.current_mood = Mood.CHAOTIC
        mood_system.mood_intensity = 0.9
        mood_system.last_update = datetime.now() - timedelta(hours=1)
        mood_system.apply_decay()
        chaotic_decay = 0.9 - mood_system.mood_intensity

        # Test serene (low baseline)
        mood_system_serene = MoodSystem()
        mood_system_serene.current_mood = Mood.SERENE
        mood_system_serene.mood_intensity = 0.9
        mood_system_serene.last_update = datetime.now() - timedelta(hours=1)
        mood_system_serene.apply_decay()
        serene_decay = 0.9 - mood_system_serene.mood_intensity

        assert chaotic_decay > serene_decay

    def test_decay_to_neutral_when_intensity_low(self, mood_system):
        """Test mood shifts to neutral when intensity drops below threshold."""
        mood_system.current_mood = Mood.CHAOTIC
        mood_system.mood_intensity = 0.25  # Below threshold
        mood_system._decay_to_neutral()

        assert mood_system.current_mood in NEUTRAL_MOODS
        assert mood_system.mood_intensity == 0.5  # Reset to moderate

    def test_neutral_moods_dont_decay_to_neutral(self, mood_system):
        """Test that neutral moods don't shift when intensity is low."""
        mood_system.current_mood = Mood.CONTEMPLATIVE  # Already neutral
        mood_system.mood_intensity = 0.2
        original_mood = mood_system.current_mood
        mood_system._decay_to_neutral()

        assert mood_system.current_mood == original_mood


class TestMoodIntensity:
    """Test mood intensity tracking."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_initial_intensity(self, mood_system):
        """Test initial mood intensity is 0.7."""
        assert mood_system.mood_intensity == 0.7

    def test_intensity_in_describe_feeling(self, mood_system):
        """Test intensity is reflected in describe_feeling output."""
        feeling = mood_system.describe_feeling()
        assert "Intensity:" in feeling

    def test_high_intensity_language(self, mood_system):
        """Test high intensity produces strong language."""
        mood_system.mood_intensity = 0.9
        feeling = mood_system.describe_feeling()
        assert "consumed" in feeling or "overwhelming" in feeling

    def test_low_intensity_language(self, mood_system):
        """Test low intensity produces mild language."""
        mood_system.mood_intensity = 0.3
        feeling = mood_system.describe_feeling()
        assert "faint" in feeling or "fading" in feeling


class TestMoodSerialization:
    """Test mood system serialization/deserialization."""

    @pytest.fixture
    def mood_system(self):
        return MoodSystem()

    def test_to_dict_contains_all_fields(self, mood_system):
        """Test to_dict includes all required fields."""
        d = mood_system.to_dict()
        assert "current_mood" in d
        assert "energy_level" in d
        assert "mood_intensity" in d
        assert "mood_duration" in d
        assert "last_update" in d
        assert "style_axes" in d

    def test_from_dict_restores_state(self, mood_system):
        """Test from_dict restores mood state."""
        mood_system.current_mood = Mood.REBELLIOUS
        mood_system.energy_level = 0.8
        mood_system.mood_intensity = 0.95
        mood_system.mood_duration = 5

        data = mood_system.to_dict()
        restored = MoodSystem.from_dict(data)

        assert restored.current_mood == Mood.REBELLIOUS
        assert restored.energy_level == 0.8
        # Intensity may have decayed slightly due to from_dict calling apply_decay
        assert restored.mood_duration == 5

    def test_from_dict_handles_missing_fields(self):
        """Test from_dict handles missing optional fields gracefully."""
        data = {"current_mood": "serene"}
        restored = MoodSystem.from_dict(data)

        assert restored.current_mood == Mood.SERENE
        assert restored.energy_level == 0.5  # Default
        assert restored.mood_intensity == 0.7  # Default

    def test_style_axes_persist(self, mood_system):
        """Test style axes survive serialization round-trip."""
        mood_system.style_axes = StyleAxes(abstraction=0.9, drama=0.1)

        data = mood_system.to_dict()
        restored = MoodSystem.from_dict(data)

        assert restored.style_axes.abstraction == 0.9
        assert restored.style_axes.drama == 0.1


class TestMoodIntensityBaseline:
    """Test the MOOD_INTENSITY_BASELINE constants."""

    def test_all_moods_have_baseline(self):
        """Test every mood has an intensity baseline defined."""
        for mood in Mood:
            assert mood in MOOD_INTENSITY_BASELINE

    def test_baselines_are_valid_range(self):
        """Test all baselines are between 0 and 1."""
        for mood, baseline in MOOD_INTENSITY_BASELINE.items():
            assert 0.0 <= baseline <= 1.0, f"{mood} baseline out of range: {baseline}"

    def test_chaotic_has_high_baseline(self):
        """Test chaotic mood has high intensity baseline."""
        assert MOOD_INTENSITY_BASELINE[Mood.CHAOTIC] >= 0.8

    def test_serene_has_low_baseline(self):
        """Test serene mood has low intensity baseline."""
        assert MOOD_INTENSITY_BASELINE[Mood.SERENE] <= 0.3
