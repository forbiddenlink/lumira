#!/usr/bin/env python3
"""Train Lumira LoRA using Replicate's FLUX LoRA training.

This script:
1. Creates a ZIP of training images
2. Uploads to Replicate
3. Starts LoRA training
4. Monitors progress
5. Downloads the trained model

Usage:
    python scripts/train_lora_replicate.py --data data/lora_training

Requirements:
    - REPLICATE_API_TOKEN environment variable
    - Training data prepared via prepare_lora_training.py

Cost: ~$2-5 for 30 images, 1000 steps
Time: 15-45 minutes
"""

import argparse
import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import replicate


def create_training_zip(data_dir: Path) -> Path:
    """Create a ZIP file of training data for upload."""
    images_dir = data_dir / "images"

    # Create temp zip
    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)  # Close the file descriptor, we'll write via ZipFile
    zip_path = Path(tmp_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img_file in images_dir.glob("*.png"):
            zf.write(img_file, img_file.name)
            # Include caption file
            caption_file = img_file.with_suffix(".txt")
            if caption_file.exists():
                zf.write(caption_file, caption_file.name)

    print(f"Created training ZIP: {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB)")
    return zip_path


def start_training(
    zip_path: Path,
    trigger_word: str = "lumira style",
    steps: int = 1000,
    model_name: str = "lumira-style-v1",
) -> str:
    """Start LoRA training on Replicate.

    Returns the training ID.
    """
    print("\nStarting FLUX LoRA training...")
    print(f"  Trigger word: {trigger_word}")
    print(f"  Steps: {steps}")
    print(f"  Model name: {model_name}")

    # Upload the ZIP file
    with open(zip_path, "rb") as f:
        training = replicate.trainings.create(
            # FLUX LoRA trainer
            version="ostris/flux-dev-lora-trainer:4ffd32160efd92e956d39c5338a9b8fbafca58e03f791f6d8011f3e20e8ea6fa",
            input={
                "input_images": f,
                "trigger_word": trigger_word,
                "steps": steps,
                "lora_rank": 16,
                "optimizer": "adamw8bit",
                "batch_size": 1,
                "resolution": "512,768,1024",
                "autocaption": False,  # We provide our own captions
                "learning_rate": 0.0004,
            },
            destination=f"liztacular/{model_name}",
        )

    print("\nTraining started!")
    print(f"  Training ID: {training.id}")
    print(f"  Status: {training.status}")
    print(f"  URL: https://replicate.com/p/{training.id}")

    return training.id


def monitor_training(training_id: str, poll_interval: int = 30) -> dict:
    """Monitor training progress until completion."""
    print(f"\nMonitoring training {training_id}...")

    while True:
        training = replicate.trainings.get(training_id)
        status = training.status

        if status == "succeeded":
            print("\n✓ Training completed successfully!")
            print(f"  Model: {training.output.get('version', 'unknown')}")
            return {
                "status": "succeeded",
                "model_version": training.output.get("version"),
                "weights_url": training.output.get("weights"),
            }

        elif status == "failed":
            print("\n✗ Training failed!")
            print(f"  Error: {training.error}")
            return {"status": "failed", "error": training.error}

        elif status == "canceled":
            print("\n✗ Training was canceled")
            return {"status": "canceled"}

        else:
            # Still processing
            logs = training.logs or ""
            last_line = logs.strip().split("\n")[-1] if logs else "Starting..."
            print(f"  [{status}] {last_line[:80]}")
            time.sleep(poll_interval)


def save_model_info(result: dict, output_dir: Path):
    """Save trained model information."""
    info_path = output_dir / "trained_model.json"
    info_path.write_text(json.dumps(result, indent=2))
    print(f"\nModel info saved to: {info_path}")


def main():
    parser = argparse.ArgumentParser(description="Train Lumira LoRA using Replicate")
    parser.add_argument(
        "--data",
        "-d",
        type=Path,
        default=Path("data/lora_training"),
        help="Training data directory",
    )
    parser.add_argument(
        "--steps",
        "-s",
        type=int,
        default=1000,
        help="Training steps (default: 1000)",
    )
    parser.add_argument(
        "--name",
        "-n",
        type=str,
        default="lumira-style-v1",
        help="Model name on Replicate",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Start training but don't wait for completion",
    )
    args = parser.parse_args()

    # Verify API token
    if not os.environ.get("REPLICATE_API_TOKEN"):
        print("Error: REPLICATE_API_TOKEN environment variable not set")
        print("Get your token at: https://replicate.com/account/api-tokens")
        return 1

    # Verify training data
    if not args.data.exists():
        print(f"Error: Training data not found at {args.data}")
        print("Run: python scripts/prepare_lora_training.py first")
        return 1

    # Load metadata
    metadata_path = args.data / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        trigger_word = metadata.get("trigger_word", "lumira style")
        print(f"Loaded training metadata: {metadata.get('image_count', 0)} images")
    else:
        trigger_word = "lumira style"

    # Create ZIP
    zip_path = create_training_zip(args.data)

    try:
        # Start training
        training_id = start_training(
            zip_path=zip_path,
            trigger_word=trigger_word,
            steps=args.steps,
            model_name=args.name,
        )

        if args.no_monitor:
            print("\nTraining started in background.")
            print(f"Check progress at: https://replicate.com/p/{training_id}")
            return 0

        # Monitor until completion
        result = monitor_training(training_id)
        save_model_info(result, args.data)

        if result["status"] == "succeeded":
            print("\n" + "=" * 60)
            print("LoRA training complete!")
            print(f"  Model: liztacular/{args.name}")
            print(f"  Trigger word: {trigger_word}")
            print("\nTo use in generations:")
            print(f'  lora_url = "{result.get("weights_url", "")}"')
            print("=" * 60)
            return 0
        else:
            return 1

    finally:
        # Cleanup temp zip
        if zip_path.exists():
            zip_path.unlink()


if __name__ == "__main__":
    exit(main())
