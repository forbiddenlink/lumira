"""Tests for IP-Adapter integration."""

from unittest.mock import MagicMock, patch

import pytest
import torch
from PIL import Image

from ai_artist.core.ip_adapter import (
    IP_ADAPTER_MODELS,
    IPAdapterManager,
    get_ip_adapter_manager,
)


@pytest.fixture
def ip_adapter_manager():
    """Create fresh IP-Adapter manager for each test."""
    return IPAdapterManager()


@pytest.fixture
def mock_pipeline():
    """Create a mock diffusion pipeline."""
    pipeline = MagicMock()
    pipeline.__class__.__name__ = "StableDiffusionXLPipeline"
    pipeline.device = "cpu"
    pipeline.load_ip_adapter = MagicMock()
    pipeline.unload_ip_adapter = MagicMock()
    pipeline.set_ip_adapter_scale = MagicMock()
    pipeline.return_value.images = [Image.new("RGB", (512, 512))]
    return pipeline


@pytest.fixture
def sample_image(tmp_path):
    """Create a sample reference image."""
    img = Image.new("RGB", (256, 256), color="red")
    path = tmp_path / "reference.png"
    img.save(path)
    return path


class TestIPAdapterModels:
    """Test IP-Adapter model configurations."""

    def test_models_have_required_fields(self):
        """Verify all model configs have required fields."""
        required_fields = ["repo", "subfolder", "weight_name", "description"]
        for name, config in IP_ADAPTER_MODELS.items():
            for field in required_fields:
                assert field in config, f"Model {name} missing field {field}"

    def test_sd15_models_exist(self):
        """Test SD 1.5 models are available."""
        sd15_models = [k for k in IP_ADAPTER_MODELS if k.endswith("_sd15")]
        assert len(sd15_models) >= 3  # Standard, plus, plus-face

    def test_sdxl_models_exist(self):
        """Test SDXL models are available."""
        sdxl_models = [k for k in IP_ADAPTER_MODELS if k.endswith("_sdxl")]
        assert len(sdxl_models) >= 3  # Standard, plus, plus-face


class TestIPAdapterManager:
    """Test IPAdapterManager class."""

    def test_init(self, ip_adapter_manager):
        """Test manager initialization."""
        assert ip_adapter_manager._loaded_adapter is None
        assert ip_adapter_manager._image_encoder is None

    def test_get_available_adapters_sd15(self, ip_adapter_manager):
        """Test getting SD 1.5 adapters."""
        adapters = ip_adapter_manager.get_available_adapters("sd15")
        assert len(adapters) >= 3
        for adapter in adapters:
            assert adapter["name"].endswith("_sd15")

    def test_get_available_adapters_sdxl(self, ip_adapter_manager):
        """Test getting SDXL adapters."""
        adapters = ip_adapter_manager.get_available_adapters("sdxl")
        assert len(adapters) >= 3
        for adapter in adapters:
            assert adapter["name"].endswith("_sdxl")

    def test_detect_model_type_sdxl(self, ip_adapter_manager, mock_pipeline):
        """Test SDXL detection."""
        mock_pipeline.__class__.__name__ = "StableDiffusionXLPipeline"
        model_type = ip_adapter_manager.detect_model_type(mock_pipeline)
        assert model_type == "sdxl"

    def test_detect_model_type_sd15(self, ip_adapter_manager, mock_pipeline):
        """Test SD 1.5 detection."""
        mock_pipeline.__class__.__name__ = "StableDiffusionPipeline"
        mock_pipeline.unet = MagicMock()
        mock_pipeline.unet.config.in_channels = 4
        model_type = ip_adapter_manager.detect_model_type(mock_pipeline)
        assert model_type == "sd15"

    def test_get_default_adapter_sdxl(self, ip_adapter_manager):
        """Test default adapter for SDXL."""
        adapter = ip_adapter_manager.get_default_adapter("sdxl")
        assert adapter == "ip-adapter_sdxl"

    def test_get_default_adapter_sd15(self, ip_adapter_manager):
        """Test default adapter for SD 1.5."""
        adapter = ip_adapter_manager.get_default_adapter("sd15")
        assert adapter == "ip-adapter_sd15"

    def test_load_ip_adapter(self, ip_adapter_manager, mock_pipeline):
        """Test loading IP-Adapter."""
        ip_adapter_manager.load_ip_adapter(mock_pipeline, "ip-adapter_sdxl")

        mock_pipeline.load_ip_adapter.assert_called_once()
        call_args = mock_pipeline.load_ip_adapter.call_args
        assert call_args[0][0] == "h94/IP-Adapter"
        assert ip_adapter_manager._loaded_adapter == "ip-adapter_sdxl"

    def test_load_ip_adapter_auto_detect(self, ip_adapter_manager, mock_pipeline):
        """Test auto-detecting adapter based on pipeline."""
        mock_pipeline.__class__.__name__ = "StableDiffusionXLPipeline"
        ip_adapter_manager.load_ip_adapter(mock_pipeline)

        assert ip_adapter_manager._loaded_adapter == "ip-adapter_sdxl"

    def test_load_ip_adapter_unknown_raises(self, ip_adapter_manager, mock_pipeline):
        """Test loading unknown adapter raises error."""
        with pytest.raises(ValueError, match="Unknown IP-Adapter"):
            ip_adapter_manager.load_ip_adapter(mock_pipeline, "unknown-adapter")

    def test_load_ip_adapter_already_loaded(self, ip_adapter_manager, mock_pipeline):
        """Test loading already-loaded adapter is a no-op."""
        ip_adapter_manager.load_ip_adapter(mock_pipeline, "ip-adapter_sdxl")
        mock_pipeline.load_ip_adapter.reset_mock()

        # Load again - should not call load_ip_adapter
        ip_adapter_manager.load_ip_adapter(mock_pipeline, "ip-adapter_sdxl")
        mock_pipeline.load_ip_adapter.assert_not_called()

    def test_unload_ip_adapter(self, ip_adapter_manager, mock_pipeline):
        """Test unloading IP-Adapter."""
        ip_adapter_manager._loaded_adapter = "ip-adapter_sdxl"
        ip_adapter_manager.unload_ip_adapter(mock_pipeline)

        mock_pipeline.unload_ip_adapter.assert_called_once()
        assert ip_adapter_manager._loaded_adapter is None

    def test_unload_ip_adapter_not_loaded(self, ip_adapter_manager, mock_pipeline):
        """Test unloading when nothing loaded is a no-op."""
        ip_adapter_manager.unload_ip_adapter(mock_pipeline)
        mock_pipeline.unload_ip_adapter.assert_not_called()

    def test_set_ip_adapter_scale(self, ip_adapter_manager, mock_pipeline):
        """Test setting IP-Adapter scale."""
        ip_adapter_manager.set_ip_adapter_scale(mock_pipeline, 0.5)
        mock_pipeline.set_ip_adapter_scale.assert_called_once_with(0.5)

    def test_set_ip_adapter_scale_invalid_raises(
        self, ip_adapter_manager, mock_pipeline
    ):
        """Test invalid scale raises error."""
        with pytest.raises(ValueError, match="must be 0.0-1.0"):
            ip_adapter_manager.set_ip_adapter_scale(mock_pipeline, 1.5)

        with pytest.raises(ValueError, match="must be 0.0-1.0"):
            ip_adapter_manager.set_ip_adapter_scale(mock_pipeline, -0.1)

    def test_prepare_reference_image_pil(self, ip_adapter_manager):
        """Test preparing PIL image."""
        img = Image.new("RGB", (256, 256))
        result = ip_adapter_manager.prepare_reference_image(img)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"

    def test_prepare_reference_image_path(self, ip_adapter_manager, sample_image):
        """Test preparing image from path."""
        result = ip_adapter_manager.prepare_reference_image(sample_image)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"

    def test_prepare_reference_image_string_path(
        self, ip_adapter_manager, sample_image
    ):
        """Test preparing image from string path."""
        result = ip_adapter_manager.prepare_reference_image(str(sample_image))
        assert isinstance(result, Image.Image)

    def test_prepare_reference_image_resize(self, ip_adapter_manager):
        """Test resizing reference image."""
        img = Image.new("RGB", (256, 256))
        result = ip_adapter_manager.prepare_reference_image(img, target_size=(128, 128))
        assert result.size == (128, 128)

    def test_prepare_reference_image_converts_mode(self, ip_adapter_manager):
        """Test converting non-RGB images."""
        img = Image.new("L", (256, 256))  # Grayscale
        result = ip_adapter_manager.prepare_reference_image(img)
        assert result.mode == "RGB"

    def test_generate_with_reference(self, ip_adapter_manager, mock_pipeline):
        """Test generating with reference image."""
        ref_image = Image.new("RGB", (256, 256))

        # Setup mock return
        result_image = Image.new("RGB", (512, 512))
        mock_pipeline.return_value.images = [result_image]

        images = ip_adapter_manager.generate_with_reference(
            pipeline=mock_pipeline,
            prompt="a beautiful sunset",
            reference_image=ref_image,
            ip_adapter_scale=0.6,
            num_images=1,
        )

        # Verify IP-Adapter was loaded and configured
        mock_pipeline.load_ip_adapter.assert_called_once()
        mock_pipeline.set_ip_adapter_scale.assert_called_with(0.6)

        # Verify pipeline was called with ip_adapter_image
        mock_pipeline.assert_called_once()
        call_kwargs = mock_pipeline.call_args.kwargs
        assert "ip_adapter_image" in call_kwargs
        assert call_kwargs["prompt"] == "a beautiful sunset"

        assert len(images) == 1
        assert images[0] == result_image

    def test_generate_with_reference_seed(self, ip_adapter_manager, mock_pipeline):
        """Test generating with seed for reproducibility."""
        ref_image = Image.new("RGB", (256, 256))
        mock_pipeline.return_value.images = [Image.new("RGB", (512, 512))]

        ip_adapter_manager.generate_with_reference(
            pipeline=mock_pipeline,
            prompt="test",
            reference_image=ref_image,
            seed=42,
        )

        call_kwargs = mock_pipeline.call_args.kwargs
        assert "generator" in call_kwargs
        assert call_kwargs["generator"] is not None

    def test_generate_style_variations(self, ip_adapter_manager, mock_pipeline):
        """Test generating style variations."""
        ref_image = Image.new("RGB", (256, 256))
        mock_pipeline.return_value.images = [Image.new("RGB", (512, 512))]

        results = ip_adapter_manager.generate_style_variations(
            pipeline=mock_pipeline,
            reference_image=ref_image,
            prompt="test",
            scales=[0.2, 0.5, 0.8],
        )

        assert len(results) == 3
        assert results[0][0] == 0.2
        assert results[1][0] == 0.5
        assert results[2][0] == 0.8

    def test_generate_style_variations_default_scales(
        self, ip_adapter_manager, mock_pipeline
    ):
        """Test default scales for variations."""
        ref_image = Image.new("RGB", (256, 256))
        mock_pipeline.return_value.images = [Image.new("RGB", (512, 512))]

        results = ip_adapter_manager.generate_style_variations(
            pipeline=mock_pipeline,
            reference_image=ref_image,
            prompt="test",
        )

        # Default scales are [0.2, 0.4, 0.6, 0.8]
        assert len(results) == 4


class TestGetIPAdapterManager:
    """Test singleton accessor."""

    def test_returns_singleton(self):
        """Test that get_ip_adapter_manager returns singleton."""
        manager1 = get_ip_adapter_manager()
        manager2 = get_ip_adapter_manager()
        assert manager1 is manager2

    def test_creates_instance(self):
        """Test that it creates an IPAdapterManager."""
        manager = get_ip_adapter_manager()
        assert isinstance(manager, IPAdapterManager)


class TestIPAdapterIntegrationWithGenerator:
    """Test IP-Adapter integration with ImageGenerator."""

    @pytest.fixture
    def mock_diffusion_pipeline(self):
        """Mock the full diffusion pipeline for integration tests."""
        with (
            patch("ai_artist.core.generator.DiffusionPipeline") as mock,
            patch(
                "ai_artist.core.generator.torch.compile",
                side_effect=lambda module, **kwargs: module,
            ) as _mock_compile,
        ):
            pipeline = MagicMock()
            pipeline.to.return_value = pipeline
            pipeline.enable_attention_slicing.return_value = None
            pipeline.enable_vae_slicing.return_value = None
            pipeline.vae = MagicMock()
            pipeline.scheduler = MagicMock()
            pipeline.scheduler.config = {}
            pipeline.unet = MagicMock()
            pipeline.__class__.__name__ = "StableDiffusionXLPipeline"

            # IP-Adapter methods
            pipeline.load_ip_adapter = MagicMock()
            pipeline.set_ip_adapter_scale = MagicMock()

            # Generation result
            import numpy as np

            noise = np.random.randint(50, 200, (512, 512, 3), dtype=np.uint8)
            mock_image = Image.fromarray(noise, mode="RGB")
            pipeline.return_value.images = [mock_image]

            mock.from_pretrained.return_value = pipeline
            yield mock, pipeline

    def test_generator_with_reference_image(self, mock_diffusion_pipeline):
        """Test ImageGenerator.generate() with reference_image parameter."""
        from ai_artist.core.generator import ImageGenerator

        mock_class, mock_instance = mock_diffusion_pipeline

        with patch(
            "ai_artist.core.generator.DPMSolverMultistepScheduler"
        ) as mock_scheduler:
            mock_scheduler.from_config.return_value = MagicMock()

            generator = ImageGenerator(
                model_id="stabilityai/stable-diffusion-xl-base-1.0",
                device="cpu",
                dtype=torch.float32,
            )
            generator.load_model()

            # Create reference image
            ref_image = Image.new("RGB", (256, 256), color="blue")

            images = generator.generate(
                prompt="a mountain landscape",
                reference_image=ref_image,
                ip_adapter_scale=0.5,
                num_images=1,
            )

            # Verify IP-Adapter was loaded
            mock_instance.load_ip_adapter.assert_called_once()

            # Verify scale was set
            mock_instance.set_ip_adapter_scale.assert_called_with(0.5)

            # Verify ip_adapter_image was passed to pipeline
            call_kwargs = mock_instance.call_args.kwargs
            assert "ip_adapter_image" in call_kwargs

            assert len(images) == 1

    def test_generator_without_reference_image(self, mock_diffusion_pipeline):
        """Test that IP-Adapter is not loaded without reference image."""
        from ai_artist.core.generator import ImageGenerator

        mock_class, mock_instance = mock_diffusion_pipeline

        with patch(
            "ai_artist.core.generator.DPMSolverMultistepScheduler"
        ) as mock_scheduler:
            mock_scheduler.from_config.return_value = MagicMock()

            generator = ImageGenerator(
                model_id="stabilityai/stable-diffusion-xl-base-1.0",
                device="cpu",
                dtype=torch.float32,
            )
            generator.load_model()

            images = generator.generate(
                prompt="a mountain landscape",
                num_images=1,
            )

            # IP-Adapter should NOT be loaded
            mock_instance.load_ip_adapter.assert_not_called()

            # No ip_adapter_image in call
            call_kwargs = mock_instance.call_args.kwargs
            assert "ip_adapter_image" not in call_kwargs

            assert len(images) == 1
