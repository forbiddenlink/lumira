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
    if intensity >= 0.7 and random.random() < 0.55:
        return True
    return False


def note_creation_for_statement(creation_record: dict[str, Any]) -> dict[str, Any] | None:
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


def apply_cli_presence_after_creation(
    *,
    mood_system: Any,
    memory_system: Any = None,
    learner: Any = None,
    subject: str = "",
    style: str = "",
    score: float = 0.0,
) -> None:
    """CLI path: satisfy drives, persist mood + desires so web continues as her."""
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
    except Exception as e:
        logger.debug("cli_desire_presence_failed", error=str(e))

    try:
        from .moods import MoodSystem

        if isinstance(mood_system, MoodSystem):
            save_json(MOOD_STATE_FILE, mood_system.to_dict())
    except Exception as e:
        logger.debug("cli_mood_persist_failed", error=str(e))

    try:
        note_creation_for_statement(
            {
                "id": subject or "cli",
                "details": {
                    "subject": subject,
                    "style": style,
                    "score": score,
                },
                "emotional_state": {
                    "mood": getattr(
                        getattr(mood_system, "current_mood", None),
                        "value",
                        "contemplative",
                    )
                },
            }
        )
    except Exception as e:
        logger.debug("cli_statement_note_failed", error=str(e))
