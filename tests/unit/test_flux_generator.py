"""Tests for FLUX image generator."""

from unittest.mock import MagicMock, patch

import pytest
import torch
from PIL import Image

from ai_artist.core.flux_generator import (
    FLUX_DEV,
    FLUX_SCHNELL,
    FluxGenerator,
    get_flux_model_for_mood,
)


class TestFluxGenerator:
    """Test FluxGenerator class."""

    def test_init_schnell(self):
        """Test generator initialization with schnell model."""
        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )
        assert generator.model_id == FLUX_SCHNELL
        assert generator.device == "cpu"
        assert generator.dtype == torch.float32
        assert generator.pipeline is None
        assert generator.is_schnell is True
        assert generator.is_dev is False
        assert generator.config["default_steps"] == 4
        assert generator.config["uses_guidance"] is False

    def test_init_dev(self):
        """Test generator initialization with dev model."""
        generator = FluxGenerator(
            model_id=FLUX_DEV,
            device="cpu",
            dtype=torch.float32,
        )
        assert generator.model_id == FLUX_DEV
        assert generator.is_schnell is False
        assert generator.is_dev is True
        assert generator.config["default_steps"] == 50
        assert generator.config["uses_guidance"] is True

    def test_init_unknown_model_defaults_to_schnell(self):
        """Test that unknown model ID defaults to schnell."""
        generator = FluxGenerator(
            model_id="unknown/model",
            device="cpu",
            dtype=torch.float32,
        )
        # Should default to schnell
        assert generator.model_id == FLUX_SCHNELL
        assert generator.config["default_steps"] == 4

    def test_context_manager(self):
        """Test context manager usage."""
        with FluxGenerator(device="cpu", dtype=torch.float32) as generator:
            assert generator is not None
            assert generator.pipeline is None

    def test_init_with_8bit(self):
        """Test initialization with 8-bit quantization flag."""
        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cuda",
            dtype=torch.float16,
            use_8bit=True,
        )
        assert generator.use_8bit is True


class TestFluxPromptEnhancement:
    """Test FLUX prompt enhancement."""

    def test_short_descriptive_prompt_unchanged(self):
        """Test that short descriptive prompts are returned as-is."""
        generator = FluxGenerator(device="cpu", dtype=torch.float32)

        prompt = "A serene mountain landscape at sunrise"
        result = generator.enhance_prompt_for_flux(prompt)

        # Short prompts without many commas should be unchanged
        assert result == prompt

    def test_long_natural_prompt_unchanged(self):
        """Test that long natural language prompts are unchanged."""
        generator = FluxGenerator(device="cpu", dtype=torch.float32)

        prompt = (
            "A detailed photograph of an ancient oak tree standing alone in a misty meadow. "
            "The morning light filters through the fog creating ethereal rays. "
            "Dew drops glisten on the grass and wildflowers surround the base of the tree."
        )
        result = generator.enhance_prompt_for_flux(prompt)

        assert result == prompt

    def test_keyword_style_prompt_enhanced(self):
        """Test that keyword-style prompts are enhanced."""
        generator = FluxGenerator(device="cpu", dtype=torch.float32)

        prompt = "mountain, sunset, dramatic lighting, oil painting style, 8k, detailed"
        result = generator.enhance_prompt_for_flux(prompt)

        # Should be converted to more natural language
        assert "mountain" in result.lower()
        assert len(result) > len(prompt) or result != prompt

    def test_mixed_prompt_handling(self):
        """Test prompts with some commas but not heavily keyword-style."""
        generator = FluxGenerator(device="cpu", dtype=torch.float32)

        prompt = "A peaceful garden, soft morning light"
        result = generator.enhance_prompt_for_flux(prompt)

        # Only 1 comma, should be unchanged
        assert result == prompt


class TestFluxGeneration:
    """Test FLUX generation (with mocked pipeline)."""

    @pytest.fixture
    def mock_flux_pipeline(self):
        """Mock FluxPipeline."""
        # Patch at the diffusers level since it's imported inside load_model()
        with patch("diffusers.FluxPipeline") as mock_class:
            pipeline = MagicMock()
            pipeline.to.return_value = pipeline
            pipeline.enable_attention_slicing.return_value = None
            pipeline.enable_vae_slicing.return_value = None

            # Create mock result with images
            import numpy as np

            noise = np.random.randint(50, 200, (512, 512, 3), dtype=np.uint8)
            mock_image = Image.fromarray(noise, mode="RGB")
            mock_result = MagicMock()
            mock_result.images = [mock_image]
            pipeline.return_value = mock_result

            mock_class.from_pretrained.return_value = pipeline
            yield mock_class, pipeline

    def test_load_model(self, mock_flux_pipeline):
        """Test FLUX model loading."""
        mock_class, mock_instance = mock_flux_pipeline

        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        mock_class.from_pretrained.assert_called_once()
        assert generator.pipeline is not None

    def test_generate_requires_loaded_model(self):
        """Test generate raises error if model not loaded."""
        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )

        with pytest.raises(RuntimeError, match="Load model first"):
            generator.generate(prompt="test")

    def test_generate_creates_images(self, mock_flux_pipeline):
        """Test image generation."""
        mock_class, mock_instance = mock_flux_pipeline

        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        images = generator.generate(
            prompt="A beautiful sunset over mountains",
            num_images=1,
            width=512,
            height=512,
        )

        assert len(images) == 1
        assert isinstance(images[0], Image.Image)
        mock_instance.assert_called_once()

    def test_generate_schnell_ignores_guidance(self, mock_flux_pipeline):
        """Test that schnell model doesn't pass guidance_scale."""
        mock_class, mock_instance = mock_flux_pipeline

        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        generator.generate(
            prompt="test",
            guidance_scale=7.5,  # Should be ignored
        )

        call_kwargs = mock_instance.call_args.kwargs
        assert "guidance_scale" not in call_kwargs

    def test_generate_dev_uses_guidance(self, mock_flux_pipeline):
        """Test that dev model uses guidance_scale."""
        mock_class, mock_instance = mock_flux_pipeline

        generator = FluxGenerator(
            model_id=FLUX_DEV,
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        generator.generate(
            prompt="test",
            guidance_scale=3.5,
        )

        call_kwargs = mock_instance.call_args.kwargs
        assert "guidance_scale" in call_kwargs
        assert call_kwargs["guidance_scale"] == 3.5

    def test_generate_uses_model_default_steps(self, mock_flux_pipeline):
        """Test that default steps are based on model."""
        mock_class, mock_instance = mock_flux_pipeline

        # Schnell defaults to 4 steps
        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        generator.generate(prompt="test")

        call_kwargs = mock_instance.call_args.kwargs
        assert call_kwargs["num_inference_steps"] == 4

    def test_unload(self, mock_flux_pipeline):
        """Test model unloading."""
        mock_class, mock_instance = mock_flux_pipeline

        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()
        assert generator.pipeline is not None

        generator.unload()
        assert generator.pipeline is None

    def test_unload_without_pipeline(self):
        """Test unload when no pipeline loaded."""
        generator = FluxGenerator(
            model_id=FLUX_SCHNELL,
            device="cpu",
            dtype=torch.float32,
        )

        # Should not raise error
        generator.unload()
        assert generator.pipeline is None


class TestFluxMoodRouting:
    """Test mood-based FLUX model routing."""

    def test_contemplative_returns_dev(self):
        """Test contemplative mood returns dev model."""
        result = get_flux_model_for_mood("contemplative")
        assert result == FLUX_DEV

    def test_introspective_returns_dev(self):
        """Test introspective mood returns dev model."""
        result = get_flux_model_for_mood("introspective")
        assert result == FLUX_DEV

    def test_melancholic_returns_dev(self):
        """Test melancholic mood returns dev model."""
        result = get_flux_model_for_mood("melancholic")
        assert result == FLUX_DEV

    def test_serene_returns_dev(self):
        """Test serene mood returns dev model."""
        result = get_flux_model_for_mood("serene")
        assert result == FLUX_DEV

    def test_chaotic_returns_schnell(self):
        """Test chaotic mood returns schnell model."""
        result = get_flux_model_for_mood("chaotic")
        assert result == FLUX_SCHNELL

    def test_energized_returns_schnell(self):
        """Test energized mood returns schnell model."""
        result = get_flux_model_for_mood("energized")
        assert result == FLUX_SCHNELL

    def test_rebellious_returns_schnell(self):
        """Test rebellious mood returns schnell model."""
        result = get_flux_model_for_mood("rebellious")
        assert result == FLUX_SCHNELL

    def test_playful_returns_schnell(self):
        """Test playful mood returns schnell model."""
        result = get_flux_model_for_mood("playful")
        assert result == FLUX_SCHNELL

    def test_unknown_mood_returns_schnell(self):
        """Test unknown mood defaults to schnell."""
        result = get_flux_model_for_mood("unknown_mood")
        assert result == FLUX_SCHNELL

    def test_case_insensitive(self):
        """Test mood matching is case insensitive."""
        assert get_flux_model_for_mood("CONTEMPLATIVE") == FLUX_DEV
        assert get_flux_model_for_mood("Chaotic") == FLUX_SCHNELL


class TestMoodSystemFluxIntegration:
    """Test MoodSystem FLUX integration."""

    def test_mood_system_flux_routing(self):
        """Test MoodSystem.get_preferred_model_type()."""
        from ai_artist.personality.moods import Mood, MoodSystem

        system = MoodSystem()

        # Set to contemplative with high intensity
        system.current_mood = Mood.CONTEMPLATIVE
        system.mood_intensity = 0.8

        assert system.get_preferred_model_type() == "flux-dev"
        assert system.should_use_flux() is True

    def test_mood_system_returns_sdxl_for_low_intensity(self):
        """Test that low intensity moods return SDXL."""
        from ai_artist.personality.moods import Mood, MoodSystem

        system = MoodSystem()

        # Set to contemplative with low intensity
        system.current_mood = Mood.CONTEMPLATIVE
        system.mood_intensity = 0.3

        assert system.get_preferred_model_type() == "sdxl"
        assert system.should_use_flux() is False

    def test_mood_system_high_energy_returns_schnell(self):
        """Test high energy moods return FLUX.1-schnell."""
        from ai_artist.personality.moods import Mood, MoodSystem

        system = MoodSystem()

        # Set to chaotic with high intensity
        system.current_mood = Mood.CHAOTIC
        system.mood_intensity = 0.9

        assert system.get_preferred_model_type() == "flux-schnell"
        assert system.should_use_flux() is True

    def test_get_flux_model_id(self):
        """Test get_flux_model_id returns correct IDs."""
        from ai_artist.personality.moods import Mood, MoodSystem

        system = MoodSystem()

        # High intensity contemplative -> FLUX.1-dev
        system.current_mood = Mood.CONTEMPLATIVE
        system.mood_intensity = 0.8
        assert system.get_flux_model_id() == FLUX_DEV

        # High intensity chaotic -> FLUX.1-schnell
        system.current_mood = Mood.CHAOTIC
        system.mood_intensity = 0.9
        assert system.get_flux_model_id() == FLUX_SCHNELL

        # Low intensity -> None (SDXL)
        system.current_mood = Mood.PLAYFUL
        system.mood_intensity = 0.5
        assert system.get_flux_model_id() is None
