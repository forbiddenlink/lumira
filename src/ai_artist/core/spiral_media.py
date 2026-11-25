"""Spiral hosted audio + video generators.

Sibling module to :mod:`spiral_generator` (images): both share the low-level
REST client in :mod:`spiral_client` (start-run -> poll -> download), but audio
and video runs produce a single downloadable media file rather than a list of
``PIL.Image``, so they get their own classes instead of slotting into the
image generator factory (see ``AI/diagrams/SPIRAL_INTEGRATION.md``).

Replaces the Magica media generators (Magica shuts down 2026-12-01). Models:
    - Audio: ``elevenlabs_music`` (default, ``elevenlabs/music``) and
      ``lyria3_pro`` (``fal/fal-ai/lyria3/pro``; can 400 on policy blocks, so it
      is registered but NOT the default).
    - Video: ``kling_v3_pro`` (default), ``gemini_omni`` and ``seedance_2``.
      Spiral has no Veo 3.1 or Sora 2. The old ``veo`` aliases map to Gemini
      Omni 1.2 Flash (Google's current video model) and the old ``sora``
      aliases map to Seedance 2.0 (closest cinematic model).

Input schemas were read with Spiral's ``inspect`` on 2026-11-25. Spiral rejects
unknown fields (``INVALID_INPUT``), so each family has its own builder. They are
NOT validated against a live key (account balance was $0); unit tests mock HTTP.
Extra/override fields can be passed through ``**kwargs`` (merged last).

Gated behind ``SPIRAL_API_KEY``: constructing either generator without a key
only logs a warning (interface parity with :class:`SpiralGenerator`); calling
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
from .spend_guard import check_and_record_images
from .spiral_client import SpiralClient, SpiralModel, parse_model_ref

logger = get_logger(__name__)

# Catalog key -> Spiral (provider, model).
SPIRAL_AUDIO_MODELS: dict[str, SpiralModel] = {
    "elevenlabs_music": SpiralModel("elevenlabs", "music"),
    "lyria3_pro": SpiralModel("fal", "fal-ai/lyria3/pro"),
}
DEFAULT_AUDIO_MODEL = "elevenlabs_music"

SPIRAL_VIDEO_MODELS: dict[str, SpiralModel] = {
    "kling_v3_pro": SpiralModel("fal", "fal-ai/kling-video/v3/pro/text-to-video"),
    "gemini_omni": SpiralModel("gemini", "gemini-omni-1.2-flash"),
    "seedance_2": SpiralModel("fal", "bytedance/seedance-2.0/text-to-video"),
}
DEFAULT_VIDEO_MODEL = "kling_v3_pro"

# Friendly alias -> catalog key.
_AUDIO_ALIASES = {
    "elevenlabs-music": "elevenlabs_music",
    "lyria-pro": "lyria3_pro",
}
_VIDEO_ALIASES = {
    "kling": "kling_v3_pro",
    "kling-v3-pro": "kling_v3_pro",
    # Spiral has no Veo 3.1 / Sora 2: closest available replacements.
    "veo": "gemini_omni",
    "veo-3-1": "gemini_omni",
    "gemini-omni": "gemini_omni",
    "sora": "seedance_2",
    "sora-2": "seedance_2",
    "seedance": "seedance_2",
}

# Mood -> catalog key. Conservative by design: audio has exactly one
# recommended default (lyria3_pro is policy-flaky), and video defaults
# everything to kling_v3_pro except higher-energy moods, which get
# gemini_omni. seedance_2 is registered but never chosen automatically.
SPIRAL_AUDIO_MOOD_MODELS: dict[str, str] = dict.fromkeys(
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

SPIRAL_VIDEO_MOOD_MODELS: dict[str, str] = {
    "contemplative": "kling_v3_pro",
    "introspective": "kling_v3_pro",
    "melancholic": "kling_v3_pro",
    "serene": "kling_v3_pro",
    "restless": "kling_v3_pro",
    "playful": "kling_v3_pro",
    "bold": "gemini_omni",
    "energized": "gemini_omni",
    "rebellious": "gemini_omni",
    "chaotic": "gemini_omni",
}


def audio_model_for_mood(mood: str) -> str:
    """Return the catalog key mapped to a mood (DEFAULT_AUDIO_MODEL if unknown)."""
    return SPIRAL_AUDIO_MOOD_MODELS.get(mood.lower(), DEFAULT_AUDIO_MODEL)


def video_model_for_mood(mood: str) -> str:
    """Return the catalog key mapped to a mood (DEFAULT_VIDEO_MODEL if unknown)."""
    return SPIRAL_VIDEO_MOOD_MODELS.get(mood.lower(), DEFAULT_VIDEO_MODEL)


def _resolve(
    key: str,
    catalog: dict[str, SpiralModel],
    aliases: dict[str, str],
) -> tuple[str, SpiralModel]:
    """Resolve a catalog key, alias, or raw ``provider/model`` ref."""
    key = aliases.get(key, key)
    if key in catalog:
        return key, catalog[key]
    return key, parse_model_ref(key)


def is_catalog_model(kind: str, model_id: str | None) -> bool:
    """True when ``model_id`` is None, a catalog key, or an alias for ``kind``.

    HTTP routes call this so web callers cannot pick an arbitrary
    ``provider/model`` ref: the spend guard prices audio/video at a flat
    per-item estimate, so an uncatalogued (possibly far pricier) model would
    slip past the dollar cap. Raw refs stay available to Python callers.
    """
    if model_id is None:
        return True
    catalog, aliases = (
        (SPIRAL_AUDIO_MODELS, _AUDIO_ALIASES)
        if kind == "audio"
        else (SPIRAL_VIDEO_MODELS, _VIDEO_ALIASES)
    )
    return aliases.get(model_id, model_id) in catalog


# Rough per-item cost estimates for the shared dollar budget (Spiral price
# sentences, 2026-11-25: ElevenLabs Music $0.195/min, Kling v3 Pro 5s silent
# ~$0.73, Gemini Omni 5s 720p ~$0.82, Seedance 5s 720p ~$0.99). Override per
# kind via LUMIRA_SPIRAL_{AUDIO,VIDEO}_COST_PER_ITEM_USD. Item-count caps via
# LUMIRA_SPIRAL_DAILY_MAX_AUDIO / LUMIRA_SPIRAL_DAILY_MAX_VIDEO.
_DEFAULT_MEDIA_COST_USD = {"audio": "0.10", "video": "1.00"}


def _check_budget(kind: str, count: int = 1) -> None:
    """Enforce the per-day Spiral budget for ``kind`` (audio/video) via the
    shared spend guard: Redis-backed, cross-worker, kill-switch + dollar-cap
    aware, one counter per kind so audio and video don't share a cap.

    Routed through the shared spend guard (mirrors ReplicateGenerator /
    SpiralGenerator); like those, the guard records on attempt.
    """
    cap = int(os.getenv(f"LUMIRA_SPIRAL_DAILY_MAX_{kind.upper()}", "20"))
    cost = float(
        os.getenv(
            f"LUMIRA_SPIRAL_{kind.upper()}_COST_PER_ITEM_USD",
            _DEFAULT_MEDIA_COST_USD.get(kind, "0.10"),
        )
    )
    check_and_record_images(f"spiral_{kind}", count, cap, cost)


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
        logger.warning("spiral_media_sidecar_write_failed", error=str(e))


def _clamp(value: int, lo: int, hi: int) -> int:
    return min(max(value, lo), hi)


def _nearest_aspect(aspect_ratio: str, allowed: tuple[str, ...], default: str) -> str:
    """Return ``aspect_ratio`` if allowed, else the allowed value nearest in ratio."""
    if aspect_ratio in allowed:
        return aspect_ratio
    try:
        w, h = (float(p) for p in aspect_ratio.split(":"))
        target = w / h
    except (ValueError, ZeroDivisionError):
        return default

    def ratio(a: str) -> float:
        aw, ah = a.split(":")
        return float(aw) / float(ah)

    return min(allowed, key=lambda a: abs(ratio(a) - target))


class SpiralAudioGenerator:
    """Hosted audio/music generator backed by the Spiral REST API.

    Usage::

        gen = SpiralAudioGenerator()  # defaults to elevenlabs/music
        path = gen.generate_audio("melancholic piano instrumental", duration_seconds=30)
    """

    def __init__(self, model_id: str | None = None) -> None:
        """Initialize the audio generator.

        Args:
            model_id: A catalog key / alias from this module, a raw
                ``provider/model`` ref, or None to pick per-call based on
                ``mood`` (falling back to DEFAULT_AUDIO_MODEL).
        """
        self._explicit_model = bool(model_id)
        self.model_key, self.model = _resolve(
            model_id or DEFAULT_AUDIO_MODEL, SPIRAL_AUDIO_MODELS, _AUDIO_ALIASES
        )
        self.model_name = model_id
        self.api_key = os.environ.get("SPIRAL_API_KEY")
        if not self.api_key:
            logger.warning(
                "spiral_key_missing",
                message="SPIRAL_API_KEY not set. Audio generation will fail.",
            )

    def _resolve_model(self, mood: str | None) -> tuple[str, SpiralModel]:
        if self._explicit_model or not mood:
            return self.model_key, self.model
        key = audio_model_for_mood(mood)
        return key, SPIRAL_AUDIO_MODELS[key]

    def _build_input(
        self,
        model_key: str,
        prompt: str,
        duration_seconds: int,
        seed: int | None,
    ) -> dict[str, Any]:
        """Build the per-model input payload.

        - ElevenLabs Music: ``prompt`` + ``music_length_ms`` (3000-600000) +
          ``force_instrumental``. ``seed`` is not allowed together with ``prompt``.
        - Lyria 3 Pro: ``prompt`` only (no duration or seed field).
        Unknown models get ``prompt`` + ``seed``; add model-specific fields via
        ``generate_audio(**kwargs)``.
        """
        if model_key == "elevenlabs_music":
            return {
                "prompt": prompt,
                "music_length_ms": _clamp(duration_seconds * 1000, 3000, 600000),
                "force_instrumental": True,
            }
        inp: dict[str, Any] = {"prompt": prompt}
        if model_key not in SPIRAL_AUDIO_MODELS and seed is not None:
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
        """Generate audio via the Spiral REST API and save it to the gallery archive.

        Args:
            prompt: Text description of the desired audio (music/sfx).
            duration_seconds: Target length in seconds (ElevenLabs only; Lyria
                has no duration field).
            mood: Optional Lumira mood; picks the model via
                :func:`audio_model_for_mood` when this instance wasn't given an
                explicit ``model_id``.
            seed: Seed for reproducibility; only sent to models that accept it
                alongside a prompt (not ElevenLabs Music or Lyria).
            gallery_root: Root gallery directory; the file is saved under
                ``gallery_root/YYYY/MM/DD/archive/``.
            **kwargs: Extra/override fields merged into the REST input, e.g.
                ``music_length_ms=30000``.

        Returns:
            Path to the saved audio file.
        """
        if not self.api_key:
            raise ValueError("SPIRAL_API_KEY not set")

        _check_budget("audio", 1)

        model_key, model = self._resolve_model(mood)
        input_params = self._build_input(model_key, prompt, duration_seconds, seed)
        input_params.update(kwargs)

        logger.info(
            "spiral_audio_generation_start",
            provider=model.provider,
            model=model.model,
            duration_seconds=duration_seconds,
            mood=mood,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        client = SpiralClient(api_key=self.api_key)
        try:
            run_id = client.start_run(model, input_params)
            urls = client.poll_run(run_id, kind="audio")
            audio_bytes = client.download_bytes(urls[0])
        except httpx.HTTPStatusError as e:
            logger.error(
                "spiral_api_error", status=e.response.status_code, error=str(e)
            )
            raise RuntimeError(f"Spiral API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("spiral_request_error", error=str(e))
            raise RuntimeError(f"Spiral request failed: {e}") from e

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
                "provider": model.provider,
                "model": model.model,
                "duration_seconds": duration_seconds,
                "mood": mood,
                "seed": seed,
                "source_url": urls[0],
                "generated_at": datetime.now().isoformat(),
            },
        )

        logger.info("spiral_audio_generation_complete", path=str(audio_path))
        return audio_path


class SpiralVideoGenerator:
    """Hosted video generator backed by the Spiral REST API.

    Usage::

        gen = SpiralVideoGenerator()  # defaults to Kling v3 Pro
        path = gen.generate_video("a serene misty forest at dawn, slow pan")
    """

    def __init__(self, model_id: str | None = None) -> None:
        """Initialize the video generator.

        Args:
            model_id: A catalog key / alias from this module, a raw
                ``provider/model`` ref, or None to pick per-call based on
                ``mood`` (falling back to DEFAULT_VIDEO_MODEL, i.e. Kling v3 Pro).
        """
        self._explicit_model = bool(model_id)
        self.model_key, self.model = _resolve(
            model_id or DEFAULT_VIDEO_MODEL, SPIRAL_VIDEO_MODELS, _VIDEO_ALIASES
        )
        self.model_name = model_id
        self.api_key = os.environ.get("SPIRAL_API_KEY")
        if not self.api_key:
            logger.warning(
                "spiral_key_missing",
                message="SPIRAL_API_KEY not set. Video generation will fail.",
            )

    def _resolve_model(self, mood: str | None) -> tuple[str, SpiralModel]:
        if self._explicit_model or not mood:
            return self.model_key, self.model
        key = video_model_for_mood(mood)
        return key, SPIRAL_VIDEO_MODELS[key]

    def _build_input(
        self,
        model_key: str,
        prompt: str,
        duration_seconds: int,
        aspect_ratio: str,
        seed: int | None,
    ) -> dict[str, Any]:
        """Build the per-model input payload.

        - Kling v3 Pro: ``duration`` as a string "3".."15", aspect 16:9/9:16/1:1,
          ``generate_audio`` off (silent is ~33% cheaper); no seed.
        - Gemini Omni 1.2 Flash: ``input`` (prompt) + ``response_format``
          (duration "Ns" 3-15, 720p, aspect 16:9/9:16) + ``generation_config.seed``.
        - Seedance 2.0: ``duration`` string "4".."15", 720p, audio off; no seed.
        Unknown models get ``prompt`` + ``seed``; add model-specific fields via
        ``generate_video(**kwargs)``.
        """
        if model_key == "kling_v3_pro":
            return {
                "prompt": prompt,
                "duration": str(_clamp(duration_seconds, 3, 15)),
                "aspect_ratio": _nearest_aspect(
                    aspect_ratio, ("16:9", "9:16", "1:1"), "16:9"
                ),
                "generate_audio": False,
            }
        if model_key == "gemini_omni":
            inp: dict[str, Any] = {
                "input": prompt,
                "response_format": {
                    "type": "video",
                    "duration": f"{_clamp(duration_seconds, 3, 15)}s",
                    "resolution": "720p",
                    "aspect_ratio": _nearest_aspect(
                        aspect_ratio, ("16:9", "9:16"), "16:9"
                    ),
                },
            }
            if seed is not None:
                inp["generation_config"] = {"seed": seed}
            return inp
        if model_key == "seedance_2":
            return {
                "prompt": prompt,
                "duration": str(_clamp(duration_seconds, 4, 15)),
                "resolution": "720p",
                "aspect_ratio": _nearest_aspect(
                    aspect_ratio,
                    ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
                    "16:9",
                ),
                "generate_audio": False,
            }
        generic: dict[str, Any] = {"prompt": prompt}
        if seed is not None:
            generic["seed"] = seed
        return generic

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
        """Generate video via the Spiral REST API and save it to the gallery archive.

        Args:
            prompt: Text description of the desired video.
            duration_seconds: Target clip length in seconds (clamped to the
                model's supported range).
            aspect_ratio: Aspect ratio (e.g. "16:9", "9:16", "1:1"); snapped to
                the nearest value the model accepts.
            mood: Optional Lumira mood; picks the model via
                :func:`video_model_for_mood` when this instance wasn't given an
                explicit ``model_id``.
            seed: Seed for reproducibility; only sent to models that accept one
                (Gemini Omni).
            gallery_root: Root gallery directory; the file is saved under
                ``gallery_root/YYYY/MM/DD/archive/``.
            **kwargs: Extra/override fields merged into the REST input.

        Returns:
            Path to the saved video file.
        """
        if not self.api_key:
            raise ValueError("SPIRAL_API_KEY not set")

        _check_budget("video", 1)

        model_key, model = self._resolve_model(mood)
        input_params = self._build_input(
            model_key, prompt, duration_seconds, aspect_ratio, seed
        )
        input_params.update(kwargs)

        logger.info(
            "spiral_video_generation_start",
            provider=model.provider,
            model=model.model,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            mood=mood,
            prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
        )

        client = SpiralClient(api_key=self.api_key)
        try:
            run_id = client.start_run(model, input_params)
            # Video runs take substantially longer than image/audio runs.
            urls = client.poll_run(run_id, timeout_s=900.0, kind="video")
            video_bytes = client.download_bytes(urls[0])
        except httpx.HTTPStatusError as e:
            logger.error(
                "spiral_api_error", status=e.response.status_code, error=str(e)
            )
            raise RuntimeError(f"Spiral API error: {e}") from e
        except httpx.HTTPError as e:
            logger.error("spiral_request_error", error=str(e))
            raise RuntimeError(f"Spiral request failed: {e}") from e

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
                "provider": model.provider,
                "model": model.model,
                "duration_seconds": duration_seconds,
                "aspect_ratio": aspect_ratio,
                "mood": mood,
                "seed": seed,
                "source_url": urls[0],
                "generated_at": datetime.now().isoformat(),
            },
        )

        logger.info("spiral_video_generation_complete", path=str(video_path))
        return video_path
