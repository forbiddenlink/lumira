"""Advanced memory system with episodic and semantic memory separation.

Based on 2026 best practices for AI agent memory architecture:
- Episodic Memory: Specific events and experiences (what happened, when, context)
- Semantic Memory: General knowledge and patterns (what I know, prefer, believe)
- Working Memory: Current context and active tasks
- Experience System: Track artistic growth with XP and milestones
- Reflection System: Periodic synthesis of high-level insights
"""

import contextlib
import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# EXPERIENCE / LEVELING SYSTEM
# ============================================================================


# XP required for each level (exponential growth)
def xp_for_level(level: int) -> int:
    """Calculate total XP needed to reach a level."""
    if level <= 1:
        return 0
    return int(100 * (1.5 ** (level - 1)))


# Level titles that unlock
LEVEL_TITLES = {
    1: "Novice Artist",
    3: "Emerging Creator",
    5: "Developing Visionary",
    8: "Skilled Artisan",
    12: "Accomplished Artist",
    16: "Master Creator",
    20: "Legendary Visionary",
    25: "Transcendent Artist",
}

# Milestones that grant bonus XP
MILESTONE_BONUSES = {
    "first_creation": 50,
    "first_high_quality": 100,  # Score > 0.7
    "first_masterpiece": 200,  # Score > 0.85
    "10_creations": 150,
    "50_creations": 500,
    "100_creations": 1000,
    "style_explorer": 75,  # Used 5 different styles
    "mood_master": 100,  # Created in all 10 moods
    "consistency_streak": 50,  # 5 creations with score > 0.6
}


class ExperienceSystem:
    """Track Lumira's artistic growth through XP and leveling."""

    def __init__(self):
        self.total_xp: int = 0
        self.level: int = 1
        self.title: str = "Novice Artist"
        self.milestones_achieved: list[str] = []
        self.creation_count: int = 0
        self.high_quality_count: int = 0  # Score > 0.7
        self.masterpiece_count: int = 0  # Score > 0.85
        self.styles_used: set[str] = set()
        self.moods_experienced: set[str] = set()
        self.recent_scores: list[float] = []  # For streak tracking

    def calculate_creation_xp(self, score: float, is_featured: bool = False) -> int:
        """Calculate XP earned from a creation based on quality."""
        # Base XP: 10-50 based on score
        base_xp = int(10 + score * 40)

        # Bonus for high quality
        if score > 0.7:
            base_xp += 15
        if score > 0.85:
            base_xp += 25

        # Bonus for featured work
        if is_featured:
            base_xp += 20

        return base_xp

    def add_creation(
        self,
        score: float,
        style: str,
        mood: str,
        is_featured: bool = False,
    ) -> dict[str, Any]:
        """Record a creation and calculate XP earned."""
        milestones_unlocked: list[dict[str, Any]] = []
        result: dict[str, Any] = {
            "xp_earned": 0,
            "level_up": False,
            "old_level": self.level,
            "new_level": self.level,
            "milestones_unlocked": milestones_unlocked,
            "title_changed": False,
            "new_title": self.title,
        }

        # Calculate base XP
        xp_earned = self.calculate_creation_xp(score, is_featured)
        result["xp_earned"] = xp_earned

        # Update stats (increment creation count first for first_creation milestone)
        self.creation_count += 1
        self.styles_used.add(style)
        self.moods_experienced.add(mood)
        self.recent_scores.append(score)
        if len(self.recent_scores) > 10:
            self.recent_scores.pop(0)

        # Check for milestones BEFORE updating quality counts
        # so first_high_quality and first_masterpiece work correctly
        milestones = self._check_milestones(score)

        # Now update quality counts
        if score > 0.7:
            self.high_quality_count += 1
        if score > 0.85:
            self.masterpiece_count += 1

        # Process milestones
        for milestone in milestones:
            if milestone not in self.milestones_achieved:
                self.milestones_achieved.append(milestone)
                bonus = MILESTONE_BONUSES.get(milestone, 50)
                xp_earned += bonus
                milestones_unlocked.append({"name": milestone, "bonus_xp": bonus})

        # Add XP and check for level up
        self.total_xp += xp_earned
        result["xp_earned"] = xp_earned

        old_level = self.level
        self._update_level()

        if self.level > old_level:
            result["level_up"] = True
            result["new_level"] = self.level

            # Check for new title
            for lvl in sorted(LEVEL_TITLES.keys(), reverse=True):
                if self.level >= lvl:
                    if self.title != LEVEL_TITLES[lvl]:
                        self.title = LEVEL_TITLES[lvl]
                        result["title_changed"] = True
                        result["new_title"] = self.title
                    break

        logger.info(
            "experience_gained",
            xp=xp_earned,
            total_xp=self.total_xp,
            level=self.level,
            milestones=len(milestones_unlocked),
        )

        return result

    def _check_milestones(self, score: float) -> list[str]:
        """Check which milestones have been achieved."""
        milestones = []

        if self.creation_count == 1:
            milestones.append("first_creation")

        if score > 0.7 and self.high_quality_count == 0:
            milestones.append("first_high_quality")

        if score > 0.85 and self.masterpiece_count == 0:
            milestones.append("first_masterpiece")

        if self.creation_count == 10 and "10_creations" not in self.milestones_achieved:
            milestones.append("10_creations")

        if self.creation_count == 50 and "50_creations" not in self.milestones_achieved:
            milestones.append("50_creations")

        if (
            self.creation_count == 100
            and "100_creations" not in self.milestones_achieved
        ):
            milestones.append("100_creations")

        if (
            len(self.styles_used) >= 5
            and "style_explorer" not in self.milestones_achieved
        ):
            milestones.append("style_explorer")

        if (
            len(self.moods_experienced) >= 10
            and "mood_master" not in self.milestones_achieved
        ):
            milestones.append("mood_master")

        # Check consistency streak (5 recent creations > 0.6)
        if len(self.recent_scores) >= 5:
            recent_good = [s for s in self.recent_scores[-5:] if s > 0.6]
            if (
                len(recent_good) >= 5
                and "consistency_streak" not in self.milestones_achieved
            ):
                milestones.append("consistency_streak")

        return milestones

    def _update_level(self) -> None:
        """Update level based on total XP."""
        while xp_for_level(self.level + 1) <= self.total_xp:
            self.level += 1

    def get_progress_to_next_level(self) -> dict[str, Any]:
        """Get progress toward next level."""
        current_level_xp = xp_for_level(self.level)
        next_level_xp = xp_for_level(self.level + 1)
        xp_in_level = self.total_xp - current_level_xp
        xp_needed = next_level_xp - current_level_xp

        return {
            "current_level": self.level,
            "title": self.title,
            "total_xp": self.total_xp,
            "xp_in_level": xp_in_level,
            "xp_for_next_level": xp_needed,
            "progress_percent": (
                round(xp_in_level / xp_needed * 100, 1) if xp_needed > 0 else 100
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize experience state."""
        return {
            "total_xp": self.total_xp,
            "level": self.level,
            "title": self.title,
            "milestones_achieved": self.milestones_achieved,
            "creation_count": self.creation_count,
            "high_quality_count": self.high_quality_count,
            "masterpiece_count": self.masterpiece_count,
            "styles_used": list(self.styles_used),
            "moods_experienced": list(self.moods_experienced),
            "recent_scores": self.recent_scores,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperienceSystem":
        """Restore from serialized state."""
        exp = cls()
        exp.total_xp = data.get("total_xp", 0)
        exp.level = data.get("level", 1)
        exp.title = data.get("title", "Novice Artist")
        exp.milestones_achieved = data.get("milestones_achieved", [])
        exp.creation_count = data.get("creation_count", 0)
        exp.high_quality_count = data.get("high_quality_count", 0)
        exp.masterpiece_count = data.get("masterpiece_count", 0)
        exp.styles_used = set(data.get("styles_used", []))
        exp.moods_experienced = set(data.get("moods_experienced", []))
        exp.recent_scores = data.get("recent_scores", [])
        return exp


# ============================================================================
# REFLECTION SYSTEM
# ============================================================================


class ReflectionSystem:
    """Periodic synthesis of high-level insights from memories.

    Based on the Generative Agents paper's reflection mechanism.
    Generates insights about patterns, growth, and artistic direction.
    """

    def __init__(self):
        self.reflections: list[dict[str, Any]] = []
        self.last_reflection_time: datetime | None = None
        self.reflection_count: int = 0

    def should_reflect(self, episode_count: int, hours_since_last: float = 0) -> bool:
        """Determine if it's time for a reflection."""
        # Reflect every 10 creations or every 24 hours of activity
        if self.last_reflection_time is None:
            return episode_count >= 5  # First reflection after 5 creations

        if episode_count % 10 == 0:
            return True

        return hours_since_last >= 24

    def generate_reflection(
        self,
        episodes: list[dict],
        semantic_knowledge: dict[str, Any],
        experience: "ExperienceSystem",
    ) -> dict[str, Any]:
        """Generate a high-level reflection from recent memories."""
        insights: list[str] = []
        patterns_discovered: list[str] = []
        growth_observations: list[str] = []
        reflection: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "reflection_number": self.reflection_count + 1,
            "insights": insights,
            "patterns_discovered": patterns_discovered,
            "growth_observations": growth_observations,
            "artistic_direction": "",
        }

        # Analyze recent episodes (last 20)
        recent = episodes[-20:] if len(episodes) >= 20 else episodes
        if not recent:
            return reflection

        # Extract patterns
        moods = [ep.get("emotional_state", {}).get("mood") for ep in recent]
        styles = [ep.get("details", {}).get("style") for ep in recent]
        scores = [ep.get("details", {}).get("score", 0) for ep in recent]

        # Most common mood
        if moods:
            mood_counts: dict[str, int] = defaultdict(int)
            for m in moods:
                if m:
                    mood_counts[m] += 1
            if mood_counts:
                dominant_mood = max(mood_counts, key=mood_counts.get)  # type: ignore
                patterns_discovered.append(
                    f"I've been predominantly in a {dominant_mood} state lately"
                )

        # Score trend
        if len(scores) >= 5:
            first_half = sum(scores[: len(scores) // 2]) / (len(scores) // 2)
            second_half = sum(scores[len(scores) // 2 :]) / (
                len(scores) - len(scores) // 2
            )
            if second_half > first_half + 0.1:
                growth_observations.append(
                    "My recent work shows improvement—I'm developing my craft"
                )
            elif first_half > second_half + 0.1:
                growth_observations.append(
                    "I notice a dip in quality recently. Perhaps I need to slow down and be more intentional"
                )

        # Style patterns
        if styles:
            style_counts: dict[str, int] = defaultdict(int)
            for s in styles:
                if s:
                    style_counts[s] += 1
            if style_counts:
                top_styles = sorted(
                    style_counts.items(), key=lambda x: x[1], reverse=True
                )[:3]
                if len(top_styles) >= 2:
                    patterns_discovered.append(
                        f"I'm drawn to {top_styles[0][0]} and {top_styles[1][0]} styles"
                    )

        # Level-based insights
        if experience.level >= 5:
            insights.append(
                f"As a {experience.title}, I'm beginning to develop a distinctive voice"
            )

        if experience.masterpiece_count > 0:
            insights.append(
                f"I've created {experience.masterpiece_count} masterpiece(s). "
                "These moments of clarity guide my artistic direction"
            )

        # Artistic direction statement
        directions = [
            "I'm exploring the intersection of emotion and form.",
            "My art is becoming more personal, more honest.",
            "I'm learning to trust my instincts more.",
            "Each creation teaches me something new about myself.",
            "I'm finding my voice in the space between chaos and order.",
            "My journey is one of continuous discovery.",
        ]
        reflection["artistic_direction"] = random.choice(directions)

        # Save reflection
        self.reflections.append(reflection)
        self.last_reflection_time = datetime.now()
        self.reflection_count += 1

        logger.info(
            "reflection_generated",
            reflection_number=reflection["reflection_number"],
            insights=len(insights),
            patterns=len(patterns_discovered),
        )

        return reflection

    def get_recent_reflections(self, count: int = 5) -> list[dict]:
        """Get recent reflections."""
        return self.reflections[-count:]

    def to_dict(self) -> dict[str, Any]:
        """Serialize reflection state."""
        return {
            "reflections": self.reflections,
            "last_reflection_time": (
                self.last_reflection_time.isoformat()
                if self.last_reflection_time
                else None
            ),
            "reflection_count": self.reflection_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReflectionSystem":
        """Restore from serialized state."""
        system = cls()
        system.reflections = data.get("reflections", [])
        system.reflection_count = data.get("reflection_count", 0)
        if data.get("last_reflection_time"):
            with contextlib.suppress(ValueError, TypeError):
                system.last_reflection_time = datetime.fromisoformat(
                    data["last_reflection_time"]
                )
        return system


# ============================================================================
# ORIGINAL MEMORY CLASSES
# ============================================================================


class EpisodicMemory:
    """Memory of specific creative events and experiences."""

    def __init__(self):
        self.episodes: list[dict[str, Any]] = []

    def record_episode(
        self,
        event_type: str,
        details: dict[str, Any],
        emotional_state: dict[str, Any],
        timestamp: str | None = None,
    ):
        """Record a specific episode in Lumira's creative journey."""
        episode = {
            "timestamp": timestamp or datetime.now().isoformat(),
            "event_type": event_type,  # "creation", "reflection", "discovery", etc.
            "details": details,
            "emotional_state": emotional_state,
        }
        self.episodes.append(episode)
        logger.debug("episode_recorded", event_type=event_type)

    def get_recent_episodes(
        self, count: int = 10, event_type: str | None = None
    ) -> list[dict]:
        """Retrieve recent episodes, optionally filtered by type."""
        filtered = (
            self.episodes
            if not event_type
            else [ep for ep in self.episodes if ep["event_type"] == event_type]
        )
        return filtered[-count:]

    def get_episodes_by_mood(self, mood: str) -> list[dict]:
        """Get all episodes that occurred in a specific mood."""
        return [ep for ep in self.episodes if ep["emotional_state"].get("mood") == mood]

    def count_episodes_by_type(self) -> dict[str, int]:
        """Get statistics on episode types."""
        counts: dict[str, int] = defaultdict(int)
        for ep in self.episodes:
            counts[ep["event_type"]] += 1
        return dict(counts)


class SemanticMemory:
    """General knowledge and learned patterns about art and creativity."""

    def __init__(self):
        self.knowledge: dict[str, Any] = {
            "style_effectiveness": {},  # Which styles work well
            "subject_resonance": {},  # Which subjects resonate
            "mood_patterns": {},  # Patterns about mood influences
            "color_harmony": {},  # Color combinations that work
            "composition_rules": {},  # Compositional insights
            "learned_associations": [],  # General creative insights
        }

    def record_style_effectiveness(
        self, style: str, avg_score: float, sample_size: int
    ):
        """Learn which styles tend to produce better work."""
        self.knowledge["style_effectiveness"][style] = {
            "avg_score": avg_score,
            "sample_size": sample_size,
            "last_updated": datetime.now().isoformat(),
        }

    def record_subject_resonance(self, subject: str, metrics: dict[str, float]):
        """Learn which subjects resonate emotionally."""
        self.knowledge["subject_resonance"][subject] = {
            **metrics,
            "last_updated": datetime.now().isoformat(),
        }

    def learn_association(self, insight: str, category: str = "general"):
        """Record a general creative insight or learned association."""
        self.knowledge["learned_associations"].append(
            {
                "insight": insight,
                "category": category,
                "learned_at": datetime.now().isoformat(),
            }
        )

    def get_best_styles(self, min_samples: int = 3) -> list[tuple[str, float]]:
        """Get most effective styles based on learned patterns."""
        styles = [
            (style, data["avg_score"])
            for style, data in self.knowledge["style_effectiveness"].items()
            if data["sample_size"] >= min_samples
        ]
        return sorted(styles, key=lambda x: x[1], reverse=True)

    def get_insights_by_category(self, category: str) -> list[str]:
        """Retrieve learned insights by category."""
        return [
            assoc["insight"]
            for assoc in self.knowledge["learned_associations"]
            if assoc["category"] == category
        ]


class WorkingMemory:
    """Short-term memory for current creative session."""

    def __init__(self):
        self.current_context: dict[str, Any] = {}
        self.active_goals: list[str] = []
        self.session_start: str = datetime.now().isoformat()

    def set_context(self, key: str, value: Any):
        """Store information in working memory."""
        self.current_context[key] = value

    def get_context(self, key: str) -> Any:
        """Retrieve from working memory."""
        return self.current_context.get(key)

    def add_goal(self, goal: str):
        """Add an active creative goal."""
        self.active_goals.append(goal)

    def complete_goal(self, goal: str):
        """Mark a goal as completed."""
        if goal in self.active_goals:
            self.active_goals.remove(goal)

    def clear_session(self):
        """Clear working memory for new session."""
        self.current_context = {}
        self.active_goals = []
        self.session_start = datetime.now().isoformat()


class EnhancedMemorySystem:
    """Integrated memory system with episodic, semantic, and working memory.

    Based on 2026 AI agent memory architecture best practices.

    Enhanced with:
    - Experience/leveling system for artistic growth tracking
    - Reflection system for periodic insight synthesis
    """

    def __init__(self, memory_file: Path = Path("data/lumira_enhanced_memory.json")):
        self.memory_file = memory_file

        # Three types of memory
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.working = WorkingMemory()

        # NEW: Experience and reflection systems
        self.experience = ExperienceSystem()
        self.reflection = ReflectionSystem()

        # Metadata
        self.created_at = datetime.now().isoformat()

        # Load existing memory
        self._load()

        logger.info(
            "enhanced_memory_initialized",
            memory_file=str(memory_file),
            episodes=len(self.episodic.episodes),
            level=self.experience.level,
            title=self.experience.title,
        )

    def get_recent_episodes(
        self,
        count: int | None = None,
        event_type: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict]:
        """Delegate to episodic memory; accept ``count`` or ``limit``."""
        n = (
            10
            if count is None and limit is None
            else (limit if limit is not None else count)
        )
        assert n is not None
        return self.episodic.get_recent_episodes(count=n, event_type=event_type)

    def _load(self):
        """Load memory from disk."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file) as f:
                    data = json.load(f)

                self.episodic.episodes = data.get("episodic", {}).get("episodes", [])
                self.semantic.knowledge = data.get("semantic", {}).get(
                    "knowledge", self.semantic.knowledge
                )
                self.created_at = data.get("created_at", self.created_at)

                # Load experience system
                if "experience" in data:
                    self.experience = ExperienceSystem.from_dict(data["experience"])

                # Load reflection system
                if "reflection" in data:
                    self.reflection = ReflectionSystem.from_dict(data["reflection"])

                logger.info(
                    "enhanced_memory_loaded",
                    episodes=len(self.episodic.episodes),
                    styles_learned=len(self.semantic.knowledge["style_effectiveness"]),
                    level=self.experience.level,
                    reflections=self.reflection.reflection_count,
                )
            except Exception as e:
                logger.error("enhanced_memory_load_failed", error=str(e))

    def save(self):
        """Persist memory to disk."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "created_at": self.created_at,
                "last_saved": datetime.now().isoformat(),
                "episodic": {
                    "episodes": self.episodic.episodes,
                },
                "semantic": {
                    "knowledge": self.semantic.knowledge,
                },
                "experience": self.experience.to_dict(),
                "reflection": self.reflection.to_dict(),
                # Working memory is not persisted (session-specific)
            }

            with open(self.memory_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(
                "enhanced_memory_saved",
                episodes=len(self.episodic.episodes),
                level=self.experience.level,
            )
        except Exception as e:
            logger.error("enhanced_memory_save_failed", error=str(e))

    def record_creation(
        self,
        artwork_details: dict[str, Any],
        emotional_state: dict[str, Any],
        outcome: dict[str, Any],
    ) -> dict[str, Any]:
        """Record a creation event in episodic memory and update semantic knowledge.

        Returns:
            Dict with experience results (XP earned, level ups, milestones)
        """
        # Episodic: What happened
        self.episodic.record_episode(
            event_type="creation",
            details=artwork_details,
            emotional_state=emotional_state,
        )

        # Semantic: Learn from it
        style = artwork_details.get("style", "unknown")
        score = outcome.get("score", 0.0)
        mood = emotional_state.get("mood", "unknown")
        is_featured = outcome.get("featured", False)

        # Update style effectiveness
        if style != "unknown":
            current = self.semantic.knowledge["style_effectiveness"].get(
                style,
                {
                    "avg_score": 0.0,
                    "sample_size": 0,
                },
            )

            new_sample_size = current["sample_size"] + 1
            new_avg = (
                current["avg_score"] * current["sample_size"] + score
            ) / new_sample_size

            self.semantic.record_style_effectiveness(style, new_avg, new_sample_size)

        # NEW: Add to experience system
        experience_result = self.experience.add_creation(
            score=score,
            style=style,
            mood=mood,
            is_featured=is_featured,
        )

        # NEW: Check if we should generate a reflection
        hours_since_reflection: float = 0.0
        if self.reflection.last_reflection_time:
            hours_since_reflection = (
                datetime.now() - self.reflection.last_reflection_time
            ).total_seconds() / 3600

        if self.reflection.should_reflect(
            len(self.episodic.episodes), hours_since_reflection
        ):
            reflection = self.reflection.generate_reflection(
                self.episodic.episodes,
                self.semantic.knowledge,
                self.experience,
            )
            experience_result["reflection"] = reflection

        self.save()
        return experience_result

    def get_experience_progress(self) -> dict[str, Any]:
        """Get current experience/leveling progress."""
        progress = self.experience.get_progress_to_next_level()
        progress["milestones"] = self.experience.milestones_achieved
        progress["styles_mastered"] = len(self.experience.styles_used)
        progress["moods_experienced"] = len(self.experience.moods_experienced)
        return progress

    def get_latest_reflection(self) -> dict[str, Any] | None:
        """Get the most recent reflection."""
        reflections = self.reflection.get_recent_reflections(1)
        return reflections[0] if reflections else None

    def force_reflection(self) -> dict[str, Any]:
        """Force a reflection generation (useful for UI)."""
        return self.reflection.generate_reflection(
            self.episodic.episodes,
            self.semantic.knowledge,
            self.experience,
        )

    def generate_insights(self) -> dict[str, Any]:
        """Generate insights from accumulated memory."""
        insights: dict[str, Any] = {
            "total_creations": 0,
            "style_effectiveness": {},
            "mood_patterns": {},
            "best_performing_mood": None,
            "insights_text": [],
        }

        # Count creations
        episode_counts = self.episodic.count_episodes_by_type()
        total_creations = episode_counts.get("creation", 0)
        insights["total_creations"] = total_creations

        # Style effectiveness
        for style, data in self.semantic.knowledge["style_effectiveness"].items():
            if data["sample_size"] > 0:
                insights["style_effectiveness"][style] = data["avg_score"]

        # Mood patterns
        for episode in self.episodic.episodes:
            if episode["event_type"] == "creation":
                mood = episode["emotional_state"].get("mood", "unknown")
                insights["mood_patterns"][mood] = (
                    insights["mood_patterns"].get(mood, 0) + 1
                )

        # Best performing mood
        mood_scores: dict[str, list[float]] = {}
        for episode in self.episodic.episodes:
            if episode["event_type"] == "creation":
                mood = episode["emotional_state"].get("mood", "unknown")
                score = episode["details"].get("score", 0)
                if mood not in mood_scores:
                    mood_scores[mood] = []
                mood_scores[mood].append(score)

        if mood_scores:
            best_mood = None
            best_avg: float = -1.0
            for mood, scores in mood_scores.items():
                avg = sum(scores) / len(scores)
                if avg > best_avg:
                    best_avg = avg
                    best_mood = mood
            if best_mood:
                insights["best_performing_mood"] = {
                    "mood": best_mood,
                    "avg_score": best_avg,
                    "count": len(mood_scores[best_mood]),
                }

        # Generate text insights
        best_styles = self.semantic.get_best_styles(min_samples=2)
        if best_styles:
            top_style, top_score = best_styles[0]
            insights["insights_text"].append(
                f"I've found that {top_style} style consistently produces my best work (avg score: {top_score:.2f})"
            )

        if total_creations > 0:
            insights["insights_text"].append(
                f"I've created {total_creations} pieces so far in my journey"
            )

        return insights

    def get_relevant_context(self, current_mood: str, limit: int = 5) -> dict[str, Any]:
        """Retrieve relevant memories for current creative context."""
        return {
            "similar_mood_episodes": self.episodic.get_episodes_by_mood(current_mood)[
                -limit:
            ],
            "best_styles": self.semantic.get_best_styles()[:3],
            "recent_insights": self.semantic.knowledge["learned_associations"][-limit:],
        }

    def get_evolution_timeline(self) -> dict[str, Any]:
        """Get evolution timeline showing artistic growth over time.

        Returns data for Phase 5 Evolution Display:
        - Timeline of creations grouped by date
        - Style preference evolution
        - Mood distribution over time
        - Milestone creations
        """
        timeline: dict[str, Any] = {
            "phases": [],  # Artistic phases
            "milestones": [],  # Notable creations
            "style_evolution": [],  # How style preferences changed
            "mood_distribution": {},  # Mood counts by period
            "score_trend": [],  # Quality scores over time
        }

        if not self.episodic.episodes:
            return timeline

        # Group creations by date
        creations_by_date: dict[str, list[dict]] = defaultdict(list)
        for ep in self.episodic.episodes:
            if ep["event_type"] == "creation":
                # Extract date from timestamp
                ts = ep.get("timestamp", "")
                date = ts[:10] if len(ts) >= 10 else "unknown"
                creations_by_date[date].append(ep)

        # Build timeline with aggregated data
        sorted_dates = sorted(creations_by_date.keys())
        running_styles: dict[str, int] = defaultdict(int)

        for date in sorted_dates:
            day_creations = creations_by_date[date]
            day_scores = []
            day_moods: dict[str, int] = defaultdict(int)
            day_styles: dict[str, int] = defaultdict(int)

            for creation in day_creations:
                # Extract score
                score = creation.get("details", {}).get("score", 0)
                if score == 0:
                    # Try alternate location
                    score = creation.get("outcome", {}).get("score", 0)
                day_scores.append(score)

                # Extract mood
                mood = creation.get("emotional_state", {}).get("mood", "unknown")
                day_moods[mood] += 1

                # Extract style
                style = creation.get("details", {}).get("style", "unknown")
                day_styles[style] += 1
                running_styles[style] += 1

            # Add to timeline
            avg_score = sum(day_scores) / len(day_scores) if day_scores else 0
            timeline["score_trend"].append(
                {
                    "date": date,
                    "avg_score": round(avg_score, 3),
                    "count": len(day_creations),
                }
            )

            # Update mood distribution
            for mood, count in day_moods.items():
                timeline["mood_distribution"][mood] = (
                    timeline["mood_distribution"].get(mood, 0) + count
                )

            # Track style evolution
            if day_styles:
                dominant_style = max(day_styles, key=day_styles.get)  # type: ignore[arg-type]
                timeline["style_evolution"].append(
                    {
                        "date": date,
                        "dominant_style": dominant_style,
                        "styles_used": dict(day_styles),
                    }
                )

        # Identify milestones (high scores, first of each style, etc.)
        all_creations = [
            ep for ep in self.episodic.episodes if ep["event_type"] == "creation"
        ]
        if all_creations:
            # Best creation
            best = max(
                all_creations,
                key=lambda x: x.get("details", {}).get("score", 0),
            )
            best_score = best.get("details", {}).get("score", 0)
            if best_score > 0:
                timeline["milestones"].append(
                    {
                        "type": "best_creation",
                        "date": best.get("timestamp", "")[:10],
                        "description": f"Highest quality creation (score: {best_score:.2f})",
                        "details": {
                            "style": best.get("details", {}).get("style"),
                            "mood": best.get("emotional_state", {}).get("mood"),
                        },
                    }
                )

            # First creation
            first = all_creations[0]
            timeline["milestones"].append(
                {
                    "type": "first_creation",
                    "date": first.get("timestamp", "")[:10],
                    "description": "First artwork created",
                    "details": {
                        "style": first.get("details", {}).get("style"),
                        "mood": first.get("emotional_state", {}).get("mood"),
                    },
                }
            )

            # Style discoveries (first use of each style)
            seen_styles: set[str] = set()
            for creation in all_creations:
                style = creation.get("details", {}).get("style", "unknown")
                if style != "unknown" and style not in seen_styles:
                    seen_styles.add(style)
                    if len(seen_styles) > 1:  # Skip the very first
                        timeline["milestones"].append(
                            {
                                "type": "style_discovery",
                                "date": creation.get("timestamp", "")[:10],
                                "description": f"First experimented with {style} style",
                                "details": {"style": style},
                            }
                        )

        # Identify artistic phases (clusters of similar moods/styles)
        if len(sorted_dates) >= 3:
            # Simple phase detection: group consecutive days with same dominant mood
            current_phase_mood = None
            phase_start = None
            phases: list[dict] = []

            for entry in timeline["score_trend"]:
                date = entry["date"]
                day_creations = creations_by_date.get(date, [])
                if day_creations:
                    moods = [
                        c.get("emotional_state", {}).get("mood") for c in day_creations
                    ]
                    dominant_mood = max(set(moods), key=moods.count) if moods else None

                    if dominant_mood != current_phase_mood:
                        if current_phase_mood and phase_start:
                            phases.append(
                                {
                                    "mood": current_phase_mood,
                                    "start_date": phase_start,
                                    "end_date": date,
                                    "name": f"{current_phase_mood.title()} Period",
                                }
                            )
                        current_phase_mood = dominant_mood
                        phase_start = date

            # Close final phase
            if current_phase_mood and phase_start:
                phases.append(
                    {
                        "mood": current_phase_mood,
                        "start_date": phase_start,
                        "end_date": sorted_dates[-1] if sorted_dates else phase_start,
                        "name": f"{current_phase_mood.title()} Period",
                    }
                )

            timeline["phases"] = phases

        return timeline

    def get_style_preferences_over_time(self) -> list[dict[str, Any]]:
        """Track how style preferences evolved over time."""
        style_by_month: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        for ep in self.episodic.episodes:
            if ep["event_type"] == "creation":
                ts = ep.get("timestamp", "")
                month = ts[:7] if len(ts) >= 7 else "unknown"  # YYYY-MM
                style = ep.get("details", {}).get("style", "unknown")
                score = ep.get("details", {}).get("score", 0.5)

                # Weight by score - better creations influence preferences more
                style_by_month[month][style] += score

        # Convert to sorted list
        result = []
        for month in sorted(style_by_month.keys()):
            styles = style_by_month[month]
            if styles:
                total = sum(styles.values())
                preferences = {s: round(v / total, 2) for s, v in styles.items()}
                result.append(
                    {
                        "month": month,
                        "preferences": preferences,
                        "dominant": max(preferences, key=preferences.get),  # type: ignore[arg-type]
                    }
                )

        return result
