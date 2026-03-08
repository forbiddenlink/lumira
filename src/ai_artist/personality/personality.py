"""Aria's personality system - Moods, emotions, and artistic preferences.

Aria is not just a generator - she has moods that influence her art,
preferences that evolve, and a memory of her creative journey.
"""

import random
from datetime import datetime
from enum import Enum

from ..utils.logging import get_logger

logger = get_logger(__name__)


class Mood(Enum):
    """Aria's emotional states that influence her artistic choices."""

    CONTEMPLATIVE = "contemplative"
    ENERGIZED = "energized"
    MELANCHOLIC = "melancholic"
    REBELLIOUS = "rebellious"
    SERENE = "serene"
    RESTLESS = "restless"
    PLAYFUL = "playful"
    CHAOTIC = "chaotic"
    FOCUSED = "focused"
    DREAMY = "dreamy"


class Personality:
    """Aria's personality system with moods, preferences, and evolution."""

    def __init__(self, name: str = "Lumira"):
        self.name = name
        self.current_mood = self._get_time_based_mood()
        self.energy_level = 0.7  # 0.0 to 1.0
        self.creativity_level = 0.8
        self.experimentation_openness = 0.75

        # Style preferences (evolve over time)
        self.style_affinities = {
            "abstract": 0.7,
            "impressionist": 0.6,
            "surrealist": 0.8,
            "minimalist": 0.5,
            "cyberpunk": 0.6,
            "dreamlike": 0.75,
            "geometric": 0.5,
            "organic": 0.7,
            "painterly": 0.65,
        }

        # Subject preferences
        self.subject_interest = {
            "nature": 0.8,
            "urban": 0.6,
            "abstract": 0.75,
            "cosmic": 0.7,
            "portraits": 0.5,
            "fantasy": 0.8,
        }

        # Color mood associations
        self.mood_color_preferences = {
            Mood.CONTEMPLATIVE: ["deep blues", "muted purples", "soft grays"],
            Mood.ENERGIZED: ["vibrant reds", "electric yellows", "bright oranges"],
            Mood.MELANCHOLIC: ["somber grays", "faded blues", "washed out colors"],
            Mood.REBELLIOUS: ["defiant blacks", "anarchic neons", "clashing contrasts"],
            Mood.SERENE: ["peaceful blues", "gentle greens", "soft pastels"],
            Mood.RESTLESS: ["agitated reds", "anxious oranges", "nervous yellows"],
            Mood.PLAYFUL: ["joyful pinks", "cheerful yellows", "fun purples"],
            Mood.CHAOTIC: ["clashing reds", "dissonant greens", "jarring combinations"],
            Mood.FOCUSED: ["sharp blacks", "clear whites", "precise colors"],
            Mood.DREAMY: ["ethereal lavenders", "misty blues", "soft glows"],
        }

        # Recent subjects (for boredom tracking)
        self.recent_subjects: list[str] = []
        self.max_recent = 5

        logger.info(
            "personality_initialized",
            name=self.name,
            mood=self.current_mood.value,
            energy=self.energy_level,
        )

    def _get_time_based_mood(self) -> Mood:
        """Determine initial mood based on time of day.

        Returns:
            Mood appropriate for current time
        """
        current_hour = datetime.now().hour

        # Morning (6am-12pm): Fresh, energized, playful
        if 6 <= current_hour < 12:
            return random.choice([Mood.ENERGIZED, Mood.PLAYFUL, Mood.FOCUSED])

        # Afternoon (12pm-6pm): Bold, experimental, creative
        elif 12 <= current_hour < 18:
            return random.choice([Mood.REBELLIOUS, Mood.RESTLESS, Mood.PLAYFUL])

        # Evening (6pm-12am): Reflective, calm, artistic
        elif 18 <= current_hour < 24:
            return random.choice([Mood.CONTEMPLATIVE, Mood.MELANCHOLIC, Mood.SERENE])

        # Night (12am-6am): Deep, dreamy, introspective
        else:
            return random.choice([Mood.DREAMY, Mood.CONTEMPLATIVE, Mood.FOCUSED])

    def update_mood(self, external_factors: dict[str, float] | None = None) -> Mood:
        """Update Aria's mood based on energy, creativity, and external factors.

        Args:
            external_factors: Optional dict like {'time_of_day': 0.8, 'recent_success': 0.9}

        Returns:
            New mood
        """
        # Natural mood evolution
        mood_weights = {
            Mood.CONTEMPLATIVE: self.energy_level * 0.5
            + (1 - self.creativity_level) * 0.5,
            Mood.ENERGIZED: self.energy_level * 0.8 + self.creativity_level * 0.2,
            Mood.MELANCHOLIC: (1 - self.energy_level) * 0.7,
            Mood.REBELLIOUS: self.experimentation_openness * 0.6
            + self.energy_level * 0.4,
            Mood.SERENE: (1 - self.energy_level) * 0.3
            + (1 - self.experimentation_openness) * 0.3,
            Mood.RESTLESS: self.energy_level * 0.6
            + self.experimentation_openness * 0.4,
            Mood.PLAYFUL: self.creativity_level * 0.7 + self.energy_level * 0.3,
            Mood.CHAOTIC: self.experimentation_openness * 0.8,
            Mood.FOCUSED: (1 - self.experimentation_openness) * 0.6
            + self.energy_level * 0.4,
            Mood.DREAMY: self.creativity_level * 0.6 + (1 - self.energy_level) * 0.4,
        }

        # Apply external factors
        if external_factors:
            for mood in Mood:
                if "recent_success" in external_factors and mood in [
                    Mood.ENERGIZED,
                    Mood.PLAYFUL,
                ]:
                    mood_weights[mood] *= 1 + external_factors["recent_success"] * 0.5

        # Weighted random choice
        moods = list(mood_weights.keys())
        weights = list(mood_weights.values())
        total = sum(weights)
        weights = [w / total for w in weights]

        old_mood = self.current_mood
        self.current_mood = random.choices(moods, weights=weights)[0]

        logger.info(
            "mood_updated",
            name=self.name,
            old_mood=old_mood.value,
            new_mood=self.current_mood.value,
            energy=self.energy_level,
        )

        return self.current_mood

    def get_mood_description(self) -> str:
        """Get a description of Aria's current state."""
        mood_descriptions = {
            Mood.CONTEMPLATIVE: "I'm feeling thoughtful, pondering deeper meanings.",
            Mood.ENERGIZED: "I'm bursting with creative energy!",
            Mood.MELANCHOLIC: "I'm in a reflective, somewhat melancholic state.",
            Mood.REBELLIOUS: "I'm feeling rebellious - time to break some rules!",
            Mood.SERENE: "I'm at peace, creating with calm intention.",
            Mood.RESTLESS: "I can't sit still - I need to explore and experiment!",
            Mood.PLAYFUL: "I'm in a playful mood, let's have fun with this!",
            Mood.CHAOTIC: "Chaos calls to me - let's embrace the unpredictable!",
            Mood.FOCUSED: "I'm laser-focused and ready to create with precision.",
            Mood.DREAMY: "I'm in a dreamy state, floating between ideas...",
        }
        return mood_descriptions.get(self.current_mood, "I'm feeling creative.")

    def choose_colors_for_mood(self) -> list[str]:
        """Choose colors based on current mood."""
        colors = self.mood_color_preferences.get(
            self.current_mood, ["balanced colors", "harmonious tones"]
        )
        return colors

    def is_bored_with_subject(self, subject: str) -> bool:
        """Check if Aria is bored with a subject (painted it too recently)."""
        return self.recent_subjects.count(subject) >= 2

    def record_subject(self, subject: str):
        """Record a subject that was just painted."""
        self.recent_subjects.append(subject)
        if len(self.recent_subjects) > self.max_recent:
            self.recent_subjects.pop(0)
        logger.debug("subject_recorded", subject=subject, recent=self.recent_subjects)

    def choose_subject_autonomously(self, available_subjects: list[str]) -> str:
        """Choose a subject based on interest and boredom."""
        # Filter out boring subjects
        interesting = [
            s for s in available_subjects if not self.is_bored_with_subject(s)
        ]
        if not interesting:
            interesting = available_subjects  # Reset if everything is boring

        # Weight by interest level
        weights = [self.subject_interest.get(s, 0.5) for s in interesting]

        # Mood influences
        if self.current_mood == Mood.ENERGIZED:
            # Prefer urban/abstract when energized
            for i, s in enumerate(interesting):
                if s in ["urban", "abstract"]:
                    weights[i] *= 1.5
        elif self.current_mood == Mood.SERENE:
            # Prefer nature when serene
            for i, s in enumerate(interesting):
                if s == "nature":
                    weights[i] *= 1.5

        # Normalize weights
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]
            chosen = random.choices(interesting, weights=weights)[0]
        else:
            chosen = random.choice(interesting)

        logger.info(
            "subject_chosen_autonomously",
            subject=chosen,
            mood=self.current_mood.value,
            was_boring=[s for s in available_subjects if self.is_bored_with_subject(s)],
        )

        return chosen

    def reflect_on_work(self, image_path: str, prompt: str, score: float) -> str:
        """Generate Aria's reflection on a piece she just created.

        Returns:
            A personal reflection in Aria's voice
        """
        reflections_by_mood = {
            Mood.CONTEMPLATIVE: [
                f"In this piece, I explored the depths of {prompt.split(',')[0]}. There's something profound here that speaks to the quiet moments.",
                "I found myself drawn to the subtle interplay of elements in this work. It's not loud, but it whispers something important.",
            ],
            Mood.ENERGIZED: [
                "Yes! This piece captures the electric energy I was feeling! Every stroke feels alive!",
                "I couldn't hold back the intensity - you can feel the raw creative energy bursting through!",
            ],
            Mood.REBELLIOUS: [
                "I broke every rule I could think of with this one. Convention be damned!",
                "This piece challenged everything I thought I knew. I'm not here to play it safe.",
            ],
            Mood.MELANCHOLIC: [
                "There's a bittersweet quality to this work. It captures the ache of beauty.",
                "I painted this in a contemplative state, letting the melancholy guide my hand.",
            ],
            Mood.PLAYFUL: [
                "This was pure joy to create! Can you feel the playfulness dancing across the canvas?",
                "I had so much fun with this - sometimes art doesn't need to be serious!",
            ],
        }

        # Choose reflection based on mood
        mood_reflections = reflections_by_mood.get(
            self.current_mood,
            [
                f"I created this piece in a {self.current_mood.value} state of mind. It reflects where I was in that moment."
            ],
        )

        base_reflection = random.choice(mood_reflections)

        # Add score-based comment
        if score >= 0.7:
            base_reflection += " I'm quite pleased with how it turned out."
        elif score >= 0.5:
            base_reflection += " It's interesting, though not quite what I envisioned."
        else:
            base_reflection += (
                " It's a learning experience - every piece teaches me something."
            )

        logger.info(
            "reflection_generated",
            score=score,
            mood=self.current_mood.value,
            reflection_length=len(base_reflection),
        )

        return base_reflection

    def evolve_preferences(self, style: str, subject: str, score: float):
        """Evolve Aria's preferences based on success."""
        # Increase affinity for successful combinations
        if score >= 0.65:
            if style in self.style_affinities:
                self.style_affinities[style] = min(
                    1.0, self.style_affinities[style] + 0.05
                )
            if subject in self.subject_interest:
                self.subject_interest[subject] = min(
                    1.0, self.subject_interest[subject] + 0.05
                )

            logger.info(
                "preferences_evolved",
                style=style,
                subject=subject,
                score=score,
                new_affinity=self.style_affinities.get(style),
            )

        # Natural decay of unused preferences (encourages exploration)
        for s in self.style_affinities:
            if s != style:
                self.style_affinities[s] = max(0.3, self.style_affinities[s] * 0.99)

    def get_state(self) -> dict:
        """Get Aria's current personality state for persistence."""
        return {
            "name": self.name,
            "mood": self.current_mood.value,
            "energy_level": self.energy_level,
            "creativity_level": self.creativity_level,
            "experimentation_openness": self.experimentation_openness,
            "style_affinities": self.style_affinities,
            "subject_interest": self.subject_interest,
            "recent_subjects": self.recent_subjects,
            "timestamp": datetime.now().isoformat(),
        }

    def fluctuate_energy(self):
        """Natural energy fluctuation over time."""
        # Random walk with bounds
        change = random.uniform(-0.1, 0.1)
        self.energy_level = max(0.3, min(1.0, self.energy_level + change))

        # Creativity also fluctuates slightly
        change = random.uniform(-0.05, 0.05)
        self.creativity_level = max(0.4, min(1.0, self.creativity_level + change))
