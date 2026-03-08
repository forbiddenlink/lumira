#!/usr/bin/env python3
"""Find and delete duplicate images on Railway."""

import os
import sys
from collections import defaultdict

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

    print("Fetching all images from Railway...")

    # Fetch all images with pagination
    images = []
    offset = 0
    limit = 500

    with httpx.Client(timeout=60.0) as client:
        while True:
            url = f"{railway_url}/api/images?limit={limit}&offset={offset}"
            print(f"  Fetching: {url}")
            response = client.get(url)
            response.raise_for_status()
            batch = response.json()

            print(f"  Got {len(batch)} images in this batch")

            if not batch:
                print("  Empty batch, stopping pagination")
                break

            images.extend(batch)
            print(f"  Total so far: {len(images)} images")

            # Continue if we got a full batch
            if len(batch) == limit:
                offset += limit
            else:
                # Last partial batch, but check if there might be more
                print(f"  Last batch had {len(batch)} < {limit}, checking for more...")
                offset += len(batch)
                # Make one more request to confirm we're done
                test_response = client.get(
                    f"{railway_url}/api/images?limit={limit}&offset={offset}"
                )
                test_batch = test_response.json()
                if test_batch:
                    print(f"  Found {len(test_batch)} more images!")
                    images.extend(test_batch)
                    offset += len(test_batch)
                else:
                    print("  No more images found, stopping")
                    break

    print(f"\nFound {len(images)} total images")

    # Group by original filename (strip the hash suffix from uploaded names)
    # Original: 20260110_181335_285878.png
    # Uploaded: 20260201_144702_61900e69.png (timestamp_hash.png format)
    # We need to match by the metadata or find actual duplicates

    # For now, let's find images with the same prompt as duplicates
    by_prompt = defaultdict(list)
    for img in images:
        prompt = img.get("prompt", "")
        if prompt:
            by_prompt[prompt].append(img)

    # Find duplicates
    duplicates = {prompt: imgs for prompt, imgs in by_prompt.items() if len(imgs) > 1}

    print(f"\nFound {len(duplicates)} prompts with duplicates")
    total_dups = sum(len(imgs) - 1 for imgs in duplicates.values())
    print(f"Total duplicate images: {total_dups}")

    if not duplicates:
        print("No duplicates found!")
        return

    # Show sample
    print("\nSample duplicates (first 3 prompts):")
    for i, (prompt, imgs) in enumerate(list(duplicates.items())[:3]):
        print(f"\n{i + 1}. Prompt: {prompt[:60]}...")
        print(f"   Count: {len(imgs)} images")
        for img in imgs[:2]:
            print(f"   - {img['filename']} (created: {img['created_at']})")

    # Ask for confirmation
    total_dups = sum(len(imgs) - 1 for imgs in duplicates.values())
    response = input(f"\nDelete {total_dups} duplicate images? (yes/no): ")

    if response.lower() != "yes":
        print("Cancelled.")
        return

    # Delete older duplicates (keep the newest one)
    print("\nDeleting duplicates...")
    deleted = 0
    errors = 0

    with httpx.Client(timeout=30.0) as client:
        for _prompt, imgs in duplicates.items():
            # Sort by created_at, keep the newest
            sorted_imgs = sorted(imgs, key=lambda x: x["created_at"], reverse=True)
            to_delete = sorted_imgs[1:]  # Delete all except the newest

            for img in to_delete:
                try:
                    path = img["path"]
                    response = client.delete(
                        f"{railway_url}/api/images/{path}", headers=headers
                    )
                    response.raise_for_status()
                    deleted += 1
                    print(f"  ✅ Deleted: {img['filename']}")
                except Exception as e:
                    errors += 1
                    print(f"  ❌ Failed: {img['filename']} - {str(e)[:80]}")

    print(f"\n{'=' * 50}")
    print("Cleanup complete!")
    print(f"  Deleted: {deleted}")
    print(f"  Errors: {errors}")
    print(f"  Remaining: {len(images) - deleted}")


if __name__ == "__main__":
    main()
