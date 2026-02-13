"""Advanced export formats for AI Artist."""

import io
from pathlib import Path

from PIL import Image

try:
    import cairosvg  # noqa: F401

    CAIRO_AVAILABLE = True
except ImportError:
    CAIRO_AVAILABLE = False

from ..utils.logging import get_logger

logger = get_logger(__name__)


class AdvancedExporter:
    """Export images in advanced formats."""

    def __init__(self) -> None:
        """Initialize exporter."""
        self.supported_formats = ["png", "jpg", "jpeg", "webp"]

        if CAIRO_AVAILABLE:
            self.supported_formats.append("svg")

    async def export_high_res_tiff(
        self,
        image: Image.Image,
        output_path: Path,
        dpi: int = 300,
        compression: str = "tiff_lzw",
    ) -> Path:
        """Export image as high-resolution TIFF.

        Args:
            image: PIL Image to export
            output_path: Output file path
            dpi: Dots per inch (default: 300 for print quality)
            compression: TIFF compression method

        Returns:
            Path to exported file
        """
        try:
            # Ensure output path has .tiff extension
            if output_path.suffix.lower() not in [".tif", ".tiff"]:
                output_path = output_path.with_suffix(".tiff")

            # Save with high quality settings
            image.save(
                output_path,
                format="TIFF",
                compression=compression,
                dpi=(dpi, dpi),
            )

            logger.info(
                "tiff_export_success",
                path=str(output_path),
                dpi=dpi,
                size=image.size,
            )

            return output_path

        except Exception as e:
            logger.error("tiff_export_error", error=str(e))
            raise

    async def export_svg_trace(
        self,
        image: Image.Image,
        output_path: Path,
        mode: str = "color",
        detail: int = 5,
    ) -> Path:
        """Export image as SVG using vectorization.

        Args:
            image: PIL Image to export
            output_path: Output file path
            mode: Trace mode ('color' or 'mono')
            detail: Detail level (1-10, higher = more detail)

        Returns:
            Path to exported SVG file
        """
        try:
            # This is a placeholder for proper SVG vectorization
            # In production, you'd use potrace, autotrace, or similar
            if not CAIRO_AVAILABLE:
                raise ImportError("cairosvg not available for SVG export")

            # Ensure output path has .svg extension
            if output_path.suffix.lower() != ".svg":
                output_path = output_path.with_suffix(".svg")

            # Simplified SVG embedding (replace with proper vectorization)
            width, height = image.size

            # Convert image to base64 for embedding
            import base64

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            img_data = base64.b64encode(buffer.getvalue()).decode()

            # Create SVG with embedded raster image
            # TODO: Implement proper vectorization using potrace
            svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{width}" height="{height}"
     viewBox="0 0 {width} {height}">
    <title>AI Artist Export</title>
    <image width="{width}" height="{height}"
           xlink:href="data:image/png;base64,{img_data}"/>
</svg>"""

            output_path.write_text(svg_content)

            logger.info(
                "svg_export_success",
                path=str(output_path),
                mode=mode,
                detail=detail,
            )

            return output_path

        except Exception as e:
            logger.error("svg_export_error", error=str(e))
            raise

    async def export_pdf(
        self,
        image: Image.Image,
        output_path: Path,
        title: str | None = None,
        author: str = "AI Artist (Aria)",
    ) -> Path:
        """Export image as PDF with metadata.

        Args:
            image: PIL Image to export
            output_path: Output file path
            title: PDF title metadata
            author: PDF author metadata

        Returns:
            Path to exported PDF file
        """
        try:
            # Ensure output path has .pdf extension
            if output_path.suffix.lower() != ".pdf":
                output_path = output_path.with_suffix(".pdf")

            # PIL can save directly to PDF
            image.save(
                output_path,
                format="PDF",
                resolution=100.0,
                title=title or "AI Generated Artwork",
                author=author,
            )

            logger.info(
                "pdf_export_success",
                path=str(output_path),
                title=title,
            )

            return output_path

        except Exception as e:
            logger.error("pdf_export_error", error=str(e))
            raise

    async def export_webp_animated(
        self,
        frames: list[Image.Image],
        output_path: Path,
        duration: int = 100,
        loop: int = 0,
    ) -> Path:
        """Export frames as animated WebP.

        Args:
            frames: List of PIL Images
            output_path: Output file path
            duration: Frame duration in milliseconds
            loop: Loop count (0 = infinite)

        Returns:
            Path to exported WebP file
        """
        try:
            if not frames:
                raise ValueError("No frames provided")

            # Ensure output path has .webp extension
            if output_path.suffix.lower() != ".webp":
                output_path = output_path.with_suffix(".webp")

            # Save first frame with append_images
            frames[0].save(
                output_path,
                format="WEBP",
                save_all=True,
                append_images=frames[1:] if len(frames) > 1 else [],
                duration=duration,
                loop=loop,
                lossless=False,
                quality=90,
                method=6,  # Best compression
            )

            logger.info(
                "webp_animated_export_success",
                path=str(output_path),
                frames=len(frames),
                duration=duration,
            )

            return output_path

        except Exception as e:
            logger.error("webp_animated_export_error", error=str(e))
            raise

    async def export_ico(
        self,
        image: Image.Image,
        output_path: Path,
        sizes: list[tuple[int, int]] | None = None,
    ) -> Path:
        """Export image as multi-resolution ICO file.

        Args:
            image: PIL Image to export
            output_path: Output file path
            sizes: List of icon sizes (default: common Windows sizes)

        Returns:
            Path to exported ICO file
        """
        try:
            if sizes is None:
                sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

            # Ensure output path has .ico extension
            if output_path.suffix.lower() != ".ico":
                output_path = output_path.with_suffix(".ico")

            # Create resized versions
            resized_images = [
                image.resize(size, Image.Resampling.LANCZOS) for size in sizes
            ]

            # Save as ICO
            resized_images[0].save(
                output_path,
                format="ICO",
                sizes=[img.size for img in resized_images],
                append_images=resized_images[1:],
            )

            logger.info(
                "ico_export_success",
                path=str(output_path),
                sizes=sizes,
            )

            return output_path

        except Exception as e:
            logger.error("ico_export_error", error=str(e))
            raise


def get_exporter() -> AdvancedExporter:
    """Get advanced exporter instance.

    Returns:
        AdvancedExporter instance
    """
    return AdvancedExporter()
