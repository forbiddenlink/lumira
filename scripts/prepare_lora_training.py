#!/usr/bin/env python3
"""Prepare training data for Lumira LoRA fine-tuning.

Selects diverse images from the gallery and prepares them with captions
for FLUX LoRA training via Replicate or local training.

Usage:
    python scripts/prepare_lora_training.py --output data/lora_training --count 30
"""

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

from ai_artist.db.models import GeneratedImage
from ai_artist.db.session import get_session_factory


def get_diverse_images(count: int = 30) -> list[dict]:
    """Select diverse images across subjects, styles, and moods.

    Uses a balanced selection strategy to ensure variety in the training set.
    """
    factory = get_session_factory()
    if not factory:
        print("Database not configured, falling back to JSON metadata")
        return get_images_from_json(count)

    with factory() as db:
        all_images = (
            db.query(GeneratedImage).filter(GeneratedImage.filename.isnot(None)).all()
        )

        # Group by subject for diversity
        by_subject: dict[str, list] = defaultdict(list)
        for img in all_images:
            subject = "unknown"
            if img.generation_params:
                subject = img.generation_params.get("subject", "unknown")
            by_subject[subject].append(img)

        # Select images ensuring diversity
        selected = []
        subjects = list(by_subject.keys())
        idx = 0

        while len(selected) < count and subjects:
            subject = subjects[idx % len(subjects)]
            if by_subject[subject]:
                img = by_subject[subject].pop(0)
                selected.append(
                    {
                        "filename": img.filename,
                        "prompt": img.prompt,
                        "subject": subject,
                        "style": (
                            img.generation_params.get("style", "")
                            if img.generation_params
                            else ""
                        ),
                        "mood": img.status or "",  # mood stored in status field
                    }
                )
                if not by_subject[subject]:
                    subjects.remove(subject)
            idx += 1

        return selected


def get_images_from_json(count: int = 30) -> list[dict]:
    """Fallback: get images from JSON metadata files."""
    gallery = Path("gallery")
    json_files = list(gallery.rglob("*.json"))

    selected = []
    for jf in json_files[:count]:
        try:
            data = json.loads(jf.read_text())
            png_file = jf.with_suffix(".png")
            if png_file.exists():
                selected.append(
                    {
                        "filename": str(png_file),
                        "prompt": data.get("prompt", ""),
                        "subject": data.get("metadata", {}).get("subject", ""),
                        "style": data.get("metadata", {}).get("style", ""),
                        "mood": data.get("metadata", {}).get("mood", ""),
                    }
                )
        except Exception:
            continue

    return selected


def generate_caption(image_data: dict) -> str:
    """Generate a training caption for an image.

    Format optimized for FLUX LoRA training.
    """
    parts = ["lumira style"]  # Trigger word

    if image_data.get("subject"):
        parts.append(image_data["subject"])

    if image_data.get("style"):
        parts.append(image_data["style"])

    if image_data.get("mood"):
        parts.append(f"{image_data['mood']} atmosphere")

    # Add quality descriptors
    parts.extend(["masterpiece", "highly detailed", "artistic"])

    return ", ".join(parts)


def prepare_training_data(
    output_dir: Path,
    count: int = 30,
    min_size: int = 512,
) -> dict:
    """Prepare training data directory structure.

    Creates:
        output_dir/
            images/
                image_001.png
                image_001.txt  (caption)
                ...
            metadata.json

    Returns metadata dict with training info.
    """
    output_dir = Path(output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Get diverse images
    images = get_diverse_images(count)
    print(f"Selected {len(images)} images for training")

    prepared = []
    for i, img_data in enumerate(images):
        src_path = Path(img_data["filename"])
        if not src_path.exists():
            print(f"  Skipping missing: {src_path}")
            continue

        # Copy image
        dest_name = f"image_{i:03d}.png"
        dest_path = images_dir / dest_name
        shutil.copy2(src_path, dest_path)

        # Generate and save caption
        caption = generate_caption(img_data)
        caption_path = images_dir / f"image_{i:03d}.txt"
        caption_path.write_text(caption)

        prepared.append(
            {
                "image": dest_name,
                "caption": caption,
                "original": str(src_path),
                "subject": img_data.get("subject", ""),
                "style": img_data.get("style", ""),
                "mood": img_data.get("mood", ""),
            }
        )

        print(f"  Prepared: {dest_name} - {img_data.get('subject', 'unknown')}")

    # Save metadata
    metadata = {
        "trigger_word": "lumira style",
        "image_count": len(prepared),
        "images": prepared,
        "training_config": {
            "steps": 1000,
            "learning_rate": 1e-4,
            "batch_size": 1,
            "resolution": 1024,
            "model": "black-forest-labs/FLUX.1-dev",
        },
    }

    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    print(f"\nTraining data prepared in: {output_dir}")
    print(f"  Images: {len(prepared)}")
    print("  Trigger word: 'lumira style'")
    print("\nNext steps:")
    print(f"  1. Review images in {images_dir}")
    print("  2. Run training via Replicate or local")

    return metadata


def main():
    parser = argparse.ArgumentParser(
        description="Prepare training data for Lumira LoRA"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("data/lora_training"),
        help="Output directory for training data",
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=30,
        help="Number of images to select (default: 30)",
    )
    args = parser.parse_args()

    prepare_training_data(args.output, args.count)


if __name__ == "__main__":
    main()
