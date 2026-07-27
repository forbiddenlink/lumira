"""Video generation utilities for turning AI-generated images into videos.

Requires the 'video' optional dependency:
    pip install lumira[video]
    # or: pip install moviepy>=2.1.1
"""

from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4


def export_dir() -> Path:
    """Return the dedicated temp subdirectory for Lumira video exports.

    Scoping exports to a subdirectory (rather than the shared system temp
    root) lets the download endpoint contain path access to Lumira's own
    files instead of any .mp4 dropped in temp by another process.
    """
    d = Path(gettempdir()) / "lumira-exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Lazy import to avoid requiring moviepy unless video features are used
_moviepy_available: bool | None = None


def _check_moviepy() -> None:
    """Check if moviepy is available, raise ImportError if not."""
    global _moviepy_available
    if _moviepy_available is None:
        try:
            import moviepy  # noqa: F401

            _moviepy_available = True
        except ImportError:
            _moviepy_available = False

    if not _moviepy_available:
        raise ImportError(
            "moviepy is required for video generation. "
            "Install with: pip install lumira[video]"
        )


def create_slideshow(
    image_paths: list[str],
    output_path: str | None = None,
    duration_per_image: float = 3.0,
    fps: int = 24,
    fade_duration: float = 0.5,
    codec: str = "libx264",
    audio_codec: str = "aac",
) -> str:
    """Create a slideshow video from a sequence of images.

    Args:
        image_paths: List of paths to images to include in the slideshow.
        output_path: Path for the output video file. If None, generates a
            temporary file in /tmp with a UUID filename.
        duration_per_image: How long each image is displayed (seconds).
        fps: Frames per second for the output video.
        fade_duration: Duration of fade in/out transitions (seconds).
            Set to 0 to disable fading.
        codec: Video codec for encoding (default: libx264 for H.264).
        audio_codec: Audio codec (default: aac).

    Returns:
        Path to the generated video file.

    Raises:
        ImportError: If moviepy is not installed.
        ValueError: If image_paths is empty.
        FileNotFoundError: If any image path doesn't exist.

    Example:
        >>> from ai_artist.utils.video import create_slideshow
        >>> video_path = create_slideshow(
        ...     image_paths=["img1.png", "img2.png", "img3.png"],
        ...     duration_per_image=3.0,
        ...     fps=24,
        ... )
    """
    _check_moviepy()

    from moviepy import ImageSequenceClip, concatenate_videoclips
    from moviepy.video.fx import CrossFadeIn, CrossFadeOut

    if not image_paths:
        raise ValueError("image_paths cannot be empty")

    # Validate all paths exist
    for path in image_paths:
        if not Path(path).exists():
            raise FileNotFoundError(f"Image not found: {path}")

    clips = []
    for path in image_paths:
        # Create clip from single image with specified duration
        clip = ImageSequenceClip([path], durations=[duration_per_image])

        # Apply fade effects if requested
        if fade_duration > 0:
            clip = clip.with_effects(
                [
                    CrossFadeIn(fade_duration),
                    CrossFadeOut(fade_duration),
                ]
            )

        clips.append(clip)

    # Concatenate all clips
    final = concatenate_videoclips(clips, method="compose")

    # Generate output path if not provided
    if output_path is None:
        output_path = str(export_dir() / f"slideshow_{uuid4()}.mp4")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Write video file
    final.write_videofile(
        output_path,
        fps=fps,
        codec=codec,
        audio_codec=audio_codec,
        logger=None,  # Suppress moviepy progress bars
    )

    # Clean up
    final.close()
    for clip in clips:
        clip.close()

    return output_path


def create_zoom_video(
    image_path: str,
    output_path: str | None = None,
    duration: float = 5.0,
    fps: int = 24,
    zoom_start: float = 1.0,
    zoom_end: float = 1.3,
    center: tuple[float, float] = (0.5, 0.5),
) -> str:
    """Create a Ken Burns-style zoom video from a single image.

    Args:
        image_path: Path to the source image.
        output_path: Path for the output video file. If None, generates a
            temporary file.
        duration: Total video duration in seconds.
        fps: Frames per second for the output video.
        zoom_start: Starting zoom level (1.0 = original size).
        zoom_end: Ending zoom level.
        center: Zoom center point as (x, y) ratios from 0.0 to 1.0.
            (0.5, 0.5) is center of image.

    Returns:
        Path to the generated video file.

    Raises:
        ImportError: If moviepy is not installed.
        FileNotFoundError: If image_path doesn't exist.

    Example:
        >>> from ai_artist.utils.video import create_zoom_video
        >>> video_path = create_zoom_video(
        ...     image_path="artwork.png",
        ...     duration=5.0,
        ...     zoom_start=1.0,
        ...     zoom_end=1.3,
        ... )
    """
    _check_moviepy()

    from moviepy import ImageClip

    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Load image
    clip = ImageClip(image_path, duration=duration)
    _ = clip.size  # used for reference, zoom operates on frames directly

    def zoom_effect(get_frame, t):
        """Apply zoom effect at time t."""
        # Calculate current zoom level (linear interpolation)
        progress = t / duration
        current_zoom = zoom_start + (zoom_end - zoom_start) * progress

        # Get the frame
        frame = get_frame(t)

        # Import here to avoid circular dependency
        import numpy as np
        from PIL import Image

        img = Image.fromarray(frame)
        w, h = img.size

        # Calculate crop box based on zoom and center
        new_w = int(w / current_zoom)
        new_h = int(h / current_zoom)

        cx, cy = center
        left = int((w - new_w) * cx)
        top = int((h - new_h) * cy)
        right = left + new_w
        bottom = top + new_h

        # Crop and resize back to original
        cropped = img.crop((left, top, right, bottom))
        resized = cropped.resize((w, h), Image.Resampling.LANCZOS)

        return np.array(resized)

    # Apply zoom effect
    zoomed_clip = clip.transform(zoom_effect)

    # Generate output path if not provided
    if output_path is None:
        output_path = str(export_dir() / f"zoom_{uuid4()}.mp4")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Write video file
    zoomed_clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    # Clean up
    zoomed_clip.close()
    clip.close()

    return output_path


def images_to_video(
    image_paths: list[str],
    output_path: str | None = None,
    fps: int = 24,
    duration_per_image: float | None = None,
) -> str:
    """Convert a sequence of images to a video (animation style).

    Unlike create_slideshow, this creates a smooth animation where each
    image is a single frame (or spans a few frames based on duration).
    Useful for creating GIF-like animations from image sequences.

    Args:
        image_paths: List of image paths in order.
        output_path: Output video path. If None, generates a temp file.
        fps: Frames per second.
        duration_per_image: If provided, each image will be displayed for
            this many seconds. If None, each image is exactly one frame.

    Returns:
        Path to the generated video file.

    Raises:
        ImportError: If moviepy is not installed.
        ValueError: If image_paths is empty.

    Example:
        >>> # Create animation from numbered frames
        >>> frames = [f"frame_{i:04d}.png" for i in range(100)]
        >>> video = images_to_video(frames, fps=30)
    """
    _check_moviepy()

    from moviepy import ImageSequenceClip

    if not image_paths:
        raise ValueError("image_paths cannot be empty")

    # Validate paths exist
    for path in image_paths:
        if not Path(path).exists():
            raise FileNotFoundError(f"Image not found: {path}")

    # Calculate durations
    if duration_per_image is not None:
        durations = [duration_per_image] * len(image_paths)
        clip = ImageSequenceClip(image_paths, durations=durations)
    else:
        # Each image is one frame
        clip = ImageSequenceClip(image_paths, fps=fps)

    # Generate output path if not provided
    if output_path is None:
        output_path = str(export_dir() / f"animation_{uuid4()}.mp4")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Write video
    clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    clip.close()

    return output_path
