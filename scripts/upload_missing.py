#!/usr/bin/env python3
"""Upload missing images to Railway by comparing local with remote."""

import json
import os
import sys
from pathlib import Path

import httpx


def main():
    railway_url = os.getenv(
        "RAILWAY_URL", "https://lumira-production-3084.up.railway.app"
    )
    api_key = os.getenv("RAILWAY_API_KEY")

    if not api_key:
        print("Error: RAILWAY_API_KEY environment variable not set")
        sys.exit(1)

    headers = {"X-API-Key": api_key}

    print("Fetching existing images from Railway...")

    # Fetch all existing images
    existing_prompts = set()
    offset = 0
    limit = 500

    with httpx.Client(timeout=60.0) as client:
        while True:
            response = client.get(
                f"{railway_url}/api/images?limit={limit}&offset={offset}"
            )
            response.raise_for_status()
            batch = response.json()

            if not batch:
                break

            for img in batch:
                prompt = img.get("prompt", "")
                if prompt:
                    existing_prompts.add(prompt)

            offset += len(batch)

            if len(batch) < limit:
                break

    print(f"Found {len(existing_prompts)} unique prompts on Railway")

    # Find local images
    print("\nScanning local gallery...")
    gallery_path = Path("gallery/2026")
    local_images = list(gallery_path.glob("**/*.png"))

    print(f"Found {len(local_images)} local images")

    # Find missing images
    missing_images = []
    for img_path in local_images:
        metadata_path = img_path.with_suffix(".json")
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
                prompt = metadata.get("prompt", "")
                if prompt and prompt not in existing_prompts:
                    missing_images.append((img_path, metadata))
            except Exception as e:
                print(f"Error reading {metadata_path}: {e}")

    print(f"\nFound {len(missing_images)} missing images")

    if not missing_images:
        print("No missing images to upload!")
        return

    # Show sample
    print("\nSample missing images:")
    for img_path, metadata in missing_images[:5]:
        prompt = metadata.get("prompt", "")[:60]
        print(f"  - {img_path.name}: {prompt}...")

    # Confirm
    response = input(f"\nUpload {len(missing_images)} missing images? (yes/no): ")

    if response.lower() != "yes":
        print("Cancelled.")
        return

    # Upload
    print("\nUploading missing images...")
    success = 0
    errors = 0

    with httpx.Client(timeout=30.0) as client:
        for i, (img_path, metadata) in enumerate(missing_images, 1):
            try:
                with open(img_path, "rb") as f:
                    files = {"file": (img_path.name, f, "image/png")}
                    data = {"metadata": json.dumps(metadata)}

                    response = client.post(
                        f"{railway_url}/api/admin/images/upload",
                        headers=headers,
                        files=files,
                        data=data,
                    )
                    response.raise_for_status()

                success += 1
                print(f"  [{i}/{len(missing_images)}] ✅ {img_path.name}")
            except Exception as e:
                errors += 1
                print(
                    f"  [{i}/{len(missing_images)}] ❌ {img_path.name}: {str(e)[:60]}"
                )

    print(f"\n{'=' * 50}")
    print("Upload complete!")
    print(f"  Success: {success}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
