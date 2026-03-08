#!/usr/bin/env python3
"""Automated LoRA training pipeline for multiple styles."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

TRAINING_PROFILES = {
    "abstract": {
        "name": "Abstract Art",
        "dataset_dir": "datasets/training_abstract",
        "output_dir": "models/lora/abstract_style",
        "rank": 16,
        "max_train_steps": 3000,
        "learning_rate": 5e-5,
        "resolution": 512,
        "description": "Colorful, artistic compositions for creative projects",
    },
    "landscape": {
        "name": "Landscape Photography",
        "dataset_dir": "datasets/training_landscape",
        "output_dir": "models/lora/landscape_style",
        "rank": 8,
        "max_train_steps": 3000,
        "learning_rate": 1e-4,
        "resolution": 512,
        "description": "Dramatic natural scenery and outdoor photography",
    },
    "webhero": {
        "name": "Web Hero Images",
        "dataset_dir": "datasets/training_webhero",
        "output_dir": "models/lora/webhero_style",
        "rank": 8,
        "max_train_steps": 2500,
        "learning_rate": 1e-4,
        "resolution": 768,
        "description": "Professional, clean compositions for website headers (16:9)",
    },
}


def check_dataset(dataset_dir: Path) -> bool:
    """Check if dataset exists and has images."""
    if not dataset_dir.exists():
        return False

    image_files = list(dataset_dir.glob("*.jpg")) + list(dataset_dir.glob("*.png"))
    return len(image_files) >= 20


def train_lora(profile_name: str, profile: dict):
    """Train a LoRA with specified profile."""
    print()
    print("=" * 80)
    print(f"🎨 Training: {profile['name']}")
    print("=" * 80)
    print(f"Description: {profile['description']}")
    print(f"Dataset: {profile['dataset_dir']}")
    print(f"Output: {profile['output_dir']}")
    print(f"Rank: {profile['rank']}")
    print(f"Steps: {profile['max_train_steps']}")
    print(f"Learning Rate: {profile['learning_rate']}")
    print(f"Resolution: {profile['resolution']}")
    print()

    # Check if dataset exists
    dataset_path = Path(profile["dataset_dir"])
    if not check_dataset(dataset_path):
        print(f"❌ Dataset not found or insufficient images: {dataset_path}")
        print(
            f"   Download with: python scripts/download_specialized_datasets.py {profile_name}"
        )
        return False

    # Count images
    image_files = list(dataset_path.glob("*.jpg")) + list(dataset_path.glob("*.png"))
    print(f"✓ Found {len(image_files)} training images")
    print()

    # Create output directory
    output_path = Path(profile["output_dir"])
    output_path.mkdir(parents=True, exist_ok=True)

    # Build training command
    cmd = [
        sys.executable,
        "-m",
        "ai_artist.training.train_lora",
        "--instance_data_dir",
        str(dataset_path),
        "--output_dir",
        str(output_path),
        "--rank",
        str(profile["rank"]),
        "--max_train_steps",
        str(profile["max_train_steps"]),
        "--learning_rate",
        str(profile["learning_rate"]),
        "--resolution",
        str(profile["resolution"]),
        "--train_batch_size",
        "1",
        "--gradient_accumulation_steps",
        "4",
    ]

    print("🚀 Starting training...")
    print(f"Command: {' '.join(cmd)}")
    print()

    start_time = time.time()

    try:
        subprocess.run(cmd, check=True)
        elapsed = time.time() - start_time

        print()
        print(f"✅ Training completed in {elapsed / 60:.1f} minutes!")
        print(f"   Model saved to: {output_path}")
        print()
        return True

    except subprocess.CalledProcessError as e:
        print()
        print(f"❌ Training failed with error code {e.returncode}")
        return False
    except KeyboardInterrupt:
        print()
        print("⚠️  Training interrupted by user")
        return False


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Automated LoRA training pipeline")
    parser.add_argument(
        "profile",
        nargs="?",
        choices=list(TRAINING_PROFILES.keys()) + ["all"],
        help="Training profile to use (or 'all' for sequential training)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available training profiles"
    )

    args = parser.parse_args()

    if args.list or not args.profile:
        print("🎨 Available Training Profiles:")
        print("=" * 80)
        print()
        for profile_name, profile in TRAINING_PROFILES.items():
            print(f"Profile: {profile_name}")
            print(f"  Name: {profile['name']}")
            print(f"  Description: {profile['description']}")
            print(f"  Dataset: {profile['dataset_dir']}")
            print(f"  Output: {profile['output_dir']}")
            print(
                f"  Parameters: rank={profile['rank']}, steps={profile['max_train_steps']}"
            )

            # Check if dataset exists
            dataset_path = Path(profile["dataset_dir"])
            if check_dataset(dataset_path):
                image_count = len(
                    list(dataset_path.glob("*.jpg")) + list(dataset_path.glob("*.png"))
                )
                print(f"  Status: ✅ Ready ({image_count} images)")
            else:
                print("  Status: ⚠️  Dataset not found")
                print(
                    f"  Download: python scripts/download_specialized_datasets.py {profile_name}"
                )
            print()

        print("Usage:")
        print("  python scripts/train_all_loras.py <profile>  # Train specific profile")
        print("  python scripts/train_all_loras.py all        # Train all profiles")
        return

    print("🎨 AI Artist - LoRA Training Pipeline")
    print("=" * 80)

    if args.profile == "all":
        print("📦 Training ALL profiles sequentially...")
        print("   This will take several hours depending on your hardware.")
        print()

        input("Press Enter to continue or Ctrl+C to cancel...")

        results = {}
        for profile_name, profile in TRAINING_PROFILES.items():
            success = train_lora(profile_name, profile)
            results[profile_name] = success

        # Summary
        print()
        print("=" * 80)
        print("🎯 Training Summary:")
        print("=" * 80)
        for profile_name, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"{TRAINING_PROFILES[profile_name]['name']}: {status}")

    else:
        profile = TRAINING_PROFILES[args.profile]
        success = train_lora(args.profile, profile)

        if success:
            print()
            print("Next steps:")
            print("1. Activate this LoRA:")
            print(f"   python scripts/manage_loras.py set {args.profile}_style")
            print()
            print("2. Generate images:")
            print("   lumira")


if __name__ == "__main__":
    main()
