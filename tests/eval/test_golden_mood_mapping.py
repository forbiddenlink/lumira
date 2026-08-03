"""Eval-regression golden set for the deterministic mood -> generation-params mapping.

Pins ``get_mood_color_palette`` / ``get_mood_style_preferences`` (pure dict
lookups, no randomness) and ``StyleAxes.from_mood`` (deterministic once
seeded) against fixed input -> expected output. No model or network calls;
runs in the fast suite.
"""

import random

from ai_artist.personality.moods import (
    Mood,
    StyleAxes,
    get_mood_color_palette,
    get_mood_style_preferences,
)


class TestMoodColorPaletteGolden:
    """get_mood_color_palette is a pure lookup -- no randomness involved."""

    def test_serene_palette_golden_case(self):
        palette = get_mood_color_palette(Mood.SERENE)

        assert palette == {
            "primary_colors": ["soft blue", "pale mint", "ivory"],
            "avoid_colors": ["neon red", "electric yellow"],
            "saturation": "low",
            "brightness": "moderate",
        }

    def test_chaotic_palette_golden_case(self):
        palette = get_mood_color_palette(Mood.CHAOTIC)

        assert palette == {
            "primary_colors": ["electric magenta", "acid green", "clashing orange"],
            "avoid_colors": ["pastel pink", "soft beige"],
            "saturation": "high",
            "brightness": "bright",
        }

    def test_palette_lookup_is_stable(self):
        """Same input yields the same output on repeated calls."""
        first = get_mood_color_palette(Mood.MELANCHOLIC)
        second = get_mood_color_palette(Mood.MELANCHOLIC)

        assert first == second


class TestMoodStylePreferencesGolden:
    """get_mood_style_preferences is a pure lookup -- no randomness involved."""

    def test_bold_style_preferences_golden_case(self):
        prefs = get_mood_style_preferences(Mood.BOLD)

        assert prefs == {
            "preferred_styles": ["heroic realism", "high contrast", "art deco"],
            "preferred_lighting": ["dramatic", "rim light", "golden"],
            "preferred_techniques": ["palette knife", "bold brushwork", "linocut"],
            "composition": "symmetric",
        }

    def test_style_preferences_lookup_is_stable(self):
        """Same input yields the same output on repeated calls."""
        first = get_mood_style_preferences(Mood.PLAYFUL)
        second = get_mood_style_preferences(Mood.PLAYFUL)

        assert first == second


class TestStyleAxesFromMoodGolden:
    """StyleAxes.from_mood adds random jitter, so pin it under a fixed seed."""

    def test_from_mood_is_stable_under_fixed_seed(self):
        """Same input + same RNG seed yields the same style axes."""
        random.seed(42)
        first = StyleAxes.from_mood(Mood.CONTEMPLATIVE, 0.7).to_dict()

        random.seed(42)
        second = StyleAxes.from_mood(Mood.CONTEMPLATIVE, 0.7).to_dict()

        assert first == second

    def test_from_mood_golden_case_under_fixed_seed(self):
        random.seed(42)

        axes = StyleAxes.from_mood(Mood.CONTEMPLATIVE, 0.7).to_dict()

        assert axes == {
            "abstraction": 0.58,
            "saturation": 0.31,
            "complexity": 0.41,
            "drama": 0.26,
            "symmetry": 0.59,
            "novelty": 0.45,
            "line_quality": 0.4,
            "palette_temperature": 0.39,
            "motion": 0.28,
            "symbolism": 0.59,
        }
