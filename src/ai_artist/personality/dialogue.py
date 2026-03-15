"""Inner Dialogue orchestrator for Lumira's creative deliberation.

The InnerDialogue coordinates four voices to develop creative concepts:
1. The Rememberer recalls relevant context
2. The Dreamer generates imaginative ideas
3. The Curator filters for portfolio fit
4. The Critic evaluates and may request refinement

This implements the "Reflection" agentic pattern with max 2-3 iterations.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils.logging import get_logger
from .inner_voices import Concept, Curator, DialogueTurn, Dreamer, Rememberer, Voice

if TYPE_CHECKING:
    from .critic import ArtistCritic
    from .moods import MoodSystem

logger = get_logger(__name__)


class InnerDialogue:
    """Orchestrates Lumira's inner voices for creative deliberation.

    The dialogue follows a structured pattern:
    1. Rememberer provides context from memory
    2. Dreamer proposes several creative ideas
    3. Curator filters ideas for portfolio fit
    4. Critic evaluates the top choice
    5. If not approved, Dreamer refines (max 2 iterations)

    All turns are broadcast via callback for real-time UI updates.
    """

    MAX_ITERATIONS = 2

    def __init__(
        self,
        dreamer: Dreamer | None = None,
        critic: "ArtistCritic | None" = None,
        curator: Curator | None = None,
        rememberer: Rememberer | None = None,
        mood_system: "MoodSystem | None" = None,
        on_turn: Callable[[DialogueTurn], Awaitable[None] | None] | None = None,
    ):
        """Initialize the inner dialogue.

        Args:
            dreamer: The Dreamer voice for generating ideas
            critic: The Critic voice for evaluation (existing ArtistCritic)
            curator: The Curator voice for portfolio coherence
            rememberer: The Rememberer voice for memory retrieval
            mood_system: Reference to mood system for state
            on_turn: Async callback for each dialogue turn
        """
        self.dreamer = dreamer or Dreamer()
        self.critic = critic
        self.curator = curator or Curator()
        self.rememberer = rememberer or Rememberer()
        self.mood_system = mood_system
        self.on_turn = on_turn

        # Dialogue history for current session
        self.history: list[DialogueTurn] = []

        logger.info("inner_dialogue_initialized")

    async def _broadcast(
        self,
        voice: Voice,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast a dialogue turn.

        Args:
            voice: Which voice is speaking
            message: What they're saying
            metadata: Optional additional data
        """
        turn = DialogueTurn(
            voice=voice,
            message=message,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )
        self.history.append(turn)

        logger.debug(
            "dialogue_turn",
            voice=voice.value,
            message=message[:100],
        )

        if self.on_turn:
            try:
                result = self.on_turn(turn)
                if result is not None:
                    await result
            except Exception as e:
                logger.warning("dialogue_broadcast_failed", error=str(e))

    async def deliberate(
        self,
        theme: str | None = None,
        mood: str | None = None,
    ) -> Concept:
        """Run the full inner dialogue to develop a concept.

        Args:
            theme: Optional theme suggestion
            mood: Current mood (uses mood_system if not provided)

        Returns:
            The approved concept after deliberation
        """
        # Determine current mood
        if mood is None and self.mood_system:
            mood = self.mood_system.current_mood.value
        mood = mood or "contemplative"

        logger.info("dialogue_started", mood=mood, theme=theme)

        # Clear history for new session
        self.history = []

        # 1. The Rememberer provides context
        context = await self.rememberer.recall(mood=mood, theme=theme)
        memory_message = self.rememberer.format_memory_message(context)
        await self._broadcast(
            Voice.REMEMBERER,
            memory_message,
            metadata={"styles": context.top_styles[:3]},
        )

        # 2. The Dreamer proposes ideas
        ideas = await self.dreamer.imagine(mood=mood, context=context, count=3)
        if not ideas:
            # Fallback concept
            ideas = [
                Concept(
                    subject="abstract emotions",
                    mood_blend={mood: 1.0},
                    style_blend={"atmospheric": 1.0},
                    reasoning="When inspiration fails, I return to pure feeling.",
                )
            ]

        dreamer_message = self._format_dreamer_ideas(ideas)
        await self._broadcast(
            Voice.DREAMER,
            dreamer_message,
            metadata={"ideas": [i.subject for i in ideas]},
        )

        # 3. The Curator filters for portfolio fit
        filtered = await self.curator.filter(
            ideas=ideas,
            recent_work=context.recent_work,
        )
        top_choice = filtered[0]

        curator_feedback = self.curator.get_feedback(top_choice, context.recent_work)
        await self._broadcast(
            Voice.CURATOR,
            f"Considering '{top_choice.subject}'... {curator_feedback}",
            metadata={"selected": top_choice.subject},
        )

        # 4. The Critic evaluates (with refinement loop)
        concept = top_choice
        for iteration in range(self.MAX_ITERATIONS):
            evaluation = await self._evaluate_concept(concept, mood)

            await self._broadcast(
                Voice.CRITIC,
                evaluation["critique"],
                metadata={
                    "approved": evaluation["approved"],
                    "confidence": evaluation["confidence"],
                    "iteration": iteration + 1,
                },
            )

            if evaluation["approved"]:
                concept.approved = True
                concept.confidence = evaluation["confidence"]
                break

            # Dreamer refines based on feedback
            if iteration < self.MAX_ITERATIONS - 1:
                concept = await self.dreamer.refine(concept, evaluation["critique"])
                await self._broadcast(
                    Voice.DREAMER,
                    f"Let me reconsider... What about '{concept.subject}'?",
                    metadata={"refined_subject": concept.subject},
                )

        # If not approved after iterations, approve anyway with lower confidence
        if not concept.approved:
            concept.approved = True
            concept.confidence = 0.5
            logger.info("dialogue_forced_approval", subject=concept.subject)

        # Build the final prompt
        concept.prompt = self._build_prompt(concept, mood)

        logger.info(
            "dialogue_completed",
            subject=concept.subject,
            confidence=concept.confidence,
            iterations=len([t for t in self.history if t.voice == Voice.CRITIC]),
        )

        return concept

    async def _evaluate_concept(
        self,
        concept: Concept,
        mood: str,
    ) -> dict[str, Any]:
        """Evaluate a concept using The Critic.

        Args:
            concept: The concept to evaluate
            mood: Current mood state

        Returns:
            Evaluation result dict
        """
        if not self.critic:
            # No critic available, auto-approve
            return {
                "approved": True,
                "confidence": 0.7,
                "critique": "Without my critical voice, I trust my intuition.",
                "suggestions": [],
            }

        # Build concept dict for critic
        concept_dict = {
            "subject": concept.subject,
            "style": list(concept.style_blend.keys())[0] if concept.style_blend else "",
            "styles": list(concept.style_blend.keys()),
            "colors": concept.colors,
            "mood": mood,
            "prompt": concept.subject,  # Simplified
        }

        # Build artist state
        artist_state = {
            "mood": mood,
            "energy": 0.5,  # Could get from mood_system
            "recent_subjects": [],
        }

        if self.mood_system:
            artist_state["energy"] = self.mood_system.energy_level

        # Get critique
        result = self.critic.critique_concept(concept_dict, artist_state)

        return {
            "approved": result.get("approved", False),
            "confidence": result.get("confidence", 0.5),
            "critique": result.get("critique", ""),
            "suggestions": result.get("suggestions", []),
        }

    def _format_dreamer_ideas(self, ideas: list[Concept]) -> str:
        """Format dreamer's ideas as a spoken message.

        Args:
            ideas: List of concepts

        Returns:
            Natural language description
        """
        if len(ideas) == 1:
            return f"What if we explored '{ideas[0].subject}'? {ideas[0].reasoning}"

        parts = ["Several visions come to me..."]
        for i, idea in enumerate(ideas[:3]):
            if i == 0:
                parts.append(f"Perhaps '{idea.subject}'?")
            elif i == 1:
                parts.append(f"Or maybe '{idea.subject}'...")
            else:
                parts.append(f"Even '{idea.subject}' calls to me.")

        return " ".join(parts)

    def _build_prompt(self, concept: Concept, mood: str) -> str:
        """Build the generation prompt from a concept.

        Args:
            concept: The approved concept
            mood: Current mood

        Returns:
            Generation prompt string
        """
        parts = [concept.subject]

        # Add style descriptors
        if concept.style_blend:
            styles = list(concept.style_blend.keys())
            if len(styles) == 1:
                parts.append(f"in {styles[0]} style")
            else:
                parts.append(f"blending {' and '.join(styles)}")

        # Add color palette if specified
        if concept.colors:
            parts.append(f"with {', '.join(concept.colors[:3])} colors")

        # Add mood atmosphere
        mood_atmospheres = {
            "contemplative": "quiet, thoughtful atmosphere",
            "playful": "joyful, whimsical energy",
            "melancholic": "wistful, nostalgic feeling",
            "euphoric": "transcendent, luminous quality",
            "serene": "peaceful, harmonious ambiance",
            "anxious": "tense, unsettling edge",
            "nostalgic": "warm, faded memory quality",
            "curious": "mysterious, intriguing presence",
            "rebellious": "bold, defiant spirit",
            "transcendent": "ethereal, cosmic dimension",
        }
        atmosphere = mood_atmospheres.get(mood, "atmospheric quality")
        parts.append(f"with {atmosphere}")

        return ", ".join(parts)

    def get_dialogue_narrative(self) -> str:
        """Get a formatted narrative of the dialogue.

        Returns:
            Human-readable dialogue transcript
        """
        lines = []
        for turn in self.history:
            voice_name = turn.voice.value.title()
            lines.append(f"[{voice_name}] {turn.message}")
        return "\n".join(lines)

    def get_dialogue_history(self) -> list[dict[str, Any]]:
        """Get dialogue history as list of dicts.

        Returns:
            List of turn dictionaries
        """
        return [turn.to_dict() for turn in self.history]

    def clear_history(self) -> None:
        """Clear dialogue history for new session."""
        self.history = []
