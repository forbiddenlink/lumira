"""Lumira's internal critic - evaluates concepts before generation.

The critique system is what separates an artist from a random generator.
Lumira evaluates her concepts, provides feedback, and iterates before creating.
"""

import random
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ArtistCritic:
    """
    An internal critic that evaluates painting concepts before generation.

    This creates the iterative improvement loop that makes Lumira's art better:
    1. Generate concept (mood + subject + style)
    2. Critique evaluates: composition, color harmony, mood alignment, novelty
    3. If not approved, revise (max 2-3 iterations)
    4. Only then generate the actual image
    """

    # Aspects to evaluate
    CRITIQUE_ASPECTS = [
        "composition",
        "color_harmony",
        "mood_alignment",
        "technical_execution",
        "conceptual_depth",
        "novelty",
    ]

    # Strong mood-style pairings that work well together
    MOOD_STYLE_PAIRINGS = {
        "contemplative": ["minimalist", "zen", "atmospheric", "impressionist"],
        "chaotic": ["abstract expressionism", "glitch art", "splatter"],
        "melancholic": ["impressionist", "muted realism", "gothic"],
        "energized": ["pop art", "vibrant", "dynamic"],
        "rebellious": ["punk", "street art", "cyberpunk"],
        "serene": ["peaceful", "soft focus", "harmonious", "minimalist"],
        "restless": ["fragmented", "layered", "complex"],
        "playful": ["whimsical", "cartoonish", "colorful"],
        "introspective": ["symbolic", "detailed realism", "surreal"],
        "bold": ["dramatic", "high contrast", "striking"],
    }

    def __init__(self, name: str = "Inner Critic"):
        self.name = name

        # Critic personality (consistent across critiques)
        self.personality = {
            "strictness": random.uniform(0.4, 0.7),
            "technical_focus": random.uniform(0.3, 0.8),
            "risk_tolerance": random.uniform(0.4, 0.7),
        }

        logger.info(
            "critic_initialized",
            name=self.name,
            strictness=round(self.personality["strictness"], 2),
        )

    def critique_concept(
        self,
        concept: dict[str, Any],
        artist_state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Evaluate a painting concept and decide whether to approve or suggest revision.

        Args:
            concept: The painting concept with keys like:
                - subject: What to paint
                - style: Artistic style
                - colors: Color palette
                - mood: Intended mood
                - prompt: The prompt to use
            artist_state: Current artist state with keys like:
                - mood: Current mood
                - energy: Energy level (0-1)
                - recent_subjects: Recently explored subjects

        Returns:
            Dict with:
                - approved: bool
                - confidence: float (0-1)
                - critique: str (feedback text)
                - suggestions: list[str] (specific improvements)
                - analysis: dict (detailed scores)
        """
        try:
            # Analyze the concept
            analysis = self._analyze_concept(concept, artist_state)

            # Generate critique text
            critique_text = self._generate_critique(concept, artist_state, analysis)

            # Make approval decision
            decision = self._decide_approval(analysis, artist_state)

            result = {
                "critic_name": self.name,
                "approved": decision["approved"],
                "confidence": decision["confidence"],
                "critique": critique_text,
                "suggestions": decision.get("suggestions", []),
                "analysis": analysis,
            }

            logger.info(
                "concept_critiqued",
                approved=result["approved"],
                confidence=round(result["confidence"], 2),
                overall_score=round(analysis.get("overall_score", 0), 2),
            )

            return result

        except Exception as e:
            logger.error("critique_failed", error=str(e))
            # Fallback: approve with generic encouragement
            return {
                "critic_name": self.name,
                "approved": True,
                "confidence": 0.5,
                "critique": "An intriguing concept. I trust your artistic vision.",
                "suggestions": [],
                "analysis": {},
            }

    def _analyze_concept(
        self,
        concept: dict[str, Any],
        artist_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze various aspects of the painting concept."""
        analysis = {}

        # Composition score (base quality)
        analysis["composition_score"] = random.uniform(0.5, 0.9)

        # Color harmony
        colors = concept.get("colors", [])
        analysis["color_harmony"] = self._assess_color_harmony(colors)

        # Mood-style alignment
        mood = concept.get("mood", artist_state.get("mood", "contemplative"))
        style = concept.get("style", "abstract")
        analysis["mood_alignment"] = self._check_mood_style_fit(mood, style)

        # Novelty (have we done this recently?)
        recent_subjects = artist_state.get("recent_subjects", [])[-5:]
        current_subject = concept.get("subject", "")
        analysis["novelty_score"] = (
            0.8 if current_subject not in recent_subjects else 0.3
        )

        # Technical feasibility (complexity vs energy)
        complexity = concept.get("complexity", 0.5)
        energy = artist_state.get("energy", 0.5)
        analysis["technical_feasibility"] = 0.9 if complexity <= energy + 0.2 else 0.5

        # Overall score (weighted average)
        scores = [v for v in analysis.values() if isinstance(v, int | float)]
        analysis["overall_score"] = sum(scores) / len(scores) if scores else 0.7

        return analysis

    def _assess_color_harmony(self, colors: list[str]) -> float:
        """Assess how well colors work together."""
        if not colors:
            return 0.7

        # Fewer colors = more harmonious (generally)
        if len(colors) <= 3:
            return random.uniform(0.7, 0.9)
        elif len(colors) <= 5:
            return random.uniform(0.5, 0.8)
        else:
            return random.uniform(0.4, 0.7)

    def _check_mood_style_fit(self, mood: str, style: str) -> float:
        """Check if mood and style complement each other."""
        mood_lower = mood.lower()
        style_lower = style.lower()

        # Check if this is a strong pairing
        if mood_lower in self.MOOD_STYLE_PAIRINGS:
            good_styles = self.MOOD_STYLE_PAIRINGS[mood_lower]
            for good_style in good_styles:
                if good_style in style_lower:
                    return random.uniform(0.8, 1.0)

        # Default: moderate fit
        return random.uniform(0.5, 0.8)

    def _generate_critique(
        self,
        concept: dict[str, Any],
        artist_state: dict[str, Any],
        analysis: dict[str, Any],
    ) -> str:
        """Generate critique text based on analysis."""
        overall = analysis.get("overall_score", 0.7)
        novelty = analysis.get("novelty_score", 0.7)
        mood_align = analysis.get("mood_alignment", 0.7)

        # Strong concept
        if overall > 0.75:
            return (
                "This is a strong concept. The composition and color choices "
                "show maturity. I'm curious to see how it develops."
            )

        # Low novelty
        if novelty < 0.4:
            return (
                "A solid approach, though you've explored similar territory recently. "
                "Perhaps push the boundaries a bit more?"
            )

        # Poor mood alignment
        if mood_align < 0.5:
            return (
                "The style feels disconnected from your current mood. "
                "Consider whether this truly expresses what you're feeling."
            )

        # Default: encouraging but noting room for growth
        return (
            "An interesting direction. The mood and style pairing is "
            "unconventional, which could yield surprising results."
        )

    def _decide_approval(
        self,
        analysis: dict[str, Any],
        artist_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Decide whether to approve the concept or suggest revision."""
        overall_score = analysis.get("overall_score", 0.7)

        # Base threshold adjusted by strictness
        threshold = 0.5 + (self.personality["strictness"] * 0.2)

        # Decision
        approved = overall_score >= threshold

        # Confidence (how sure are we?)
        confidence = abs(overall_score - threshold) + 0.5
        confidence = min(1.0, confidence)

        result = {
            "approved": approved,
            "confidence": round(confidence, 2),
        }

        # If not approved, provide specific suggestions
        if not approved:
            suggestions = []

            if analysis.get("color_harmony", 1.0) < 0.6:
                suggestions.append("Consider simplifying the color palette")

            if analysis.get("novelty_score", 1.0) < 0.4:
                suggestions.append(
                    "This theme has been explored recently - try a fresh angle"
                )

            if analysis.get("technical_feasibility", 1.0) < 0.6:
                suggestions.append("The complexity might exceed current energy levels")

            if analysis.get("mood_alignment", 1.0) < 0.5:
                suggestions.append(
                    "The style doesn't quite match your mood - reconsider the approach"
                )

            result["suggestions"] = suggestions

        return result

    def get_personality_description(self) -> str:
        """Describe the critic's personality."""
        strictness = self.personality["strictness"]
        tech_focus = self.personality["technical_focus"]
        risk_tol = self.personality["risk_tolerance"]

        style = "demanding" if strictness > 0.6 else "encouraging"
        focus = "technically-minded" if tech_focus > 0.6 else "conceptually-focused"
        risk = "experimental" if risk_tol > 0.6 else "traditional"

        return f"A {style}, {focus} critic with {risk} tendencies"
