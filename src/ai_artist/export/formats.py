"""Advanced export formats for AI Artist."""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cairosvg  # noqa: F401

    CAIRO_AVAILABLE = True
except ImportError:
    CAIRO_AVAILABLE = False

try:
    import cv2  # noqa: F401

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from ..utils.logging import get_logger

logger = get_logger(__name__)


class AdvancedExporter:
    """Export images in advanced formats."""

    def __init__(self) -> None:
        """Initialize exporter."""
        self.supported_formats = ["png", "jpg", "jpeg", "webp"]

        if CAIRO_AVAILABLE or CV2_AVAILABLE:
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
            if not CAIRO_AVAILABLE and not CV2_AVAILABLE:
                raise ImportError(
                    "Neither cairosvg nor opencv-python is available for SVG export"
                )

            # Ensure output path has .svg extension
            if output_path.suffix.lower() != ".svg":
                output_path = output_path.with_suffix(".svg")

            # --- Try potrace binary first (best quality) ---
            if shutil.which("potrace"):
                result = self._export_svg_potrace(image, output_path, mode, detail)
                if result:
                    return result

            # --- cv2 colour-quantisation vectorisation ---
            if CV2_AVAILABLE:
                return self._export_svg_cv2(image, output_path, mode, detail)

            # --- Fallback: embed raster inside SVG wrapper ---
            return self._export_svg_embedded(image, output_path)

        except Exception as e:
            logger.error("svg_export_error", error=str(e))
            raise

    def _export_svg_potrace(
        self,
        image: Image.Image,
        output_path: Path,
        mode: str,
        detail: int,
    ) -> Path | None:
        """Vectorise using the potrace binary (highest quality).

        Returns the output path on success, None if potrace fails.
        """
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                bmp_path = Path(tmpdir) / "input.bmp"
                if mode == "mono":
                    gray = image.convert("L")
                    threshold = 256 - int(detail / 10 * 200 + 56)  # 56-256
                    bw = gray.point(lambda p: 255 if p > threshold else 0, "1")
                    bw.save(str(bmp_path))
                else:
                    image.convert("L").save(str(bmp_path), format="BMP")

                svg_tmp = Path(tmpdir) / "output.svg"
                result = subprocess.run(
                    [
                        "potrace",
                        "--svg",
                        "--turdsize",
                        str(max(1, 10 - detail)),
                        "--output",
                        str(svg_tmp),
                        str(bmp_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0 and svg_tmp.exists():
                    svg_content = svg_tmp.read_text(encoding="utf-8")
                    output_path.write_text(svg_content, encoding="utf-8")
                    logger.info(
                        "svg_potrace_success",
                        path=str(output_path),
                        mode=mode,
                    )
                    return output_path
        except Exception as e:
            logger.debug("svg_potrace_failed", error=str(e))
        return None

    def _export_svg_cv2(
        self,
        image: Image.Image,
        output_path: Path,
        mode: str,
        detail: int,
    ) -> Path:
        """Vectorise using OpenCV contour extraction.

        Quantises the image to a small colour palette, extracts per-colour
        contours, and renders them as SVG ``<path>`` elements.  This produces
        a genuine vector document rather than an embedded raster.
        """
        import cv2  # local import, cv2 availability already checked

        width, height = image.size
        n_colors = max(2, min(32, detail * 3))  # 3-30 colours for detail 1-10

        if mode == "mono":
            # Black-on-white: threshold then contour-trace
            gray_img = image.convert("L")
            img_np = np.array(gray_img)
            threshold = 256 - int(detail / 10 * 200 + 56)
            _, binary = cv2.threshold(img_np, threshold, 255, cv2.THRESH_BINARY_INV)
            paths = _contours_to_paths(binary, fill="#000000")
            bg_color = "#ffffff"
            palette_paths: list[str] = paths if paths else []
        else:
            # Colour mode: quantise then contour-trace each colour
            quantized = image.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
            rgb_quantized = quantized.convert("RGB")
            img_np = np.array(rgb_quantized)
            unique_colors = np.unique(img_np.reshape(-1, 3), axis=0)
            bg_np = img_np[0, 0]  # top-left pixel as background
            bg_color = "#{:02x}{:02x}{:02x}".format(*bg_np)
            palette_paths = []
            for color in unique_colors:
                hex_col = "#{:02x}{:02x}{:02x}".format(*color)
                mask = np.all(img_np == color, axis=2).astype(np.uint8) * 255
                paths = _contours_to_paths(mask, fill=hex_col)
                palette_paths.extend(paths)

        path_elements = "\n  ".join(palette_paths)
        svg_content = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg"\n'
            f'     width="{width}" height="{height}"\n'
            f'     viewBox="0 0 {width} {height}">\n'
            f"  <title>AI Artist Export</title>\n"
            f'  <rect width="{width}" height="{height}" fill="{bg_color}"/>\n'
            f"  {path_elements}\n"
            f"</svg>"
        )
        output_path.write_text(svg_content, encoding="utf-8")
        logger.info(
            "svg_cv2_success",
            path=str(output_path),
            mode=mode,
            colors=n_colors,
        )
        return output_path

    def _export_svg_embedded(
        self,
        image: Image.Image,
        output_path: Path,
    ) -> Path:
        """Fallback: embed a PNG raster inside an SVG wrapper."""
        import base64

        width, height = image.size
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        img_data = base64.b64encode(buffer.getvalue()).decode()

        svg_content = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg"\n'
            f'     xmlns:xlink="http://www.w3.org/1999/xlink"\n'
            f'     width="{width}" height="{height}"\n'
            f'     viewBox="0 0 {width} {height}">\n'
            f"  <title>AI Artist Export</title>\n"
            f'  <image width="{width}" height="{height}"\n'
            f'         xlink:href="data:image/png;base64,{img_data}"/>\n'
            f"</svg>"
        )
        output_path.write_text(svg_content, encoding="utf-8")
        logger.info("svg_embedded_fallback", path=str(output_path))
        return output_path

    async def export_pdf(
        self,
        image: Image.Image,
        output_path: Path,
        title: str | None = None,
        author: str = "Lumira",
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


def _contours_to_paths(
    binary_mask: "np.ndarray",
    fill: str = "#000000",
) -> list[str]:
    """Convert a binary mask to a list of SVG ``<path>`` elements.

    Uses OpenCV contour detection to trace the filled regions in
    *binary_mask* (white = foreground) and converts each contour to an
    SVG path ``d`` attribute using absolute ``M``/``L``/``Z`` commands.

    Args:
        binary_mask: uint8 numpy array where 255 marks the filled region.
        fill: CSS colour string for the SVG ``fill`` attribute.

    Returns:
        List of ``<path …/>`` SVG element strings.
    """
    import cv2  # cv2 availability checked at call site

    contours, _ = cv2.findContours(
        binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    elements: list[str] = []
    for contour in contours:
        pts = contour.reshape(-1, 2)
        if len(pts) < 2:
            continue
        coords = " L ".join(f"{x} {y}" for x, y in pts)
        d = f"M {coords} Z"
        elements.append(f'<path d="{d}" fill="{fill}"/>')
    return elements
