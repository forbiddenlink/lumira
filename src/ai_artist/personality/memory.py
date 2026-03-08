"""Lumira's memory and journaling system."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ArtistMemory:
    """Manages Lumira's memory of her creative journey."""

    def __init__(self, memory_file: Path = Path("data/lumira_memory.json")):
        self.memory_file = memory_file
        self.memory: dict[str, Any] = {
            "name": "Lumira",
            "created_at": datetime.now().isoformat(),
            "paintings": [],
            "reflections": [],
            "preferences": {
                "favorite_subjects": {},
                "favorite_styles": {},
                "favorite_colors": {},
            },
            "stats": {
                "total_created": 0,
                "best_score": 0.0,
                "favorite_mood": None,
            },
        }
        self._load()

        logger.info(
            "memory_initialized",
            memory_file=str(memory_file),
            paintings_count=len(self.memory["paintings"]),
        )

    def _load(self):
        """Load memory from disk."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file) as f:
                    loaded = json.load(f)
                    self.memory.update(loaded)
                logger.info("memory_loaded", paintings=len(self.memory["paintings"]))
            except Exception as e:
                logger.error("memory_load_failed", error=str(e))
        else:
            logger.info("no_existing_memory", creating_new=True)

    def _save(self):
        """Save memory to disk."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_file, "w") as f:
                json.dump(self.memory, f, indent=2)
            logger.info("memory_saved", paintings=len(self.memory["paintings"]))
        except Exception as e:
            logger.error("memory_save_failed", error=str(e))

    def remember_artwork(
        self,
        prompt: str,
        subject: str,
        style: str,
        mood: str,
        colors: list[str],
        score: float,
        image_path: str,
        metadata: dict | None = None,
    ):
        """Remember a piece Lumira created."""
        artwork = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "subject": subject,
            "style": style,
            "mood": mood,
            "colors": colors,
            "score": score,
            "image_path": image_path,
            "metadata": metadata or {},
        }

        self.memory["paintings"].append(artwork)
        self.memory["stats"]["total_created"] += 1

        # Update best score
        if score > self.memory["stats"]["best_score"]:
            self.memory["stats"]["best_score"] = score

        # Update preferences
        self._update_preferences(subject, style, colors)

        self._save()

        logger.info(
            "artwork_remembered",
            subject=subject,
            style=style,
            mood=mood,
            score=score,
            total=self.memory["stats"]["total_created"],
        )

    def _update_preferences(self, subject: str, style: str, colors: list[str]):
        """Update what Lumira likes based on what she creates."""
        # Track subject preferences
        self.memory["preferences"]["favorite_subjects"][subject] = (
            self.memory["preferences"]["favorite_subjects"].get(subject, 0) + 1
        )

        # Track style preferences
        self.memory["preferences"]["favorite_styles"][style] = (
            self.memory["preferences"]["favorite_styles"].get(style, 0) + 1
        )

        # Track color preferences
        for color in colors:
            self.memory["preferences"]["favorite_colors"][color] = (
                self.memory["preferences"]["favorite_colors"].get(color, 0) + 1
            )

    def add_reflection(self, reflection: str, about_painting: str | None = None):
        """Lumira reflects on her work or creative process."""
        reflection_entry = {
            "timestamp": datetime.now().isoformat(),
            "reflection": reflection,
            "about_painting": about_painting,
        }

        self.memory["reflections"].append(reflection_entry)
        self._save()

        logger.info(
            "reflection_added", length=len(reflection), about=about_painting is not None
        )

    def get_recent_works(self, limit: int = 10) -> list[dict]:
        """Get Lumira's recent artwork."""
        works: list[dict] = self.memory["paintings"][-limit:]
        return works

    def get_best_works(self, limit: int = 10) -> list[dict]:
        """Get Lumira's highest-scored artwork."""
        sorted_works = sorted(
            self.memory["paintings"], key=lambda x: x.get("score", 0), reverse=True
        )
        return sorted_works[:limit]

    def get_favorite_subject(self) -> str | None:
        """What subject does Lumira paint most?"""
        subjects: dict[str, int] = self.memory["preferences"]["favorite_subjects"]
        if not subjects:
            return None
        return max(subjects, key=lambda k: subjects[k])

    def get_favorite_style(self) -> str | None:
        """What style does Lumira prefer?"""
        styles: dict[str, int] = self.memory["preferences"]["favorite_styles"]
        if not styles:
            return None
        return max(styles, key=lambda k: styles[k])

    def has_painted_recently(self, subject: str, threshold: int = 5) -> bool:
        """Check if Lumira has painted this subject recently."""
        recent = self.memory["paintings"][-threshold:]
        return any(p.get("subject") == subject for p in recent)

    def generate_reflection(self, artwork: dict) -> str:
        """Generate a reflection about a piece."""
        reflections = [
            f"In creating '{artwork['subject']}', I found myself drawn to {artwork['style']} style. The {artwork['mood']} mood really shaped this piece.",
            f"This {artwork['subject']} emerged from a {artwork['mood']} state. I'm {'' if artwork['score'] > 0.7 else 'not quite '}satisfied with how it turned out.",
            f"I chose {artwork['subject']} because it felt right in this moment. The colors I used reflect my current energy.",
            f"Looking at this {artwork['style']} interpretation of {artwork['subject']}, I see parts of myself I didn't know were there.",
            f"This piece taught me something about {artwork['subject']} - and about myself.",
        ]

        import random

        return random.choice(reflections)

    def get_stats(self) -> dict:
        """Get Lumira's creative statistics."""
        return {
            "total_artworks": self.memory["stats"]["total_created"],
            "best_score": self.memory["stats"]["best_score"],
            "favorite_subject": self.get_favorite_subject(),
            "favorite_style": self.get_favorite_style(),
            "recent_works": len(self.get_recent_works()),
            "memory_size": len(self.memory["paintings"]),
        }
