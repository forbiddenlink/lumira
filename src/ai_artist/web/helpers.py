"""Helper functions for the web API to keep routes clean and focused."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..gallery.manager import GalleryManager
from ..utils.logging import get_logger

logger = get_logger(__name__)


def is_valid_image(img_path: Path, gallery_path: Path) -> tuple[bool, str | None]:
    """
    Check if an image is valid and should be included in results.

    Args:
        img_path: Path to the image file
        gallery_path: Base gallery path

    Returns:
        Tuple of (is_valid, reason_if_invalid)
    """
    # Skip test images
    if "/test/" in str(img_path):
        return False, "test_image"

    # Check metadata exists
    metadata_path = img_path.with_suffix(".json")
    if not metadata_path.exists():
        return False, "no_metadata"

    try:
        # Load metadata
        metadata = json.loads(metadata_path.read_text())

        # Skip images without prompts
        prompt = metadata.get("prompt", "")
        if not prompt or not prompt.strip():
            return False, "no_prompt"

        # Check if image is corrupted or mostly black
        try:
            with Image.open(img_path) as img:
                img_array = np.array(img.convert("RGB"))
                if img_array.mean() < 10:
                    return False, "black_image"
        except Exception as e:
            return False, f"corrupted: {str(e)}"

        return True, None

    except Exception as e:
        return False, f"metadata_error: {str(e)}"


def load_image_metadata(
    img_path: Path,
    gallery_path: Path,
) -> dict | None:
    """
    Load metadata for a single image.

    Args:
        img_path: Path to the image file
        gallery_path: Base gallery path

    Returns:
        Metadata dictionary or None if invalid
    """
    try:
        metadata_path = img_path.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text())
        relative_path = img_path.relative_to(gallery_path)

        from ..utils.metadata_helpers import enrich_sidecar_metadata

        return {
            "path": str(relative_path),
            "filename": img_path.name,
            "prompt": metadata.get("prompt", ""),
            "created_at": metadata.get("created_at", ""),
            "featured": metadata.get("featured", False),
            "metadata": enrich_sidecar_metadata(metadata),
            "thumbnail_url": f"/api/images/file/{relative_path}",
            "full_url": f"/api/images/file/{relative_path}",
        }
    except Exception as e:
        logger.warning("failed_to_load_metadata", path=str(img_path), error=str(e))
        return None


def filter_by_search(
    image_paths: list[Path],
    search_term: str,
) -> list[Path]:
    """
    Filter image paths by search term in prompts.

    Args:
        image_paths: List of image paths to filter
        search_term: Search term to look for in prompts

    Returns:
        Filtered list of image paths
    """
    filtered_paths = []
    search_lower = search_term.lower()

    for img_path in image_paths:
        metadata_path = img_path.with_suffix(".json")
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text())
                if search_lower in metadata.get("prompt", "").lower():
                    filtered_paths.append(img_path)
            except Exception:
                continue

    return filtered_paths


def calculate_gallery_stats(gallery_manager: GalleryManager) -> dict:
    """
    Calculate comprehensive gallery statistics.

    Args:
        gallery_manager: Gallery manager instance

    Returns:
        Dictionary with statistics
    """
    all_images = gallery_manager.list_images(featured_only=False)
    featured_images = gallery_manager.list_images(featured_only=True)

    # Count unique prompts
    prompts = set()
    dates = []

    for img_path in all_images:
        metadata_path = img_path.with_suffix(".json")
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text())
                prompt = metadata.get("prompt", "")
                if prompt:
                    prompts.add(prompt)

                created_at = metadata.get("created_at")
                if created_at:
                    dates.append(created_at)
            except Exception:
                continue

    # Date range
    date_range = {}
    if dates:
        date_range = {
            "earliest": min(dates),
            "latest": max(dates),
        }

    return {
        "total_images": len(all_images),
        "featured_images": len(featured_images),
        "total_prompts": len(prompts),
        "date_range": date_range,
    }
