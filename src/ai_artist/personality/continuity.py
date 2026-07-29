"""Cross-runtime continuity helpers — shared by web studio and CLI.

Keeps Lumira feeling like one being across processes: mood, desires,
statement growth, and multimodal impulses.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

MOOD_STATE_FILE = Path("data/lumira_mood_state.json")
DESIRES_FILE = Path("data/lumira_desires.json")
STATEMENT_EVOLVED_FILE = Path("data/lumira_evolved_statement.json")


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("continuity_load_failed", path=str(path), error=str(e))
        return None


def should_deep_deliberate(
    *,
    drive_status: dict[str, Any] | None = None,
    chance: float = 0.32,
) -> bool:
    """Sometimes she needs a full inner council before choosing."""
    drives = drive_status or {}
    series = (drives.get("series_continuation") or {}).get("intensity", 0)
    thematic = (drives.get("thematic_continuation") or {}).get("intensity", 0)
    if max(float(series or 0), float(thematic or 0)) >= 0.65:
        return True
    return random.random() < chance


def should_pair_soundtrack(
    *,
    mood: str | None,
    drive_status: dict[str, Any] | None = None,
    explicit: bool = False,
) -> bool:
    """Pair audio when asked, env-forced, or her emotional drive wants sound."""
    if explicit:
        return True
    if os.getenv("LUMIRA_AUTO_SOUNDTRACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return True
    if not os.environ.get("MAGICA_API_KEY"):
        return False
    mood_l = (mood or "").lower()
    emotional_moods = {
        "melancholic",
        "serene",
        "contemplative",
        "introspective",
        "energized",
        "bold",
    }
    emotion = (drive_status or {}).get("emotional_expression") or {}
    intensity = float(emotion.get("intensity") or 0)
    if mood_l in emotional_moods and intensity >= 0.45:
        return True
    return bool(intensity >= 0.7 and random.random() < 0.55)


def note_creation_for_statement(
    creation_record: dict[str, Any],
) -> dict[str, Any] | None:
    """Feed hierarchical reflection; evolve statement after a short streak."""
    try:
        from .hierarchical_reflection import get_hierarchical_reflection

        reflection = get_hierarchical_reflection()
        reflection.record_session_creation(creation_record)
        streak = len(getattr(reflection, "_session_creations", []) or [])
        # Evolve after every 3 pieces in the live session
        if streak > 0 and streak % 3 == 0:
            reflection.record_session_end()
            statement = reflection.generate_artist_statement()
            payload = {
                "identity": statement.identity,
                "philosophy": statement.philosophy,
                "themes": list(statement.themes or []),
                "full_statement": statement.full_statement,
                "version": statement.version,
            }
            save_json(STATEMENT_EVOLVED_FILE, payload)
            logger.info(
                "artist_statement_evolved",
                version=statement.version,
                streak=streak,
            )
            return payload
    except Exception as e:
        logger.debug("statement_evolution_failed", error=str(e))
    return None


def load_evolved_statement() -> dict[str, Any] | None:
    return load_json(STATEMENT_EVOLVED_FILE)


def maybe_pair_soundtrack(
    *,
    prompt: str,
    mood: str | None,
    image_path: Path,
    metadata: dict[str, Any],
    enabled: bool,
    gallery_root: str = "gallery",
) -> Path | None:
    """Optionally generate a Magica soundtrack next to a new artwork.

    Opt-in via ``enabled`` or ``LUMIRA_AUTO_SOUNDTRACK=1``. Failures are logged
    and swallowed so image creation still succeeds. Shared by web + CLI.
    """
    if not enabled and os.getenv("LUMIRA_AUTO_SOUNDTRACK", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return None
    if not os.environ.get("MAGICA_API_KEY"):
        return None
    try:
        from ..core.magica_media import MagicaAudioGenerator

        audio_prompt = (
            f"Instrumental soundtrack for an artwork: {prompt[:200]}. "
            f"Mood: {mood or 'contemplative'}."
        )
        path = MagicaAudioGenerator().generate_audio(
            audio_prompt,
            duration_seconds=30,
            mood=mood,
            gallery_root=gallery_root,
        )
        try:
            soundtrack_url = (
                f"/api/images/file/{path.relative_to(Path(gallery_root)).as_posix()}"
            )
        except ValueError:
            soundtrack_url = str(path)

        # Web studio nests under metadata.metadata; gallery sidecars use top-level.
        nest = metadata.get("metadata")
        if isinstance(nest, dict):
            nest["soundtrack"] = str(path)
            nest["soundtrack_url"] = soundtrack_url
        else:
            metadata["soundtrack"] = str(path)
            metadata["soundtrack_url"] = soundtrack_url

        sidecar = image_path.with_suffix(".json")
        payload = metadata
        if sidecar.exists():
            try:
                existing = json.loads(sidecar.read_text())
                if isinstance(existing, dict):
                    if isinstance(nest, dict):
                        existing.setdefault("metadata", {})
                        if isinstance(existing["metadata"], dict):
                            existing["metadata"]["soundtrack"] = str(path)
                            existing["metadata"]["soundtrack_url"] = soundtrack_url
                        existing["soundtrack"] = str(path)
                        existing["soundtrack_url"] = soundtrack_url
                    else:
                        existing["soundtrack"] = str(path)
                        existing["soundtrack_url"] = soundtrack_url
                    payload = existing
            except Exception:
                payload = metadata
        sidecar.write_text(json.dumps(payload, indent=2, default=str))
        logger.info("soundtrack_paired", image=str(image_path), audio=str(path))
        return path
    except Exception as e:
        logger.warning("soundtrack_pairing_failed", error=str(e))
        return None


def apply_cli_presence_after_creation(
    *,
    mood_system: Any,
    memory_system: Any = None,
    learner: Any = None,
    subject: str = "",
    style: str = "",
    score: float = 0.0,
    prompt: str = "",
    image_path: Path | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """CLI path: satisfy drives, persist mood + desires, maybe pair soundtrack."""
    drive_status: dict[str, Any] | None = None
    try:
        from ..intelligence.desire_engine import get_desire_engine

        engine = get_desire_engine(
            mood_system=mood_system,
            memory_system=memory_system,
            learner=learner,
        )
        desire = engine.get_strongest_desire()
        engine.satisfy_drive(desire.drive_name, subject=subject, style=style)
        engine.save()
        try:
            drive_status = engine.get_drive_status()
        except Exception:
            drive_status = None
    except Exception as e:
        logger.debug("cli_desire_presence_failed", error=str(e))

    try:
        from .moods import MoodSystem

        if isinstance(mood_system, MoodSystem):
            save_json(MOOD_STATE_FILE, mood_system.to_dict())
    except Exception as e:
        logger.debug("cli_mood_persist_failed", error=str(e))

    mood_value = getattr(
        getattr(mood_system, "current_mood", None),
        "value",
        "contemplative",
    )

    try:
        note_creation_for_statement(
            {
                "id": subject or "cli",
                "details": {
                    "subject": subject,
                    "style": style,
                    "score": score,
                },
                "emotional_state": {"mood": mood_value},
            }
        )
    except Exception as e:
        logger.debug("cli_statement_note_failed", error=str(e))

    if image_path is not None and (prompt or subject):
        try:
            want_sound = should_pair_soundtrack(
                mood=mood_value,
                drive_status=drive_status,
            )
            meta = metadata if metadata is not None else {}
            maybe_pair_soundtrack(
                prompt=prompt or f"{subject}, {style}".strip(", "),
                mood=mood_value,
                image_path=Path(image_path),
                metadata=meta,
                enabled=want_sound,
            )
        except Exception as e:
            logger.debug("cli_soundtrack_presence_failed", error=str(e))


async def apply_cli_presence_before_creation(
    *,
    mood_system: Any,
    inner_dialogue: Any = None,
    memory_system: Any = None,
    learner: Any = None,
    theme: str | None = None,
) -> dict[str, Any]:
    """CLI/scheduler: occasional deep deliberate + seed subject/style.

    Returns a context dict that may include ``seed_subject`` / ``seed_style``.
    """
    context: dict[str, Any] = {}
    if theme:
        context["theme"] = theme
        return context
    if inner_dialogue is None:
        return context

    drive_status: dict[str, Any] | None = None
    try:
        from ..intelligence.desire_engine import get_desire_engine

        drive_status = get_desire_engine(
            mood_system=mood_system,
            memory_system=memory_system,
            learner=learner,
        ).get_drive_status()
    except Exception as e:
        logger.debug("cli_drive_status_failed", error=str(e))

    if not should_deep_deliberate(drive_status=drive_status):
        return context

    try:
        mood_value = getattr(
            getattr(mood_system, "current_mood", None),
            "value",
            "contemplative",
        )
        concept = await inner_dialogue.deliberate(
            mood=mood_value,
            clear_history=False,
        )
        if concept and getattr(concept, "subject", None):
            context["seed_subject"] = concept.subject
            context["theme"] = concept.subject
            top_style = None
            style_blend = getattr(concept, "style_blend", None) or {}
            if style_blend:
                top_style = max(style_blend.items(), key=lambda x: x[1])[0]
            if top_style:
                context["seed_style"] = top_style
            logger.info(
                "cli_deep_deliberation_seeded",
                subject=concept.subject,
                style=top_style,
            )
    except Exception as e:
        logger.debug("cli_deep_deliberation_skipped", error=str(e))
    return context
