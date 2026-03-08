#!/usr/bin/env python3
"""Upload images from local gallery to Railway deployment.

This script scans the local gallery directory and uploads new images
to your Railway deployment via the admin API endpoint.

Usage:
    # Upload all images from last 7 days
    python scripts/upload_to_railway.py

    # Upload all images
    python scripts/upload_to_railway.py --all

    # Upload specific directory
    python scripts/upload_to_railway.py --directory gallery/2026/01

    # Dry run (show what would be uploaded)
    python scripts/upload_to_railway.py --dry-run

Requirements:
    - Set RAILWAY_API_KEY environment variable or pass via --api-key
    - Railway deployment must be running with admin endpoints enabled
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx


def load_metadata(image_path: Path) -> dict:
    """Load metadata JSON file for an image."""
    metadata_path = image_path.with_suffix(".json")
    if metadata_path.exists():
        with open(metadata_path) as f:
            return json.load(f)
    return {}


def should_upload(image_path: Path, days: int | None = None) -> bool:
    """Check if image should be uploaded based on modification time."""
    if days is None:
        return True

    mod_time = datetime.fromtimestamp(image_path.stat().st_mtime)
    cutoff = datetime.now() - timedelta(days=days)
    return mod_time > cutoff


def upload_image(
    image_path: Path, railway_url: str, api_key: str, dry_run: bool = False
) -> dict:
    """Upload a single image to Railway."""
    # Load metadata
    metadata = load_metadata(image_path)

    # Prepare upload data
    with open(image_path, "rb") as f:
        files = {"image": (image_path.name, f.read(), "image/png")}

    data = {}
    if metadata:
        data["metadata"] = json.dumps(metadata)

    if dry_run:
        print(f"  [DRY RUN] Would upload: {image_path.name}")
        if metadata:
            print(f"    Metadata: {metadata.get('prompt', 'N/A')[:50]}...")
        return {"status": "dry_run", "path": str(image_path)}

    # Upload
    headers = {"X-API-Key": api_key}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{railway_url}/api/admin/upload-image",
                files=files,
                data=data,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        return {"error": str(e), "path": str(image_path)}
    finally:
        files["image"][1].close()


def upload_batch(
    image_paths: list[Path], railway_url: str, api_key: str, batch_size: int = 10
) -> dict:
    """Upload multiple images in batches."""
    total = len(image_paths)
    success = 0
    errors = []

    for i in range(0, total, batch_size):
        batch = image_paths[i : i + batch_size]
        print(
            f"\nUploading batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size}..."
        )

        for image_path in batch:
            result = upload_image(image_path, railway_url, api_key, dry_run=False)

            if "error" in result:
                errors.append(result)
                print(f"  ❌ Failed: {image_path.name} - {result['error']}")
            else:
                success += 1
                print(f"  ✅ Uploaded: {image_path.name}")

    return {
        "total": total,
        "success": success,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Upload images to Railway deployment")
    parser.add_argument(
        "--railway-url",
        default=os.getenv("RAILWAY_URL", "https://lumira-production-3084.up.railway.app"),
        help="Railway deployment URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("RAILWAY_API_KEY"),
        help="API key for authentication (or set RAILWAY_API_KEY env var)",
    )
    parser.add_argument(
        "--gallery-path",
        type=Path,
        default=Path("gallery"),
        help="Local gallery directory path",
    )
    parser.add_argument(
        "--directory",
        type=str,
        help="Specific subdirectory to upload (e.g., gallery/2026/01)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Only upload images from last N days (default: 7, use 0 for all)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Upload all images regardless of age"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of images to upload per batch (default: 10)",
    )

    args = parser.parse_args()

    # Validate API key
    if not args.api_key and not args.dry_run:
        print("Error: API key required. Set RAILWAY_API_KEY env var or use --api-key")
        sys.exit(1)

    # Validate gallery path
    if not args.gallery_path.exists():
        print(f"Error: Gallery path not found: {args.gallery_path}")
        sys.exit(1)

    # Determine search path
    search_path = Path(args.directory) if args.directory else args.gallery_path

    if not search_path.exists():
        print(f"Error: Search path not found: {search_path}")
        sys.exit(1)

    # Find images
    print(f"Scanning {search_path}...")
    all_images = list(search_path.glob("**/*.png"))

    # Filter by date if needed
    days = None if args.all else (args.days if args.days > 0 else None)
    images_to_upload = [
        img
        for img in all_images
        if should_upload(img, days) and not img.parent.name.startswith(".")
    ]

    print(f"Found {len(all_images)} total images")
    print(f"Will upload {len(images_to_upload)} images")

    if not images_to_upload:
        print("No images to upload.")
        sys.exit(0)

    if args.dry_run:
        print("\n🔍 DRY RUN MODE - No images will be uploaded\n")
        for img in images_to_upload[:10]:  # Show first 10
            upload_image(img, args.railway_url, args.api_key or "dummy", dry_run=True)
        if len(images_to_upload) > 10:
            print(f"  ... and {len(images_to_upload) - 10} more")
        sys.exit(0)

    # Confirm upload
    print(f"\nReady to upload {len(images_to_upload)} images to {args.railway_url}")
    response = input("Continue? (y/N): ")

    if response.lower() != "y":
        print("Upload cancelled.")
        sys.exit(0)

    # Upload
    print("\n🚀 Starting upload...")
    result = upload_batch(
        images_to_upload, args.railway_url, args.api_key, batch_size=args.batch_size
    )

    # Summary
    print("\n" + "=" * 50)
    print("Upload complete!")
    print(f"  Total: {result['total']}")
    print(f"  Success: {result['success']}")
    print(f"  Errors: {len(result['errors'])}")

    if result["errors"]:
        print("\nErrors:")
        for error in result["errors"][:5]:  # Show first 5 errors
            print(f"  - {error['path']}: {error['error']}")
        if len(result["errors"]) > 5:
            print(f"  ... and {len(result['errors']) - 5} more errors")


if __name__ == "__main__":
    main()
