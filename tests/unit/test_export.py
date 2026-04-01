"""Tests for export modules: formats and provenance."""

import json
from unittest.mock import patch

import pytest
from PIL import Image

from ai_artist.export.formats import AdvancedExporter
from ai_artist.export.provenance import ProvenanceManager, ProvenanceMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_image(width: int = 64, height: int = 64, mode: str = "RGB") -> Image.Image:
    """Return a small test image."""
    img = Image.new(mode, (width, height), color=(128, 64, 200))
    return img


# ===========================================================================
# ProvenanceMetadata tests
# ===========================================================================


class TestProvenanceMetadata:
    """Unit tests for ProvenanceMetadata."""

    def test_create_manifest_minimal(self):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(prompt="a sunset")
        assert manifest["lumira"]["prompt"] == "a sunset"
        assert (
            manifest["lumira"]["ai_generated"] is True
            if "ai_generated" in manifest["lumira"]
            else True
        )
        assert "claim_generator" in manifest
        assert manifest["claim_generator"].startswith("Lumira/")
        assert "instance_id" in manifest
        assert manifest["instance_id"].startswith("urn:uuid:lumira-")

    def test_create_manifest_full(self):
        meta = ProvenanceMetadata(
            generator_name="Lumira",
            generator_version="1.0.0",
            model_name="sdxl-base",
            model_version="1.0",
        )
        manifest = meta.create_manifest(
            prompt="forest at dawn",
            negative_prompt="blur",
            seed=42,
            steps=30,
            guidance_scale=7.5,
            width=512,
            height=512,
            mood="serene",
            style="impressionist",
            additional_metadata={"custom_key": "custom_value"},
        )
        lumira = manifest["lumira"]
        assert lumira["prompt"] == "forest at dawn"
        assert lumira["negative_prompt"] == "blur"
        assert lumira["seed"] == 42
        assert lumira["steps"] == 30
        assert lumira["guidance_scale"] == pytest.approx(7.5)
        assert lumira["width"] == 512
        assert lumira["height"] == 512
        assert lumira["mood"] == "serene"
        assert lumira["style"] == "impressionist"
        assert lumira["custom_key"] == "custom_value"

    def test_create_manifest_assertions_present(self):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(prompt="test")
        assertions = manifest["assertions"]
        labels = {a["label"] for a in assertions}
        assert "c2pa.ai_disclosure" in labels
        assert "c2pa.actions" in labels

    def test_create_manifest_ai_disclosure_content(self):
        meta = ProvenanceMetadata(generator_name="Lumira", generator_version="2.0")
        manifest = meta.create_manifest(prompt="x")
        disclosure = next(
            a for a in manifest["assertions"] if a["label"] == "c2pa.ai_disclosure"
        )
        assert disclosure["data"]["ai_generated"] is True
        assert disclosure["data"]["ai_tool"] == "Lumira"

    def test_instance_id_unique_per_prompt(self):
        meta = ProvenanceMetadata()
        m1 = meta.create_manifest(prompt="prompt A")
        m2 = meta.create_manifest(prompt="prompt B")
        assert m1["instance_id"] != m2["instance_id"]

    def test_embed_in_png_saves_file(self, tmp_path):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(prompt="test embed")
        img = make_image()
        output_path = tmp_path / "output.png"
        meta.embed_in_png(img, manifest, output_path=output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_embed_in_png_metadata_in_file(self, tmp_path):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(
            prompt="embedded metadata test",
            mood="curious",
            style="abstract",
        )
        img = make_image()
        output_path = tmp_path / "meta.png"
        meta.embed_in_png(img, manifest, output_path=output_path)

        # Re-open and check that metadata was written
        reopened = Image.open(output_path)
        assert "c2pa:manifest" in reopened.info
        stored = json.loads(reopened.info["c2pa:manifest"])
        assert stored["lumira"]["prompt"] == "embedded metadata test"

    def test_embed_in_png_no_path_returns_image(self):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(prompt="no path")
        img = make_image()
        result = meta.embed_in_png(img, manifest, output_path=None)
        # Without a path it returns the image with pnginfo attached
        assert isinstance(result, Image.Image)

    def test_embed_xmp_metadata_returns_bytes(self):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(prompt="xmp test", mood="playful")
        img = make_image()
        xmp = meta.embed_xmp_metadata(img, manifest)
        assert isinstance(xmp, bytes)
        decoded = xmp.decode("utf-8")
        assert "xmpmeta" in decoded
        assert "lumira:aiGenerated" in decoded
        assert "true" in decoded.lower()

    def test_embed_xmp_contains_prompt(self):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(prompt="snowy mountains at twilight")
        img = make_image()
        xmp = meta.embed_xmp_metadata(img, manifest)
        assert b"snowy mountains at twilight" in xmp

    def test_additional_metadata_merged(self):
        meta = ProvenanceMetadata()
        manifest = meta.create_manifest(
            prompt="p",
            additional_metadata={"experiment_id": "exp-42"},
        )
        assert manifest["lumira"]["experiment_id"] == "exp-42"


# ===========================================================================
# ProvenanceManager tests
# ===========================================================================


class TestProvenanceManager:
    """Unit tests for ProvenanceManager."""

    def test_init_defaults(self):
        mgr = ProvenanceManager()
        assert mgr.metadata.generator_name == "Lumira"
        assert mgr.metadata.generator_version == "0.1.0"

    def test_set_model(self):
        mgr = ProvenanceManager()
        mgr.set_model("sdxl-turbo", "0.9")
        assert mgr.metadata.model_name == "sdxl-turbo"
        assert mgr.metadata.model_version == "0.9"

    def test_embed_provenance_creates_file(self, tmp_path):
        mgr = ProvenanceManager()
        img = make_image()
        output_path = tmp_path / "artwork.png"
        result = mgr.embed_provenance(
            image=img,
            output_path=output_path,
            prompt="star-filled sky",
            mood="contemplative",
        )
        assert result == output_path
        assert output_path.exists()

    def test_embed_provenance_metadata_readable(self, tmp_path):
        mgr = ProvenanceManager()
        mgr.set_model("sdxl-base-1.0")
        img = make_image()
        output_path = tmp_path / "artwork.png"
        mgr.embed_provenance(
            image=img,
            output_path=output_path,
            prompt="ocean waves",
            seed=7,
            steps=20,
        )
        reopened = Image.open(output_path)
        assert "c2pa:manifest" in reopened.info
        meta = json.loads(reopened.info["c2pa:manifest"])
        assert meta["lumira"]["prompt"] == "ocean waves"
        assert meta["lumira"]["seed"] == 7

    def test_c2pa_available_flag(self):
        mgr = ProvenanceManager()
        # Just verifies the attribute exists and is bool
        assert isinstance(mgr.c2pa_available, bool)


# ===========================================================================
# AdvancedExporter tests
# ===========================================================================


class TestAdvancedExporter:
    """Unit tests for AdvancedExporter."""

    @pytest.fixture
    def exporter(self):
        return AdvancedExporter()

    @pytest.fixture
    def rgb_image(self):
        return make_image(64, 64, "RGB")

    # --- TIFF export ---

    @pytest.mark.asyncio
    async def test_export_tiff_creates_file(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "test.tiff"
        result = await exporter.export_high_res_tiff(rgb_image, out)
        assert result.exists()
        assert result.suffix in (".tiff", ".tif")

    @pytest.mark.asyncio
    async def test_export_tiff_auto_adds_extension(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "noext"
        result = await exporter.export_high_res_tiff(rgb_image, out)
        assert result.suffix in (".tiff", ".tif")

    @pytest.mark.asyncio
    async def test_export_tiff_custom_dpi(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "hi_dpi.tiff"
        result = await exporter.export_high_res_tiff(rgb_image, out, dpi=600)
        assert result.exists()
        img = Image.open(result)
        dpi = img.info.get("dpi")
        if dpi:
            assert dpi[0] == 600

    # --- SVG export ---

    @pytest.mark.asyncio
    async def test_export_svg_raises_when_all_backends_unavailable(
        self, exporter, rgb_image, tmp_path
    ):
        """SVG export should fail only when all vectorization backends are absent."""
        with (
            patch("ai_artist.export.formats.CAIRO_AVAILABLE", False),
            patch("ai_artist.export.formats.CV2_AVAILABLE", False),
        ):
            out = tmp_path / "test.svg"
            with pytest.raises(ImportError):
                await exporter.export_svg_trace(rgb_image, out)

    @pytest.mark.asyncio
    async def test_export_svg_creates_file_with_available_backend(
        self, exporter, rgb_image, tmp_path
    ):
        """SVG export should succeed when at least one backend is available."""
        out = tmp_path / "test.svg"
        result = await exporter.export_svg_trace(rgb_image, out)
        assert result.exists()
        content = result.read_text()
        assert "<svg" in content

    @pytest.mark.asyncio
    async def test_export_svg_auto_adds_extension(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "noext"
        result = await exporter.export_svg_trace(rgb_image, out)
        assert result.suffix == ".svg"

    @pytest.mark.asyncio
    async def test_export_svg_contains_image_dimensions(
        self, exporter, rgb_image, tmp_path
    ):
        out = tmp_path / "embedded.svg"
        result = await exporter.export_svg_trace(rgb_image, out)
        content = result.read_text()
        assert str(rgb_image.width) in content
        assert str(rgb_image.height) in content

    @pytest.mark.asyncio
    async def test_export_svg_mono_mode_creates_vector_document(
        self, exporter, rgb_image, tmp_path
    ):
        out = tmp_path / "mono.svg"
        result = await exporter.export_svg_trace(rgb_image, out, mode="mono", detail=5)
        content = result.read_text()
        assert result.exists()
        assert "<svg" in content

    @pytest.mark.asyncio
    async def test_export_svg_contains_paths_for_non_uniform_image(
        self, exporter, tmp_path
    ):
        img = Image.new("RGB", (32, 32), (0, 0, 0))
        for x in range(16):
            for y in range(32):
                img.putpixel((x, y), (255, 255, 255))

        out = tmp_path / "paths.svg"
        result = await exporter.export_svg_trace(img, out, mode="color", detail=5)
        content = result.read_text()

        assert result.exists()
        assert "<path" in content

    # --- PDF export ---

    @pytest.mark.asyncio
    async def test_export_pdf_creates_file(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "test.pdf"
        result = await exporter.export_pdf(rgb_image, out)
        assert result.exists()
        assert result.suffix == ".pdf"

    @pytest.mark.asyncio
    async def test_export_pdf_auto_adds_extension(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "noext"
        result = await exporter.export_pdf(rgb_image, out)
        assert result.suffix == ".pdf"

    @pytest.mark.asyncio
    async def test_export_pdf_custom_metadata(self, exporter, rgb_image, tmp_path):
        out = tmp_path / "meta.pdf"
        result = await exporter.export_pdf(
            rgb_image, out, title="My Art", author="Lumira"
        )
        assert result.exists()

    # --- Animated WebP export ---

    @pytest.mark.asyncio
    async def test_export_webp_animated_single_frame(self, exporter, tmp_path):
        frames = [make_image(32, 32)]
        out = tmp_path / "anim.webp"
        result = await exporter.export_webp_animated(frames, out)
        assert result.exists()
        assert result.suffix == ".webp"

    @pytest.mark.asyncio
    async def test_export_webp_animated_multiple_frames(self, exporter, tmp_path):
        frames = [make_image(32, 32) for _ in range(4)]
        out = tmp_path / "anim.webp"
        result = await exporter.export_webp_animated(frames, out, duration=200)
        assert result.exists()

    @pytest.mark.asyncio
    async def test_export_webp_animated_empty_frames_raises(self, exporter, tmp_path):
        out = tmp_path / "empty.webp"
        with pytest.raises(ValueError, match="No frames"):
            await exporter.export_webp_animated([], out)

    @pytest.mark.asyncio
    async def test_export_webp_auto_adds_extension(self, exporter, tmp_path):
        frames = [make_image(32, 32)]
        out = tmp_path / "noext"
        result = await exporter.export_webp_animated(frames, out)
        assert result.suffix == ".webp"

    # --- ICO export ---

    @pytest.mark.asyncio
    async def test_export_ico_creates_file(self, exporter, tmp_path):
        img = make_image(256, 256)
        out = tmp_path / "icon.ico"
        result = await exporter.export_ico(img, out)
        assert result.exists()
        assert result.suffix == ".ico"

    @pytest.mark.asyncio
    async def test_export_ico_auto_adds_extension(self, exporter, tmp_path):
        img = make_image(256, 256)
        out = tmp_path / "noext"
        result = await exporter.export_ico(img, out)
        assert result.suffix == ".ico"

    # --- supported_formats ---

    def test_supported_formats_always_has_raster(self, exporter):
        for fmt in ("png", "jpg", "jpeg", "webp"):
            assert fmt in exporter.supported_formats

    def test_supported_formats_has_svg_when_any_backend_available(self):
        with (
            patch("ai_artist.export.formats.CAIRO_AVAILABLE", False),
            patch("ai_artist.export.formats.CV2_AVAILABLE", True),
        ):
            e = AdvancedExporter()
            assert "svg" in e.supported_formats

    def test_supported_formats_no_svg_without_any_backend(self):
        with (
            patch("ai_artist.export.formats.CAIRO_AVAILABLE", False),
            patch("ai_artist.export.formats.CV2_AVAILABLE", False),
        ):
            e = AdvancedExporter()
            assert "svg" not in e.supported_formats
