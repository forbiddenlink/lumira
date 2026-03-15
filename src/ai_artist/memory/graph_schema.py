"""Graph schema definitions for Lumira's knowledge graph."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MoodNode:
    """Represents an emotional state in the graph."""

    name: str
    energy_min: float = 0.0
    energy_max: float = 1.0
    typical_styles: list[str] = field(default_factory=list)
    typical_colors: list[str] = field(default_factory=list)

    def to_cypher_props(self) -> dict[str, Any]:
        """Convert to Cypher property map."""
        return {
            "name": self.name,
            "energy_min": self.energy_min,
            "energy_max": self.energy_max,
            "typical_styles": self.typical_styles,
            "typical_colors": self.typical_colors,
        }


@dataclass
class StyleNode:
    """Represents an artistic style (LoRA or built-in)."""

    name: str
    lora_path: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def to_cypher_props(self) -> dict[str, Any]:
        """Convert to Cypher property map."""
        return {
            "name": self.name,
            "lora_path": self.lora_path or "",
            "description": self.description,
            "tags": self.tags,
        }


@dataclass
class DecisionNode:
    """Represents a creative decision made by Lumira."""

    id: str
    prompt: str
    mood: str
    styles: list[str]
    style_weights: list[float]
    score: float
    timestamp: datetime = field(default_factory=datetime.now)

    def to_cypher_props(self) -> dict[str, Any]:
        """Convert to Cypher property map."""
        return {
            "id": self.id,
            "prompt": self.prompt,
            "mood": self.mood,
            "styles": self.styles,
            "style_weights": self.style_weights,
            "score": self.score,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ArtworkNode:
    """Represents a generated artwork."""

    id: str
    path: str
    score: float
    created_at: datetime = field(default_factory=datetime.now)
    width: int = 1024
    height: int = 1024

    def to_cypher_props(self) -> dict[str, Any]:
        """Convert to Cypher property map."""
        return {
            "id": self.id,
            "path": self.path,
            "score": self.score,
            "created_at": self.created_at.isoformat(),
            "width": self.width,
            "height": self.height,
        }


# Schema creation queries
SCHEMA_QUERIES = [
    # Create indexes for fast lookups
    "CREATE INDEX IF NOT EXISTS FOR (m:Mood) ON (m.name)",
    "CREATE INDEX IF NOT EXISTS FOR (s:Style) ON (s.name)",
    "CREATE INDEX IF NOT EXISTS FOR (d:Decision) ON (d.id)",
    "CREATE INDEX IF NOT EXISTS FOR (d:Decision) ON (d.score)",
    "CREATE INDEX IF NOT EXISTS FOR (a:Artwork) ON (a.id)",
    "CREATE INDEX IF NOT EXISTS FOR (a:Artwork) ON (a.score)",
]

# Default mood profiles for initialization
DEFAULT_MOODS = [
    MoodNode(
        name="contemplative",
        energy_min=0.3,
        energy_max=0.5,
        typical_styles=["impressionist", "minimalist"],
        typical_colors=["deep blue", "muted grey", "soft white"],
    ),
    MoodNode(
        name="playful",
        energy_min=0.7,
        energy_max=0.9,
        typical_styles=["pop-art", "cartoon", "vibrant"],
        typical_colors=["bright yellow", "hot pink", "electric blue"],
    ),
    MoodNode(
        name="melancholic",
        energy_min=0.2,
        energy_max=0.4,
        typical_styles=["romantic", "atmospheric"],
        typical_colors=["navy", "charcoal", "dusty rose"],
    ),
    MoodNode(
        name="euphoric",
        energy_min=0.8,
        energy_max=1.0,
        typical_styles=["psychedelic", "maximalist"],
        typical_colors=["gold", "magenta", "cyan"],
    ),
    MoodNode(
        name="serene",
        energy_min=0.3,
        energy_max=0.5,
        typical_styles=["zen", "naturalist"],
        typical_colors=["sage green", "sky blue", "cream"],
    ),
    MoodNode(
        name="anxious",
        energy_min=0.6,
        energy_max=0.8,
        typical_styles=["expressionist", "glitch"],
        typical_colors=["stark white", "harsh red", "black"],
    ),
    MoodNode(
        name="nostalgic",
        energy_min=0.4,
        energy_max=0.6,
        typical_styles=["vintage", "sepia", "film-grain"],
        typical_colors=["amber", "faded brown", "soft pink"],
    ),
    MoodNode(
        name="curious",
        energy_min=0.5,
        energy_max=0.7,
        typical_styles=["surrealist", "abstract"],
        typical_colors=["purple", "teal", "coral"],
    ),
    MoodNode(
        name="rebellious",
        energy_min=0.7,
        energy_max=0.9,
        typical_styles=["punk", "graffiti", "brutalist"],
        typical_colors=["neon red", "black", "chrome"],
    ),
    MoodNode(
        name="transcendent",
        energy_min=0.5,
        energy_max=0.8,
        typical_styles=["ethereal", "cosmic", "sacred-geometry"],
        typical_colors=["iridescent", "deep purple", "starlight"],
    ),
]
