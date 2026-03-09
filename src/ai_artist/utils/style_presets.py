"""
Style Presets System - inspired by AUTOMATIC1111 and InvokeAI.

Allows saving and loading reusable style presets with positive/negative prompts.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class StylePreset:
    """A reusable style preset with prompts and metadata."""

    name: str
    positive: str  # Prompt additions
    negative: str = ""  # Negative prompt additions
    description: str = ""
    category: str = "general"  # art, photography, abstract, etc.
    tags: list[str] | None = None
    mood_affinity: list[str] | None = None  # Moods this style works well with

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.mood_affinity is None:
            self.mood_affinity = []

    def apply_to_prompt(self, base_prompt: str) -> str:
        """
        Apply style to a base prompt.

        The style's positive prompt can use {prompt} placeholder,
        otherwise it's appended with a comma.
        """
        if "{prompt}" in self.positive:
            return self.positive.replace("{prompt}", base_prompt)
        else:
            parts = [p.strip() for p in [base_prompt, self.positive] if p.strip()]
            return ", ".join(parts)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StylePreset":
        """Create from dictionary."""
        return cls(**data)


class StylePresetsManager:
    """Manage style presets - load, save, and apply."""

    def __init__(self, presets_file: Path | None = None):
        """
        Initialize style presets manager.

        Args:
            presets_file: Path to JSON file with presets (default: config/style_presets.json)
        """
        self.presets_file = presets_file or Path("config/style_presets.json")
        self.presets: dict[str, StylePreset] = {}

        # Load presets if file exists
        if self.presets_file.exists():
            self.load()
        else:
            # Create with defaults
            self._create_default_presets()
            self.save()

    def _create_default_presets(self):
        """Create default style presets inspired by popular styles."""
        default_presets = [
            StylePreset(
                name="Cinematic",
                positive="cinematic lighting, dramatic shadows, film grain, depth of field, bokeh",
                negative="flat lighting, overexposed, amateur",
                description="Movie-like quality with dramatic lighting",
                category="photography",
                tags=["dramatic", "professional", "film"],
            ),
            StylePreset(
                name="Dreamy",
                positive="soft focus, ethereal, pastel colors, dreamlike atmosphere, gentle lighting",
                negative="harsh, realistic, sharp details",
                description="Soft and dreamlike aesthetic",
                category="art",
                tags=["soft", "fantasy", "atmospheric"],
            ),
            StylePreset(
                name="Vibrant",
                positive="vibrant colors, high saturation, bold contrasts, energetic, vivid",
                negative="muted, desaturated, dull, washed out",
                description="Bold and colorful",
                category="art",
                tags=["colorful", "bold", "energetic"],
            ),
            StylePreset(
                name="Minimalist",
                positive="minimalist, clean composition, negative space, simple, elegant",
                negative="cluttered, busy, complex, ornate",
                description="Clean and simple aesthetic",
                category="art",
                tags=["simple", "clean", "modern"],
            ),
            StylePreset(
                name="Oil Painting",
                positive="oil painting, brushstrokes visible, canvas texture, {prompt}, masterpiece",
                negative="digital art, photography, 3d render, smooth",
                description="Traditional oil painting style",
                category="art",
                tags=["traditional", "painting", "classic"],
            ),
            StylePreset(
                name="Studio Portrait",
                positive="professional studio lighting, soft box lighting, {prompt}, high resolution, detailed",
                negative="amateur, poorly lit, blurry, distorted",
                description="Professional portrait photography",
                category="photography",
                tags=["portrait", "professional", "studio"],
            ),
            StylePreset(
                name="Watercolor",
                positive="watercolor painting, soft blends, flowing colors, translucent, {prompt}",
                negative="digital, sharp edges, opaque, photographic",
                description="Soft watercolor painting style",
                category="art",
                tags=["painting", "traditional", "soft"],
            ),
            StylePreset(
                name="Dark Moody",
                positive="dark atmosphere, moody lighting, dramatic shadows, cinematic, {prompt}",
                negative="bright, cheerful, flat lighting, overexposed",
                description="Dark and atmospheric mood",
                category="photography",
                tags=["dark", "atmospheric", "dramatic"],
            ),
            StylePreset(
                name="Anime",
                positive="anime style, cel shaded, vibrant colors, {prompt}, detailed",
                negative="realistic, photographic, western cartoon, 3d",
                description="Japanese anime art style",
                category="art",
                tags=["anime", "illustration", "stylized"],
            ),
            StylePreset(
                name="Retro Vintage",
                positive="retro, vintage aesthetic, faded colors, film grain, 1970s, nostalgic",
                negative="modern, digital, crisp, high tech",
                description="Vintage 70s aesthetic",
                category="photography",
                tags=["vintage", "retro", "nostalgic"],
            ),
        ]

        for preset in default_presets:
            self.presets[preset.name] = preset

    def load(self):
        """Load presets from JSON file."""
        try:
            with open(self.presets_file) as f:
                data = json.load(f)

            self.presets = {
                name: StylePreset.from_dict(preset_data)
                for name, preset_data in data.items()
            }

            logger.info(
                "style_presets_loaded",
                count=len(self.presets),
                file=str(self.presets_file),
            )
        except Exception as e:
            logger.error("style_presets_load_failed", error=str(e))
            self.presets = {}

    def save(self):
        """Save presets to JSON file."""
        try:
            # Ensure directory exists
            self.presets_file.parent.mkdir(parents=True, exist_ok=True)

            data = {name: preset.to_dict() for name, preset in self.presets.items()}

            with open(self.presets_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(
                "style_presets_saved",
                count=len(self.presets),
                file=str(self.presets_file),
            )
        except Exception as e:
            logger.error("style_presets_save_failed", error=str(e))

    def add_preset(self, preset: StylePreset, overwrite: bool = False):
        """Add a new preset."""
        if preset.name in self.presets and not overwrite:
            raise ValueError(
                f"Preset '{preset.name}' already exists. Use overwrite=True to replace."
            )

        self.presets[preset.name] = preset
        self.save()
        logger.info("style_preset_added", name=preset.name)

    def get_preset(self, name: str) -> StylePreset | None:
        """Get a preset by name."""
        return self.presets.get(name)

    def list_presets(self, category: str | None = None) -> list[StylePreset]:
        """List all presets, optionally filtered by category."""
        presets = list(self.presets.values())

        if category:
            presets = [p for p in presets if p.category == category]

        return sorted(presets, key=lambda p: p.name)

    def list_categories(self) -> list[str]:
        """Get all unique categories."""
        categories = {preset.category for preset in self.presets.values()}
        return sorted(categories)

    def get_presets_for_mood(self, mood: str, limit: int = 5) -> list[StylePreset]:
        """Get presets that have affinity for a specific mood.

        Args:
            mood: The mood to match (e.g., 'contemplative', 'chaotic')
            limit: Maximum number of presets to return

        Returns:
            List of StylePresets with matching mood affinity
        """
        mood_lower = mood.lower()
        matching = []

        for preset in self.presets.values():
            if preset.mood_affinity:
                # Check if mood matches any affinity
                for affinity in preset.mood_affinity:
                    if mood_lower in affinity.lower() or affinity.lower() in mood_lower:
                        matching.append(preset)
                        break

        # Sort by how early the mood appears in the affinity list (stronger match first)
        def sort_key(p: StylePreset) -> int:
            if not p.mood_affinity:
                return 999
            for i, aff in enumerate(p.mood_affinity):
                if mood_lower in aff.lower() or aff.lower() in mood_lower:
                    return i
            return 999

        matching.sort(key=sort_key)
        return matching[:limit]

    def suggest_style_for_mood(self, mood: str) -> StylePreset | None:
        """Suggest a single style that best matches the given mood.

        Args:
            mood: The current mood

        Returns:
            Best matching StylePreset or None
        """
        presets = self.get_presets_for_mood(mood, limit=1)
        return presets[0] if presets else None

    def delete_preset(self, name: str):
        """Delete a preset."""
        if name in self.presets:
            del self.presets[name]
            self.save()
            logger.info("style_preset_deleted", name=name)
        else:
            logger.warning("style_preset_not_found", name=name)

    def apply_preset(self, preset_name: str, base_prompt: str) -> tuple[str, str]:
        """
        Apply a preset to a base prompt.

        Returns:
            Tuple of (modified_positive_prompt, negative_prompt)
        """
        preset = self.get_preset(preset_name)

        if not preset:
            logger.warning("style_preset_not_found", name=preset_name)
            return base_prompt, ""

        positive = preset.apply_to_prompt(base_prompt)
        negative = preset.negative

        logger.debug(
            "style_preset_applied",
            preset=preset_name,
            original=base_prompt,
            modified=positive,
        )

        return positive, negative


# Example usage
if __name__ == "__main__":
    manager = StylePresetsManager(Path("test_presets.json"))

    # List all presets
    print("Available presets:")
    for preset in manager.list_presets():
        print(f"  - {preset.name} ({preset.category}): {preset.description}")

    # Apply a preset
    base_prompt = "portrait of a woman"
    positive, negative = manager.apply_preset("Cinematic", base_prompt)
    print(f"\nBase: {base_prompt}")
    print("With 'Cinematic' style:")
    print(f"  Positive: {positive}")
    print(f"  Negative: {negative}")
