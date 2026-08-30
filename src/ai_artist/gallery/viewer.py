"""Gallery viewer CLI tool."""

import argparse
from datetime import datetime
from pathlib import Path

from PIL import Image


def list_recent_images(gallery_path: Path, limit: int = 10) -> None:
    """List recent images in the gallery."""
    # Find all PNG files
    images = sorted(
        gallery_path.glob("**/*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    if not images:
        print("No images found in gallery.")
        return

    print(f"\n🖼️  Recent Images (latest {len(images)}):\n")
    for idx, img_path in enumerate(images, 1):
        # Get file info
        stat = img_path.stat()
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime)

        # Get image dimensions
        try:
            with Image.open(img_path) as img:
                dims = f"{img.width}x{img.height}"
        except Exception:
            dims = "unknown"

        # Relative path from gallery
        rel_path = img_path.relative_to(gallery_path)

        print(f"{idx:2d}. {rel_path}")
        print(f"    Size: {size_mb:.2f} MB | Dimensions: {dims}")
        print(f"    Created: {modified.strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def open_image(image_path: Path) -> None:
    """Open an image in the default viewer."""
    try:
        img = Image.open(image_path)
        img.show()
        print(f"✅ Opened: {image_path.name}")
    except Exception as e:
        print(f"❌ Error opening image: {e}")


def main() -> None:
    """Gallery viewer CLI."""
    parser = argparse.ArgumentParser(description="AI Artist Gallery Viewer")
    parser.add_argument(
        "--gallery",
        type=Path,
        default=Path("gallery"),
        help="Path to gallery directory",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    list_parser = subparsers.add_parser("list", help="List recent images")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of images to show",
    )

    # Open command
    open_parser = subparsers.add_parser("open", help="Open an image")
    open_parser.add_argument("path", type=Path, help="Path to image file")

    args = parser.parse_args()

    if args.command == "list":
        list_recent_images(args.gallery, args.limit)
    elif args.command == "open":
        open_image(args.path)
    else:
        # Default: list recent images
        list_recent_images(args.gallery)


if __name__ == "__main__":
    main()
