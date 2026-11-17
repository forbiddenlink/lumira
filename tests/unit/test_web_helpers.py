"""Unit tests for web helper functions."""

import json
import os
from unittest.mock import Mock, patch

import pytest

from ai_artist.web.helpers import (
    calculate_gallery_stats,
    filter_by_search,
    is_valid_image,
    load_image_metadata,
    resolve_within,
)


class TestIsValidImage:
    """Test the is_valid_image function."""

    def test_valid_image(self, tmp_path):
        """Test with a valid image and metadata."""
        img_path = tmp_path / "test.png"
        metadata_path = img_path.with_suffix(".json")

        # Create mock image
        img_path.touch()
        metadata_path.write_text(json.dumps({"prompt": "test prompt"}))

        with patch("ai_artist.web.helpers.Image.open") as mock_open:
            mock_img = Mock()
            mock_img.convert.return_value = Mock()
            mock_open.return_value.__enter__.return_value = mock_img

            with patch("ai_artist.web.helpers.np.array") as mock_array:
                mock_array.return_value.mean.return_value = 128  # Not black

                is_valid, reason = is_valid_image(img_path, tmp_path)
                assert is_valid is True
                assert reason is None

    def test_test_image(self, tmp_path):
        """Test that test images are filtered out."""
        img_path = tmp_path / "test" / "image.png"
        img_path.parent.mkdir()
        img_path.touch()

        is_valid, reason = is_valid_image(img_path, tmp_path)
        assert is_valid is False
        assert reason == "test_image"

    def test_no_metadata(self, tmp_path):
        """Test image without metadata."""
        img_path = tmp_path / "test.png"
        img_path.touch()

        is_valid, reason = is_valid_image(img_path, tmp_path)
        assert is_valid is False
        assert reason == "no_metadata"

    def test_empty_prompt(self, tmp_path):
        """Test image with empty prompt."""
        img_path = tmp_path / "test.png"
        metadata_path = img_path.with_suffix(".json")

        img_path.touch()
        metadata_path.write_text(json.dumps({"prompt": ""}))

        is_valid, reason = is_valid_image(img_path, tmp_path)
        assert is_valid is False
        assert reason == "no_prompt"

    def test_black_image(self, tmp_path):
        """Test detection of mostly black images."""
        img_path = tmp_path / "test.png"
        metadata_path = img_path.with_suffix(".json")

        img_path.touch()
        metadata_path.write_text(json.dumps({"prompt": "test prompt"}))

        with patch("ai_artist.web.helpers.Image.open") as mock_open:
            mock_img = Mock()
            mock_img.convert.return_value = Mock()
            mock_open.return_value.__enter__.return_value = mock_img

            with patch("ai_artist.web.helpers.np.array") as mock_array:
                mock_array.return_value.mean.return_value = 5  # Black

                is_valid, reason = is_valid_image(img_path, tmp_path)
                assert is_valid is False
                assert reason == "black_image"

    def test_corrupted_image(self, tmp_path):
        """Test detection of corrupted images."""
        img_path = tmp_path / "test.png"
        metadata_path = img_path.with_suffix(".json")

        img_path.touch()
        metadata_path.write_text(json.dumps({"prompt": "test prompt"}))

        with patch("ai_artist.web.helpers.Image.open") as mock_open:
            mock_open.side_effect = Exception("Corrupted")

            is_valid, reason = is_valid_image(img_path, tmp_path)
            assert is_valid is False
            assert "corrupted" in reason


class TestLoadImageMetadata:
    """Test the load_image_metadata function."""

    def test_load_valid_metadata(self, tmp_path):
        """Test loading valid metadata."""
        gallery_path = tmp_path / "gallery"
        gallery_path.mkdir()
        img_path = gallery_path / "test.png"
        metadata_path = img_path.with_suffix(".json")

        img_path.touch()
        metadata = {
            "prompt": "test prompt",
            "created_at": "2024-01-01T00:00:00",
            "featured": True,
            "metadata": {"model": "test-model"},
        }
        metadata_path.write_text(json.dumps(metadata))

        result = load_image_metadata(img_path, gallery_path)

        assert result is not None
        assert result["path"] == "test.png"
        assert result["filename"] == "test.png"
        assert result["prompt"] == "test prompt"
        assert result["created_at"] == "2024-01-01T00:00:00"
        assert result["featured"] is True
        assert result["metadata"] == {"model": "test-model"}

    def test_load_missing_metadata(self, tmp_path):
        """Test with missing metadata file."""
        gallery_path = tmp_path / "gallery"
        gallery_path.mkdir()
        img_path = gallery_path / "test.png"
        img_path.touch()

        result = load_image_metadata(img_path, gallery_path)
        assert result is None

    def test_load_invalid_json(self, tmp_path):
        """Test with invalid JSON metadata."""
        gallery_path = tmp_path / "gallery"
        gallery_path.mkdir()
        img_path = gallery_path / "test.png"
        metadata_path = img_path.with_suffix(".json")

        img_path.touch()
        metadata_path.write_text("invalid json")

        result = load_image_metadata(img_path, gallery_path)
        assert result is None

    def test_subdirectory_path(self, tmp_path):
        """Test with image in subdirectory."""
        gallery_path = tmp_path / "gallery"
        subdir = gallery_path / "2024" / "01"
        subdir.mkdir(parents=True)

        img_path = subdir / "test.png"
        metadata_path = img_path.with_suffix(".json")

        img_path.touch()
        metadata = {"prompt": "test", "created_at": "2024-01-01T00:00:00"}
        metadata_path.write_text(json.dumps(metadata))

        result = load_image_metadata(img_path, gallery_path)

        assert result is not None
        assert result["path"] == "2024/01/test.png"


class TestFilterBySearch:
    """Test the filter_by_search function."""

    def test_filter_with_match(self, tmp_path):
        """Test filtering with matching prompts."""
        img1 = tmp_path / "image1.png"
        img2 = tmp_path / "image2.png"

        img1.touch()
        img2.touch()

        # Image 1 matches search
        metadata1 = {"prompt": "a beautiful sunset"}
        img1.with_suffix(".json").write_text(json.dumps(metadata1))

        # Image 2 doesn't match
        metadata2 = {"prompt": "a mountain landscape"}
        img2.with_suffix(".json").write_text(json.dumps(metadata2))

        result = filter_by_search([img1, img2], "sunset")

        assert len(result) == 1
        assert result[0] == img1

    def test_filter_case_insensitive(self, tmp_path):
        """Test that filtering is case-insensitive."""
        img_path = tmp_path / "image.png"
        img_path.touch()

        metadata = {"prompt": "A Beautiful SUNSET"}
        img_path.with_suffix(".json").write_text(json.dumps(metadata))

        result = filter_by_search([img_path], "sunset")

        assert len(result) == 1
        assert result[0] == img_path

    def test_filter_no_matches(self, tmp_path):
        """Test filtering with no matches."""
        img_path = tmp_path / "image.png"
        img_path.touch()

        metadata = {"prompt": "a mountain landscape"}
        img_path.with_suffix(".json").write_text(json.dumps(metadata))

        result = filter_by_search([img_path], "sunset")

        assert len(result) == 0

    def test_filter_missing_metadata(self, tmp_path):
        """Test filtering with missing metadata files."""
        img_path = tmp_path / "image.png"
        img_path.touch()

        result = filter_by_search([img_path], "sunset")

        assert len(result) == 0

    def test_filter_empty_list(self):
        """Test filtering empty list."""
        result = filter_by_search([], "sunset")
        assert len(result) == 0


class TestCalculateGalleryStats:
    """Test the calculate_gallery_stats function."""

    def test_calculate_stats(self, tmp_path):
        """Test calculating gallery statistics."""
        gallery_path = tmp_path / "gallery"
        gallery_path.mkdir()

        # Create mock images
        img1 = gallery_path / "image1.png"
        img2 = gallery_path / "image2.png"
        img1.touch()
        img2.touch()

        # Add metadata
        metadata1 = {
            "prompt": "prompt 1",
            "created_at": "2024-01-01T00:00:00",
        }
        img1.with_suffix(".json").write_text(json.dumps(metadata1))

        metadata2 = {
            "prompt": "prompt 2",
            "created_at": "2024-01-02T00:00:00",
        }
        img2.with_suffix(".json").write_text(json.dumps(metadata2))

        # Create mock gallery manager
        mock_manager = Mock()
        mock_manager.list_images.side_effect = lambda featured_only: (
            [] if featured_only else [img1, img2]
        )

        result = calculate_gallery_stats(mock_manager)

        assert result["total_images"] == 2
        assert result["featured_images"] == 0
        assert result["total_prompts"] == 2
        assert result["date_range"]["earliest"] == "2024-01-01T00:00:00"
        assert result["date_range"]["latest"] == "2024-01-02T00:00:00"

    def test_calculate_stats_with_featured(self, tmp_path):
        """Test statistics with featured images."""
        gallery_path = tmp_path / "gallery"
        gallery_path.mkdir()

        img_path = gallery_path / "image.png"
        img_path.touch()

        metadata = {
            "prompt": "test prompt",
            "created_at": "2024-01-01T00:00:00",
            "featured": True,
        }
        img_path.with_suffix(".json").write_text(json.dumps(metadata))

        mock_manager = Mock()
        mock_manager.list_images.side_effect = lambda featured_only: (
            [img_path] if featured_only else [img_path]
        )

        result = calculate_gallery_stats(mock_manager)

        assert result["total_images"] == 1
        assert result["featured_images"] == 1

    def test_calculate_stats_duplicate_prompts(self, tmp_path):
        """Test that duplicate prompts are counted once."""
        gallery_path = tmp_path / "gallery"
        gallery_path.mkdir()

        img1 = gallery_path / "image1.png"
        img2 = gallery_path / "image2.png"
        img1.touch()
        img2.touch()

        # Same prompt for both
        metadata = {
            "prompt": "same prompt",
            "created_at": "2024-01-01T00:00:00",
        }
        img1.with_suffix(".json").write_text(json.dumps(metadata))
        img2.with_suffix(".json").write_text(json.dumps(metadata))

        mock_manager = Mock()
        mock_manager.list_images.side_effect = lambda featured_only: (
            [] if featured_only else [img1, img2]
        )

        result = calculate_gallery_stats(mock_manager)

        assert result["total_images"] == 2
        assert result["total_prompts"] == 1  # Deduplicated

    def test_calculate_stats_empty_gallery(self):
        """Test statistics for empty gallery."""
        mock_manager = Mock()
        mock_manager.list_images.return_value = []

        result = calculate_gallery_stats(mock_manager)

        assert result["total_images"] == 0
        assert result["featured_images"] == 0
        assert result["total_prompts"] == 0
        assert result["date_range"] == {}


class TestResolveWithin:
    """Containment guard used by every route that joins a request path."""

    def test_relative_path_inside_base(self, tmp_path):
        assert resolve_within(tmp_path, "2026/01/a.png") == (
            tmp_path.resolve() / "2026/01/a.png"
        )

    def test_dotdot_escape_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            resolve_within(tmp_path / "gallery", "../secret.json")

    def test_absolute_outside_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "/etc/passwd")

    def test_absolute_inside_allowed(self, tmp_path):
        inside = tmp_path / "x.mp4"
        assert resolve_within(tmp_path, str(inside)) == inside.resolve()

    def test_sibling_prefix_rejected(self, tmp_path):
        (tmp_path / "gallery").mkdir()
        with pytest.raises(ValueError):
            resolve_within(tmp_path / "gallery", "../gallery-evil/a.png")

    def test_symlink_escape_rejected(self, tmp_path):
        base = tmp_path / "gallery"
        base.mkdir()
        os.symlink(tmp_path, base / "link")
        with pytest.raises(ValueError):
            resolve_within(base, "link/outside.json")
