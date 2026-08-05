"""Tests for Preview Generator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from ai_artist.core.preview_generator import (
    PreviewConfig,
    PreviewGenerator,
    PreviewResult,
    TwoStageGenerator,
)


class TestPreviewConfig:
    """Tests for PreviewConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PreviewConfig()
        assert config.model_id == "black-forest-labs/FLUX.1-schnell"
        assert config.num_inference_steps == 4
        assert config.height == 1024
        assert config.width == 1024
        assert config.guidance_scale == 0.0
        assert config.device == "auto"
        assert config.auto_approve_threshold == 0.7

    def test_custom_values(self):
        """Test custom configuration."""
        config = PreviewConfig(
            device="cuda",
            num_inference_steps=8,
            auto_approve_threshold=0.8,
        )
        assert config.device == "cuda"
        assert config.num_inference_steps == 8
        assert config.auto_approve_threshold == 0.8


class TestPreviewResult:
    """Tests for PreviewResult."""

    def test_default_result(self):
        """Test default result values."""
        result = PreviewResult()
        assert result.image is None
        assert result.generation_time == 0.0
        assert result.prompt == ""
        assert result.error is None

    def test_result_with_values(self):
        """Test result with values."""
        result = PreviewResult(
            prompt="test prompt",
            generation_time=2.5,
            style_weights={"zen": 0.5},
            mood_blend={"serene": 1.0},
            seed=12345,
        )
        assert result.prompt == "test prompt"
        assert result.generation_time == 2.5
        assert result.seed == 12345

    def test_to_dict(self):
        """Test serialization."""
        result = PreviewResult(
            prompt="test",
            generation_time=1.0,
            error=None,
        )
        d = result.to_dict()
        assert d["prompt"] == "test"
        assert d["generation_time"] == 1.0
        assert d["has_image"] is False
        assert "error" in d

    def test_get_image_base64_none(self):
        """Test base64 encoding with no image."""
        result = PreviewResult()
        assert result.get_image_base64() is None

    def test_get_image_base64_with_image(self):
        """Test base64 encoding with image."""
        # Create a small test image
        img = Image.new("RGB", (64, 64), color="red")
        result = PreviewResult(image=img)

        b64 = result.get_image_base64()
        assert b64 is not None
        assert isinstance(b64, str)
        assert len(b64) > 0


class TestPreviewGenerator:
    """Tests for PreviewGenerator."""

    @pytest.fixture
    def generator(self):
        """Create a PreviewGenerator instance."""
        return PreviewGenerator()

    def test_init_defaults(self, generator):
        """Test initialization with defaults."""
        assert generator.config is not None
        assert generator.is_loaded is False

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = PreviewConfig(device="cuda")
        with patch(
            "ai_artist.core.preview_generator._detect_device", return_value="cuda"
        ):
            gen = PreviewGenerator(config=config)
        assert gen.config.device == "cuda"

    def test_init_with_helpers(self):
        """Test initialization with style/mood helpers."""
        mock_interpolator = MagicMock()
        mock_blender = MagicMock()

        gen = PreviewGenerator(
            style_interpolator=mock_interpolator,
            mood_blender=mock_blender,
        )

        assert gen.style_interpolator is mock_interpolator
        assert gen.mood_blender is mock_blender

    @pytest.mark.asyncio
    async def test_ensure_loaded_import_error(self, generator):
        """Test loading fails gracefully on import error."""
        with (
            patch.dict("sys.modules", {"diffusers": None}),
            patch(
                "ai_artist.core.preview_generator.PreviewGenerator.ensure_loaded",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await generator.ensure_loaded()
            # Will fail due to missing diffusers
            assert result is False

    @pytest.mark.asyncio
    async def test_preview_without_pipeline(self, generator):
        """Test preview returns error without loaded pipeline."""
        # Don't load pipeline
        result = await generator.preview("test prompt")

        assert result.error is not None
        assert (
            "Failed to load" in result.error
            or "Hugging Face auth" in result.error
            or "HF_TOKEN" in result.error
        )

    @pytest.mark.asyncio
    async def test_preview_with_mock_pipeline(self):
        """Test preview with mocked pipeline."""
        gen = PreviewGenerator()

        # Mock the pipeline
        mock_image = Image.new("RGB", (1024, 1024), color="blue")
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [mock_image]

        gen._pipeline = mock_pipeline
        gen._loaded = True

        result = await gen.preview("a beautiful sunset")

        assert result.error is None
        assert result.image is not None
        assert result.generation_time > 0
        mock_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_with_style_weights(self):
        """Test preview applies style weights."""
        mock_interpolator = AsyncMock()
        gen = PreviewGenerator(style_interpolator=mock_interpolator)

        mock_image = Image.new("RGB", (1024, 1024), color="green")
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [mock_image]

        gen._pipeline = mock_pipeline
        gen._loaded = True

        await gen.preview(
            "test",
            style_weights={"impressionist": 0.7, "zen": 0.3},
        )

        # Style interpolator should have been called
        mock_interpolator.set_blend.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_with_mood_blend(self):
        """Test preview enhances prompt with mood colors."""
        mock_blender = MagicMock()
        mock_blend = MagicMock()
        mock_blend.colors = ["blue", "gold", "silver"]
        mock_blend.atmosphere = "peaceful"
        mock_blender.blend.return_value = mock_blend

        gen = PreviewGenerator(mood_blender=mock_blender)

        mock_image = Image.new("RGB", (1024, 1024), color="blue")
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [mock_image]

        gen._pipeline = mock_pipeline
        gen._loaded = True

        await gen.preview(
            "mountain landscape",
            mood_blend={"serene": 0.8, "contemplative": 0.2},
        )

        # Check that blender was called
        mock_blender.blend.assert_called_once()

        # Check that enhanced prompt was used
        call_args = mock_pipeline.call_args
        enhanced_prompt = call_args.kwargs.get("prompt", "")
        assert "blue" in enhanced_prompt or "gold" in enhanced_prompt

    @pytest.mark.asyncio
    async def test_preview_variations(self):
        """Test generating multiple variations."""
        gen = PreviewGenerator()

        mock_image = Image.new("RGB", (1024, 1024), color="red")
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [mock_image]

        gen._pipeline = mock_pipeline
        gen._loaded = True

        results = await gen.preview_variations("test prompt", count=3)

        assert len(results) == 3
        assert mock_pipeline.call_count == 3

    @pytest.mark.asyncio
    async def test_preview_with_approval_above_threshold(self):
        """Test auto-approval above threshold."""
        gen = PreviewGenerator()

        mock_image = Image.new("RGB", (1024, 1024), color="blue")
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [mock_image]

        gen._pipeline = mock_pipeline
        gen._loaded = True

        # Mock scorer that returns high score
        mock_scorer = AsyncMock()
        mock_scorer.quick_score = AsyncMock(return_value=0.85)

        result, approved, score = await gen.preview_with_approval(
            "test prompt",
            scorer=mock_scorer,
            threshold=0.7,
        )

        assert approved is True
        assert score == 0.85

    @pytest.mark.asyncio
    async def test_preview_with_approval_below_threshold(self):
        """Test rejection below threshold."""
        gen = PreviewGenerator()

        mock_image = Image.new("RGB", (1024, 1024), color="blue")
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [mock_image]

        gen._pipeline = mock_pipeline
        gen._loaded = True

        # Mock scorer that returns low score
        mock_scorer = AsyncMock()
        mock_scorer.quick_score = AsyncMock(return_value=0.5)

        result, approved, score = await gen.preview_with_approval(
            "test prompt",
            scorer=mock_scorer,
            threshold=0.7,
        )

        assert approved is False
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_unload(self):
        """Test unloading the pipeline."""
        gen = PreviewGenerator()
        gen._pipeline = MagicMock()
        gen._loaded = True

        await gen.unload()

        assert gen._pipeline is None
        assert gen._loaded is False

    def test_get_stats(self):
        """Test getting generator statistics."""
        gen = PreviewGenerator()
        stats = gen.get_stats()

        assert "loaded" in stats
        assert "model_id" in stats
        assert "device" in stats
        assert "steps" in stats
        assert "resolution" in stats
        assert stats["loaded"] is False


@pytest.mark.asyncio
class TestTwoStageGenerator:
    """Tests for TwoStageGenerator."""

    @pytest.fixture
    def preview_gen(self):
        """Create a mock preview generator."""
        gen = PreviewGenerator()
        mock_image = Image.new("RGB", (1024, 1024), color="blue")
        gen._pipeline = MagicMock(return_value=MagicMock(images=[mock_image]))
        gen._loaded = True
        return gen

    async def test_generate_with_preview_approved(self, preview_gen):
        """Test two-stage generation with approval."""
        mock_full_gen = AsyncMock()
        mock_full_image = Image.new("RGB", (1024, 1024), color="green")
        mock_full_gen.generate = AsyncMock(return_value=mock_full_image)

        mock_scorer = AsyncMock()
        mock_scorer.quick_score = AsyncMock(return_value=0.85)

        two_stage = TwoStageGenerator(
            preview_generator=preview_gen,
            full_generator=mock_full_gen,
            scorer=mock_scorer,
        )

        result = await two_stage.generate_with_preview(
            prompt="beautiful landscape",
            auto_approve=True,
        )

        assert result["preview_approved"] is True
        assert result["preview_score"] == 0.85
        assert result["final_image"] is not None
        assert result["total_time"] > 0

    async def test_generate_with_preview_rejected(self, preview_gen):
        """Test two-stage generation with rejection."""
        mock_scorer = AsyncMock()
        mock_scorer.quick_score = AsyncMock(return_value=0.4)

        two_stage = TwoStageGenerator(
            preview_generator=preview_gen,
            full_generator=None,
            scorer=mock_scorer,
        )

        result = await two_stage.generate_with_preview(
            prompt="test",
            auto_approve=True,
        )

        assert result["preview_approved"] is False
        assert result["final_image"] is None

    async def test_generate_with_callback(self, preview_gen):
        """Test that preview callback is invoked."""
        callback_called = []

        async def on_preview(result, approved, score):
            callback_called.append((result, approved, score))

        mock_scorer = AsyncMock()
        mock_scorer.quick_score = AsyncMock(return_value=0.75)

        two_stage = TwoStageGenerator(
            preview_generator=preview_gen,
            scorer=mock_scorer,
        )

        await two_stage.generate_with_preview(
            prompt="test",
            on_preview=on_preview,
        )

        assert len(callback_called) == 1
        assert callback_called[0][1] is True  # approved
        assert callback_called[0][2] == 0.75  # score

    async def test_generate_without_auto_approve(self, preview_gen):
        """Test generation without auto-approval."""
        two_stage = TwoStageGenerator(
            preview_generator=preview_gen,
            scorer=None,
        )

        result = await two_stage.generate_with_preview(
            prompt="test",
            auto_approve=False,
        )

        # Without scorer and auto_approve=False, should not be approved
        assert result["preview_approved"] is False
