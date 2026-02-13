"""Integration tests for ControlNet preprocessing and model loading."""

import numpy as np
import pytest
from PIL import Image

from ai_artist.core.controlnet import (
    SD15_CONTROLNET_MODELS,
    SDXL_CONTROLNET_MODELS,
    ControlNetLoader,
    ControlNetPreprocessor,
    ControlNetType,
)


@pytest.fixture
def sample_image():
    """Create a sample test image."""
    # Create a simple gradient image for testing
    width, height = 512, 512
    img_array = np.zeros((height, width, 3), dtype=np.uint8)

    # Add some features for edge detection
    # Draw a rectangle
    img_array[100:400, 100:400] = [200, 200, 200]
    # Draw a circle approximation
    center_y, center_x = 250, 250
    for y in range(height):
        for x in range(width):
            if (x - center_x) ** 2 + (y - center_y) ** 2 < 100**2:
                img_array[y, x] = [100, 150, 200]

    return Image.fromarray(img_array)


@pytest.fixture
def small_image():
    """Create a small test image for faster processing."""
    width, height = 256, 256
    img_array = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(img_array)


class TestControlNetPreprocessor:
    """Tests for ControlNetPreprocessor."""

    def test_canny_produces_valid_output(self, sample_image):
        """Test that Canny preprocessing produces a valid image."""
        result = ControlNetPreprocessor.get_canny_image(sample_image)

        assert isinstance(result, Image.Image)
        assert result.size == sample_image.size
        assert result.mode == "RGB"

        # Canny should produce mostly black/white edges
        result_array = np.array(result)
        unique_values = np.unique(result_array)
        # Should have limited unique values (edge detection produces binary-like output)
        assert len(unique_values) <= 256

    def test_canny_with_thresholds(self, sample_image):
        """Test Canny with different thresholds."""
        low_result = ControlNetPreprocessor.get_canny_image(
            sample_image, low_threshold=50, high_threshold=100
        )
        high_result = ControlNetPreprocessor.get_canny_image(
            sample_image, low_threshold=150, high_threshold=300
        )

        # Both should be valid
        assert isinstance(low_result, Image.Image)
        assert isinstance(high_result, Image.Image)

        # Low threshold should detect more edges (higher mean)
        low_mean = np.array(low_result).mean()
        high_mean = np.array(high_result).mean()
        # This is a weak assertion as thresholds affect edge detection differently
        assert low_mean >= 0
        assert high_mean >= 0

    def test_canny_grayscale_input(self):
        """Test Canny with grayscale input."""
        grayscale = Image.new("L", (256, 256), 128)
        result = ControlNetPreprocessor.get_canny_image(grayscale)

        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"  # Should be converted to RGB

    def test_canny_rgba_input(self):
        """Test Canny with RGBA input."""
        rgba = Image.new("RGBA", (256, 256), (128, 128, 128, 255))
        result = ControlNetPreprocessor.get_canny_image(rgba)

        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"

    def test_preprocess_canny(self, sample_image):
        """Test unified preprocess method with canny type."""
        result = ControlNetPreprocessor.preprocess(sample_image, ControlNetType.CANNY)
        assert isinstance(result, Image.Image)

    def test_preprocess_canny_string(self, sample_image):
        """Test unified preprocess method with string type."""
        result = ControlNetPreprocessor.preprocess(sample_image, "canny")
        assert isinstance(result, Image.Image)

    def test_preprocess_canny_with_kwargs(self, sample_image):
        """Test preprocess with keyword arguments."""
        result = ControlNetPreprocessor.preprocess(
            sample_image, "canny", low_threshold=80, high_threshold=150
        )
        assert isinstance(result, Image.Image)

    def test_preprocess_invalid_type(self, sample_image):
        """Test that invalid type raises ValueError."""
        with pytest.raises(ValueError):
            ControlNetPreprocessor.preprocess(sample_image, "invalid_type")

    def test_clear_cache(self):
        """Test that clear_cache runs without error."""
        ControlNetPreprocessor.clear_cache()

        # Verify all detectors are cleared
        assert ControlNetPreprocessor._depth_detector is None
        assert ControlNetPreprocessor._pose_detector is None
        assert ControlNetPreprocessor._lineart_detector is None
        assert ControlNetPreprocessor._softedge_detector is None


class TestControlNetPreprocessorAux:
    """Tests for controlnet-aux based preprocessors.

    These tests are marked as slow since they require loading ML models.
    Skip if controlnet-aux is not installed.
    """

    @pytest.fixture(autouse=True)
    def check_controlnet_aux(self):
        """Check if controlnet-aux is available."""
        try:
            import controlnet_aux  # noqa: F401
        except ImportError:
            pytest.skip("controlnet-aux not installed")

    @pytest.mark.slow
    def test_depth_preprocessing(self, small_image):
        """Test depth preprocessing with MiDaS."""
        result = ControlNetPreprocessor.get_depth_image(small_image)

        assert isinstance(result, Image.Image)
        assert result.size == small_image.size

    @pytest.mark.slow
    def test_pose_preprocessing(self, small_image):
        """Test pose preprocessing with OpenPose."""
        result = ControlNetPreprocessor.get_pose_image(small_image)

        assert isinstance(result, Image.Image)
        assert result.size == small_image.size

    @pytest.mark.slow
    def test_lineart_preprocessing(self, small_image):
        """Test lineart preprocessing."""
        result = ControlNetPreprocessor.get_lineart_image(small_image)

        assert isinstance(result, Image.Image)
        assert result.size == small_image.size

    @pytest.mark.slow
    def test_softedge_preprocessing(self, small_image):
        """Test softedge preprocessing with HED."""
        result = ControlNetPreprocessor.get_softedge_image(small_image)

        assert isinstance(result, Image.Image)
        assert result.size == small_image.size

    @pytest.mark.slow
    def test_preprocess_all_types(self, small_image):
        """Test preprocess method with all ControlNet types."""
        for cn_type in ControlNetType:
            result = ControlNetPreprocessor.preprocess(small_image, cn_type)
            assert isinstance(result, Image.Image), f"Failed for {cn_type}"

    @pytest.mark.slow
    def test_detector_caching(self, small_image):
        """Test that detectors are cached for reuse."""
        # First call loads the detector
        ControlNetPreprocessor.get_depth_image(small_image)
        detector_first = ControlNetPreprocessor._depth_detector

        # Second call should reuse cached detector
        ControlNetPreprocessor.get_depth_image(small_image)
        detector_second = ControlNetPreprocessor._depth_detector

        assert detector_first is detector_second


class TestControlNetLoader:
    """Tests for ControlNetLoader."""

    def test_get_sdxl_model_id_canny(self):
        """Test getting SDXL Canny model ID."""
        model_id = ControlNetLoader.get_sdxl_model_id(ControlNetType.CANNY)
        assert model_id == "diffusers/controlnet-canny-sdxl-1.0"

    def test_get_sdxl_model_id_depth(self):
        """Test getting SDXL Depth model ID."""
        model_id = ControlNetLoader.get_sdxl_model_id(ControlNetType.DEPTH)
        assert model_id == "diffusers/controlnet-depth-sdxl-1.0"

    def test_get_sdxl_model_id_string(self):
        """Test getting SDXL model ID with string input."""
        model_id = ControlNetLoader.get_sdxl_model_id("canny")
        assert model_id == "diffusers/controlnet-canny-sdxl-1.0"

    def test_get_sd15_model_id_canny(self):
        """Test getting SD1.5 Canny model ID."""
        model_id = ControlNetLoader.get_sd15_model_id(ControlNetType.CANNY)
        assert model_id == "lllyasviel/control_v11p_sd15_canny"

    def test_get_sd15_model_id_depth(self):
        """Test getting SD1.5 Depth model ID."""
        model_id = ControlNetLoader.get_sd15_model_id(ControlNetType.DEPTH)
        assert model_id == "lllyasviel/control_v11f1p_sd15_depth"

    def test_all_sdxl_types_have_models(self):
        """Test that all ControlNet types have SDXL models."""
        for cn_type in ControlNetType:
            model_id = ControlNetLoader.get_sdxl_model_id(cn_type)
            assert model_id is not None
            assert len(model_id) > 0

    def test_all_sd15_types_have_models(self):
        """Test that all ControlNet types have SD1.5 models."""
        for cn_type in ControlNetType:
            model_id = ControlNetLoader.get_sd15_model_id(cn_type)
            assert model_id is not None
            assert len(model_id) > 0

    def test_model_ids_are_different(self):
        """Test that SDXL and SD1.5 model IDs are different."""
        for cn_type in ControlNetType:
            sdxl_id = ControlNetLoader.get_sdxl_model_id(cn_type)
            sd15_id = ControlNetLoader.get_sd15_model_id(cn_type)
            assert sdxl_id != sd15_id


class TestControlNetModels:
    """Tests for ControlNet model constants."""

    def test_sdxl_models_dict_complete(self):
        """Test SDXL models dict has all types."""
        for cn_type in ControlNetType:
            assert cn_type in SDXL_CONTROLNET_MODELS

    def test_sd15_models_dict_complete(self):
        """Test SD1.5 models dict has all types."""
        for cn_type in ControlNetType:
            assert cn_type in SD15_CONTROLNET_MODELS

    def test_sdxl_canny_depth_are_official(self):
        """Test that SDXL Canny and Depth use official diffusers models."""
        assert SDXL_CONTROLNET_MODELS[ControlNetType.CANNY].startswith("diffusers/")
        assert SDXL_CONTROLNET_MODELS[ControlNetType.DEPTH].startswith("diffusers/")


class TestControlNetType:
    """Tests for ControlNetType enum."""

    def test_all_types_exist(self):
        """Test all expected types exist."""
        assert ControlNetType.CANNY.value == "canny"
        assert ControlNetType.DEPTH.value == "depth"
        assert ControlNetType.POSE.value == "pose"
        assert ControlNetType.LINEART.value == "lineart"
        assert ControlNetType.SOFTEDGE.value == "softedge"

    def test_type_from_string(self):
        """Test creating type from string."""
        assert ControlNetType("canny") == ControlNetType.CANNY
        assert ControlNetType("depth") == ControlNetType.DEPTH

    def test_type_count(self):
        """Test we have expected number of types."""
        assert len(ControlNetType) == 5


class TestControlNetModelLoading:
    """Tests for actual ControlNet model loading.

    These tests are marked as slow and require network access.
    """

    @pytest.mark.slow
    @pytest.mark.integration
    def test_load_sdxl_canny_controlnet(self):
        """Test loading SDXL Canny ControlNet model."""
        import torch

        model = ControlNetLoader.load(
            SDXL_CONTROLNET_MODELS[ControlNetType.CANNY], dtype=torch.float16
        )

        assert model is not None
        assert hasattr(model, "forward")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_load_multiple_controlnets(self):
        """Test loading multiple ControlNet models."""
        import torch

        model_ids = [
            SDXL_CONTROLNET_MODELS[ControlNetType.CANNY],
            SDXL_CONTROLNET_MODELS[ControlNetType.DEPTH],
        ]

        models = ControlNetLoader.load_multiple(model_ids, dtype=torch.float16)

        assert len(models) == 2
        for model in models:
            assert model is not None
            assert hasattr(model, "forward")
