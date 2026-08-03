"""Eval-regression golden set for deterministic curation scoring math.

Pins ``QualityMetrics.overall_score`` (fixed-weight aesthetic/clip/technical
blend) and ``ImageCurator.should_keep`` against fixed numeric fixture inputs
-- no image, no CLIP/aesthetic model, no network. Runs in the fast suite.

Model-backed curation (CLIP scoring, AGIQA, ensemble voting) is explicitly
NOT faked here -- see the skipped test at the bottom for why.
"""

import pytest

from ai_artist.curation.curator import ImageCurator, QualityMetrics

# (aesthetic_score, clip_score, technical_score, expected_overall_score)
_OVERALL_SCORE_GOLDEN_CASES = [
    (0.8, 0.7, 0.6, 0.73),
    (0.9, 0.85, 0.8, 0.865),
    (0.2, 0.3, 0.1, 0.21),
    (1.0, 1.0, 1.0, 1.0),
    (0.0, 0.0, 0.0, 0.0),
]


class TestQualityMetricsOverallScoreGolden:
    """QualityMetrics.overall_score is a pure 0.5/0.3/0.2 weighted blend."""

    @pytest.mark.parametrize(
        "aesthetic,clip,technical,expected", _OVERALL_SCORE_GOLDEN_CASES
    )
    def test_overall_score_golden_case(self, aesthetic, clip, technical, expected):
        metrics = QualityMetrics(
            aesthetic_score=aesthetic,
            clip_score=clip,
            technical_score=technical,
        )

        assert metrics.overall_score == pytest.approx(expected)

    def test_overall_score_is_stable(self):
        """Same fixture input yields the same output on repeated reads."""
        metrics = QualityMetrics(
            aesthetic_score=0.8, clip_score=0.7, technical_score=0.6
        )

        assert metrics.overall_score == metrics.overall_score
        assert metrics.overall_score == pytest.approx(0.73)


class TestCuratorShouldKeepGolden:
    """ImageCurator.should_keep is a pure threshold comparison over overall_score."""

    def _curator(self) -> ImageCurator:
        # should_keep() reads no self state (no model load needed).
        return ImageCurator.__new__(ImageCurator)

    def test_high_quality_metrics_are_kept(self):
        curator = self._curator()
        good_metrics = QualityMetrics(
            aesthetic_score=0.8, clip_score=0.75, technical_score=0.7
        )

        assert curator.should_keep(good_metrics, threshold=0.6) is True

    def test_low_quality_metrics_are_rejected(self):
        curator = self._curator()
        bad_metrics = QualityMetrics(
            aesthetic_score=0.2, clip_score=0.3, technical_score=0.1
        )

        assert curator.should_keep(bad_metrics, threshold=0.6) is False

    def test_should_keep_is_stable(self):
        curator = self._curator()
        metrics = QualityMetrics(
            aesthetic_score=0.8, clip_score=0.75, technical_score=0.7
        )

        first = curator.should_keep(metrics, threshold=0.6)
        second = curator.should_keep(metrics, threshold=0.6)

        assert first == second


@pytest.mark.skip(
    reason=(
        "CLIP + LAION aesthetic scoring (ImageCurator.evaluate) requires "
        "downloading and running real models -- not deterministic/offline-safe "
        "for this fixture-only eval gate. tests/unit/test_curator.py already "
        "skips the equivalent case (@pytest.mark.skipif(True, reason="
        "'Requires CLIP model download')); not faked here either."
    )
)
def test_model_backed_curation_not_covered_by_golden_set():
    """Placeholder documenting the deliberate scope boundary of this eval gate."""
