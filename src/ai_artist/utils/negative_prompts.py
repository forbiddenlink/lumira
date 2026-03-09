"""Negative prompt library for enhanced image quality.

Provides mood-aware and context-specific negative prompts to improve
generation quality and consistency.
"""

import json
from pathlib import Path
from typing import Any

from .logging import get_logger

logger = get_logger(__name__)


class NegativePromptLibrary:
    """Library of negative prompts organized by context and mood.

    Provides intelligent negative prompt composition based on:
    - Universal quality issues
    - Subject-specific problems
    - Style-specific artifacts
    - Mood-appropriate exclusions
    """

    def __init__(
        self,
        config_path: Path | str = Path("config/negative_prompts.json"),
    ):
        self.config_path = Path(config_path)
        self._prompts: dict[str, Any] = {}
        self._load_library()

    def _load_library(self) -> None:
        """Load negative prompts from configuration file."""
        if not self.config_path.exists():
            logger.warning(
                "negative_prompts_not_found",
                path=str(self.config_path),
            )
            self._prompts = self._get_defaults()
            return

        try:
            with open(self.config_path, encoding="utf-8") as f:
                self._prompts = json.load(f)
            logger.info(
                "negative_prompts_loaded",
                categories=len(self._prompts),
            )
        except Exception as e:
            logger.error("negative_prompts_load_failed", error=str(e))
            self._prompts = self._get_defaults()

    def _get_defaults(self) -> dict[str, Any]:
        """Return default negative prompts if config not found."""
        return {
            "universal": {
                "quality": "blurry, low quality, low resolution, pixelated, jpeg artifacts",
                "anatomy": "bad anatomy, deformed, disfigured, mutation, extra limbs",
                "composition": "cropped, out of frame, watermark, signature, text",
            }
        }

    def get_universal(self) -> str:
        """Get all universal negative prompts combined."""
        universal = self._prompts.get("universal", {})
        parts = [v for v in universal.values() if isinstance(v, str)]
        return ", ".join(parts)

    def get_for_mood(self, mood: str) -> str:
        """Get negative prompts appropriate for a specific mood.

        Args:
            mood: The current mood (contemplative, chaotic, etc.)

        Returns:
            Mood-specific negative prompt additions
        """
        mood_specific = self._prompts.get("mood_specific", {})
        mood_lower = mood.lower()
        return mood_specific.get(mood_lower, "")

    def get_for_subject(self, subject: str) -> str:
        """Get negative prompts for specific subject types.

        Args:
            subject: Subject type (animals, architecture, etc.)

        Returns:
            Subject-specific negative prompts
        """
        by_subject = self._prompts.get("by_subject", {})

        # Check for matching subject keywords
        subject_lower = subject.lower()
        for key, prompts in by_subject.items():
            if key in subject_lower or subject_lower in key:
                return prompts
        return ""

    def get_for_style(self, style: str) -> str:
        """Get negative prompts for specific art styles.

        Args:
            style: Art style (anime, realistic, etc.)

        Returns:
            Style-specific negative prompts
        """
        style_specific = self._prompts.get("style_specific", {})
        style_lower = style.lower()

        for key, prompts in style_specific.items():
            if key in style_lower or style_lower in key:
                return prompts
        return ""

    def get_for_category(self, category: str) -> str:
        """Get negative prompts for a content category.

        Args:
            category: Category like 'portrait', 'landscape', 'digital_art'

        Returns:
            Category-specific negative prompts
        """
        category_data = self._prompts.get(category, {})
        if isinstance(category_data, dict):
            return category_data.get("base", "")
        return ""

    def compose(
        self,
        base_negative: str = "",
        mood: str | None = None,
        style: str | None = None,
        subject: str | None = None,
        category: str | None = None,
        include_universal: bool = True,
    ) -> str:
        """Compose a comprehensive negative prompt from multiple sources.

        Args:
            base_negative: Base negative prompt to start with
            mood: Current mood for mood-specific exclusions
            style: Art style for style-specific exclusions
            subject: Subject type for subject-specific exclusions
            category: Content category (portrait, landscape, etc.)
            include_universal: Whether to include universal quality negatives

        Returns:
            Composed negative prompt string
        """
        parts: list[str] = []

        # Start with base if provided
        if base_negative:
            parts.append(base_negative)

        # Add universal quality negatives
        if include_universal:
            universal = self.get_universal()
            if universal:
                parts.append(universal)

        # Add mood-specific negatives
        if mood:
            mood_negative = self.get_for_mood(mood)
            if mood_negative:
                parts.append(mood_negative)

        # Add style-specific negatives
        if style:
            style_negative = self.get_for_style(style)
            if style_negative:
                parts.append(style_negative)

        # Add subject-specific negatives
        if subject:
            subject_negative = self.get_for_subject(subject)
            if subject_negative:
                parts.append(subject_negative)

        # Add category negatives
        if category:
            category_negative = self.get_for_category(category)
            if category_negative:
                parts.append(category_negative)

        # Combine and deduplicate
        combined = ", ".join(filter(None, parts))

        # Remove duplicate terms
        terms = [term.strip() for term in combined.split(",")]
        seen: set[str] = set()
        unique_terms: list[str] = []
        for term in terms:
            term_lower = term.lower()
            if term_lower and term_lower not in seen:
                seen.add(term_lower)
                unique_terms.append(term)

        return ", ".join(unique_terms)

    def reload(self) -> None:
        """Reload the library from disk."""
        self._load_library()


# Singleton instance
_library: NegativePromptLibrary | None = None


def get_negative_prompt_library() -> NegativePromptLibrary:
    """Get the singleton NegativePromptLibrary instance."""
    global _library
    if _library is None:
        _library = NegativePromptLibrary()
    return _library
