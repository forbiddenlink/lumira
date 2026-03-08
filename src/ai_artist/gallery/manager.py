"""Gallery management for storing generated images.

Enhanced with:
- Comprehensive EXIF-style metadata embedding in PNG chunks
- Full reproducibility information (seed, model, parameters)
- Mood, style axes, and experience level tracking
- Metadata extraction utilities
- C2PA content provenance (EU AI Act compliance)
"""

import contextlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin

from ..curation.curator import is_black_or_blank
from ..export.provenance import ProvenanceManager
from ..utils.logging import get_logger

logger = get_logger(__name__)


# Standard PNG text chunk keys for AI art metadata
METADATA_KEYS = {
    "prompt": "prompt",
    "negative_prompt": "negative_prompt",
    "seed": "seed",
    "model": "model",
    "model_hash": "model_hash",
    "lora": "lora",
    "lora_scale": "lora_scale",
    "steps": "steps",
    "cfg_scale": "cfg_scale",
    "width": "width",
    "height": "height",
    "sampler": "sampler",
    "mood": "lumira_mood",
    "mood_intensity": "lumira_mood_intensity",
    "energy": "lumira_energy",
    "style_axes": "lumira_style_axes",
    "experience_level": "lumira_level",
    "experience_title": "lumira_title",
    "aesthetic_score": "lumira_aesthetic_score",
    "clip_score": "lumira_clip_score",
    "critique": "lumira_critique",
}


class GalleryManager:
    """Manage gallery storage and organization."""

    def __init__(self, gallery_path: Path, enable_c2pa: bool = True):
        """Initialize gallery manager.

        Args:
            gallery_path: Path to gallery directory
            enable_c2pa: Enable C2PA provenance metadata embedding
        """
        self.gallery_path = gallery_path
        self.gallery_path.mkdir(parents=True, exist_ok=True)
        self.enable_c2pa = enable_c2pa
        self._provenance_manager: ProvenanceManager | None = None

    @property
    def provenance_manager(self) -> ProvenanceManager:
        """Lazy-loaded provenance manager."""
        if self._provenance_manager is None:
            self._provenance_manager = ProvenanceManager()
        return self._provenance_manager

    def save_image(
        self,
        image: Image.Image,
        prompt: str,
        metadata: dict[str, Any],
        featured: bool = False,
        lumira_state: dict[str, Any] | None = None,
    ) -> Path:
        """Save image with comprehensive metadata for reproducibility.

        Args:
            image: PIL Image to save
            prompt: The generation prompt
            metadata: Generation parameters (seed, steps, cfg, model, etc.)
            featured: Whether this is a featured/high-quality piece
            lumira_state: Optional Lumira personality state (mood, style_axes, experience)

        Returns:
            Path to saved image
        """
        # Create directory structure: year/month/day
        now = datetime.now()
        save_dir = (
            self.gallery_path / f"{now.year}" / f"{now.month:02d}" / f"{now.day:02d}"
        )

        save_dir = save_dir / "featured" if featured else save_dir / "archive"

        save_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{metadata.get('seed', 'noseed')}.png"
        image_path = save_dir / filename

        # Build comprehensive PNG metadata
        pnginfo = PngImagePlugin.PngInfo()

        # Core generation parameters
        pnginfo.add_text("prompt", prompt)
        pnginfo.add_text("negative_prompt", metadata.get("negative_prompt", ""))
        pnginfo.add_text("seed", str(metadata.get("seed", "")))
        pnginfo.add_text("model", metadata.get("model", ""))
        pnginfo.add_text("model_hash", metadata.get("model_hash", ""))
        pnginfo.add_text("steps", str(metadata.get("steps", "")))
        pnginfo.add_text(
            "cfg_scale",
            str(metadata.get("guidance_scale", metadata.get("cfg_scale", ""))),
        )
        pnginfo.add_text("width", str(metadata.get("width", image.width)))
        pnginfo.add_text("height", str(metadata.get("height", image.height)))
        pnginfo.add_text(
            "sampler", metadata.get("sampler", metadata.get("scheduler", ""))
        )

        # LoRA information
        if metadata.get("lora"):
            pnginfo.add_text("lora", metadata["lora"])
            pnginfo.add_text("lora_scale", str(metadata.get("lora_scale", 0.8)))

        # Lumira personality state (for reproducibility and analysis)
        if lumira_state:
            pnginfo.add_text("lumira_mood", lumira_state.get("mood", ""))
            pnginfo.add_text(
                "lumira_mood_intensity", str(lumira_state.get("mood_intensity", ""))
            )
            pnginfo.add_text("lumira_energy", str(lumira_state.get("energy", "")))

            # Style axes as JSON
            if lumira_state.get("style_axes"):
                pnginfo.add_text(
                    "lumira_style_axes", json.dumps(lumira_state["style_axes"])
                )

            # Experience level
            pnginfo.add_text("lumira_level", str(lumira_state.get("level", 1)))
            pnginfo.add_text("lumira_title", lumira_state.get("title", ""))

            # Quality scores
            if lumira_state.get("aesthetic_score"):
                pnginfo.add_text(
                    "lumira_aesthetic_score", str(lumira_state["aesthetic_score"])
                )
            if lumira_state.get("clip_score"):
                pnginfo.add_text("lumira_clip_score", str(lumira_state["clip_score"]))

            # Critique summary
            if lumira_state.get("critique"):
                pnginfo.add_text(
                    "lumira_critique", lumira_state["critique"][:500]
                )  # Limit length

        # Full metadata as JSON (backup/detailed)
        pnginfo.add_text("metadata", json.dumps(metadata))

        # EU AI Act compliance
        pnginfo.add_text("AI-Generated", "true")
        pnginfo.add_text("generator", "LUMIRA - Autonomous AI Artist")
        pnginfo.add_text("generation_timestamp", now.isoformat())

        # Save image with basic PNG metadata
        image.save(image_path, pnginfo=pnginfo)

        # Embed C2PA provenance metadata (EU AI Act compliance)
        if self.enable_c2pa:
            try:
                self.provenance_manager.set_model(
                    model_name=metadata.get("model", "unknown"),
                    model_version=metadata.get("model_version"),
                )
                self.provenance_manager.embed_provenance(
                    image=image,
                    output_path=image_path,
                    prompt=prompt,
                    negative_prompt=metadata.get("negative_prompt", ""),
                    seed=metadata.get("seed"),
                    steps=metadata.get("steps"),
                    guidance_scale=metadata.get(
                        "guidance_scale", metadata.get("cfg_scale")
                    ),
                    mood=lumira_state.get("mood") if lumira_state else None,
                    style=lumira_state.get("style") if lumira_state else None,
                    featured=featured,
                    aesthetic_score=(
                        lumira_state.get("aesthetic_score") if lumira_state else None
                    ),
                )
                logger.debug("c2pa_provenance_embedded", path=str(image_path))
            except Exception as e:
                logger.warning(
                    "c2pa_provenance_failed",
                    path=str(image_path),
                    error=str(e),
                    message="Image saved without C2PA provenance",
                )

        # Save sidecar metadata file (human-readable, complete)
        sidecar_data = {
            "prompt": prompt,
            "negative_prompt": metadata.get("negative_prompt", ""),
            "generation_params": {
                "seed": metadata.get("seed"),
                "steps": metadata.get("steps"),
                "cfg_scale": metadata.get("guidance_scale", metadata.get("cfg_scale")),
                "width": metadata.get("width", image.width),
                "height": metadata.get("height", image.height),
                "sampler": metadata.get("sampler", metadata.get("scheduler")),
                "model": metadata.get("model"),
                "lora": metadata.get("lora"),
                "lora_scale": metadata.get("lora_scale"),
            },
            "lumira_state": lumira_state or {},
            "created_at": now.isoformat(),
            "featured": featured,
            "reproducibility_hash": self._generate_reproducibility_hash(
                prompt, metadata
            ),
        }

        metadata_path = image_path.with_suffix(".json")
        metadata_path.write_text(json.dumps(sidecar_data, indent=2, default=str))

        logger.info(
            "image_saved",
            path=str(image_path),
            featured=featured,
            has_lumira_state=lumira_state is not None,
        )

        return image_path

    def _generate_reproducibility_hash(self, prompt: str, metadata: dict) -> str:
        """Generate a hash for reproducibility verification."""
        import hashlib

        key_params = f"{prompt}|{metadata.get('seed')}|{metadata.get('model')}|{metadata.get('steps')}"
        return hashlib.sha256(key_params.encode()).hexdigest()[:16]

    @staticmethod
    def extract_metadata(image_path: Path) -> dict[str, Any]:
        """Extract all metadata from a saved image.

        Args:
            image_path: Path to PNG image

        Returns:
            Dict with all embedded metadata
        """
        metadata: dict[str, Any] = {
            "prompt": "",
            "generation_params": {},
            "lumira_state": {},
            "raw_metadata": {},
        }

        try:
            with Image.open(image_path) as img:
                if hasattr(img, "text"):
                    png_text = img.text

                    # Extract prompt
                    metadata["prompt"] = png_text.get("prompt", "")
                    metadata["negative_prompt"] = png_text.get("negative_prompt", "")

                    # Extract generation params
                    metadata["generation_params"] = {
                        "seed": png_text.get("seed"),
                        "model": png_text.get("model"),
                        "steps": png_text.get("steps"),
                        "cfg_scale": png_text.get("cfg_scale"),
                        "sampler": png_text.get("sampler"),
                        "width": png_text.get("width"),
                        "height": png_text.get("height"),
                        "lora": png_text.get("lora"),
                        "lora_scale": png_text.get("lora_scale"),
                    }

                    # Extract Lumira state
                    metadata["lumira_state"] = {
                        "mood": png_text.get("lumira_mood"),
                        "mood_intensity": png_text.get("lumira_mood_intensity"),
                        "energy": png_text.get("lumira_energy"),
                        "level": png_text.get("lumira_level"),
                        "title": png_text.get("lumira_title"),
                        "aesthetic_score": png_text.get("lumira_aesthetic_score"),
                        "clip_score": png_text.get("lumira_clip_score"),
                        "critique": png_text.get("lumira_critique"),
                    }

                    # Parse style axes if present
                    if png_text.get("lumira_style_axes"):
                        with contextlib.suppress(json.JSONDecodeError):
                            metadata["lumira_state"]["style_axes"] = json.loads(
                                png_text["lumira_style_axes"]
                            )

                    # Full metadata JSON if present
                    if png_text.get("metadata"):
                        with contextlib.suppress(json.JSONDecodeError):
                            metadata["raw_metadata"] = json.loads(png_text["metadata"])

        except Exception as e:
            logger.error(
                "metadata_extraction_failed", path=str(image_path), error=str(e)
            )

        return metadata

    def list_images(self, featured_only: bool = False) -> list[Path]:
        """List all images in gallery, sorted by modification time (newest first)."""
        pattern = "**/featured/*.png" if featured_only else "**/*.png"
        images = list(self.gallery_path.glob(pattern))
        # Sort by modification time, newest first
        return sorted(images, key=lambda p: p.stat().st_mtime, reverse=True)

    def cleanup_invalid_images(
        self, dry_run: bool = False
    ) -> dict[str, int | list[str]]:
        """Scan gallery and remove black/blank/invalid images.

        Args:
            dry_run: If True, only report what would be deleted without deleting

        Returns:
            Dict with cleanup statistics
        """
        # Track statistics with proper types
        scanned = 0
        deleted = 0
        errors = 0
        deleted_files: list[str] = []
        error_files: list[str] = []

        all_images = self.list_images()
        logger.info("cleanup_starting", total_images=len(all_images), dry_run=dry_run)

        for img_path in all_images:
            scanned += 1

            try:
                # Load and check image
                with Image.open(img_path) as img:
                    is_invalid, reason = is_black_or_blank(img)

                if is_invalid:
                    logger.info(
                        "cleanup_found_invalid",
                        path=str(img_path),
                        reason=reason,
                        dry_run=dry_run,
                    )

                    if not dry_run:
                        # Delete image file
                        img_path.unlink()

                        # Delete associated metadata JSON
                        metadata_path = img_path.with_suffix(".json")
                        if metadata_path.exists():
                            metadata_path.unlink()

                    deleted += 1
                    deleted_files.append(str(img_path))

            except Exception as e:
                logger.error("cleanup_error", path=str(img_path), error=str(e))
                errors += 1
                error_files.append(str(img_path))

        logger.info(
            "cleanup_complete",
            scanned=scanned,
            deleted=deleted,
            errors=errors,
            dry_run=dry_run,
        )

        return {
            "scanned": scanned,
            "deleted": deleted,
            "errors": errors,
            "deleted_files": deleted_files,
            "error_files": error_files,
        }
