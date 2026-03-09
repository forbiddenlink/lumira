"""Tests for the NegativePromptLibrary."""

import json

import pytest

from ai_artist.utils.negative_prompts import (
    NegativePromptLibrary,
    get_negative_prompt_library,
)


class TestNegativePromptLibrary:
    """Test the NegativePromptLibrary class."""

    @pytest.fixture
    def library(self):
        """Create a library instance with default config."""
        return NegativePromptLibrary()

    @pytest.fixture
    def custom_library(self, tmp_path):
        """Create a library with custom config."""
        config = {
            "universal": {
                "quality": "blurry, low quality",
                "anatomy": "bad anatomy, deformed",
            },
            "mood_specific": {
                "serene": "chaotic, busy, cluttered",
                "chaotic": "orderly, calm, peaceful",
            },
            "style_specific": {
                "anime": "realistic, photographic",
                "realistic": "cartoon, anime, drawing",
            },
            "by_subject": {
                "portrait": "bad hands, extra fingers",
                "landscape": "people, figures, crowds",
            },
        }
        config_path = tmp_path / "negative_prompts.json"
        config_path.write_text(json.dumps(config))
        return NegativePromptLibrary(config_path=config_path)

    def test_initialization(self, library):
        """Test library initializes successfully."""
        assert library is not None
        assert library._prompts is not None

    def test_get_universal(self, library):
        """Test getting universal negative prompts."""
        universal = library.get_universal()
        assert isinstance(universal, str)
        assert len(universal) > 0

    def test_get_for_mood(self, custom_library):
        """Test getting mood-specific negative prompts."""
        serene_prompts = custom_library.get_for_mood("serene")
        assert "chaotic" in serene_prompts

        chaotic_prompts = custom_library.get_for_mood("chaotic")
        assert "orderly" in chaotic_prompts

        # Unknown mood returns empty
        unknown = custom_library.get_for_mood("unknown_mood")
        assert unknown == ""

    def test_get_for_style(self, custom_library):
        """Test getting style-specific negative prompts."""
        anime_prompts = custom_library.get_for_style("anime")
        assert "realistic" in anime_prompts

        realistic_prompts = custom_library.get_for_style("realistic")
        assert "cartoon" in realistic_prompts

    def test_get_for_subject(self, custom_library):
        """Test getting subject-specific negative prompts."""
        portrait_prompts = custom_library.get_for_subject("portrait")
        assert "bad hands" in portrait_prompts

        landscape_prompts = custom_library.get_for_subject("landscape")
        assert "people" in landscape_prompts

    def test_compose_basic(self, custom_library):
        """Test basic composition of negative prompts."""
        composed = custom_library.compose(
            base_negative="watermark, signature",
            include_universal=True,
        )
        assert "watermark" in composed
        assert "blurry" in composed  # From universal
        assert "bad anatomy" in composed  # From universal

    def test_compose_with_mood(self, custom_library):
        """Test composition with mood-specific prompts."""
        composed = custom_library.compose(
            base_negative="watermark",
            mood="serene",
            include_universal=True,
        )
        assert "watermark" in composed
        assert "chaotic" in composed  # From serene mood
        assert "blurry" in composed  # From universal

    def test_compose_with_style(self, custom_library):
        """Test composition with style-specific prompts."""
        composed = custom_library.compose(
            base_negative="text",
            style="anime",
            include_universal=False,
        )
        assert "text" in composed
        assert "realistic" in composed  # From anime style

    def test_compose_full(self, custom_library):
        """Test full composition with all parameters."""
        composed = custom_library.compose(
            base_negative="watermark",
            mood="serene",
            style="realistic",
            subject="portrait",
            include_universal=True,
        )
        # Should contain elements from all sources
        assert "watermark" in composed  # Base
        assert "blurry" in composed  # Universal
        assert "chaotic" in composed  # Mood: serene
        assert "cartoon" in composed  # Style: realistic
        assert "bad hands" in composed  # Subject: portrait

    def test_compose_deduplicates(self, custom_library):
        """Test that compose deduplicates terms."""
        composed = custom_library.compose(
            base_negative="blurry, deformed",  # Duplicates universal terms
            include_universal=True,
        )
        # Count occurrences of 'blurry'
        terms = [t.strip().lower() for t in composed.split(",")]
        blurry_count = terms.count("blurry")
        assert blurry_count == 1

    def test_compose_no_universal(self, custom_library):
        """Test composition without universal prompts."""
        composed = custom_library.compose(
            base_negative="watermark",
            include_universal=False,
        )
        assert "watermark" in composed
        assert "blurry" not in composed  # Universal excluded

    def test_defaults_when_config_missing(self, tmp_path):
        """Test that defaults are used when config file doesn't exist."""
        library = NegativePromptLibrary(config_path=tmp_path / "nonexistent.json")
        universal = library.get_universal()
        assert "blurry" in universal  # Default includes blurry

    def test_singleton_pattern(self):
        """Test that get_negative_prompt_library returns singleton."""
        lib1 = get_negative_prompt_library()
        lib2 = get_negative_prompt_library()
        assert lib1 is lib2

    def test_reload(self, tmp_path):
        """Test reloading the library from disk."""
        config_path = tmp_path / "negative_prompts.json"
        config1 = {"universal": {"quality": "blurry"}}
        config_path.write_text(json.dumps(config1))

        library = NegativePromptLibrary(config_path=config_path)
        assert "blurry" in library.get_universal()

        # Modify config
        config2 = {"universal": {"quality": "pixelated"}}
        config_path.write_text(json.dumps(config2))

        # Reload
        library.reload()
        assert "pixelated" in library.get_universal()
