"""
Narrative Engine for Lumira.

Enables connected artwork series for artistic coherence with variety.
A ThematicSeries is a group of related artworks that explore a common theme,
visual thread, or emotional arc.

When Lumira creates a particularly compelling piece, she may feel inspired
to explore that theme further through a series of connected works.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from .desire_engine import CreativeDesire

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ThematicSeries(BaseModel):
    """A connected series of artworks exploring a common theme."""

    series_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str  # "Solitude in Urban Spaces"
    theme: str  # The underlying theme/concept
    planned_count: int = Field(default=5, ge=2, le=10)  # How many works planned
    completed_works: list[str] = Field(default_factory=list)  # Artwork IDs
    visual_threads: list[str] = Field(
        default_factory=list,
        description="Recurring visual elements (colors, motifs, compositions)",
    )
    variations: list[str] = Field(
        default_factory=list,
        description="What to explore differently each time",
    )
    mood_arc: list[str] = Field(
        default_factory=list,
        description="How mood should evolve across the series",
    )
    status: Literal["active", "completed", "abandoned"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seed_artwork: dict[str, Any] = Field(
        default_factory=dict,
        description="The artwork that inspired this series",
    )


# ---------------------------------------------------------------------------
# Series Title Generation
# ---------------------------------------------------------------------------


def generate_series_title(
    subject: str,
    style: str,
    mood: str,
) -> str:
    """Generate an evocative title for a thematic series."""
    # Title patterns
    patterns = [
        f"{subject.title()} Studies",
        f"Variations on {subject.title()}",
        f"The {mood.title()} {subject.title()}",
        f"{subject.title()} in {style.title()}",
        f"Exploring {subject.title()}",
        f"{mood.title()} {subject.title()} Series",
        f"Meditations on {subject.title()}",
        f"{subject.title()} Variations",
    ]

    return random.choice(patterns)


def generate_visual_threads(
    seed_creation: dict[str, Any],
) -> list[str]:
    """Generate visual threads to maintain across the series."""
    threads = []

    # Extract from seed creation
    details = seed_creation.get("details", {})
    style = details.get("style", "")
    subject = details.get("subject", "")

    # Color thread
    color_threads = [
        "consistent color palette",
        "recurring warm tones",
        "deep blues and shadows",
        "high contrast lighting",
        "desaturated, muted colors",
        "vibrant accent colors",
    ]
    threads.append(random.choice(color_threads))

    # Composition thread
    composition_threads = [
        "centered composition",
        "asymmetric balance",
        "rule of thirds",
        "leading lines",
        "negative space",
        "layered depth",
    ]
    threads.append(random.choice(composition_threads))

    # Style-based thread
    if style:
        threads.append(f"{style} technique throughout")

    # Motif based on subject
    if subject:
        motifs = [
            f"recurring {subject} motif",
            f"variations of {subject}",
            f"abstract references to {subject}",
        ]
        threads.append(random.choice(motifs))

    return threads[:4]


def generate_variations(subject: str, mood: str) -> list[str]:
    """Generate what to explore differently in each piece."""
    variations = [
        "different time of day",
        "varying perspectives",
        "shifting scale",
        "alternate moods within the theme",
        "different lighting conditions",
        "abstract vs realistic treatment",
        "close-up vs wide angle",
        "different color temperatures",
        "evolving emotional intensity",
    ]

    # Select 3-4 variations
    selected = random.sample(variations, min(4, len(variations)))
    return selected


def generate_mood_arc(starting_mood: str, length: int) -> list[str]:
    """Generate a mood arc for the series."""
    from ..personality.moods import Mood

    all_moods = [m.value for m in Mood]

    # Start with the seed mood
    arc = [starting_mood]

    # Build a narrative arc
    while len(arc) < length:
        current = arc[-1]

        # Mood transitions that make narrative sense
        transitions = {
            "serene": ["contemplative", "melancholic", "serene"],
            "melancholic": ["introspective", "contemplative", "serene"],
            "energized": ["playful", "bold", "chaotic"],
            "chaotic": ["restless", "rebellious", "energized"],
            "contemplative": ["serene", "introspective", "melancholic"],
            "playful": ["energized", "bold", "serene"],
            "bold": ["energized", "rebellious", "contemplative"],
            "rebellious": ["chaotic", "bold", "restless"],
            "restless": ["chaotic", "contemplative", "rebellious"],
            "introspective": ["contemplative", "melancholic", "serene"],
        }

        next_options = transitions.get(current, all_moods)
        arc.append(random.choice(next_options))

    return arc


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------


class NarrativeEngine:
    """Manages Lumira's thematic series and narrative connections."""

    def __init__(
        self,
        storage_path: Path = Path("data/thematic_series.json"),
        mood_system: Any | None = None,
    ):
        self.storage_path = storage_path
        self.mood_system = mood_system
        self.active_series: list[ThematicSeries] = []
        self.completed_series: list[ThematicSeries] = []

        # Thresholds for starting a series
        self.quality_threshold = 0.7  # Minimum score to trigger series consideration
        self.intensity_threshold = 0.6  # Minimum mood intensity

        self._load_state()
        logger.info(
            "narrative_engine_initialized",
            active_series=len(self.active_series),
            completed_series=len(self.completed_series),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_start_series(
        self,
        recent_creation: dict[str, Any],
    ) -> bool:
        """Determine if a recent creation should spawn a new series.

        A series starts when:
        1. The creation scored well (> quality_threshold)
        2. Current mood intensity is high (> intensity_threshold)
        3. We don't already have too many active series
        """
        # Check if we already have enough active series
        if len(self.active_series) >= 3:
            logger.debug("too_many_active_series", count=len(self.active_series))
            return False

        # Check quality score
        details = recent_creation.get("details", {})
        score = details.get("score", 0)
        if score < self.quality_threshold:
            logger.debug("score_too_low_for_series", score=score)
            return False

        # Check mood intensity
        if self.mood_system:
            intensity = getattr(self.mood_system, "mood_intensity", 0.5)
            if intensity < self.intensity_threshold:
                logger.debug("intensity_too_low_for_series", intensity=intensity)
                return False

        # Check if subject already has an active series
        subject = details.get("subject", "").lower()
        for series in self.active_series:
            if series.theme.lower() in subject or subject in series.theme.lower():
                logger.debug(
                    "similar_series_already_active",
                    subject=subject,
                    existing_theme=series.theme,
                )
                return False

        # Random chance to prevent every high-quality piece from starting a series
        if random.random() > 0.4:  # 40% chance to start
            logger.debug("random_skip_series_start")
            return False

        logger.info(
            "series_start_recommended",
            subject=subject,
            score=score,
        )
        return True

    def create_series(
        self,
        seed_creation: dict[str, Any],
    ) -> ThematicSeries:
        """Create a new thematic series inspired by a seed creation."""
        details = seed_creation.get("details", {})
        emotional_state = seed_creation.get("emotional_state", {})

        subject = details.get("subject", "abstract composition")
        style = details.get("style", "digital art")
        mood = emotional_state.get("mood", "contemplative")

        # Generate series elements
        title = generate_series_title(subject, style, mood)
        visual_threads = generate_visual_threads(seed_creation)
        variations = generate_variations(subject, mood)
        mood_arc = generate_mood_arc(mood, 5)

        series = ThematicSeries(
            title=title,
            theme=subject,
            planned_count=random.randint(3, 5),
            completed_works=[seed_creation.get("id", str(uuid.uuid4())[:8])],
            visual_threads=visual_threads,
            variations=variations,
            mood_arc=mood_arc,
            seed_artwork=seed_creation,
        )

        self.active_series.append(series)
        self._save_state()

        logger.info(
            "series_created",
            series_id=series.series_id,
            title=series.title,
            theme=series.theme,
            planned_count=series.planned_count,
        )

        return series

    def get_series_continuation_desire(self) -> CreativeDesire | None:
        """Get a creative desire for continuing an active series.

        Returns None if no series needs continuation.
        """
        from .desire_engine import CreativeDesire

        if not self.active_series:
            return None

        # Find series that could use continuation
        for series in self.active_series:
            remaining = series.planned_count - len(series.completed_works)
            if remaining <= 0:
                continue

            # Calculate urgency based on how much is left vs started
            progress = len(series.completed_works) / series.planned_count
            urgency = 0.7 if progress < 0.5 else 0.5  # Higher urgency early in series

            # Get a variation to explore
            variation_idx = (
                len(series.completed_works) % len(series.variations)
                if series.variations
                else 0
            )
            variation = series.variations[variation_idx] if series.variations else None

            # Build the continuation prompt
            subject_suggestion = series.theme
            if variation:
                subject_suggestion = f"{series.theme}, {variation}"

            visual_thread = series.visual_threads[0] if series.visual_threads else None

            reasoning = (
                f"I'm working on '{series.title}' — "
                f"{len(series.completed_works)}/{series.planned_count} complete. "
            )
            if visual_thread:
                reasoning += f"Maintaining {visual_thread}. "
            if variation:
                reasoning += f"This piece explores {variation}."

            desire = CreativeDesire(
                drive_name="series_continuation",
                subject_suggestion=subject_suggestion,
                style_suggestion=None,  # Maintain consistency
                theme=series.title,
                reasoning=reasoning,
                urgency=urgency,
                keywords=[
                    series.theme,
                    "series",
                    "continuation",
                    *series.visual_threads[:2],
                ],
            )

            logger.info(
                "series_continuation_desire",
                series_id=series.series_id,
                title=series.title,
                progress=f"{len(series.completed_works)}/{series.planned_count}",
            )

            return desire

        return None

    def complete_series_work(
        self,
        series_id: str,
        artwork_id: str,
    ) -> bool:
        """Record completion of a work within a series."""
        for series in self.active_series:
            if series.series_id == series_id:
                if artwork_id not in series.completed_works:
                    series.completed_works.append(artwork_id)
                    series.last_updated = datetime.now(UTC)

                # Check if series is complete
                if len(series.completed_works) >= series.planned_count:
                    series.status = "completed"
                    self.active_series.remove(series)
                    self.completed_series.append(series)

                    logger.info(
                        "series_completed",
                        series_id=series.series_id,
                        title=series.title,
                        works=len(series.completed_works),
                    )

                self._save_state()
                return True

        logger.warning(
            "series_not_found_for_completion",
            series_id=series_id,
            artwork_id=artwork_id,
        )
        return False

    def get_active_series(self) -> list[ThematicSeries]:
        """Get all active series."""
        return self.active_series

    def get_series_by_id(self, series_id: str) -> ThematicSeries | None:
        """Get a specific series by ID."""
        for series in self.active_series + self.completed_series:
            if series.series_id == series_id:
                return series
        return None

    def abandon_series(self, series_id: str) -> bool:
        """Mark a series as abandoned."""
        for series in self.active_series:
            if series.series_id == series_id:
                series.status = "abandoned"
                series.last_updated = datetime.now(UTC)
                self.active_series.remove(series)
                self.completed_series.append(series)
                self._save_state()

                logger.info(
                    "series_abandoned",
                    series_id=series_id,
                    title=series.title,
                )
                return True
        return False

    def get_series_status(self) -> dict[str, Any]:
        """Get status of all series."""
        return {
            "active": [
                {
                    "series_id": s.series_id,
                    "title": s.title,
                    "theme": s.theme,
                    "progress": f"{len(s.completed_works)}/{s.planned_count}",
                    "visual_threads": s.visual_threads,
                }
                for s in self.active_series
            ],
            "completed_count": len(
                [s for s in self.completed_series if s.status == "completed"]
            ),
            "abandoned_count": len(
                [s for s in self.completed_series if s.status == "abandoned"]
            ),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Save series state to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "active_series": [s.model_dump() for s in self.active_series],
            "completed_series": [s.model_dump() for s in self.completed_series],
            "last_updated": datetime.now(UTC).isoformat(),
        }

        try:
            with open(self.storage_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error("failed_to_save_series_state", error=str(e))

    def _load_state(self) -> None:
        """Load series state from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path) as f:
                state = json.load(f)

            for series_data in state.get("active_series", []):
                self.active_series.append(ThematicSeries(**series_data))

            for series_data in state.get("completed_series", []):
                self.completed_series.append(ThematicSeries(**series_data))

            logger.info(
                "series_state_loaded",
                active=len(self.active_series),
                completed=len(self.completed_series),
            )

        except Exception as e:
            logger.error("failed_to_load_series_state", error=str(e))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_narrative_engine: NarrativeEngine | None = None


def get_narrative_engine(
    mood_system: Any | None = None,
) -> NarrativeEngine:
    """Get or create the global NarrativeEngine instance."""
    global _narrative_engine
    if _narrative_engine is None:
        _narrative_engine = NarrativeEngine(mood_system=mood_system)
    elif mood_system is not None and _narrative_engine.mood_system is None:
        _narrative_engine.mood_system = mood_system
    return _narrative_engine
