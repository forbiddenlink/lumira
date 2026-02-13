"""Aria's memory system - Journaling and reflection on her creative journey."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ArtistMemory:
    """Aria's memory of her creative journey.

    Stores:
    - Paintings created
    - Reflections on each piece
    - Evolution of preferences
    - Notable moments in her artistic development
    """

    def __init__(self, memory_file: Path = Path("data/aria_memory.json")):
        self.memory_file = memory_file
        self.memory: dict[str, Any] = {
            "artist_name": "Aria",
            "started_creating": datetime.now().isoformat(),
            "paintings": [],
            "reflections": [],
            "milestones": [],
            "personality_snapshots": [],
            "total_creations": 0,
        }

        # Load existing memory if available
        self._load_memory()

        logger.info(
            "memory_initialized",
            memory_file=str(self.memory_file),
            total_creations=self.memory["total_creations"],
        )

    def _coerce_paintings(self) -> list[dict[str, Any]]:
        """Return normalized painting records."""
        paintings = self.memory.get("paintings", [])
        if not isinstance(paintings, list):
            return []
        return [p for p in paintings if isinstance(p, dict)]

    def _coerce_snapshots(self) -> list[dict[str, Any]]:
        """Return normalized personality snapshots."""
        snapshots = self.memory.get("personality_snapshots", [])
        if not isinstance(snapshots, list):
            return []
        return [s for s in snapshots if isinstance(s, dict)]

    def _coerce_milestones(self) -> list[dict[str, Any]]:
        """Return normalized milestone records."""
        milestones = self.memory.get("milestones", [])
        if not isinstance(milestones, list):
            return []
        return [m for m in milestones if isinstance(m, dict)]

    def _load_memory(self) -> None:
        """Load memory from disk."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file) as f:
                    loaded = json.load(f)

                if isinstance(loaded, dict):
                    self.memory = loaded
                else:
                    logger.warning(
                        "memory_file_invalid_format", file=str(self.memory_file)
                    )

                logger.info(
                    "memory_loaded",
                    total_creations=self.memory.get("total_creations", 0),
                    paintings=len(self._coerce_paintings()),
                )
            except Exception as e:
                logger.error("memory_load_failed", error=str(e))

    def save_memory(self) -> None:
        """Save memory to disk."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_file, "w") as f:
                json.dump(self.memory, f, indent=2)
            logger.info("memory_saved", file=str(self.memory_file))
        except Exception as e:
            logger.error("memory_save_failed", error=str(e))

    def record_painting(
        self,
        image_path: str,
        prompt: str,
        mood: str,
        style: str,
        subject: str,
        score: float,
        reflection: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        """Record a newly created painting."""
        painting_record = {
            "number": int(self.memory.get("total_creations", 0)) + 1,
            "timestamp": datetime.now().isoformat(),
            "image_path": image_path,
            "prompt": prompt,
            "mood": mood,
            "style": style,
            "subject": subject,
            "score": score,
            "reflection": reflection,
            "metadata": metadata or {},
        }

        paintings = self._coerce_paintings()
        paintings.append(painting_record)
        self.memory["paintings"] = paintings
        self.memory["total_creations"] = int(self.memory.get("total_creations", 0)) + 1

        logger.info(
            "painting_recorded",
            number=painting_record["number"],
            score=score,
            mood=mood,
        )

        self.save_memory()

    def record_reflection(
        self, reflection: str, context: dict[Any, Any] | None = None
    ) -> None:
        """Record a general reflection or thought."""
        reflection_entry = {
            "timestamp": datetime.now().isoformat(),
            "reflection": reflection,
            "context": context or {},
        }

        reflections = self.memory.get("reflections", [])
        if not isinstance(reflections, list):
            reflections = []
        reflections.append(reflection_entry)
        self.memory["reflections"] = reflections
        logger.debug("reflection_recorded", length=len(reflection))
        self.save_memory()

    def record_milestone(
        self, milestone: str, details: dict[str, Any] | None = None
    ) -> None:
        """Record a significant milestone in artistic development."""
        milestone_entry = {
            "timestamp": datetime.now().isoformat(),
            "milestone": milestone,
            "creation_count": self.memory["total_creations"],
            "details": details or {},
        }

        milestones = self._coerce_milestones()
        milestones.append(milestone_entry)
        self.memory["milestones"] = milestones
        logger.info("milestone_recorded", milestone=milestone)
        self.save_memory()

    def snapshot_personality(self, personality_state: dict[str, Any]) -> None:
        """Save a snapshot of personality state for evolution tracking."""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "creation_count": self.memory["total_creations"],
            "state": personality_state,
        }

        snapshots = self._coerce_snapshots()
        snapshots.append(snapshot)
        self.memory["personality_snapshots"] = snapshots[-50:]

        self.save_memory()

    def get_recent_paintings(self, count: int = 10) -> list[dict[str, Any]]:
        """Get most recent paintings."""
        return self._coerce_paintings()[-count:]

    def get_best_paintings(
        self, count: int = 10, min_score: float = 0.65
    ) -> list[dict[str, Any]]:
        """Get highest-scored paintings."""
        scored = [p for p in self._coerce_paintings() if p.get("score", 0) >= min_score]
        scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        return scored[:count]

    def get_paintings_by_mood(self, mood: str) -> list[dict[str, Any]]:
        """Get all paintings created in a specific mood."""
        return [p for p in self._coerce_paintings() if p.get("mood") == mood]

    def get_paintings_by_subject(self, subject: str) -> list[dict[str, Any]]:
        """Get all paintings of a specific subject."""
        return [p for p in self._coerce_paintings() if p.get("subject") == subject]

    def get_style_statistics(self) -> dict[str, int]:
        """Get count of paintings by style."""
        stats: dict[str, int] = {}
        for painting in self._coerce_paintings():
            style = painting.get("style", "unknown")
            if not isinstance(style, str):
                style = "unknown"
            stats[style] = stats.get(style, 0) + 1
        return stats

    def get_average_score_by_mood(self) -> dict[str, float]:
        """Calculate average score for each mood."""
        mood_scores: dict[str, float] = {}
        mood_counts: dict[str, int] = {}

        for painting in self._coerce_paintings():
            mood = painting.get("mood")
            score = painting.get("score")
            if not isinstance(mood, str) or not isinstance(score, int | float):
                continue

            mood_scores[mood] = mood_scores.get(mood, 0.0) + float(score)
            mood_counts[mood] = mood_counts.get(mood, 0) + 1

        return {mood: mood_scores[mood] / mood_counts[mood] for mood in mood_scores}

    def journal_entry(self) -> str:
        """Generate a journal entry summarizing recent creative activity."""
        recent = self.get_recent_paintings(5)
        if not recent:
            return "I haven't created anything yet. The canvas awaits..."

        avg_score = sum(float(p.get("score", 0.0)) for p in recent) / len(recent)
        moods = [str(p.get("mood", "unknown")) for p in recent]
        most_common_mood = max(set(moods), key=moods.count)

        entry = f"I've created {len(recent)} pieces recently. "
        entry += f"I've been feeling mostly {most_common_mood}, "
        entry += f"and my work has been scoring an average of {avg_score:.2f}. "

        if avg_score >= 0.7:
            entry += "I'm quite pleased with my recent output."
        elif avg_score >= 0.5:
            entry += "There's room for growth, but I'm learning."
        else:
            entry += (
                "I'm in an experimental phase - not everything lands, but that's okay."
            )

        return entry

    def import_legacy_memory(self, legacy_file: Path) -> None:
        """Import memory from the original autonomous-artist project."""
        if not legacy_file.exists():
            logger.warning("legacy_memory_not_found", file=str(legacy_file))
            return

        try:
            with open(legacy_file) as f:
                legacy = json.load(f)

            # Add legacy paintings as historical
            if "paintings" in legacy and isinstance(legacy["paintings"], list):
                paintings = self._coerce_paintings()
                for painting in legacy["paintings"]:
                    if not isinstance(painting, dict):
                        continue
                    painting["legacy"] = True
                    painting["imported_at"] = datetime.now().isoformat()
                    paintings.append(painting)
                self.memory["paintings"] = paintings

            # Record milestone
            self.record_milestone(
                "Imported legacy memories from previous artistic life",
                {
                    "legacy_file": str(legacy_file),
                    "paintings_imported": len(legacy.get("paintings", [])),
                },
            )

            logger.info(
                "legacy_memory_imported",
                paintings=len(legacy.get("paintings", [])),
                source=str(legacy_file),
            )

            self.save_memory()
        except Exception as e:
            logger.error("legacy_import_failed", error=str(e))
