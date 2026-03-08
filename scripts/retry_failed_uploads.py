#!/usr/bin/env python3
"""Retry failed uploads with delays to respect rate limits."""

import json
import os
import sys
import time
from pathlib import Path

import httpx


def upload_image(image_path: Path, railway_url: str, api_key: str) -> dict:
    """Upload a single image to Railway."""
    # Load metadata
    metadata_path = image_path.with_suffix(".json")
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)

    # Prepare upload data
    with open(image_path, "rb") as f:
        files = {"image": (image_path.name, f.read(), "image/png")}

    data = {}
    if metadata:
        data["metadata"] = json.dumps(metadata)

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


def main():
    # Failed images from previous upload
    failed_images = [
        "gallery/2026/01/10/archive/20260110_181016_824128.png",
        "gallery/2026/01/10/archive/20260110_185347_196782.png",
        "gallery/2026/01/10/archive/20260110_141431_591863.png",
        "gallery/2026/01/10/archive/20260110_185610_980320.png",
        "gallery/2026/01/10/archive/20260110_141550_801200.png",
        "gallery/2026/01/10/archive/20260110_184020_771345.png",
        "gallery/2026/01/10/archive/20260110_182249_155264.png",
        "gallery/2026/01/10/archive/20260110_134336_144746.png",
        "gallery/2026/01/10/archive/20260110_181413_20926.png",
        "gallery/2026/01/10/archive/20260110_141400_518047.png",
    ]

    railway_url = os.getenv(
        "RAILWAY_URL", "https://lumira-production-3084.up.railway.app"
    )
    api_key = os.getenv("RAILWAY_API_KEY")

    if not api_key:
        print("Error: RAILWAY_API_KEY environment variable not set")
        sys.exit(1)

    print(f"Retrying {len(failed_images)} failed uploads...")
    print("Using 6-second delay between uploads to respect 10/min rate limit\n")

    success = 0
    errors = []

    for i, image_path_str in enumerate(failed_images, 1):
        image_path = Path(image_path_str)

        if not image_path.exists():
            print(
                f"  [{i}/{len(failed_images)}] ⚠️  Skipped: "
                f"{image_path.name} (file not found)"
            )
            continue

        result = upload_image(image_path, railway_url, api_key)

        if "error" in result:
            errors.append(result)
            print(
                f"  [{i}/{len(failed_images)}] ❌ Failed: "
                f"{image_path.name} - {result['error'][:80]}"
            )
        else:
            success += 1
            print(f"  [{i}/{len(failed_images)}] ✅ Uploaded: {image_path.name}")

        # Rate limit: 10/min = 1 every 6 seconds
        if i < len(failed_images):
            time.sleep(6)

    print(f"\n{'=' * 50}")
    print("Retry complete!")
    print(f"  Total: {len(failed_images)}")
    print(f"  Success: {success}")
    print(f"  Errors: {len(errors)}")


if __name__ == "__main__":
    main()
