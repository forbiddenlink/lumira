"""Lumira's inner voices for creative deliberation.

The four voices represent different aspects of Lumira's artistic process:
- The Dreamer: Generates creative ideas, pushes boundaries
- The Critic: Evaluates quality, spots weaknesses (uses existing ArtistCritic)
- The Curator: Ensures portfolio coherence, avoids repetition
- The Rememberer: Surfaces relevant memories from graph and vector stores
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from ..memory.graph_memory import GraphMemory, MemoryContext
    from ..personality.enhanced_memory import EnhancedMemorySystem
    from ..personality.vector_memory import VectorMemory

logger = get_logger(__name__)


class Voice(str, Enum):
    """The four inner voices."""

    DREAMER = "dreamer"
    CRITIC = "critic"
    CURATOR = "curator"
    REMEMBERER = "rememberer"


@dataclass
class Concept:
    """A creative concept developed through inner dialogue."""

    subject: str
    mood_blend: dict[str, float] = field(default_factory=dict)
    style_blend: dict[str, float] = field(default_factory=dict)
    colors: list[str] = field(default_factory=list)
    prompt: str = ""
    reasoning: str = ""
    approved: bool = False
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "subject": self.subject,
            "mood_blend": self.mood_blend,
            "style_blend": self.style_blend,
            "colors": self.colors,
            "prompt": self.prompt,
            "reasoning": self.reasoning,
            "approved": self.approved,
            "confidence": self.confidence,
        }


@dataclass
class DialogueTurn:
    """A single turn in the inner dialogue."""

    voice: Voice
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "voice": self.voice.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class Dreamer:
    """The Dreamer generates creative ideas, pushing boundaries.

    This voice is imaginative, bold, and sometimes wild. It proposes
    subjects, style combinations, and mood blends that might surprise.
    """

    # Imaginative subject templates by mood
    MOOD_INSPIRATIONS = {
        "contemplative": [
            "a solitary {object} in the mist",
            "the space between {thing1} and {thing2}",
            "silence made visible",
            "the weight of an unspoken thought",
        ],
        "playful": [
            "{animal} discovering {unexpected_thing}",
            "a carnival of {abstract_concept}",
            "dancing {objects} in {unlikely_place}",
            "the joy of {simple_action}",
        ],
        "melancholic": [
            "rain on {surface}",
            "the last {thing} of {time_period}",
            "fading {memories}",
            "a letter never sent",
        ],
        "euphoric": [
            "explosion of {colors}",
            "the moment of {achievement}",
            "light breaking through {barrier}",
            "transcendent {being}",
        ],
        "serene": [
            "still water reflecting {sky_condition}",
            "{nature_element} at rest",
            "the breath between moments",
            "harmony of {elements}",
        ],
        "anxious": [
            "edges that won't align",
            "the shadow of {fear}",
            "fragments seeking wholeness",
            "tension before {event}",
        ],
        "nostalgic": [
            "{object} from {time}",
            "faded {photograph_subject}",
            "the scent of {memory_trigger}",
            "childhood {place}",
        ],
        "curious": [
            "what lies beyond {boundary}",
            "the anatomy of {abstract}",
            "intersection of {concept1} and {concept2}",
            "questions made visible",
        ],
        "rebellious": [
            "breaking {convention}",
            "{symbol} reimagined",
            "defiance of {authority}",
            "chaos claiming {order}",
        ],
        "transcendent": [
            "the universe within {small_thing}",
            "consciousness expanding",
            "boundaries dissolving",
            "infinite {pattern}",
        ],
    }

    # Words to fill in templates
    FILL_WORDS = {
        "object": ["stone", "leaf", "key", "mirror", "clock", "book", "door"],
        "thing1": ["light", "shadow", "past", "future", "silence", "sound"],
        "thing2": ["darkness", "hope", "memory", "dream", "motion", "stillness"],
        "animal": ["fox", "crow", "moth", "octopus", "owl", "butterfly"],
        "unexpected_thing": ["stars", "music", "time", "language", "color"],
        "objects": ["letters", "numbers", "clocks", "chairs", "umbrellas"],
        "unlikely_place": ["clouds", "dreams", "mathematics", "a heartbeat"],
        "abstract_concept": ["dreams", "mathematics", "music", "poetry"],
        "simple_action": ["breathing", "walking", "opening a door"],
        "surface": ["old windows", "forgotten photographs", "empty streets"],
        "thing": ["leaf", "light", "word", "song", "breath"],
        "time_period": ["autumn", "the century", "childhood", "the old world"],
        "memories": ["photographs", "letters", "songs", "faces"],
        "colors": ["gold and crimson", "azure and violet", "all spectrum"],
        "achievement": ["flight", "discovery", "reunion", "understanding"],
        "barrier": ["clouds", "doubt", "darkness", "time"],
        "being": ["dancer", "phoenix", "soul", "consciousness"],
        "sky_condition": ["sunset", "storms", "stars", "nothing"],
        "nature_element": ["water", "mountain", "forest", "desert"],
        "elements": ["earth and sky", "fire and water", "chaos and order"],
        "fear": ["tomorrow", "the unknown", "loss", "change"],
        "event": ["the storm", "dawn", "the truth", "transformation"],
        "time": ["grandmother's attic", "the old country", "1923"],
        "photograph_subject": ["summer", "faces", "places", "promises"],
        "memory_trigger": ["rain", "bread", "flowers", "old books"],
        "place": ["kitchen", "garden", "street", "window"],
        "boundary": ["the horizon", "the mirror", "the door", "sleep"],
        "abstract": ["a thought", "time", "love", "fear"],
        "concept1": ["technology", "nature", "mathematics", "emotion"],
        "concept2": ["biology", "art", "chaos", "order"],
        "convention": ["perspective", "form", "expectation", "rules"],
        "symbol": ["the flag", "the crown", "the cross", "the machine"],
        "authority": ["gravity", "time", "tradition", "logic"],
        "order": ["symmetry", "silence", "the grid", "certainty"],
        "small_thing": ["a grain of sand", "an atom", "an eye", "a seed"],
        "pattern": ["spirals", "fractals", "reflections", "echoes"],
    }

    # Unexpected style combinations
    STYLE_MASHUPS = [
        (["impressionist", "cyberpunk"], "impressionist circuitry"),
        (["zen", "glitch"], "meditative disruption"),
        (["baroque", "minimalist"], "ornate simplicity"),
        (["pop-art", "gothic"], "dark celebration"),
        (["romantic", "brutalist"], "tender concrete"),
        (["surrealist", "photorealist"], "impossible clarity"),
        (["art-nouveau", "synthwave"], "organic neon"),
        (["renaissance", "street-art"], "classical rebellion"),
    ]

    def __init__(self, temperature: float = 0.8):
        """Initialize the Dreamer.

        Args:
            temperature: Creativity level (0.0-1.0). Higher = wilder ideas.
        """
        self.temperature = temperature
        logger.info("dreamer_initialized", temperature=temperature)

    def _fill_template(self, template: str) -> str:
        """Fill in a template with random words."""
        result = template
        for key, options in self.FILL_WORDS.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, random.choice(options), 1)
        return result

    async def imagine(
        self,
        mood: str,
        context: "MemoryContext | None" = None,
        count: int = 3,
    ) -> list[Concept]:
        """Generate creative ideas based on mood and context.

        Args:
            mood: Current mood state
            context: Optional memory context for inspiration
            count: Number of ideas to generate

        Returns:
            List of Concept objects
        """
        ideas = []
        templates = self.MOOD_INSPIRATIONS.get(
            mood, self.MOOD_INSPIRATIONS["contemplative"]
        )

        # Use context to avoid repetition
        recent_subjects = []
        if context:
            recent_subjects = context.recent_subjects

        for _i in range(count):
            # Pick a template and fill it
            template = random.choice(templates)
            subject = self._fill_template(template)

            # Avoid recent subjects
            attempts = 0
            while any(recent in subject for recent in recent_subjects) and attempts < 5:
                template = random.choice(templates)
                subject = self._fill_template(template)
                attempts += 1

            # Decide on style blend
            if random.random() < self.temperature and self.STYLE_MASHUPS:
                # Wild mashup
                mashup = random.choice(self.STYLE_MASHUPS)
                style_blend = {s: 1.0 / len(mashup[0]) for s in mashup[0]}
                reasoning = f"What if we tried {mashup[1]}?"
            else:
                # Single style from context or default
                if context and context.top_styles:
                    style_name = context.top_styles[0].get("name", "impressionist")
                else:
                    style_name = random.choice(["impressionist", "atmospheric", "zen"])
                style_blend = {style_name: 1.0}
                reasoning = f"This mood calls for {style_name}..."

            # Mood blend (mostly current mood with a hint of contrast)
            mood_blend = {mood: 0.85}
            if random.random() < self.temperature:
                # Add a contrasting mood
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
                contrast = contrasts.get(mood, "serene")
                mood_blend[mood] = 0.7
                mood_blend[contrast] = 0.3
                reasoning += f" With a touch of {contrast} for tension."

            concept = Concept(
                subject=subject,
                mood_blend=mood_blend,
                style_blend=style_blend,
                reasoning=reasoning,
            )
            ideas.append(concept)

            logger.debug(
                "dreamer_imagined",
                subject=subject[:50],
                styles=list(style_blend.keys()),
            )

        return ideas

    async def refine(self, concept: Concept, feedback: str) -> Concept:
        """Refine a concept based on feedback from The Critic.

        Args:
            concept: The concept to refine
            feedback: Feedback from evaluation

        Returns:
            Refined concept
        """
        refined = Concept(
            subject=concept.subject,
            mood_blend=concept.mood_blend.copy(),
            style_blend=concept.style_blend.copy(),
            colors=concept.colors.copy(),
            reasoning=concept.reasoning,
        )

        # Parse feedback for keywords and adjust
        feedback_lower = feedback.lower()

        if "repetitive" in feedback_lower or "similar" in feedback_lower:
            # Make it more unique
            refined.subject = f"unexpected {concept.subject}"
            refined.reasoning += " Made more unique."

        if "color" in feedback_lower:
            # Adjust colors (this would use mood colors in full impl)
            refined.colors = ["deep blue", "soft gold", "muted rose"]
            refined.reasoning += " Refined the palette."

        if "bold" in feedback_lower or "stronger" in feedback_lower:
            # Increase contrast in styles
            if len(refined.style_blend) == 1:
                style = list(refined.style_blend.keys())[0]
                refined.style_blend = {style: 0.7, "dramatic": 0.3}
            refined.reasoning += " Added more dramatic tension."

        if "subtle" in feedback_lower or "gentle" in feedback_lower:
            # Soften the approach
            refined.mood_blend = {k: v * 0.8 for k, v in refined.mood_blend.items()}
            refined.mood_blend["serene"] = refined.mood_blend.get("serene", 0) + 0.2
            refined.reasoning += " Softened the approach."

        logger.debug("dreamer_refined", subject=refined.subject[:50])
        return refined


class Curator:
    """The Curator ensures portfolio coherence and variety.

    This voice considers the body of work, ensures variety without
    losing artistic identity, and filters ideas for portfolio fit.
    """

    def __init__(self, variety_weight: float = 0.6):
        """Initialize the Curator.

        Args:
            variety_weight: How much to prioritize variety (0.0-1.0)
        """
        self.variety_weight = variety_weight
        logger.info("curator_initialized", variety_weight=variety_weight)

    async def filter(
        self,
        ideas: list[Concept],
        recent_work: list[dict[str, Any]],
        portfolio_themes: list[str] | None = None,
    ) -> list[Concept]:
        """Filter and rank ideas for portfolio fit.

        Args:
            ideas: List of concepts to evaluate
            recent_work: Recent creations to check for variety
            portfolio_themes: Established themes in the portfolio

        Returns:
            Sorted list of concepts (best first)
        """
        if not ideas:
            return []

        # Extract recent subjects and styles
        recent_subjects = set()
        recent_styles = set()
        for work in recent_work[-10:]:
            if isinstance(work, dict):
                prompt = work.get("prompt", "")
                styles = work.get("styles", [])
                # Simple subject extraction (first few words)
                words = prompt.split()[:3]
                recent_subjects.update(words)
                recent_styles.update(styles)

        scored_ideas = []
        for idea in ideas:
            score = 50.0  # Base score

            # Novelty: penalize similar subjects
            subject_words = set(idea.subject.lower().split())
            overlap = len(subject_words & recent_subjects)
            novelty_score = max(0, 30 - (overlap * 10))
            score += novelty_score * self.variety_weight

            # Style variety: bonus for different styles
            idea_styles = set(idea.style_blend.keys())
            style_overlap = len(idea_styles & recent_styles)
            variety_score = (
                20 if style_overlap == 0 else max(0, 20 - (style_overlap * 8))
            )
            score += variety_score * self.variety_weight

            # Coherence: bonus for fitting portfolio themes
            if portfolio_themes:
                theme_match = any(
                    theme.lower() in idea.subject.lower() for theme in portfolio_themes
                )
                score += 15 if theme_match else 0

            # Mood alignment (prefer concepts with clear mood)
            if idea.mood_blend:
                dominant_mood_weight = max(idea.mood_blend.values())
                score += dominant_mood_weight * 10

            scored_ideas.append((score, idea))

        # Sort by score (highest first)
        scored_ideas.sort(key=lambda x: x[0], reverse=True)

        logger.debug(
            "curator_filtered",
            input_count=len(ideas),
            output_count=len(scored_ideas),
            top_score=scored_ideas[0][0] if scored_ideas else 0,
        )

        return [idea for _, idea in scored_ideas]

    def get_feedback(self, concept: Concept, recent_work: list[dict]) -> str:
        """Generate curator feedback on a concept.

        Args:
            concept: The concept to evaluate
            recent_work: Recent work for context

        Returns:
            Feedback string
        """
        feedback_parts = []

        # Check for subject repetition
        recent_subjects = [
            w.get("prompt", "").split()[:3]
            for w in recent_work[-5:]
            if isinstance(w, dict)
        ]
        recent_subjects_flat = [word for sublist in recent_subjects for word in sublist]

        subject_words = concept.subject.lower().split()
        if any(word in recent_subjects_flat for word in subject_words):
            feedback_parts.append(
                "This subject feels similar to recent work. Consider a fresh direction."
            )

        # Check style variety
        if len(concept.style_blend) == 1:
            style = list(concept.style_blend.keys())[0]
            feedback_parts.append(
                f"Using only {style} is fine, but a blend might create "
                "more interesting tension."
            )

        # Encourage if unique
        if not feedback_parts:
            feedback_parts.append(
                "This adds something fresh to the portfolio. "
                "I approve of this direction."
            )

        return " ".join(feedback_parts)


class Rememberer:
    """The Rememberer surfaces relevant memories.

    This voice connects to both graph memory (relationships, decisions)
    and vector memory (semantic similarity) to provide context.
    """

    def __init__(
        self,
        graph_memory: "GraphMemory | None" = None,
        vector_memory: "VectorMemory | None" = None,
        enhanced_memory: "EnhancedMemorySystem | None" = None,
    ):
        """Initialize the Rememberer.

        Args:
            graph_memory: FalkorDB graph memory for decisions/relationships
            vector_memory: ChromaDB vector memory for semantic search
            enhanced_memory: Existing enhanced memory system
        """
        self.graph = graph_memory
        self.vectors = vector_memory
        self.enhanced = enhanced_memory
        logger.info(
            "rememberer_initialized",
            has_graph=graph_memory is not None,
            has_vectors=vector_memory is not None,
            has_enhanced=enhanced_memory is not None,
        )

    async def recall(
        self,
        mood: str,
        theme: str | None = None,
        limit: int = 5,
    ) -> "MemoryContext":
        """Recall relevant context for creation.

        Combines graph memory (what worked for this mood) with
        vector memory (similar past work) and enhanced memory
        (episodic/semantic patterns).

        Args:
            mood: Current mood state
            theme: Optional theme to search for
            limit: Maximum items to retrieve

        Returns:
            MemoryContext with combined memories
        """
        from ..memory.graph_memory import MemoryContext

        # Initialize empty context
        top_styles: list[dict] = []
        mood_pairs: list[dict] = []
        similar_works: list[dict] = []
        recent_work: list[dict] = []
        recent_subjects: list[str] = []
        style_blends: list[dict] = []

        # Query graph memory if available
        if self.graph:
            try:
                context = await self.graph.get_context_for_creation(mood, theme)
                top_styles = context.top_styles
                mood_pairs = context.mood_pairs
                recent_work = context.recent_work
                recent_subjects = context.recent_subjects
                style_blends = context.style_blends
            except Exception as e:
                logger.warning("graph_recall_failed", error=str(e))

        # Query vector memory for similar work
        if self.vectors and theme:
            try:
                # VectorMemory.search_creations is synchronous (not async)
                similar = self.vectors.search_creations(theme, n_results=limit)
                similar_works = [
                    {
                        "id": s.get("id"),
                        "prompt": s.get("prompt"),
                        "score": s.get("score"),
                    }
                    for s in similar
                ]
            except Exception as e:
                logger.warning("vector_recall_failed", error=str(e))

        # Fallback to enhanced memory
        if self.enhanced and not top_styles:
            try:
                enhanced_context = self.enhanced.get_relevant_context(mood, limit=limit)
                best_styles = enhanced_context.get("best_styles", [])
                top_styles = [
                    {"name": s[0], "avg_score": s[1]} for s in best_styles[:limit]
                ]

                recent_episodes = enhanced_context.get("similar_mood_episodes", [])
                for ep in recent_episodes:
                    details = ep.get("details", {})
                    recent_subjects.append(details.get("subject", ""))
            except Exception as e:
                logger.warning("enhanced_recall_failed", error=str(e))

        logger.debug(
            "rememberer_recalled",
            mood=mood,
            theme=theme,
            styles_found=len(top_styles),
            similar_found=len(similar_works),
        )

        return MemoryContext(
            top_styles=top_styles,
            mood_pairs=mood_pairs,
            similar_works=similar_works,
            recent_work=recent_work,
            recent_subjects=recent_subjects,
            style_blends=style_blends,
        )

    def format_memory_message(self, context: "MemoryContext") -> str:
        """Format memory context as a spoken message.

        Args:
            context: The memory context to describe

        Returns:
            Natural language description of memories
        """
        parts = []

        if context.top_styles:
            style_names = [s.get("name", "unknown") for s in context.top_styles[:3]]
            parts.append(
                f"I recall that {', '.join(style_names)} have served me well "
                "in this mood."
            )

        if context.style_blends:
            blend = context.style_blends[0]
            parts.append(
                f"An interesting combination was {blend.get('style_a', '')} "
                f"with {blend.get('style_b', '')}..."
            )

        if context.similar_works:
            parts.append(
                f"I've explored similar territory {len(context.similar_works)} "
                "times before."
            )

        if context.recent_subjects:
            recent = context.recent_subjects[:3]
            parts.append(f"Recently I've been drawn to: {', '.join(recent)}.")

        if not parts:
            parts.append(
                "My memories offer no specific guidance here... a fresh start."
            )

        return " ".join(parts)
