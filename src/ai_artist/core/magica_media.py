"""Magica (Galaxy AI) hosted audio + video generators.

Sibling module to :mod:`magica_generator` (images): both share the low-level
REST client in :mod:`magica_client` (start-run -> poll -> download), but audio
and video runs produce a single downloadable media file rather than a list of
``PIL.Image``, so they get their own classes instead of slotting into the
image generator factory (see ``AI/diagrams/MAGICA_INTEGRATION.md``, "New
modalities" section).

Proven node types (per ``AI/diagrams/MAGICA_INTEGRATION.md`` + the
``gallery/magica_demo/`` reference run, 2026-07-28):
    - Audio: ``elevenlabs_music`` (default) — a 30s instrumental generated
      cleanly end-to-end via the Claude-orchestrated MCP path. ``lyria3_pro``
      (Google Vertex) 400'd on a policy block for the same prompt, so it is
      registered but NOT the default.
    - Video: ``kling_v3_pro`` (default, cheaper/more permissive), ``veo_3_1``,
      ``sora_2``.

Input schemas below are best-effort, built from the documented common fields
(``prompt`` + duration/aspect + optional ``seed``) plus known Magica usage;
they have NOT been validated end-to-end against a live key the way the image
generator's ``nano_banana_pro`` path has. Per-model quirks (e.g. Magica may
expect ``music_length_ms`` instead of/alongside ``duration_seconds`` for some
ElevenLabs sub-modes) should be confirmed via Magica's ``get_model_schema``
and can always be passed/overridden through ``**kwargs``, which are merged
into the request input verbatim (last write wins).

Gated behind ``MAGICA_API_KEY``: constructing either generator without a key
only logs a warning (interface parity with :class:`MagicaGenerator`); calling
``generate_audio`` / ``generate_video`` without a key raises ``ValueError``.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..utils.logging import get_logger
from .magica_client import MagicaClient
from .spend_guard import check_and_record_images

logger = get_logger(__name__)

# Friendly-name -> Magica nodeType for audio models. Callers may also pass a
# raw nodeType directly (snake_case) as ``model_id``.
MAGICA_AUDIO_MODELS = {
    "elevenlabs-music": "elevenlabs_music",  # default: instrumental/music
    "lyria-pro": "lyria3_pro",  # Google Vertex; can 400 on policy blocks
}
DEFAULT_AUDIO_MODEL = "elevenlabs_music"

# Friendly-name -> Magica nodeType for video models.
MAGICA_VIDEO_MODELS = {
    "kling": "kling_v3_pro",  # default: cheaper + more permissive than sora
    "kling-v3-pro": "kling_v3_pro",
    "veo": "veo_3_1",
    "veo-3-1": "veo_3_1",
    "sora": "sora_2",
    "sora-2": "sora_2",
}
DEFAULT_VIDEO_MODEL = "kling_v3_pro"

# Mood -> nodeType maps (optional; mirror MAGICA_MOOD_MODELS in
# magica_generator.py). Conservative by design: audio has exactly one
# recommended default (lyria3_pro is policy-flaky), and video defaults
# everything to kling_v3_pro (cheap/permissive) except higher-energy moods,
# which get veo_3_1 for extra fidelity. sora_2 is registered but never chosen
# automatically -- opt in explicitly via ``model_id``.
MAGICA_AUDIO_MOOD_MODELS: dict[str, str] = dict.fromkeys(
    [
        "contemplative",
        "chaotic",
        "melancholic",
        "energized",
        "rebellious",
        "serene",
        "restless",
        "playful",
        "introspective",
        "bold",
    ],
    DEFAULT_AUDIO_MODEL,
)

MAGICA_VIDEO_MOOD_MODELS: dict[str, str] = {
    "contemplative": "kling_v3_pro",
    "introspective": "kling_v3_pro",
    "melancholic": "kling_v3_pro",
    "serene": "kling_v3_pro",
    "restless": "kling_v3_pro",
    "playful": "kling_v3_pro",
    "bold": "veo_3_1",
    "energized": "veo_3_1",
    "rebellious": "veo_3_1",
    "chaotic": "veo_3_1",
}


def audio_model_for_mood(mood: str) -> str:
    """Return the Magica nodeType mapped to a mood (DEFAULT_AUDIO_MODEL if unknown)."""
    return MAGICA_AUDIO_MOOD_MODELS.get(mood.lower(), DEFAULT_AUDIO_MODEL)


def video_model_for_mood(mood: str) -> str:
    """Return the Magica nodeType mapped to a mood (DEFAULT_VIDEO_MODEL if unknown)."""
    return MAGICA_VIDEO_MOOD_MODELS.get(mood.lower(), DEFAULT_VIDEO_MODEL)


# Rough per-item cost estimates for the shared dollar budget (override per kind
# as pricing shifts). Configure the item-count caps via
# LUMIRA_MAGICA_DAILY_MAX_AUDIO / LUMIRA_MAGICA_DAILY_MAX_VIDEO.
_DEFAULT_MEDIA_COST_USD = {"audio": "0.10", "video": "0.50"}


def _check_budget(kind: str, count: int = 1) -> None:
    """Enforce the per-day Magica budget for ``kind`` (audio/video) via the
    shared spend guard: Redis-backed, cross-worker, kill-switch + dollar-cap
    aware, one counter per kind so audio and video don't share a cap.

    Routed through the shared spend guard (mirrors ReplicateGenerator /
    MagicaGenerator); like those, the guard records on attempt.
    """
    cap = int(os.getenv(f"LUMIRA_MAGICA_DAILY_MAX_{kind.upper()}", "20"))
    cost = float(
        os.getenv(
            f"LUMIRA_MAGICA_{kind.upper()}_COST_PER_ITEM_USD",
            _DEFAULT_MEDIA_COST_USD.get(kind, "0.10"),
        )
    )
    check_and_record_images(f"magica_{kind}", count, cap, cost)


def _infer_extension(url: str, default: str) -> str:
    """Best-effort file extension from a download URL's path (else ``default``)."""
    path = urlsplit(url).path
    suffix = Path(path).suffix
    return suffix if suffix and len(suffix) <= 6 else default


def _gallery_archive_dir(
    gallery_root: str | Path, when: datetime | None = None
) -> Path:
    """Return (and create) ``gallery_root/YYYY/MM/DD/archive`` for ``when`` (now by default).

    Mirrors :meth:`ai_artist.gallery.manager.GalleryManager.save_image`'s
    year/month/day/archive layout so audio/video assets land alongside images.
    """
    now = when or datetime.now()
    save_dir = (
        Path(gallery_root)
        / f"{now.year}"
        / f"{now.month:02d}"
        / f"{now.day:02d}"
        / "archive"
    )
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def _write_sidecar_metadata(media_path: Path, metadata: dict[str, Any]) -> None:
    """Best-effort JSON sidecar next to the media file (never blocks generation)."""
    import json

    try:
        media_path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2, default=str)
        )
    except OSError as e:
        logger.warning("magica_media_sidecar_write_failed", error=str(e))


class MagicaAudioGenerator:
    """Hosted audio/music generator backed by the Magica REST API.

    Usage::

        gen = MagicaAudioGenerator()  # defaults to elevenlabs_music
        path = gen.generate_audio("melancholic piano instrumental", duration_seconds=30)
    """

    def __init__(
        self, model_id: str | None = None, sub_model_id: str | None = None
    ) -> None:
        """Initialize the audio generator.

        Args:
            model_id: A key from MAGICA_AUDIO_MODELS, a raw Magica nodeType, or
                None to pick per-call based on ``mood`` (falling back to
                DEFAULT_AUDIO_MODEL).
            sub_model_id: Optional Magica subModelId for multi-mode nodes.
        """
        self._explicit_model = bool(model_id)
        self.node_type = (
            MAGICA_AUDIO_MODELS.get(model_id, model_id)
            if model_id
            else DEFAULT_AUDIO_MODEL
        )
        self.model_name = model_id
        self.sub_model_id = sub_model_id
        self.api_key = os.environ.get("MAGICA_API_KEY")
        if not self.api_key:
            logger.warning(
                "magica_key_missing",
                message="MAGICA_API_KEY not set. Audio generation will fail.",
            )

    def _resolve_node_type(self, mood: str | None) -> str:
        if self._explicit_model or not mood:
            return self.node_type
        return audio_model_for_mood(mood)

    def _build_input(
        self, node_type: str, prompt: str, duration_seconds: int, seed: int | None
    ) -> dict[str, Any]:
        """Build the per-model input payload.

        Best-effort common schema (verified live only for ``elevenlabs_music``
        via the MCP path, see module docstring): ``prompt`` + a duration field.
        Unknown/other audio node types get the same minimal fields; callers can
        add/override model-specific fields (e.g. ``music_length_ms``,
        ``voice_id``) via ``generate_audio(**kwargs)``.
        """
        inp: dict[str, Any] = {"prompt": prompt, "duration_seconds": duration_seconds}
        if seed is not None:
            inp["seed"] = seed
        return inp

    def generate_audio(
        self,
        prompt: str,
        *,
        duration_seconds: int = 30,
        mood: str | None = None,
        seed: int | None = None,
        gallery_root: str | Path = "gallery",
        **kwargs: Any,
    ) -> Path:
        """Generate audio via the Magica REST API and save it to the gallery archive.

        Args:
            prompt: Text description of the desired audio (music/sfx).
            duration_seconds: Target length in seconds.
            mood: Optional Lumira mood; picks the nodeType via
                :func:`audio_model_for_mood` when this instance wasn't given an
                explicit ``model_id``.
            seed: Optional seed for reproducibility (if the model supports it).
            gallery_root: Root gallery directory; the file is saved under
                ``gallery_root/YYYY/MM/DD/archive/``.
            **kwargs: Extra/override fields merged into the REST input, e.g.
                ``music_length_ms=30000``.

        Returns:
            Path to the saved audio file.
        """
        if not self.api_key:
            raise ValueError("MAGICA_API_KEY not set")

        _check_budget("audio", 1)

        node_type = self._resolve_node_type(mood)
        input_params = self._build_input(node_type, prompt, duration_seconds, seed)
        input_params.update(kwargs)

        logger.info(
            "magica_audio_generation_start",
            node_type=node_type,
            duration_seconds=duration_seconds,
            mood=mood,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        client = MagicaClient(api_key=self.api_key)
        try:
            run_id = client.start_run(
                node_type, input_params, sub_model_id=self.sub_model_id
            )
            urls = client.poll_run(run_id)
            audio_bytes = client.download_bytes(urls[0])
        except httpx.HTTPStatusError as e:
            logger.error(
                "magica_api_error", status=e.response.status_code, error=str(e)
            )
            raise RuntimeError(f"Magica API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("magica_request_error", error=str(e))
            raise RuntimeError(f"Magica request failed: {e}") from e

        save_dir = _gallery_archive_dir(gallery_root)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = _infer_extension(urls[0], default=".mp3")
        audio_path = (
            save_dir / f"{timestamp}_{seed if seed is not None else 'noseed'}{ext}"
        )
        audio_path.write_bytes(audio_bytes)

        _write_sidecar_metadata(
            audio_path,
            {
                "prompt": prompt,
                "node_type": node_type,
                "duration_seconds": duration_seconds,
                "mood": mood,
                "seed": seed,
                "source_url": urls[0],
                "generated_at": datetime.now().isoformat(),
            },
        )

        logger.info("magica_audio_generation_complete", path=str(audio_path))
        return audio_path


class MagicaVideoGenerator:
    """Hosted video generator backed by the Magica REST API.

    Usage::

        gen = MagicaVideoGenerator()  # defaults to kling_v3_pro
        path = gen.generate_video("a serene misty forest at dawn, slow pan")
    """

    def __init__(
        self, model_id: str | None = None, sub_model_id: str | None = None
    ) -> None:
        """Initialize the video generator.

        Args:
            model_id: A key from MAGICA_VIDEO_MODELS, a raw Magica nodeType, or
                None to pick per-call based on ``mood`` (falling back to
                DEFAULT_VIDEO_MODEL, i.e. kling_v3_pro).
            sub_model_id: Optional Magica subModelId for multi-mode nodes.
        """
        self._explicit_model = bool(model_id)
        self.node_type = (
            MAGICA_VIDEO_MODELS.get(model_id, model_id)
            if model_id
            else DEFAULT_VIDEO_MODEL
        )
        self.model_name = model_id
        self.sub_model_id = sub_model_id
        self.api_key = os.environ.get("MAGICA_API_KEY")
        if not self.api_key:
            logger.warning(
                "magica_key_missing",
                message="MAGICA_API_KEY not set. Video generation will fail.",
            )

    def _resolve_node_type(self, mood: str | None) -> str:
        if self._explicit_model or not mood:
            return self.node_type
        return video_model_for_mood(mood)

    def _build_input(
        self,
        node_type: str,
        prompt: str,
        duration_seconds: int,
        aspect_ratio: str,
        seed: int | None,
    ) -> dict[str, Any]:
        """Build the per-model input payload.

        Best-effort common schema (see module docstring): ``prompt`` +
        ``duration`` + ``aspect_ratio``. Unknown/other video node types get the
        same minimal fields; callers can add/override model-specific fields
        via ``generate_video(**kwargs)``.
        """
        inp: dict[str, Any] = {
            "prompt": prompt,
            "duration": duration_seconds,
            "aspect_ratio": aspect_ratio,
        }
        if seed is not None:
            inp["seed"] = seed
        return inp

    def generate_video(
        self,
        prompt: str,
        *,
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9",
        mood: str | None = None,
        seed: int | None = None,
        gallery_root: str | Path = "gallery",
        **kwargs: Any,
    ) -> Path:
        """Generate video via the Magica REST API and save it to the gallery archive.

        Args:
            prompt: Text description of the desired video.
            duration_seconds: Target clip length in seconds.
            aspect_ratio: Magica aspect_ratio enum (e.g. "16:9", "9:16", "1:1").
            mood: Optional Lumira mood; picks the nodeType via
                :func:`video_model_for_mood` when this instance wasn't given an
                explicit ``model_id``.
            seed: Optional seed for reproducibility (if the model supports it).
            gallery_root: Root gallery directory; the file is saved under
                ``gallery_root/YYYY/MM/DD/archive/``.
            **kwargs: Extra/override fields merged into the REST input.

        Returns:
            Path to the saved video file.
        """
        if not self.api_key:
            raise ValueError("MAGICA_API_KEY not set")

        _check_budget("video", 1)

        node_type = self._resolve_node_type(mood)
        input_params = self._build_input(
            node_type, prompt, duration_seconds, aspect_ratio, seed
        )
        input_params.update(kwargs)

        logger.info(
            "magica_video_generation_start",
            node_type=node_type,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            mood=mood,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        client = MagicaClient(api_key=self.api_key)
        try:
            run_id = client.start_run(
                node_type, input_params, sub_model_id=self.sub_model_id
            )
            # Video runs take substantially longer than image/audio runs.
            urls = client.poll_run(run_id, timeout_s=900.0)
            video_bytes = client.download_bytes(urls[0])
        except httpx.HTTPStatusError as e:
            logger.error(
                "magica_api_error", status=e.response.status_code, error=str(e)
            )
            raise RuntimeError(f"Magica API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("magica_request_error", error=str(e))
            raise RuntimeError(f"Magica request failed: {e}") from e

        save_dir = _gallery_archive_dir(gallery_root)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = _infer_extension(urls[0], default=".mp4")
        video_path = (
            save_dir / f"{timestamp}_{seed if seed is not None else 'noseed'}{ext}"
        )
        video_path.write_bytes(video_bytes)

        _write_sidecar_metadata(
            video_path,
            {
                "prompt": prompt,
                "node_type": node_type,
                "duration_seconds": duration_seconds,
                "aspect_ratio": aspect_ratio,
                "mood": mood,
                "seed": seed,
                "source_url": urls[0],
                "generated_at": datetime.now().isoformat(),
            },
        )

        logger.info("magica_video_generation_complete", path=str(video_path))
        return video_path
