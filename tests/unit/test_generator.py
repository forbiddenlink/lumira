"""Tests for image generator."""

from unittest.mock import MagicMock, patch

import pytest
import torch
from PIL import Image

from ai_artist.core.generator import ImageGenerator


@pytest.fixture
def mock_pipeline():
    """Mock Diffusion pipeline."""
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
        pipeline.disable_attention_slicing.return_value = None
        pipeline.fuse_lora.return_value = None
        pipeline.load_lora_weights.return_value = None
        pipeline.vae = MagicMock()
        pipeline.scheduler = MagicMock()
        pipeline.scheduler.config = {}
        pipeline.unet = MagicMock()
        mock.from_pretrained.return_value = pipeline
        yield mock, pipeline


class TestImageGenerator:
    """Test ImageGenerator class."""

    def test_init(self):
        """Test generator initialization."""
        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        assert generator.model_id == "runwayml/stable-diffusion-v1-5"
        assert generator.device == "cpu"
        assert generator.dtype == torch.float32
        assert generator.pipeline is None

    def test_load_model(self, mock_pipeline):
        """Test model loading."""
        mock_class, mock_instance = mock_pipeline
        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )

        generator.load_model()

        mock_class.from_pretrained.assert_called_once()
        assert generator.pipeline is not None

    def test_load_model_mps_fixes(self, mock_pipeline):
        """Test MPS-specific optimizations are applied."""
        mock_class, mock_instance = mock_pipeline

        with patch(
            "ai_artist.core.generator.DPMSolverMultistepScheduler"
        ) as mock_scheduler:
            mock_scheduler.from_config.return_value = MagicMock()

            generator = ImageGenerator(
                model_id="runwayml/stable-diffusion-v1-5",
                device="mps",
                dtype=torch.float32,
            )

            generator.load_model()

            # On MPS, attention slicing should NOT be enabled (it's slower)
            mock_instance.enable_attention_slicing.assert_not_called()
            mock_instance.enable_vae_slicing.assert_not_called()

    def test_generate_requires_loaded_model(self):
        """Test generate raises error if model not loaded."""
        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )

        with pytest.raises(RuntimeError, match="Load model first"):
            generator.generate(prompt="test")

    def test_generate_creates_images(self, mock_pipeline):
        """Test image generation."""
        mock_class, mock_instance = mock_pipeline

        # Create a non-uniform image with noise (uniform images are filtered)
        import numpy as np

        noise = np.random.randint(50, 200, (512, 512, 3), dtype=np.uint8)
        mock_image = Image.fromarray(noise, mode="RGB")
        mock_instance.return_value.images = [mock_image, mock_image, mock_image]

        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        images = generator.generate(
            prompt="a beautiful sunset",
            num_images=3,
            width=512,
            height=512,
            num_inference_steps=20,
            guidance_scale=7.5,
        )

        assert len(images) == 3
        assert all(isinstance(img, Image.Image) for img in images)
        mock_instance.assert_called_once()

    def test_generate_with_negative_prompt(self, mock_pipeline):
        """Test generation with negative prompt."""
        mock_class, mock_instance = mock_pipeline
        # Create a non-uniform image with noise (uniform images are filtered)
        import numpy as np

        noise = np.random.randint(50, 200, (512, 512, 3), dtype=np.uint8)
        mock_image = Image.fromarray(noise, mode="RGB")
        mock_instance.return_value.images = [mock_image]

        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        images = generator.generate(
            prompt="a beautiful sunset",
            negative_prompt="ugly, blurry, low quality",
            num_images=1,
        )

        assert len(images) == 1
        # Check that negative_prompt was passed
        call_kwargs = mock_instance.call_args.kwargs
        assert "negative_prompt" in call_kwargs

    def test_load_lora(self, mock_pipeline, tmp_path):
        """Test LoRA loading."""
        mock_class, mock_instance = mock_pipeline

        # Create mock LoRA file
        lora_path = tmp_path / "test_lora"
        lora_path.mkdir()
        (lora_path / "pytorch_lora_weights.safetensors").touch()

        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        generator.load_lora(lora_path, lora_scale=0.8)

        # Should call load_lora_weights (with string path)
        mock_instance.load_lora_weights.assert_called_once_with(str(lora_path))
        # Should call fuse_lora with scale
        mock_instance.fuse_lora.assert_called_once_with(lora_scale=0.8)

    def test_load_lora_missing_file(self, mock_pipeline, tmp_path):
        """Test LoRA loading with missing file - should not raise."""
        mock_class, mock_instance = mock_pipeline
        lora_path = tmp_path / "nonexistent_lora"

        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        # The actual diffusers library will handle the missing file
        # Our code doesn't check for file existence before calling load_lora_weights
        # So we just verify it calls the method (which would fail in real use)
        generator.load_lora(lora_path, lora_scale=0.8)

        mock_instance.load_lora_weights.assert_called_once_with(str(lora_path))

    def test_unload(self, mock_pipeline):
        """Test model unloading."""
        mock_class, mock_instance = mock_pipeline

        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        generator.unload()

        # Pipeline should be moved to CPU and cleared
        mock_instance.to.assert_called_with("cpu")
        assert generator.pipeline is None

    def test_unload_without_pipeline(self):
        """Test unload when no pipeline loaded."""
        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )

        # Should not raise error
        generator.unload()
        assert generator.pipeline is None

    def test_progress_callback(self, mock_pipeline):
        """Test progress callback during generation."""
        mock_class, mock_instance = mock_pipeline
        mock_image = Image.new("RGB", (512, 512))
        mock_instance.return_value.images = [mock_image]

        generator = ImageGenerator(
            model_id="runwayml/stable-diffusion-v1-5",
            device="cpu",
            dtype=torch.float32,
        )
        generator.load_model()

        progress_calls = []

        def callback(step, total):
            progress_calls.append((step, total))

        generator.generate(
            prompt="test",
            num_images=1,
            num_inference_steps=10,
        )

        # Verify callback was set up (passed to pipeline)
        call_kwargs = mock_instance.call_args.kwargs
        assert "callback" in call_kwargs or "callback_on_step_end" in call_kwargs
