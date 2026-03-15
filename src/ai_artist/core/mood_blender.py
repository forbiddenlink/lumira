"""Mood blending for Lumira's emotional state interpolation.

The MoodBlender enables smooth transitions between emotional states,
creating nuanced artistic expressions that combine multiple moods.
"""

from dataclasses import dataclass
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MoodProfile:
    """Profile defining a mood's characteristics."""

    name: str
    energy_min: float
    energy_max: float
    colors: list[str]
    styles: list[str]
    atmosphere: str
    brush_style: str = "varied"
    contrast: str = "medium"

    @property
    def avg_energy(self) -> float:
        """Average energy level for this mood."""
        return (self.energy_min + self.energy_max) / 2


@dataclass
class BlendedMood:
    """A blended mood state combining multiple moods."""

    components: dict[str, float]  # {"melancholic": 0.7, "serene": 0.3}
    energy: float
    colors: list[str]
    styles: list[str]
    atmosphere: str
    name: str  # Display name like "melancholic+serene"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "components": self.components,
            "energy": self.energy,
            "colors": self.colors,
            "styles": self.styles,
            "atmosphere": self.atmosphere,
            "name": self.name,
        }


# Default mood profiles matching Lumira's 10 moods
DEFAULT_MOOD_PROFILES = {
    "contemplative": MoodProfile(
        name="contemplative",
        energy_min=0.3,
        energy_max=0.5,
        colors=["deep blue", "muted grey", "soft white", "slate"],
        styles=["impressionist", "minimalist", "atmospheric"],
        atmosphere="quiet, thoughtful",
        brush_style="soft",
        contrast="low",
    ),
    "playful": MoodProfile(
        name="playful",
        energy_min=0.7,
        energy_max=0.9,
        colors=["bright yellow", "hot pink", "electric blue", "lime green"],
        styles=["pop-art", "cartoon", "vibrant", "whimsical"],
        atmosphere="joyful, whimsical",
        brush_style="bold",
        contrast="high",
    ),
    "melancholic": MoodProfile(
        name="melancholic",
        energy_min=0.2,
        energy_max=0.4,
        colors=["navy", "charcoal", "dusty rose", "faded purple"],
        styles=["romantic", "atmospheric", "impressionist"],
        atmosphere="wistful, nostalgic",
        brush_style="soft",
        contrast="low",
    ),
    "euphoric": MoodProfile(
        name="euphoric",
        energy_min=0.8,
        energy_max=1.0,
        colors=["gold", "magenta", "cyan", "pure white"],
        styles=["psychedelic", "maximalist", "radiant"],
        atmosphere="transcendent, luminous",
        brush_style="dynamic",
        contrast="high",
    ),
    "serene": MoodProfile(
        name="serene",
        energy_min=0.3,
        energy_max=0.5,
        colors=["sage green", "sky blue", "cream", "soft lavender"],
        styles=["zen", "naturalist", "peaceful"],
        atmosphere="peaceful, harmonious",
        brush_style="gentle",
        contrast="low",
    ),
    "anxious": MoodProfile(
        name="anxious",
        energy_min=0.6,
        energy_max=0.8,
        colors=["stark white", "harsh red", "black", "electric yellow"],
        styles=["expressionist", "glitch", "fragmented"],
        atmosphere="tense, unsettling",
        brush_style="jagged",
        contrast="extreme",
    ),
    "nostalgic": MoodProfile(
        name="nostalgic",
        energy_min=0.4,
        energy_max=0.6,
        colors=["amber", "faded brown", "soft pink", "sepia"],
        styles=["vintage", "sepia", "film-grain", "romantic"],
        atmosphere="warm, faded memory",
        brush_style="textured",
        contrast="medium",
    ),
    "curious": MoodProfile(
        name="curious",
        energy_min=0.5,
        energy_max=0.7,
        colors=["purple", "teal", "coral", "metallic"],
        styles=["surrealist", "abstract", "experimental"],
        atmosphere="mysterious, intriguing",
        brush_style="varied",
        contrast="medium",
    ),
    "rebellious": MoodProfile(
        name="rebellious",
        energy_min=0.7,
        energy_max=0.9,
        colors=["neon red", "black", "chrome", "acid green"],
        styles=["punk", "graffiti", "brutalist", "street-art"],
        atmosphere="bold, defiant",
        brush_style="aggressive",
        contrast="extreme",
    ),
    "transcendent": MoodProfile(
        name="transcendent",
        energy_min=0.5,
        energy_max=0.8,
        colors=["iridescent", "deep purple", "starlight", "ethereal blue"],
        styles=["ethereal", "cosmic", "sacred-geometry"],
        atmosphere="ethereal, cosmic",
        brush_style="flowing",
        contrast="medium",
    ),
}


class MoodBlender:
    """Blends multiple moods into a unified artistic state.

    Enables Lumira to express nuanced emotions by combining
    characteristics from multiple mood profiles.
    """

    def __init__(self, profiles: dict[str, MoodProfile] | None = None):
        """Initialize the mood blender.

        Args:
            profiles: Custom mood profiles. Uses defaults if not provided.
        """
        self.profiles = profiles or DEFAULT_MOOD_PROFILES
        logger.info("mood_blender_initialized", mood_count=len(self.profiles))

    def blend(self, weights: dict[str, float]) -> BlendedMood:
        """Blend multiple moods with given weights.

        Args:
            weights: Dictionary of mood names to weights, e.g.,
                     {"melancholic": 0.7, "serene": 0.3}

        Returns:
            BlendedMood with combined characteristics
        """
        if not weights:
            # Default to contemplative
            weights = {"contemplative": 1.0}

        # Normalize weights to sum to 1.0
        total = sum(weights.values())
        if total == 0:
            total = 1.0
        normalized = {k: v / total for k, v in weights.items()}

        # Calculate weighted energy
        energy = sum(
            self.profiles[mood].avg_energy * weight
            for mood, weight in normalized.items()
            if mood in self.profiles
        )

        # Blend colors (weighted selection)
        blended_colors = self._blend_colors(normalized)

        # Blend styles (weighted union)
        blended_styles = self._blend_styles(normalized)

        # Blend atmosphere
        blended_atmosphere = self._blend_atmosphere(normalized)

        # Create display name
        sorted_moods = sorted(normalized.items(), key=lambda x: -x[1])
        if len(sorted_moods) == 1:
            name = sorted_moods[0][0]
        else:
            name = "+".join(f"{m}({w:.0%})" for m, w in sorted_moods if w > 0.1)

        blended = BlendedMood(
            components=normalized,
            energy=energy,
            colors=blended_colors,
            styles=blended_styles,
            atmosphere=blended_atmosphere,
            name=name,
        )

        logger.debug(
            "mood_blended",
            components=list(normalized.keys()),
            energy=round(energy, 2),
        )

        return blended

    def _blend_colors(self, weights: dict[str, float], limit: int = 5) -> list[str]:
        """Blend color palettes from multiple moods.

        Args:
            weights: Normalized mood weights
            limit: Maximum colors to return

        Returns:
            List of blended colors
        """
        color_scores: dict[str, float] = {}

        for mood, weight in weights.items():
            if mood not in self.profiles:
                continue
            profile = self.profiles[mood]

            for i, color in enumerate(profile.colors):
                # Earlier colors in list get higher weight
                position_weight = 1.0 - (i * 0.15)
                color_scores[color] = (
                    color_scores.get(color, 0) + weight * position_weight
                )

        # Sort by score and return top colors
        sorted_colors = sorted(color_scores.items(), key=lambda x: -x[1])
        return [color for color, _ in sorted_colors[:limit]]

    def _blend_styles(self, weights: dict[str, float], limit: int = 4) -> list[str]:
        """Blend style preferences from multiple moods.

        Args:
            weights: Normalized mood weights
            limit: Maximum styles to return

        Returns:
            List of blended styles
        """
        style_scores: dict[str, float] = {}

        for mood, weight in weights.items():
            if mood not in self.profiles:
                continue
            profile = self.profiles[mood]

            for i, style in enumerate(profile.styles):
                # Earlier styles get higher weight
                position_weight = 1.0 - (i * 0.2)
                style_scores[style] = (
                    style_scores.get(style, 0) + weight * position_weight
                )

        # Sort by score and return top styles
        sorted_styles = sorted(style_scores.items(), key=lambda x: -x[1])
        return [style for style, _ in sorted_styles[:limit]]

    def _blend_atmosphere(self, weights: dict[str, float]) -> str:
        """Create a blended atmosphere description.

        Args:
            weights: Normalized mood weights

        Returns:
            Combined atmosphere string
        """
        # Get atmospheres from top moods
        sorted_moods = sorted(weights.items(), key=lambda x: -x[1])
        atmospheres = []

        for mood, weight in sorted_moods[:2]:
            if mood in self.profiles and weight > 0.2:
                atmospheres.append(self.profiles[mood].atmosphere)

        if not atmospheres:
            return "atmospheric quality"

        if len(atmospheres) == 1:
            return atmospheres[0]

        # Combine two atmospheres
        return f"{atmospheres[0]} with hints of {atmospheres[1]}"

    def get_mood_contrast(self, mood: str) -> str:
        """Get a contrasting mood for tension.

        Args:
            mood: The base mood

        Returns:
            Name of a contrasting mood
        """
        contrasts = {
            "contemplative": "playful",
            "playful": "melancholic",
            "melancholic": "euphoric",
            "euphoric": "serene",
            "serene": "anxious",
            "anxious": "transcendent",
            "nostalgic": "curious",
            "curious": "nostalgic",
            "rebellious": "serene",
            "transcendent": "rebellious",
        }
        return contrasts.get(mood, "contemplative")

    def suggest_blend(
        self, primary_mood: str, tension: float = 0.2
    ) -> dict[str, float]:
        """Suggest a mood blend with controlled tension.

        Args:
            primary_mood: The dominant mood
            tension: Amount of contrasting mood to add (0.0-0.5)

        Returns:
            Suggested blend weights
        """
        tension = max(0.0, min(0.5, tension))
        contrast = self.get_mood_contrast(primary_mood)

        return {
            primary_mood: 1.0 - tension,
            contrast: tension,
        }

    def interpolate(
        self,
        mood_a: str,
        mood_b: str,
        t: float,
    ) -> BlendedMood:
        """Smoothly interpolate between two moods.

        Args:
            mood_a: Starting mood
            mood_b: Ending mood
            t: Interpolation factor (0.0 = mood_a, 1.0 = mood_b)

        Returns:
            Interpolated BlendedMood
        """
        t = max(0.0, min(1.0, t))

        weights = {
            mood_a: 1.0 - t,
            mood_b: t,
        }

        return self.blend(weights)

    def get_profile(self, mood: str) -> MoodProfile | None:
        """Get the profile for a mood.

        Args:
            mood: Mood name

        Returns:
            MoodProfile or None if not found
        """
        return self.profiles.get(mood)
