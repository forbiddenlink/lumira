"""Tests for mood coupling functions — subject affinity, color palettes, style preferences."""

from __future__ import annotations

from ai_artist.personality.moods import (
    MOOD_SUBJECT_AFFINITY,
    Mood,
    get_mood_color_palette,
    get_mood_preferred_subjects,
    get_mood_style_preferences,
)


class TestMoodSubjectAffinity:
    """Test MOOD_SUBJECT_AFFINITY data structure and lookup."""

    def test_mood_subject_affinity_all_moods_covered(self):
        """MOOD_SUBJECT_AFFINITY has entries for all 10 Mood values."""
        for mood in Mood:
            assert mood in MOOD_SUBJECT_AFFINITY, f"Missing affinity for {mood.value}"
            assert len(MOOD_SUBJECT_AFFINITY[mood]) > 0

    def test_get_mood_preferred_subjects(self):
        """get_mood_preferred_subjects returns a list of strings of requested count."""
        subjects = get_mood_preferred_subjects(Mood.SERENE, count=3)
        assert isinstance(subjects, list)
        assert len(subjects) <= 3
        assert all(isinstance(s, str) for s in subjects)
        assert len(subjects) > 0

    def test_different_moods_different_subjects(self):
        """MELANCHOLIC and EUPHORIC (ENERGIZED) give different subject affinities."""
        melancholic_subjects = set(MOOD_SUBJECT_AFFINITY[Mood.MELANCHOLIC].keys())
        energized_subjects = set(MOOD_SUBJECT_AFFINITY[Mood.ENERGIZED].keys())
        # The two sets should not be identical
        assert melancholic_subjects != energized_subjects


class TestMoodColorPalette:
    """Test mood color palettes."""

    def test_get_mood_color_palette_structure(self):
        """Returned dict has primary_colors, avoid_colors, saturation, brightness."""
        palette = get_mood_color_palette(Mood.SERENE)
        assert isinstance(palette, dict)
        assert "primary_colors" in palette
        assert "avoid_colors" in palette
        assert "saturation" in palette
        assert "brightness" in palette
        assert isinstance(palette["primary_colors"], list)
        assert isinstance(palette["avoid_colors"], list)
        assert len(palette["primary_colors"]) > 0

    def test_mood_color_palette_all_moods(self):
        """Every mood has a color palette defined."""
        for mood in Mood:
            palette = get_mood_color_palette(mood)
            assert "primary_colors" in palette, f"Missing palette for {mood.value}"
            assert len(palette["primary_colors"]) > 0


class TestMoodStylePreferences:
    """Test mood style preferences."""

    def test_get_mood_style_preferences_structure(self):
        """Returned dict has preferred_styles, preferred_lighting, preferred_techniques, composition."""
        prefs = get_mood_style_preferences(Mood.BOLD)
        assert isinstance(prefs, dict)
        assert "preferred_styles" in prefs
        assert "preferred_lighting" in prefs
        assert "preferred_techniques" in prefs
        assert "composition" in prefs
        assert isinstance(prefs["preferred_styles"], list)
        assert isinstance(prefs["preferred_lighting"], list)
        assert isinstance(prefs["preferred_techniques"], list)
        assert isinstance(prefs["composition"], str)
