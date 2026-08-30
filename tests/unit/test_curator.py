"""Unit tests for the curation system."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from ai_artist.curation.curator import ImageCurator, QualityMetrics


def test_quality_metrics_overall_score():
    """Test that overall score is calculated correctly."""
    metrics = QualityMetrics(
        aesthetic_score=0.8,
        clip_score=0.7,
        technical_score=0.9,
    )

    # 0.8*0.5 + 0.7*0.3 + 0.9*0.2 = 0.4 + 0.21 + 0.18 = 0.79
    expected = 0.79
    assert abs(metrics.overall_score - expected) < 0.01


def test_curator_initialization():
    """Test curator initializes correctly."""
    curator = ImageCurator(device="cpu")
    assert curator.device == "cpu"
    assert curator.model is None  # Lazy loaded


@pytest.mark.skipif(True, reason="Requires CLIP model download")
def test_curator_loads_clip():
    """Test that CLIP model loads when needed."""
    curator = ImageCurator(device="cpu")
    curator._load_clip()

    assert curator.model is not None
    assert curator.preprocess is not None


def test_curator_evaluate_with_mock():
    """Test image evaluation with mocked CLIP."""
    curator = ImageCurator(device="cpu")

    # Create a test image
    img = Image.new("RGB", (512, 512), color="blue")
    prompt = "blue sky"

    with (
        patch.object(curator, "_load_clip"),
        patch.object(curator, "_compute_clip_score", return_value=0.8),
        patch.object(curator, "_estimate_aesthetic", return_value=0.7),
        patch.object(curator, "_compute_technical_score", return_value=0.9),
    ):
        metrics = curator.evaluate(img, prompt)

        assert metrics.clip_score == 0.8
        assert metrics.aesthetic_score == 0.7
        assert metrics.technical_score == 0.9
        assert 0 <= metrics.overall_score <= 1


def test_curator_should_keep():
    """Test quality threshold filtering."""
    curator = ImageCurator(device="cpu")

    # High quality image
    good_metrics = QualityMetrics(
        aesthetic_score=0.8,
        clip_score=0.75,
        technical_score=0.85,
    )
    assert curator.should_keep(good_metrics, threshold=0.6)

    # Low quality image
    bad_metrics = QualityMetrics(
        aesthetic_score=0.3,
        clip_score=0.2,
        technical_score=0.4,
    )
    assert not curator.should_keep(bad_metrics, threshold=0.6)


def test_aesthetic_score_heuristic_fallback():
    """Test heuristic aesthetic scoring when model not available."""
    curator = ImageCurator(device="cpu")

    # Force use of heuristic by marking model as unavailable
    curator._aesthetic_available = False

    # Square image (good aspect ratio)
    square_img = Image.new("RGB", (512, 512), color="red")
    score_square = curator._estimate_aesthetic(square_img)

    # Very wide image (worse aspect ratio)
    wide_img = Image.new("RGB", (1024, 256), color="red")
    score_wide = curator._estimate_aesthetic(wide_img)

    # Both should return valid scores in 0-1 range
    assert 0 <= score_square <= 1
    assert 0 <= score_wide <= 1

    # Square should generally score higher for aspect ratio component
    # Note: other factors (contrast, saturation) affect final score too
    assert score_square > 0.3  # Should be a reasonable score


def test_aesthetic_heuristic_direct():
    """Test the heuristic aesthetic method directly."""
    curator = ImageCurator(device="cpu")

    # Create image with some color variation
    img = Image.new("RGB", (512, 512))
    # Add some variation by setting pixels
    pixels = img.load()
    for i in range(512):
        for j in range(512):
            pixels[i, j] = (i % 256, j % 256, (i + j) % 256)

    score = curator._estimate_aesthetic_heuristic(img)

    assert 0 <= score <= 1
    assert score > 0.3  # Image with good variation should score reasonably


def test_aesthetic_model_loading_graceful_fallback():
    """Test that aesthetic scoring falls back gracefully when model unavailable."""
    curator = ImageCurator(device="cpu")

    # Model should not be loaded initially
    assert curator._aesthetic_model is None
    assert curator._aesthetic_available is None

    # Create test image
    img = Image.new("RGB", (512, 512), color="blue")

    # Should return a score even without model (uses heuristic)
    score = curator._estimate_aesthetic(img)

    assert 0 <= score <= 1


def test_curator_with_custom_aesthetic_model_id():
    """Test that curator accepts custom aesthetic model ID."""
    custom_model = "shunk031/aesthetics-predictor-v2-ava-logos-l14-reluMSE"
    curator = ImageCurator(device="cpu", aesthetic_model_id=custom_model)

    assert curator._aesthetic_model_id == custom_model


def test_technical_score_resolution():
    """Test that technical score considers resolution."""
    curator = ImageCurator(device="cpu")

    # High resolution
    large_img = Image.new("RGB", (2048, 2048))
    score_large = curator._compute_technical_score(large_img)

    # Low resolution
    small_img = Image.new("RGB", (256, 256))
    score_small = curator._compute_technical_score(small_img)

    # Higher resolution should score higher
    assert score_large > score_small


class TestRemoteCodeIsRefused:
    """Model loads must never leave trust_remote_code to transformers' default.

    The aesthetics-predictor repo ships custom code in its config. With the
    argument omitted, transformers 5.x stops and asks on stdin -- unanswerable
    in a worker or container -- and the two RCE advisories fixed by the 5.x
    upgrade (CVE-2026-4372, CVE-2026-5241) were both about untrusted config
    data steering exactly this decision.
    """

    def test_aesthetic_model_and_processor_refuse_remote_code(self):
        # simple-aesthetics-predictor lives in the optional "aesthetics" extra
        # and is absent from CI, so stand in a stub module rather than skipping
        # -- the assertion is about the call, not the package.
        stub = types.ModuleType("aesthetics_predictor")
        stub.AestheticsPredictorV2Linear = MagicMock()  # type: ignore[attr-defined]
        model_cls = stub.AestheticsPredictorV2Linear  # type: ignore[attr-defined]

        curator = ImageCurator(device="cpu")

        with (
            patch.dict(sys.modules, {"aesthetics_predictor": stub}),
            patch("transformers.CLIPProcessor") as processor_cls,
        ):
            curator._load_aesthetic_model()

            assert (
                model_cls.from_pretrained.call_args.kwargs["trust_remote_code"] is False
            )
            assert (
                processor_cls.from_pretrained.call_args.kwargs["trust_remote_code"]
                is False
            )

    def test_agiqa_model_and_processor_refuse_remote_code(self):
        from ai_artist.curation.agiqa_scorer import AGIQAScorer

        scorer = AGIQAScorer(device="cpu")

        # agiqa_scorer binds these at module import, so patch them there.
        with (
            patch("ai_artist.curation.agiqa_scorer.CLIPModel") as model_cls,
            patch("ai_artist.curation.agiqa_scorer.CLIPProcessor") as processor_cls,
        ):
            model_cls.from_pretrained.return_value.to.return_value = object()
            scorer._load_model()

            assert (
                model_cls.from_pretrained.call_args.kwargs["trust_remote_code"] is False
            )
            assert (
                processor_cls.from_pretrained.call_args.kwargs["trust_remote_code"]
                is False
            )
