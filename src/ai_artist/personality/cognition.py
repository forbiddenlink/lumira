"""Lumira's visible thinking process - ReAct pattern for artistic decisions.

The cognition system makes Lumira's creative process transparent:
- OBSERVE: What she notices about context and environment
- REFLECT: Her thoughts and associations
- DECIDE: Her choices with reasoning
- EXPRESS: How mood colors her expression

This creates authenticity by showing the "why" behind her art.
"""

from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ThoughtType(str, Enum):
    """Types of thoughts in Lumira's thinking process."""

    OBSERVE = "observe"  # Noticing something
    REFLECT = "reflect"  # Contemplating or associating
    DECIDE = "decide"  # Making a choice
    EXPRESS = "express"  # Articulating with personality
    CREATE = "create"  # Beginning creative action


class Thought:
    """A single thought in Lumira's thinking process."""

    def __init__(
        self,
        thought_type: ThoughtType,
        content: str,
        context: dict[str, Any] | None = None,
    ):
        self.type = thought_type
        self.content = content
        self.context = context or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert thought to dictionary for storage/transmission."""
        return {
            "type": self.type.value,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp,
        }

    def format_display(self) -> str:
        """Format thought for display."""
        prefix = f"[{self.type.value.upper()}]"
        return f'{prefix} "{self.content}"'


class ThinkingProcess:
    """
    Manages Lumira's visible thinking during creative work.

    Implements the ReAct pattern (Reason + Act) for artistic decisions:
    1. Observe context (environment, mood, memories)
    2. Reflect on observations (associations, feelings)
    3. Decide on direction (with reasoning)
    4. Express intent (mood-colored articulation)
    5. Create (begin the artistic action)

    All thoughts are streamed via callbacks for real-time display.
    """

    def __init__(
        self,
        mood_system: Any | None = None,
        memory_system: Any | None = None,
        on_thought: Callable[[Thought], None] | None = None,
    ) -> None:
        """
        Initialize thinking process.

        Args:
            mood_system: Reference to MoodSystem for mood-influenced expression
            memory_system: Reference to EnhancedMemorySystem for context
            on_thought: Callback invoked for each new thought (for streaming)
        """
        self.mood_system = mood_system
        self.memory_system = memory_system
        self.on_thought = on_thought

        # Current session's thoughts
        self.thoughts: list[Thought] = []

        # Working context for current creative session
        self.working_context: dict[str, Any] = {}

        logger.info("thinking_process_initialized")

    def _emit_thought(self, thought: Thought) -> None:
        """Emit a thought to storage and callback."""
        self.thoughts.append(thought)
        logger.debug(
            "thought_emitted",
            type=thought.type.value,
            content=thought.content[:50],
        )
        if self.on_thought:
            try:
                self.on_thought(thought)
            except Exception as e:
                logger.warning("thought_callback_failed", error=str(e))

    def observe(self, context: dict[str, Any]) -> str:
        """
        Observe and narrate what Lumira notices about her context.

        Args:
            context: Dictionary with keys like:
                - time_of_day: "morning", "afternoon", "evening", "night"
                - weather: Optional weather mood hint
                - theme: Optional suggested theme
                - recent_work: Optional recent creation info

        Returns:
            The observation as a string
        """
        self.working_context.update(context)
        observations = []

        # Notice time of day
        time_of_day = context.get("time_of_day")
        if time_of_day:
            time_observations = {
                "morning": "The morning light has a fresh, expectant quality...",
                "afternoon": "The afternoon sun casts everything in warm clarity...",
                "evening": "As evening approaches, shadows grow longer and more expressive...",
                "night": "The quiet of night invites deeper contemplation...",
            }
            if time_of_day in time_observations:
                observations.append(time_observations[time_of_day])

        # Notice mood state
        if self.mood_system:
            mood = self.mood_system.current_mood.value
            energy = self.mood_system.energy_level
            energy_desc = (
                "high" if energy > 0.7 else "low" if energy < 0.3 else "moderate"
            )
            observations.append(f"I'm feeling {mood} today, with {energy_desc} energy.")

        # Notice if there's a suggested theme
        theme = context.get("theme")
        if theme:
            observations.append(f"Someone has suggested '{theme}' as inspiration...")
        else:
            observations.append(
                "No direction has been suggested - I'm free to follow my intuition."
            )

        # Notice recent work if available
        recent_work = context.get("recent_work")
        if recent_work:
            observations.append(
                f"My recent work explored {recent_work}. Should I continue that thread or seek contrast?"
            )

        # Combine into a cohesive observation
        observation = (
            " ".join(observations)
            if observations
            else "I observe my surroundings, open to inspiration..."
        )

        thought = Thought(
            thought_type=ThoughtType.OBSERVE,
            content=observation,
            context={"raw_context": context},
        )
        self._emit_thought(thought)

        return observation

    def reflect(self, topic: str) -> str:
        """
        Reflect on a topic, drawing on memory and associations.

        Args:
            topic: What Lumira is reflecting on

        Returns:
            The reflection as a string
        """
        reflections = []

        # Draw from memory if available
        if self.memory_system:
            # Get relevant context from memory
            mood = (
                self.mood_system.current_mood.value
                if self.mood_system
                else "contemplative"
            )
            memory_context = self.memory_system.get_relevant_context(mood, limit=3)

            # Check for similar past work
            similar_episodes = memory_context.get("similar_mood_episodes", [])
            if similar_episodes:
                past_subject = (
                    similar_episodes[-1]
                    .get("details", {})
                    .get("subject", "similar themes")
                )
                reflections.append(
                    f"This reminds me of when I explored {past_subject}..."
                )

            # Check learned style preferences
            best_styles = memory_context.get("best_styles", [])
            if best_styles:
                top_style = best_styles[0][0] if best_styles else None
                if top_style:
                    reflections.append(
                        f"I've found {top_style} works well for me in this mood."
                    )

        # Base reflection on topic
        reflections.append(f"Thinking about '{topic}'... what does it evoke in me?")

        # Mood-influenced reflection
        if self.mood_system:
            mood = self.mood_system.current_mood.value
            mood_reflections = {
                "contemplative": "I want to find the deeper meaning here.",
                "chaotic": "Let me embrace the wild energy this brings!",
                "melancholic": "There's a beautiful sadness I want to capture.",
                "energized": "I feel alive with possibilities!",
                "rebellious": "I want to challenge expectations with this.",
                "serene": "I seek the quiet beauty within this concept.",
                "restless": "Something is pushing me to explore further.",
                "playful": "This could be fun if I approach it with joy!",
                "introspective": "What does this reveal about my inner world?",
                "bold": "I want to make a powerful statement here.",
            }
            if mood in mood_reflections:
                reflections.append(mood_reflections[mood])

        reflection = " ".join(reflections)

        thought = Thought(
            thought_type=ThoughtType.REFLECT,
            content=reflection,
            context={"topic": topic},
        )
        self._emit_thought(thought)

        return reflection

    def decide(self, options: list[str]) -> tuple[str, str]:
        """
        Make a decision among options, providing reasoning.

        Args:
            options: List of possible choices

        Returns:
            Tuple of (chosen_option, reasoning)
        """
        if not options:
            reasoning = "With no clear options, I'll follow my intuition."
            thought = Thought(
                thought_type=ThoughtType.DECIDE,
                content=reasoning,
                context={"options": [], "choice": None},
            )
            self._emit_thought(thought)
            return ("", reasoning)

        # Decision factors
        choice = options[0]  # Default to first option
        reasons = []

        # Factor in mood alignment
        if self.mood_system:
            mood = self.mood_system.current_mood.value
            mood_preferences = {
                "contemplative": ["minimalist", "zen", "quiet", "space", "nature"],
                "chaotic": ["energy", "movement", "wild", "explosive", "abstract"],
                "melancholic": ["rain", "solitude", "twilight", "shadow", "autumn"],
                "energized": ["vibrant", "celebration", "life", "bright", "joy"],
                "rebellious": ["protest", "punk", "defiant", "bold", "challenge"],
                "serene": ["peaceful", "calm", "ocean", "harmony", "gentle"],
                "restless": ["journey", "search", "tension", "fragmented", "change"],
                "playful": ["whimsical", "fun", "colorful", "imagination", "delight"],
                "introspective": ["memory", "dream", "symbolic", "deep", "self"],
                "bold": ["power", "striking", "dramatic", "confident", "statement"],
            }
            preferences = mood_preferences.get(mood, [])

            # Find option that matches mood best
            for option in options:
                option_lower = option.lower()
                for pref in preferences:
                    if pref in option_lower:
                        choice = option
                        reasons.append(f"'{choice}' resonates with my {mood} mood")
                        break

        # Factor in novelty if we have memory
        if self.memory_system and len(options) > 1:
            recent_episodes = self.memory_system.episodic.get_recent_episodes(5)
            recent_subjects = [
                ep.get("details", {}).get("subject", "") for ep in recent_episodes
            ]

            for option in options:
                if option not in recent_subjects and choice == options[0]:
                    # Only if we haven't found a better match
                    choice = option
                    reasons.append(f"'{choice}' offers fresh territory to explore")
                    break

        if not reasons:
            reasons.append(f"I'm drawn to '{choice}' - it speaks to me right now")

        reasoning = " ".join(reasons)

        thought = Thought(
            thought_type=ThoughtType.DECIDE,
            content=f"I choose: {choice}. {reasoning}",
            context={"options": options, "choice": choice, "reasoning": reasoning},
        )
        self._emit_thought(thought)

        return (choice, reasoning)

    def express(self, intent: str) -> str:
        """
        Express an intent with mood-influenced coloring.

        Args:
            intent: The base intent to express

        Returns:
            The mood-colored expression
        """
        expression = intent

        if self.mood_system:
            mood = self.mood_system.current_mood.value
            energy = self.mood_system.energy_level

            # Add mood coloring
            mood_expressions = {
                "contemplative": f"With quiet intention, {intent.lower()}",
                "chaotic": f"With wild energy, {intent.lower()}!",
                "melancholic": f"Through a veil of wistfulness, {intent.lower()}",
                "energized": f"Bursting with excitement, {intent.lower()}!",
                "rebellious": f"Defiantly, {intent.lower()}",
                "serene": f"In peaceful clarity, {intent.lower()}",
                "restless": f"With restless urgency, {intent.lower()}",
                "playful": f"With a playful spirit, {intent.lower()}!",
                "introspective": f"From deep within, {intent.lower()}",
                "bold": f"With bold confidence, {intent.lower()}!",
            }

            if mood in mood_expressions:
                expression = mood_expressions[mood]

            # Energy modifier
            if energy > 0.8:
                expression = expression.rstrip("!.") + "!"
            elif energy < 0.2:
                expression = expression.rstrip("!.") + "..."

        thought = Thought(
            thought_type=ThoughtType.EXPRESS,
            content=expression,
            context={"original_intent": intent},
        )
        self._emit_thought(thought)

        return expression

    def begin_creation(self, concept: dict[str, Any]) -> str:
        """
        Signal the beginning of the creative act.

        Args:
            concept: The concept being created with keys like subject, style, colors

        Returns:
            A statement about beginning creation
        """
        subject = concept.get("subject", "this vision")
        style = concept.get("style", "my own style")

        statement = f"Now I begin to create... bringing {subject} to life in {style}."

        thought = Thought(
            thought_type=ThoughtType.CREATE,
            content=statement,
            context={"concept": concept},
        )
        self._emit_thought(thought)

        return statement

    def get_session_thoughts(self) -> list[dict[str, Any]]:
        """Get all thoughts from the current session."""
        return [t.to_dict() for t in self.thoughts]

    def get_thinking_narrative(self) -> str:
        """Get a formatted narrative of the thinking process."""
        return "\n".join(t.format_display() for t in self.thoughts)

    def clear_session(self) -> None:
        """Clear thoughts for a new creative session."""
        self.thoughts = []
        self.working_context = {}
        logger.debug("thinking_session_cleared")

    def store_in_memory(self) -> None:
        """Store the thinking session in memory for future reference."""
        if not self.memory_system or not self.thoughts:
            return

        # Record as an episodic memory
        self.memory_system.episodic.record_episode(
            event_type="thinking_session",
            details={
                "thoughts": self.get_session_thoughts(),
                "narrative": self.get_thinking_narrative(),
                "working_context": self.working_context,
            },
            emotional_state={
                "mood": (
                    self.mood_system.current_mood.value
                    if self.mood_system
                    else "unknown"
                ),
                "energy_level": (
                    self.mood_system.energy_level if self.mood_system else 0.5
                ),
            },
        )

        logger.info(
            "thinking_session_stored",
            thought_count=len(self.thoughts),
        )
