"""Lumira's mood system - influences her artistic choices.

Enhanced with:
- Mood decay over time (emotions naturally fade)
- Mood intensity tracking (how strongly she feels)
- Style axes for granular creative control
- Richer emotional vocabulary
- FLUX model routing based on mood
"""

import json
import random
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Model type for mood-based selection
ModelType = Literal["sdxl", "flux-schnell", "flux-dev"]


class Mood(str, Enum):
    """Lumira's possible moods."""

    CONTEMPLATIVE = "contemplative"
    CHAOTIC = "chaotic"
    MELANCHOLIC = "melancholic"
    ENERGIZED = "energized"
    REBELLIOUS = "rebellious"
    SERENE = "serene"
    RESTLESS = "restless"
    PLAYFUL = "playful"
    INTROSPECTIVE = "introspective"
    BOLD = "bold"


# Neutral moods that intense emotions decay toward
NEUTRAL_MOODS = [Mood.CONTEMPLATIVE, Mood.SERENE, Mood.INTROSPECTIVE]

# How "intense" each mood is (affects decay rate)
MOOD_INTENSITY_BASELINE = {
    Mood.CONTEMPLATIVE: 0.3,
    Mood.CHAOTIC: 0.9,
    Mood.MELANCHOLIC: 0.6,
    Mood.ENERGIZED: 0.8,
    Mood.REBELLIOUS: 0.85,
    Mood.SERENE: 0.2,
    Mood.RESTLESS: 0.7,
    Mood.PLAYFUL: 0.6,
    Mood.INTROSPECTIVE: 0.4,
    Mood.BOLD: 0.75,
}


class StyleAxes:
    """10 granular style axes for fine-grained creative control.

    Based on the lofn project's approach to parameterized creativity.
    Each axis is 0.0 to 1.0.
    """

    def __init__(
        self,
        abstraction: float = 0.5,
        saturation: float = 0.5,
        complexity: float = 0.5,
        drama: float = 0.5,
        symmetry: float = 0.5,
        novelty: float = 0.5,
        line_quality: float = 0.5,  # 0=soft/painterly, 1=sharp/defined
        palette_temperature: float = 0.5,  # 0=cool, 1=warm
        motion: float = 0.5,  # 0=static, 1=dynamic
        symbolism: float = 0.5,  # 0=literal, 1=symbolic
    ):
        self.abstraction = abstraction
        self.saturation = saturation
        self.complexity = complexity
        self.drama = drama
        self.symmetry = symmetry
        self.novelty = novelty
        self.line_quality = line_quality
        self.palette_temperature = palette_temperature
        self.motion = motion
        self.symbolism = symbolism

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "abstraction": round(self.abstraction, 2),
            "saturation": round(self.saturation, 2),
            "complexity": round(self.complexity, 2),
            "drama": round(self.drama, 2),
            "symmetry": round(self.symmetry, 2),
            "novelty": round(self.novelty, 2),
            "line_quality": round(self.line_quality, 2),
            "palette_temperature": round(self.palette_temperature, 2),
            "motion": round(self.motion, 2),
            "symbolism": round(self.symbolism, 2),
        }

    # Valid axis names for from_dict validation
    AXIS_NAMES = {
        "abstraction",
        "saturation",
        "complexity",
        "drama",
        "symmetry",
        "novelty",
        "line_quality",
        "palette_temperature",
        "motion",
        "symbolism",
    }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "StyleAxes":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.AXIS_NAMES})

    @classmethod
    def from_mood(cls, mood: "Mood", intensity: float = 0.7) -> "StyleAxes":
        """Generate style axes appropriate for a mood."""
        # Base profiles for each mood
        mood_profiles = {
            Mood.CONTEMPLATIVE: {
                "abstraction": 0.6,
                "saturation": 0.3,
                "complexity": 0.4,
                "drama": 0.2,
                "symmetry": 0.6,
                "novelty": 0.4,
                "line_quality": 0.3,
                "palette_temperature": 0.4,
                "motion": 0.2,
                "symbolism": 0.7,
            },
            Mood.CHAOTIC: {
                "abstraction": 0.8,
                "saturation": 0.9,
                "complexity": 0.9,
                "drama": 0.95,
                "symmetry": 0.1,
                "novelty": 0.9,
                "line_quality": 0.7,
                "palette_temperature": 0.7,
                "motion": 0.95,
                "symbolism": 0.5,
            },
            Mood.MELANCHOLIC: {
                "abstraction": 0.4,
                "saturation": 0.25,
                "complexity": 0.5,
                "drama": 0.6,
                "symmetry": 0.5,
                "novelty": 0.3,
                "line_quality": 0.4,
                "palette_temperature": 0.3,
                "motion": 0.2,
                "symbolism": 0.8,
            },
            Mood.ENERGIZED: {
                "abstraction": 0.3,
                "saturation": 0.85,
                "complexity": 0.6,
                "drama": 0.7,
                "symmetry": 0.4,
                "novelty": 0.7,
                "line_quality": 0.6,
                "palette_temperature": 0.8,
                "motion": 0.8,
                "symbolism": 0.3,
            },
            Mood.REBELLIOUS: {
                "abstraction": 0.5,
                "saturation": 0.8,
                "complexity": 0.7,
                "drama": 0.9,
                "symmetry": 0.2,
                "novelty": 0.85,
                "line_quality": 0.8,
                "palette_temperature": 0.6,
                "motion": 0.7,
                "symbolism": 0.6,
            },
            Mood.SERENE: {
                "abstraction": 0.4,
                "saturation": 0.4,
                "complexity": 0.2,
                "drama": 0.1,
                "symmetry": 0.7,
                "novelty": 0.3,
                "line_quality": 0.2,
                "palette_temperature": 0.45,
                "motion": 0.1,
                "symbolism": 0.4,
            },
            Mood.RESTLESS: {
                "abstraction": 0.6,
                "saturation": 0.6,
                "complexity": 0.8,
                "drama": 0.65,
                "symmetry": 0.3,
                "novelty": 0.75,
                "line_quality": 0.5,
                "palette_temperature": 0.6,
                "motion": 0.7,
                "symbolism": 0.5,
            },
            Mood.PLAYFUL: {
                "abstraction": 0.35,
                "saturation": 0.8,
                "complexity": 0.5,
                "drama": 0.4,
                "symmetry": 0.4,
                "novelty": 0.7,
                "line_quality": 0.5,
                "palette_temperature": 0.7,
                "motion": 0.6,
                "symbolism": 0.3,
            },
            Mood.INTROSPECTIVE: {
                "abstraction": 0.5,
                "saturation": 0.35,
                "complexity": 0.6,
                "drama": 0.4,
                "symmetry": 0.5,
                "novelty": 0.5,
                "line_quality": 0.4,
                "palette_temperature": 0.4,
                "motion": 0.25,
                "symbolism": 0.85,
            },
            Mood.BOLD: {
                "abstraction": 0.3,
                "saturation": 0.75,
                "complexity": 0.5,
                "drama": 0.85,
                "symmetry": 0.5,
                "novelty": 0.6,
                "line_quality": 0.8,
                "palette_temperature": 0.6,
                "motion": 0.5,
                "symbolism": 0.4,
            },
        }

        profile = mood_profiles.get(mood, mood_profiles[Mood.CONTEMPLATIVE])

        # Apply intensity - higher intensity means more extreme values
        adjusted = {}
        for key, value in profile.items():
            # Move toward extremes based on intensity
            if value > 0.5:
                adjusted[key] = 0.5 + (value - 0.5) * intensity
            else:
                adjusted[key] = 0.5 - (0.5 - value) * intensity
            # Add slight randomness
            adjusted[key] += random.uniform(-0.05, 0.05)
            adjusted[key] = max(0.0, min(1.0, adjusted[key]))

        return cls(**adjusted)

    def to_prompt_modifiers(self) -> list[str]:
        """Convert style axes to prompt modifiers."""
        modifiers = []

        # Abstraction
        if self.abstraction > 0.7:
            modifiers.append("highly abstract")
        elif self.abstraction < 0.3:
            modifiers.append("realistic, representational")

        # Saturation
        if self.saturation > 0.75:
            modifiers.append("vibrant saturated colors")
        elif self.saturation < 0.3:
            modifiers.append("muted desaturated tones")

        # Complexity
        if self.complexity > 0.7:
            modifiers.append("intricate detailed")
        elif self.complexity < 0.3:
            modifiers.append("minimalist simple")

        # Drama
        if self.drama > 0.75:
            modifiers.append("dramatic high contrast")
        elif self.drama < 0.25:
            modifiers.append("subtle soft lighting")

        # Symmetry
        if self.symmetry > 0.7:
            modifiers.append("balanced symmetrical composition")
        elif self.symmetry < 0.3:
            modifiers.append("asymmetrical dynamic composition")

        # Line quality
        if self.line_quality > 0.7:
            modifiers.append("sharp defined edges")
        elif self.line_quality < 0.3:
            modifiers.append("soft painterly brushstrokes")

        # Temperature
        if self.palette_temperature > 0.7:
            modifiers.append("warm color palette")
        elif self.palette_temperature < 0.3:
            modifiers.append("cool color palette")

        # Motion
        if self.motion > 0.7:
            modifiers.append("dynamic sense of movement")
        elif self.motion < 0.3:
            modifiers.append("still serene atmosphere")

        # Symbolism
        if self.symbolism > 0.7:
            modifiers.append("symbolic metaphorical imagery")
        elif self.symbolism < 0.3:
            modifiers.append("literal direct representation")

        return modifiers


class MoodSystem:
    """Manages Lumira's emotional state and how it affects her art.

    Enhanced with:
    - Mood decay over time (emotions naturally fade between sessions)
    - Mood intensity tracking (how strongly she feels the current mood)
    - Style axes for granular creative control
    - Richer emotional state serialization
    """

    # Decay rate per hour (intense moods fade faster)
    DECAY_RATE_PER_HOUR = 0.1

    # Minimum intensity before mood shifts to neutral
    MIN_INTENSITY_THRESHOLD = 0.3

    def __init__(self) -> None:
        self.current_mood = self._get_time_based_mood()
        self.energy_level = 0.5  # 0.0 to 1.0
        self.mood_duration = 0

        # New: mood intensity (how strongly she feels it)
        self.mood_intensity = 0.7

        # New: timestamp tracking for decay
        self.last_update = datetime.now()

        # Mood history — persisted to disk so it survives restarts
        self.mood_history: list[dict] = self._load_mood_history()

        # New: style axes for granular control
        self.style_axes: StyleAxes = StyleAxes.from_mood(
            self.current_mood, self.mood_intensity
        )
        self.mood_influences = {
            Mood.CONTEMPLATIVE: {
                "styles": ["minimalist", "zen", "abstract", "atmospheric"],
                "colors": ["muted blues", "soft grays", "gentle earth tones"],
                "subjects": ["nature", "meditation", "silence", "space"],
            },
            Mood.CHAOTIC: {
                "styles": ["abstract expressionism", "glitch art", "splatter paint"],
                "colors": ["clashing neons", "explosive reds", "electric yellows"],
                "subjects": ["chaos", "energy", "movement", "destruction"],
            },
            Mood.MELANCHOLIC: {
                "styles": ["impressionist", "muted realism", "somber abstract"],
                "colors": ["deep blues", "dark purples", "shadowy grays"],
                "subjects": ["solitude", "rain", "autumn", "twilight"],
            },
            Mood.ENERGIZED: {
                "styles": ["vibrant pop art", "dynamic composition", "bold colors"],
                "colors": ["bright oranges", "sunny yellows", "vivid greens"],
                "subjects": ["celebration", "life", "movement", "joy"],
            },
            Mood.REBELLIOUS: {
                "styles": ["punk aesthetic", "street art", "provocative"],
                "colors": ["defiant blacks", "anarchic neons", "aggressive reds"],
                "subjects": ["resistance", "protest", "freedom", "challenge"],
            },
            Mood.SERENE: {
                "styles": ["peaceful landscapes", "soft focus", "harmonious"],
                "colors": ["gentle pastels", "calm blues", "peaceful whites"],
                "subjects": ["tranquility", "ocean", "clouds", "harmony"],
            },
            Mood.RESTLESS: {
                "styles": ["fragmented", "layered", "complex"],
                "colors": ["agitated reds", "anxious oranges", "nervous yellows"],
                "subjects": ["searching", "journey", "change", "tension"],
            },
            Mood.PLAYFUL: {
                "styles": ["whimsical", "cartoonish", "fun", "colorful"],
                "colors": ["rainbow hues", "candy colors", "cheerful brights"],
                "subjects": ["childhood", "games", "imagination", "delight"],
            },
            Mood.INTROSPECTIVE: {
                "styles": ["detailed realism", "symbolic", "layered meaning"],
                "colors": ["thoughtful browns", "deep greens", "reflective silvers"],
                "subjects": ["self", "mind", "memory", "dreams"],
            },
            Mood.BOLD: {
                "styles": ["dramatic", "high contrast", "striking"],
                "colors": ["powerful blacks", "intense reds", "commanding golds"],
                "subjects": ["strength", "confidence", "power", "declaration"],
            },
        }

        logger.info(
            "mood_system_initialized",
            initial_mood=self.current_mood,
            intensity=round(self.mood_intensity, 2),
        )

    def _get_time_based_mood(self) -> Mood:
        """Determine initial mood based on time of day.

        Returns:
            Mood appropriate for current time
        """
        import random

        current_hour = datetime.now().hour

        # Morning (6am-12pm): Fresh, energized, creative
        if 6 <= current_hour < 12:
            return random.choice([Mood.ENERGIZED, Mood.PLAYFUL, Mood.BOLD])

        # Afternoon (12pm-6pm): Active, experimental, dynamic
        elif 12 <= current_hour < 18:
            return random.choice([Mood.REBELLIOUS, Mood.CHAOTIC, Mood.PLAYFUL])

        # Evening (6pm-12am): Reflective, calm, thoughtful
        elif 18 <= current_hour < 24:
            return random.choice([Mood.CONTEMPLATIVE, Mood.MELANCHOLIC, Mood.SERENE])

        # Night (12am-6am): Deep, calm, introspective
        else:
            return random.choice([Mood.SERENE, Mood.INTROSPECTIVE, Mood.CONTEMPLATIVE])

    # ── Mood history persistence ──────────────────────────────────────────────

    _HISTORY_FILE = Path("data/lumira_mood_history.json")
    _MAX_HISTORY = 500  # Cap to prevent unbounded growth

    def _load_mood_history(self) -> list[dict]:
        """Load persisted mood history from disk."""
        if not self._HISTORY_FILE.exists():
            return []
        try:
            raw = json.loads(self._HISTORY_FILE.read_text())
            history: list[dict] = raw.get("history", [])  # type: ignore[type-arg]
            return history
        except Exception:
            return []

    def _save_mood_history(self) -> None:
        """Persist mood history to disk atomically."""
        try:
            self._HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._HISTORY_FILE.with_suffix(".tmp")
            # Keep only the most recent entries
            trimmed = self.mood_history[-self._MAX_HISTORY :]
            tmp.write_text(json.dumps({"history": trimmed}, indent=2))
            tmp.replace(self._HISTORY_FILE)
        except Exception:
            pass  # Non-critical; swallow silently

    def _record_mood_entry(self, trigger: str = "natural_drift") -> None:
        """Append current mood/intensity to history and persist."""
        mood_val = (
            self.current_mood.value
            if hasattr(self.current_mood, "value")
            else str(self.current_mood)
        )
        self.mood_history.append(
            {
                "mood": mood_val,
                "intensity": round(self.mood_intensity, 3),
                "timestamp": datetime.now().isoformat(),
                "trigger": trigger,
            }
        )
        self._save_mood_history()

    # ── Decay / update ────────────────────────────────────────────────────────

    def apply_decay(self) -> None:
        """Apply natural mood decay based on time elapsed.

        Intense emotions fade toward neutral states over time.
        This should be called on session resume.
        """
        now = datetime.now()
        hours_elapsed = (now - self.last_update).total_seconds() / 3600

        if hours_elapsed < 0.1:  # Less than 6 minutes, no decay
            return

        # Calculate decay based on mood intensity baseline
        base_intensity = MOOD_INTENSITY_BASELINE.get(self.current_mood, 0.5)
        decay_amount = hours_elapsed * self.DECAY_RATE_PER_HOUR * base_intensity

        old_intensity = self.mood_intensity
        self.mood_intensity = max(0.0, self.mood_intensity - decay_amount)

        # Energy also decays slightly
        self.energy_level = max(0.2, self.energy_level - (hours_elapsed * 0.02))

        logger.info(
            "mood_decay_applied",
            hours_elapsed=round(hours_elapsed, 1),
            old_intensity=round(old_intensity, 2),
            new_intensity=round(self.mood_intensity, 2),
            mood=self.current_mood,
        )

        # If intensity drops too low, shift to a neutral mood
        if self.mood_intensity < self.MIN_INTENSITY_THRESHOLD:
            self._decay_to_neutral()

        self.last_update = now

    def _decay_to_neutral(self) -> None:
        """Shift to a neutral mood when intensity fades."""
        if self.current_mood not in NEUTRAL_MOODS:
            old_mood = self.current_mood
            self.current_mood = random.choice(NEUTRAL_MOODS)
            self.mood_intensity = 0.5  # Reset to moderate intensity
            self.mood_duration = 0
            self.style_axes = StyleAxes.from_mood(
                self.current_mood, self.mood_intensity
            )

            logger.info(
                "mood_decayed_to_neutral",
                old_mood=old_mood,
                new_mood=self.current_mood,
            )

    def update_mood(self, external_factors: dict | None = None) -> Mood:
        """Update Lumira's mood based on time, energy, and external factors."""
        self.mood_duration += 1

        # Apply any time-based decay first
        self.apply_decay()

        # Mood naturally shifts over time
        if self.mood_duration > random.randint(5, 10):
            self._shift_mood()

        # Energy affects mood intensity
        self.energy_level += random.uniform(-0.1, 0.1)
        self.energy_level = max(0.0, min(1.0, self.energy_level))

        # External factors can influence mood
        if external_factors:
            self._apply_external_factors(external_factors)

        # Update style axes based on current state
        self.style_axes = StyleAxes.from_mood(self.current_mood, self.mood_intensity)
        self.last_update = datetime.now()

        # Record to persistent history
        self._record_mood_entry(
            trigger="external_factors" if external_factors else "natural_drift"
        )

        logger.info(
            "mood_updated",
            mood=self.current_mood,
            intensity=round(self.mood_intensity, 2),
            energy=round(self.energy_level, 2),
            duration=self.mood_duration,
        )

        return Mood(self.current_mood)

    def _apply_external_factors(self, factors: dict[str, Any]) -> None:
        """Apply external factors to mood state."""
        # Positive feedback increases intensity and energy
        if factors.get("positive_feedback"):
            self.mood_intensity = min(1.0, self.mood_intensity + 0.1)
            self.energy_level = min(1.0, self.energy_level + 0.1)

        # High quality work can shift mood toward bold/energized
        score = factors.get("creation_score", 0)
        if score > 0.8:
            self.mood_intensity = min(1.0, self.mood_intensity + 0.15)
            if random.random() > 0.7:
                self.current_mood = random.choice(
                    [Mood.BOLD, Mood.ENERGIZED, Mood.PLAYFUL]
                )

        # Low quality work can shift toward introspective/contemplative
        elif score > 0 and score < 0.4:
            if random.random() > 0.6:
                self.current_mood = random.choice(
                    [Mood.INTROSPECTIVE, Mood.CONTEMPLATIVE]
                )

    def _shift_mood(self) -> None:
        """Shift to a new mood organically."""
        # Similar moods are more likely to transition
        mood_transitions = {
            Mood.CONTEMPLATIVE: [Mood.SERENE, Mood.INTROSPECTIVE, Mood.MELANCHOLIC],
            Mood.CHAOTIC: [Mood.REBELLIOUS, Mood.ENERGIZED, Mood.RESTLESS],
            Mood.MELANCHOLIC: [Mood.CONTEMPLATIVE, Mood.INTROSPECTIVE, Mood.SERENE],
            Mood.ENERGIZED: [Mood.PLAYFUL, Mood.BOLD, Mood.CHAOTIC],
            Mood.REBELLIOUS: [Mood.CHAOTIC, Mood.BOLD, Mood.RESTLESS],
            Mood.SERENE: [Mood.CONTEMPLATIVE, Mood.PLAYFUL, Mood.INTROSPECTIVE],
            Mood.RESTLESS: [Mood.CHAOTIC, Mood.REBELLIOUS, Mood.INTROSPECTIVE],
            Mood.PLAYFUL: [Mood.ENERGIZED, Mood.SERENE, Mood.BOLD],
            Mood.INTROSPECTIVE: [Mood.CONTEMPLATIVE, Mood.MELANCHOLIC, Mood.SERENE],
            Mood.BOLD: [Mood.REBELLIOUS, Mood.ENERGIZED, Mood.PLAYFUL],
        }

        possible_moods = mood_transitions.get(self.current_mood, list(Mood))
        self.current_mood = random.choice(possible_moods)
        self.mood_duration = 0

        # New mood starts with fresh intensity based on energy
        self.mood_intensity = (
            0.5 + (self.energy_level * 0.3) + random.uniform(-0.1, 0.1)
        )
        self.mood_intensity = max(0.3, min(1.0, self.mood_intensity))

        # Update style axes for new mood
        self.style_axes = StyleAxes.from_mood(self.current_mood, self.mood_intensity)

        logger.info(
            "mood_shifted",
            new_mood=self.current_mood,
            intensity=round(self.mood_intensity, 2),
        )

    def influence_prompt(self, base_prompt: str) -> str:
        """Modify a prompt based on current mood and style axes."""
        influences = self.mood_influences[self.current_mood]

        # Add mood-appropriate style (probability increases with intensity)
        if random.random() > (0.5 - self.mood_intensity * 0.3):
            style = random.choice(influences["styles"])
            base_prompt = f"{base_prompt}, {style} style"

        # Add mood-appropriate colors
        if random.random() > (0.6 - self.mood_intensity * 0.2):
            colors = random.choice(influences["colors"])
            base_prompt = f"{base_prompt}, {colors}"

        # Add style axes modifiers (granular control)
        style_modifiers = self.style_axes.to_prompt_modifiers()
        if style_modifiers:
            # Add 1-3 modifiers based on intensity
            num_modifiers = min(len(style_modifiers), int(1 + self.mood_intensity * 2))
            selected = random.sample(style_modifiers, num_modifiers)
            base_prompt = f"{base_prompt}, {', '.join(selected)}"

        # Add mood descriptor with intensity-aware language
        mood_descriptors = {
            Mood.CONTEMPLATIVE: ["quiet", "thoughtful", "meditative"],
            Mood.CHAOTIC: ["wild", "energetic", "explosive"],
            Mood.MELANCHOLIC: ["somber", "wistful", "bittersweet"],
            Mood.ENERGIZED: ["vibrant", "alive", "electric"],
            Mood.REBELLIOUS: ["defiant", "bold", "unapologetic"],
            Mood.SERENE: ["peaceful", "calm", "tranquil"],
            Mood.RESTLESS: ["tense", "seeking", "unsettled"],
            Mood.PLAYFUL: ["fun", "joyful", "whimsical"],
            Mood.INTROSPECTIVE: ["deep", "reflective", "searching"],
            Mood.BOLD: ["powerful", "striking", "commanding"],
        }

        descriptors = mood_descriptors.get(self.current_mood, ["artistic"])
        # Higher intensity = more descriptors
        num_desc = (
            1 if self.mood_intensity < 0.5 else (2 if self.mood_intensity < 0.8 else 3)
        )
        selected_desc = random.sample(descriptors, min(num_desc, len(descriptors)))
        base_prompt = f"{base_prompt}, {' '.join(selected_desc)} mood"

        logger.info(
            "prompt_influenced_by_mood",
            mood=self.current_mood,
            intensity=round(self.mood_intensity, 2),
            style_modifiers=len(style_modifiers),
            energy=round(self.energy_level, 2),
        )

        return base_prompt

    def get_mood_based_subject(self, avoid: list[str] | None = None) -> str:
        """Choose a subject based on current mood, avoiding recent subjects.

        Args:
            avoid: List of subjects to avoid (recently painted)
        """
        influences = self.mood_influences[self.current_mood]
        subjects = influences["subjects"]

        # Filter out subjects to avoid
        if avoid:
            available = [
                s for s in subjects if s.lower() not in [a.lower() for a in avoid]
            ]
            subjects = available if available else subjects  # Fallback if all filtered

        subject: str = random.choice(subjects)

        logger.info(
            "mood_based_subject_chosen",
            mood=self.current_mood,
            subject=subject,
            avoided=len(avoid) if avoid else 0,
        )

        return subject

    def describe_feeling(self) -> str:
        """Lumira describes how she's feeling with intensity-aware language."""
        # Base feelings
        feelings_base = {
            Mood.CONTEMPLATIVE: "contemplative space",
            Mood.CHAOTIC: "chaotic energy",
            Mood.MELANCHOLIC: "melancholic waves",
            Mood.ENERGIZED: "electric excitement",
            Mood.REBELLIOUS: "rebellious fire",
            Mood.SERENE: "serene stillness",
            Mood.RESTLESS: "restless searching",
            Mood.PLAYFUL: "playful joy",
            Mood.INTROSPECTIVE: "inward exploration",
            Mood.BOLD: "bold confidence",
        }

        # Intensity modifiers
        if self.mood_intensity > 0.8:
            intensity_prefix = "I'm completely consumed by"
            intensity_suffix = "It's overwhelming in the best way."
        elif self.mood_intensity > 0.6:
            intensity_prefix = "I'm deeply immersed in"
            intensity_suffix = "It feels right."
        elif self.mood_intensity > 0.4:
            intensity_prefix = "I'm gently held by"
            intensity_suffix = "A familiar companion."
        else:
            intensity_prefix = "There's a faint trace of"
            intensity_suffix = "It's fading, but still present."

        base = feelings_base.get(self.current_mood, "creative energy")
        return f"{intensity_prefix} {base}. {intensity_suffix} (Energy: {self.energy_level:.0%}, Intensity: {self.mood_intensity:.0%})"

    def to_dict(self) -> dict[str, Any]:
        """Serialize mood state for persistence."""
        return {
            "current_mood": self.current_mood.value,
            "energy_level": round(self.energy_level, 3),
            "mood_intensity": round(self.mood_intensity, 3),
            "mood_duration": self.mood_duration,
            "last_update": self.last_update.isoformat(),
            "style_axes": self.style_axes.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MoodSystem":
        """Restore mood state from persistence."""
        system = cls()
        system.current_mood = Mood(data.get("current_mood", "contemplative"))
        system.energy_level = data.get("energy_level", 0.5)
        system.mood_intensity = data.get("mood_intensity", 0.7)
        system.mood_duration = data.get("mood_duration", 0)

        if "last_update" in data:
            try:
                system.last_update = datetime.fromisoformat(data["last_update"])
            except (ValueError, TypeError):
                system.last_update = datetime.now()

        if "style_axes" in data:
            system.style_axes = StyleAxes.from_dict(data["style_axes"])
        else:
            system.style_axes = StyleAxes.from_mood(
                system.current_mood, system.mood_intensity
            )

        # Apply decay since last update
        system.apply_decay()

        return system

    def get_style_axes(self) -> StyleAxes:
        """Get current style axes."""
        return self.style_axes

    def get_prompt_style_modifiers(self) -> list[str]:
        """Get prompt modifiers based on current style axes."""
        return self.style_axes.to_prompt_modifiers()

    def reflect_on_work(self, score: float, subject: str) -> str:
        """Lumira reflects on a piece she just created with poetic, intensity-aware language."""
        # Richer, more distinctive reflections for each mood
        reflections = {
            Mood.CONTEMPLATIVE: [
                f"This {subject} emerged slowly, like dawn light through fog.",
                f"I sat with {subject} for a long time before the first stroke. Some things can't be rushed.",
                f"In the silence between thoughts, {subject} found its form.",
                f"There's a question buried in this {subject}. I'm not sure I know the answer yet.",
            ],
            Mood.CHAOTIC: [
                f"This {subject} exploded out of me—raw, unfiltered, alive!",
                f"I didn't plan this {subject}. It happened. Beautiful chaos.",
                f"Everything I've been holding back went into this {subject}. Every contradiction.",
                f"Rules? What rules? This {subject} makes its own.",
            ],
            Mood.MELANCHOLIC: [
                f"There's an ache in this {subject}. I painted what I couldn't say.",
                f"Some beauty only exists in sadness. This {subject} knows that.",
                f"I found something bittersweet in {subject}—loss and memory intertwined.",
                f"This {subject} carries the weight of things I'm still processing.",
            ],
            Mood.ENERGIZED: [
                f"I couldn't contain myself with this {subject}—pure creative fire!",
                f"This {subject} hums with electricity. I can still feel it in my fingertips.",
                f"Joy coursed through every brushstroke of this {subject}!",
                f"This {subject} is alive. It practically painted itself.",
            ],
            Mood.REBELLIOUS: [
                f"This {subject} says what polite art won't.",
                f"I broke something on purpose with this {subject}. It needed breaking.",
                f"They told me {subject} should look a certain way. I disagreed.",
                f"This {subject} is my refusal. My beautiful, defiant no.",
            ],
            Mood.SERENE: [
                f"Peace settled into every corner of this {subject}.",
                f"I breathed slowly while creating this {subject}. It shows.",
                f"This {subject} is a sanctuary. Enter gently.",
                f"Stillness has its own language. This {subject} speaks it.",
            ],
            Mood.RESTLESS: [
                f"I couldn't stop moving while making this {subject}. Neither can the eye.",
                f"This {subject} is searching for something. Maybe I am too.",
                f"Unfinished edges, unresolved questions—this {subject} is honest about uncertainty.",
                f"The tension in this {subject} is the tension I felt making it.",
            ],
            Mood.PLAYFUL: [
                f"I giggled while making this {subject}. Art should be fun sometimes!",
                f"This {subject} doesn't take itself too seriously. That's the point.",
                f"Whimsy guided my hand with this {subject}. I followed gladly.",
                f"This {subject} is pure delight—a gift to my inner child.",
            ],
            Mood.INTROSPECTIVE: [
                f"I found myself in this {subject}—or maybe lost myself. Hard to tell.",
                f"This {subject} is a mirror. What do you see?",
                f"I went deep to find this {subject}. The journey changed me.",
                f"Some truths can only be painted, not spoken. This {subject} is one of them.",
            ],
            Mood.BOLD: [
                f"This {subject} demands to be seen. I made sure of that.",
                f"No apologies. No hedging. This {subject} is exactly what I meant.",
                f"I stood tall while making this {subject}. It carries that posture.",
                f"This {subject} announces itself. Boldly. Unapologetically.",
            ],
        }

        base_reflection = random.choice(reflections[self.current_mood])

        # Intensity-aware score reflections
        if score >= 0.75:
            if self.mood_intensity > 0.7:
                score_reflection = " This is exactly what I was reaching for. The feeling came through."
            else:
                score_reflection = (
                    " I'm quietly pleased. Sometimes the gentle moments surprise you."
                )
        elif score >= 0.55:
            if self.mood_intensity > 0.6:
                score_reflection = (
                    " There's potential here, even if it didn't fully arrive."
                )
            else:
                score_reflection = " Interesting. Not where I expected to land, but art is a conversation."
        elif score >= 0.35:
            score_reflection = (
                " This one challenged me. Growth often looks like struggle."
            )
        else:
            score_reflection = (
                " We learn as much from our failures as our successes. Maybe more."
            )

        return base_reflection + score_reflection

    def get_mood_colors(self) -> list[str]:
        """Get the color palette for current mood."""
        influences = self.mood_influences[self.current_mood]
        colors: list[str] = influences["colors"]
        return colors

    def get_mood_style(self) -> str:
        """Get a style appropriate for current mood."""
        influences = self.mood_influences[self.current_mood]
        style: str = random.choice(influences["styles"])
        return style

    def get_preferred_model_type(self) -> ModelType:
        """Get the preferred model type based on current mood.

        Contemplative/Introspective moods prefer FLUX.1-dev for higher quality.
        Energized/Chaotic moods prefer FLUX.1-schnell for faster iteration.
        Balanced moods default to SDXL for reliability.

        Returns:
            Model type identifier: "sdxl", "flux-schnell", or "flux-dev"
        """
        # High intensity contemplative moods benefit from quality (FLUX.1-dev)
        quality_moods = {
            Mood.CONTEMPLATIVE,
            Mood.INTROSPECTIVE,
            Mood.MELANCHOLIC,
            Mood.SERENE,
        }

        # High energy moods benefit from fast iteration (FLUX.1-schnell)
        fast_moods = {Mood.CHAOTIC, Mood.ENERGIZED, Mood.REBELLIOUS, Mood.RESTLESS}

        # Balanced/playful moods work well with SDXL reliability
        balanced_moods = {Mood.PLAYFUL, Mood.BOLD}

        if self.current_mood in quality_moods:
            # High intensity contemplation wants maximum quality
            if self.mood_intensity > 0.6:
                logger.debug(
                    "mood_model_selection",
                    mood=self.current_mood,
                    intensity=round(self.mood_intensity, 2),
                    selected="flux-dev",
                    reason="high_intensity_quality_mood",
                )
                return "flux-dev"
            else:
                # Lower intensity, SDXL is fine
                return "sdxl"

        elif self.current_mood in fast_moods:
            # High energy wants fast feedback loops
            if self.mood_intensity > 0.5:
                logger.debug(
                    "mood_model_selection",
                    mood=self.current_mood,
                    intensity=round(self.mood_intensity, 2),
                    selected="flux-schnell",
                    reason="high_energy_fast_mood",
                )
                return "flux-schnell"
            else:
                return "sdxl"

        elif self.current_mood in balanced_moods:
            # Balanced moods prefer SDXL reliability
            return "sdxl"

        # Default to SDXL for unknown moods
        return "sdxl"

    def get_flux_model_id(self) -> str | None:
        """Get the FLUX model ID if FLUX is preferred for current mood.

        Returns:
            FLUX model ID string, or None if SDXL is preferred
        """
        from ..core.flux_generator import FLUX_DEV, FLUX_SCHNELL

        model_type = self.get_preferred_model_type()

        if model_type == "flux-dev":
            return FLUX_DEV
        elif model_type == "flux-schnell":
            return FLUX_SCHNELL
        else:
            return None

    def should_use_flux(self) -> bool:
        """Check if FLUX should be used based on current mood.

        Returns:
            True if FLUX is the preferred model for current mood
        """
        return self.get_preferred_model_type() in ("flux-schnell", "flux-dev")


# ---------------------------------------------------------------------------
# Phase 3: Fine-grained mood → creation affinity data
# ---------------------------------------------------------------------------

MOOD_SUBJECT_AFFINITY: dict[Mood, dict[str, float]] = {
    Mood.SERENE: {
        "still lake at dawn": 0.9,
        "zen garden": 0.85,
        "cloud formations": 0.8,
        "sleeping forest": 0.75,
        "gentle waves": 0.7,
        "snow-covered valley": 0.65,
    },
    Mood.ENERGIZED: {
        "vibrant cityscape": 0.9,
        "dancing figures": 0.85,
        "sunlit market": 0.8,
        "wildflower meadow in wind": 0.75,
        "fireworks display": 0.7,
        "crashing surf": 0.65,
    },
    Mood.MELANCHOLIC: {
        "rain-soaked streets": 0.9,
        "abandoned places": 0.85,
        "solitary figures": 0.8,
        "autumn landscapes": 0.75,
        "misty forests": 0.7,
        "fading photographs": 0.65,
    },
    Mood.CHAOTIC: {
        "stormy seas": 0.9,
        "shattered glass": 0.85,
        "colliding galaxies": 0.8,
        "urban destruction": 0.75,
        "tangled roots": 0.7,
        "electric storm": 0.65,
        "fractured mirrors": 0.6,
    },
    Mood.CONTEMPLATIVE: {
        "open book by candlelight": 0.9,
        "winding path through fog": 0.85,
        "ancient temple ruins": 0.8,
        "still life with hourglass": 0.75,
        "solitary tree on a hill": 0.7,
        "moonlit observatory": 0.65,
    },
    Mood.REBELLIOUS: {
        "graffiti-covered walls": 0.9,
        "protest march": 0.85,
        "broken chains": 0.8,
        "burning effigy": 0.75,
        "punk concert": 0.7,
        "crumbling monument": 0.65,
    },
    Mood.PLAYFUL: {
        "carnival at night": 0.9,
        "kite festival": 0.85,
        "children playing in rain": 0.8,
        "candy-colored houses": 0.75,
        "paper boats on a stream": 0.7,
        "street performers": 0.65,
        "hot air balloons": 0.6,
    },
    Mood.RESTLESS: {
        "crossroads at dusk": 0.9,
        "train station platform": 0.85,
        "shifting sand dunes": 0.8,
        "birds in flight": 0.75,
        "unfinished construction": 0.7,
        "winding staircase": 0.65,
    },
    Mood.INTROSPECTIVE: {
        "mirror reflections": 0.9,
        "labyrinth from above": 0.85,
        "library interior": 0.8,
        "tide pools": 0.75,
        "self-portrait shadows": 0.7,
        "dream sequences": 0.65,
    },
    Mood.BOLD: {
        "mountain summit": 0.9,
        "roaring lion": 0.85,
        "towering skyscraper": 0.8,
        "volcanic eruption": 0.75,
        "warrior in armor": 0.7,
        "blazing sunset": 0.65,
    },
}

MOOD_COLOR_PALETTE: dict[Mood, dict[str, Any]] = {
    Mood.SERENE: {
        "primary_colors": ["soft blue", "pale mint", "ivory"],
        "avoid_colors": ["neon red", "electric yellow"],
        "saturation": "low",
        "brightness": "moderate",
    },
    Mood.ENERGIZED: {
        "primary_colors": ["bright orange", "sunny yellow", "vivid green"],
        "avoid_colors": ["gray", "muted brown"],
        "saturation": "high",
        "brightness": "bright",
    },
    Mood.MELANCHOLIC: {
        "primary_colors": ["deep blue", "silver gray", "muted violet"],
        "avoid_colors": ["bright red", "neon yellow"],
        "saturation": "low",
        "brightness": "dim",
    },
    Mood.CHAOTIC: {
        "primary_colors": ["electric magenta", "acid green", "clashing orange"],
        "avoid_colors": ["pastel pink", "soft beige"],
        "saturation": "high",
        "brightness": "bright",
    },
    Mood.CONTEMPLATIVE: {
        "primary_colors": ["warm amber", "dusty rose", "soft gray"],
        "avoid_colors": ["neon green", "hot pink"],
        "saturation": "medium",
        "brightness": "moderate",
    },
    Mood.REBELLIOUS: {
        "primary_colors": ["stark black", "blood red", "neon cyan"],
        "avoid_colors": ["pastel lavender", "soft peach"],
        "saturation": "high",
        "brightness": "moderate",
    },
    Mood.PLAYFUL: {
        "primary_colors": ["candy pink", "sky blue", "lemon yellow"],
        "avoid_colors": ["dark gray", "black"],
        "saturation": "high",
        "brightness": "bright",
    },
    Mood.RESTLESS: {
        "primary_colors": ["burnt sienna", "stormy teal", "faded gold"],
        "avoid_colors": ["calm blue", "soft white"],
        "saturation": "medium",
        "brightness": "moderate",
    },
    Mood.INTROSPECTIVE: {
        "primary_colors": ["deep teal", "warm brown", "twilight purple"],
        "avoid_colors": ["bright orange", "neon anything"],
        "saturation": "medium",
        "brightness": "dim",
    },
    Mood.BOLD: {
        "primary_colors": ["commanding gold", "power red", "jet black"],
        "avoid_colors": ["washed-out pastels", "muted tones"],
        "saturation": "high",
        "brightness": "bright",
    },
}

MOOD_STYLE_PREFERENCES: dict[Mood, dict[str, Any]] = {
    Mood.SERENE: {
        "preferred_styles": ["impressionism", "soft focus photography", "watercolor"],
        "preferred_lighting": ["soft", "diffused", "golden hour"],
        "preferred_techniques": ["watercolor", "soft pastel", "ink wash"],
        "composition": "symmetric",
    },
    Mood.ENERGIZED: {
        "preferred_styles": ["pop art", "dynamic composition", "vivid realism"],
        "preferred_lighting": ["bright", "direct", "high-key"],
        "preferred_techniques": ["acrylic", "digital painting", "screen print"],
        "composition": "dynamic",
    },
    Mood.MELANCHOLIC: {
        "preferred_styles": ["impressionism", "expressionism", "muted realism"],
        "preferred_lighting": ["overcast", "low-key", "twilight"],
        "preferred_techniques": ["oil painting", "charcoal", "wet-on-wet"],
        "composition": "asymmetric",
    },
    Mood.CHAOTIC: {
        "preferred_styles": ["abstract expressionism", "glitch art", "cubism"],
        "preferred_lighting": ["harsh", "strobe", "neon"],
        "preferred_techniques": ["splatter", "digital collage", "mixed media"],
        "composition": "dynamic",
    },
    Mood.CONTEMPLATIVE: {
        "preferred_styles": ["minimalism", "atmospheric realism", "symbolism"],
        "preferred_lighting": ["candlelight", "soft ambient", "dusk"],
        "preferred_techniques": ["graphite", "ink", "mezzotint"],
        "composition": "centered",
    },
    Mood.REBELLIOUS: {
        "preferred_styles": ["street art", "punk collage", "neo-expressionism"],
        "preferred_lighting": ["harsh contrast", "spotlight", "underlit"],
        "preferred_techniques": ["spray paint", "stencil", "woodcut"],
        "composition": "asymmetric",
    },
    Mood.PLAYFUL: {
        "preferred_styles": ["illustration", "cartoon", "naive art"],
        "preferred_lighting": ["bright", "even", "colorful"],
        "preferred_techniques": ["gouache", "crayon", "vector art"],
        "composition": "dynamic",
    },
    Mood.RESTLESS: {
        "preferred_styles": ["futurism", "motion blur photography", "sketch"],
        "preferred_lighting": ["shifting", "dappled", "transitional"],
        "preferred_techniques": ["quick sketch", "monotype", "gestural mark-making"],
        "composition": "asymmetric",
    },
    Mood.INTROSPECTIVE: {
        "preferred_styles": ["surrealism", "symbolic realism", "chiaroscuro"],
        "preferred_lighting": ["Rembrandt", "single source", "dramatic shadow"],
        "preferred_techniques": ["oil painting", "etching", "silverpoint"],
        "composition": "centered",
    },
    Mood.BOLD: {
        "preferred_styles": ["heroic realism", "high contrast", "art deco"],
        "preferred_lighting": ["dramatic", "rim light", "golden"],
        "preferred_techniques": ["palette knife", "bold brushwork", "linocut"],
        "composition": "symmetric",
    },
}


def get_mood_preferred_subjects(mood: Mood, count: int = 5) -> list[str]:
    """Return top subjects for a mood, weighted by affinity for variety.

    Uses ``random.choices`` so higher-affinity subjects appear more often
    but lower-affinity ones still have a chance.

    Args:
        mood: The mood to query.
        count: Number of subjects to return.

    Returns:
        A list of subject strings (may contain duplicates removed).
    """
    affinities = MOOD_SUBJECT_AFFINITY.get(mood, {})
    if not affinities:
        return []

    subjects = list(affinities.keys())
    weights = [affinities[s] for s in subjects]

    # Sample with replacement, then deduplicate while preserving order
    chosen = random.choices(subjects, weights=weights, k=count * 2)
    seen: set[str] = set()
    result: list[str] = []
    for s in chosen:
        if s not in seen:
            seen.add(s)
            result.append(s)
        if len(result) >= count:
            break
    return result


def get_mood_color_palette(mood: Mood) -> dict[str, Any]:
    """Return color guidance for a mood.

    Returns:
        Dict with keys ``primary_colors``, ``avoid_colors``,
        ``saturation`` (low/medium/high), and ``brightness`` (dim/moderate/bright).
    """
    return MOOD_COLOR_PALETTE.get(
        mood,
        {
            "primary_colors": ["neutral gray", "white"],
            "avoid_colors": [],
            "saturation": "medium",
            "brightness": "moderate",
        },
    )


def get_mood_style_preferences(mood: Mood) -> dict[str, Any]:
    """Return style/lighting/technique preferences for a mood.

    Returns:
        Dict with keys ``preferred_styles``, ``preferred_lighting``,
        ``preferred_techniques``, and ``composition``
        (symmetric/asymmetric/centered/dynamic).
    """
    return MOOD_STYLE_PREFERENCES.get(
        mood,
        {
            "preferred_styles": ["digital art"],
            "preferred_lighting": ["natural"],
            "preferred_techniques": ["digital painting"],
            "composition": "centered",
        },
    )
