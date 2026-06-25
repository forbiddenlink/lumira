"""Tests for web helper utilities."""

from pathlib import Path

from PIL import Image

from ai_artist.web.helpers import resolve_gallery_file_path


class TestResolveGalleryFilePath:
    """Tests for gallery-relative path resolution."""

    def test_relative_path_unchanged(self, tmp_path):
        gallery = tmp_path / "gallery"
        gallery.mkdir()
        rel = "2026/06/art.png"
        (gallery / "2026" / "06").mkdir(parents=True)
        Image.new("RGB", (4, 4), color="red").save(gallery / "2026" / "06" / "art.png")

        assert resolve_gallery_file_path(rel, gallery) == rel

    def test_absolute_path_resolves_relative(self, tmp_path):
        gallery = tmp_path / "gallery"
        image_dir = gallery / "2026"
        image_dir.mkdir(parents=True)
        img_path = image_dir / "abs.png"
        Image.new("RGB", (4, 4), color="blue").save(img_path)

        assert (
            resolve_gallery_file_path(str(img_path.resolve()), gallery) == "2026/abs.png"
        )

    def test_basename_fallback_search(self, tmp_path):
        gallery = tmp_path / "gallery"
        nested = gallery / "deep" / "nested"
        nested.mkdir(parents=True)
        Image.new("RGB", (4, 4), color="green").save(nested / "found.png")

        assert resolve_gallery_file_path("found.png", gallery) == "deep/nested/found.png"
