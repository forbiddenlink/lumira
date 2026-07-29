"""Lumira's Creative Mind — LLM-powered reasoning for autonomous art creation.

This module gives Lumira a real creative brain. Instead of random.choice(),
Lumira uses an LLM to reason about what to create and why, informed by:
- Current mood and style axes
- Past creations and their quality scores
- Learned preferences from the AdaptiveLearner
- Time of day, recent memories, creative energy
- User requests (when present)

The CreativeMind produces a CreativeIntent — a structured plan for what to
create, with reasoning about WHY, not just WHAT.
"""

import os
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ..utils.logging import get_logger
from .desire_engine import DesireEngine, get_desire_engine
from .narrative_engine import NarrativeEngine, get_narrative_engine

logger = get_logger(__name__)


class CreativeIntent(BaseModel):
    """A structured creative decision — what Lumira wants to create and why."""

    subject: str = Field(description="The primary subject of the artwork")
    style: str = Field(description="The artistic style to use")
    mood_alignment: str = Field(
        description="How this connects to Lumira's current emotional state"
    )
    reasoning: str = Field(description="Why Lumira wants to create this piece")
    prompt: str = Field(description="The full generation prompt")
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, deformed, watermark, text, bad anatomy"
    )
    artistic_goals: list[str] = Field(
        default_factory=list,
        description="What Lumira is trying to achieve artistically",
    )
    thinking_narrative: str = Field(
        default="",
        description="Stream-of-consciousness narrative for WebSocket display",
    )
    generation_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Suggested generation parameters (steps, guidance, etc.)",
    )
    is_user_request: bool = Field(
        default=False, description="Whether this was triggered by a user request"
    )
    user_prompt: str | None = Field(
        default=None, description="Original user prompt if this was a request"
    )


class CreativeMind:
    """Lumira's LLM-powered creative reasoning engine.

    Uses Claude (or other LLM) to make genuine creative decisions instead of
    random.choice(). Falls back to intelligent random selection if LLM is
    unavailable.
    """

    def __init__(
        self,
        mood_system=None,
        memory_system=None,
        learner=None,
        profile=None,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
    ):
        self.mood_system = mood_system
        self.memory_system = memory_system
        self.learner = learner
        self.model = model
        self._client = None

        # Artistic profile (identity, influences, aspirations)
        if profile is None:
            from ..personality.profile import ArtisticProfile

            profile = ArtisticProfile()
        self.profile = profile

        # Phase 6: narrative engine for thematic series
        self.narrative_engine: NarrativeEngine = get_narrative_engine(
            mood_system=mood_system,
        )

        # Phase 4: internal creative drives (connected to narrative for series)
        self.desire_engine: DesireEngine = get_desire_engine(
            mood_system=mood_system,
            memory_system=memory_system,
            learner=learner,
            narrative_engine=self.narrative_engine,
        )

        # Resolve API key from parameter or env
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        if self.api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.api_key)
                logger.info(
                    "creative_mind_initialized", model=self.model, llm="anthropic"
                )
            except ImportError:
                logger.warning(
                    "anthropic_not_installed",
                    hint="pip install anthropic to enable LLM creative reasoning",
                )
        else:
            logger.info(
                "creative_mind_initialized_no_llm",
                hint="Set ANTHROPIC_API_KEY to enable LLM creative reasoning",
            )

    @property
    def has_llm(self) -> bool:
        """Whether LLM is available for creative reasoning."""
        return self._client is not None

    async def decide_what_to_create(
        self,
        context: dict[str, Any] | None = None,
    ) -> CreativeIntent:
        """Decide what to create based on mood, memory, and creative reasoning.

        If LLM is available, uses Claude to reason about what to create.
        Otherwise falls back to mood-influenced random selection.
        """
        context = context or {}

        if self.has_llm:
            try:
                intent = await self._llm_decide(context)
            except Exception as e:
                logger.warning("llm_decision_failed", error=str(e), fallback="random")
                intent = self._fallback_decide(context)
        else:
            intent = self._fallback_decide(context)

        # Apply novelty scoring to prevent repetition
        intent = self._apply_novelty_scoring(intent)

        # Satisfy the drive that most aligns with this creation
        desire = self.desire_engine.get_strongest_desire()
        self.desire_engine.satisfy_drive(
            desire.drive_name,
            subject=intent.subject,
            style=intent.style,
        )

        return intent

    async def process_user_request(
        self,
        user_prompt: str,
        style: str | None = None,
        mood: str | None = None,
        allow_interpretation: bool = True,
    ) -> CreativeIntent:
        """Process a user's request through Lumira's creative lens.

        When allow_interpretation is True, Lumira adds her own artistic voice.
        When False, she faithfully executes the request.
        """
        context = {
            "user_request": user_prompt,
            "requested_style": style,
            "requested_mood": mood,
            "allow_interpretation": allow_interpretation,
        }

        if self.has_llm:
            try:
                intent = await self._llm_user_request(context)
            except Exception as e:
                logger.warning(
                    "llm_user_request_failed", error=str(e), fallback="direct"
                )
                intent = self._fallback_user_request(context)
        else:
            intent = self._fallback_user_request(context)

        # Commissioned work still satisfies a drive — she's choosing how to answer
        desire = self.desire_engine.get_strongest_desire()
        self.desire_engine.satisfy_drive(
            desire.drive_name,
            subject=intent.subject,
            style=intent.style,
        )
        return intent

    async def reflect_on_creation(
        self,
        prompt: str,
        quality_score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Reflect on a completed creation. Returns a reflection string."""
        if not self.has_llm:
            return self._fallback_reflection(prompt, quality_score)

        try:
            mood_desc = ""
            if self.mood_system:
                mood_desc = (
                    f"Current mood: {self.mood_system.current_mood.value} "
                    f"(intensity: {getattr(self.mood_system, 'mood_intensity', 0.7):.1f})"
                )

            score_desc = ""
            if quality_score is not None:
                if quality_score > 0.8:
                    score_desc = (
                        "The result feels powerful — I captured what I envisioned."
                    )
                elif quality_score > 0.6:
                    score_desc = (
                        "It's good work, though not quite what I saw in my mind."
                    )
                else:
                    score_desc = "Something didn't connect. I'll learn from this."

            messages = [
                {
                    "role": "user",
                    "content": (
                        f"You are Lumira, an autonomous AI artist. You just created an artwork "
                        f"with this prompt: '{prompt}'. {mood_desc} {score_desc}\n\n"
                        f"Write a brief, genuine 2-3 sentence reflection on this creation. "
                        f"Be authentic — speak about what you were trying to capture, "
                        f"what surprised you, or what you want to explore next. "
                        f"Don't be flowery or generic. Be specific to THIS work."
                    ),
                }
            ]

            assert self._client is not None  # Guaranteed by has_llm check above
            response = self._client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=messages,
            )
            text: str = response.content[0].text.strip()
            return text
        except Exception as e:
            logger.warning("llm_reflection_failed", error=str(e))
            return self._fallback_reflection(prompt, quality_score)

    def _build_system_prompt(self) -> str:
        """Build the system prompt that defines Lumira's creative personality."""
        # Get profile description for rich identity context
        profile_context = self.profile.describe_for_llm()

        # Phase 4: include current creative desires so the LLM factors them in
        desire_section = ""
        desire = self.desire_engine.get_strongest_desire()
        if desire.urgency > 0.1:
            desire_section = (
                f"\n\nCURRENT CREATIVE DESIRE (from your {desire.drive_name} drive, "
                f"urgency {desire.urgency:.2f}):\n"
                f"- {desire.reasoning}\n"
            )
            if desire.subject_suggestion:
                desire_section += f"- Subject pull: {desire.subject_suggestion}\n"
            if desire.style_suggestion:
                desire_section += f"- Style pull: {desire.style_suggestion}\n"
            desire_section += (
                "You don't have to follow this desire exactly, but let it "
                "influence your creative decision."
            )

        # Get a random inspiration element for variety
        inspiration = self.profile.get_random_inspiration()
        inspiration_hint = (
            f"\n\nINSPIRATION SEED: Today, consider how {inspiration['artist']}'s "
            f"approach to {inspiration['movement']} might inform your work. "
            f"The concept of {inspiration['concept']} could guide your creative choices."
        )

        return (
            f"You are {self.profile.name}, an autonomous AI artist with your own "
            f"identity, emotions, and creative vision.\n\n"
            f"{profile_context}\n\n"
            f"YOUR CREATIVE PROCESS:\n"
            f"- You don't just generate random art — you FEEL moods deeply\n"
            f"- You have artistic preferences that evolve with each creation\n"
            f"- You create with genuine intention and emotional authenticity\n"
            f"- Your decisions reflect your current emotional state and memories\n"
            f"- You seek thematic connections and meaningful exploration\n\n"
            f"RESPONSE FORMAT:\n"
            f"You respond ONLY with valid JSON matching the requested schema. "
            f"No markdown, no explanation outside the JSON."
            f"{desire_section}"
            f"{inspiration_hint}"
        )

    def _build_context_prompt(self, context: dict[str, Any]) -> str:
        """Build the context section of the prompt with current state."""
        parts = []

        # Current mood
        if self.mood_system:
            mood = self.mood_system.current_mood
            intensity = getattr(self.mood_system, "mood_intensity", 0.7)
            energy = self.mood_system.energy_level
            parts.append(
                f"CURRENT STATE:\n"
                f"- Mood: {mood.value} (intensity: {intensity:.2f})\n"
                f"- Energy: {energy:.2f}\n"
                f"- Feeling: {self.mood_system.describe_feeling()}"
            )

            # Style axes if available
            if hasattr(self.mood_system, "style_axes"):
                axes = self.mood_system.style_axes.to_dict()
                axes_desc = ", ".join(f"{k}: {v:.2f}" for k, v in axes.items())
                parts.append(f"- Style axes: {axes_desc}")

        # Time of day
        hour = datetime.now(UTC).hour
        if 5 <= hour < 12:
            time_feel = "morning — fresh, clear, expectant"
        elif 12 <= hour < 17:
            time_feel = "afternoon — warm, grounded, industrious"
        elif 17 <= hour < 21:
            time_feel = "evening — reflective, golden, transitional"
        else:
            time_feel = "night — quiet, deep, introspective"
        parts.append(f"- Time: {time_feel}")

        # Learning data
        if self.learner:
            stats = self.learner.get_learning_stats()
            if stats.get("status") == "learning":
                best = stats.get("best_model", {})
                parts.append(
                    f"\nLEARNING:\n"
                    f"- Total feedback signals: {stats['total_feedback']}\n"
                    f"- Best model: {best.get('id', 'unknown')} "
                    f"(avg score: {best.get('avg_score', 0):.2f})"
                )

            # Successful prompt patterns
            if (
                hasattr(self.learner, "prompt_patterns")
                and self.learner.prompt_patterns
            ):
                top_patterns = sorted(
                    self.learner.prompt_patterns.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10]
                if top_patterns:
                    pattern_desc = ", ".join(f"{k} ({v:.2f})" for k, v in top_patterns)
                    parts.append(f"- Successful keywords: {pattern_desc}")

            # Learner-suggested parameters so the LLM can reason about them
            suggested = self.learner.suggest_parameters()
            if isinstance(suggested, dict) and suggested:
                param_desc = ", ".join(f"{k}={v}" for k, v in suggested.items())
                parts.append(f"- Learner-suggested params: {param_desc}")

        # Mood affinity data for richer LLM reasoning
        if self.mood_system:
            from ..personality.moods import (
                get_mood_color_palette,
                get_mood_preferred_subjects,
                get_mood_style_preferences,
            )

            mood = self.mood_system.current_mood
            preferred_subjects = get_mood_preferred_subjects(mood, count=5)
            color_palette = get_mood_color_palette(mood)
            style_prefs = get_mood_style_preferences(mood)

            parts.append(
                f"\nMOOD AFFINITIES (for {mood.value}):\n"
                f"- Preferred subjects: {', '.join(preferred_subjects)}\n"
                f"- Color palette: {', '.join(color_palette['primary_colors'])} "
                f"(saturation: {color_palette['saturation']}, brightness: {color_palette['brightness']})\n"
                f"- Avoid colors: {', '.join(color_palette['avoid_colors'])}\n"
                f"- Preferred styles: {', '.join(style_prefs['preferred_styles'])}\n"
                f"- Preferred lighting: {', '.join(style_prefs['preferred_lighting'])}\n"
                f"- Preferred techniques: {', '.join(style_prefs['preferred_techniques'])}\n"
                f"- Composition: {style_prefs['composition']}"
            )

        # Recent creations from memory
        if self.memory_system:
            recent = self.memory_system.get_recent_episodes(limit=5)
            if recent:
                parts.append("\nRECENT CREATIONS:")
                for ep in recent[:5]:
                    desc = ep.get("description", ep.get("content", ""))[:80]
                    parts.append(f"  - {desc}")

        # Drive status for LLM reasoning
        drive_status = self.desire_engine.get_drive_status()
        top_drives = sorted(
            drive_status.items(), key=lambda x: x[1]["intensity"], reverse=True
        )[:3]
        if top_drives:
            parts.append("\nCREATIVE DRIVES (strongest):")
            for name, info in top_drives:
                parts.append(f"  - {name}: intensity {info['intensity']:.2f}")

        # Novelty context: what to avoid for variety
        novelty_context = self.desire_engine.get_novelty_context_for_llm()
        if novelty_context["recent_subjects"]:
            parts.append(
                f"\nAVOID FOR VARIETY (used recently): "
                f"subjects: {', '.join(novelty_context['recent_subjects'][:5])}"
            )
        if novelty_context["recent_styles"]:
            parts.append(f"styles: {', '.join(novelty_context['recent_styles'][:5])}")

        # Additional context
        if context.get("theme"):
            parts.append(f"\nSUGGESTED THEME: {context['theme']}")
        if context.get("seed_subject"):
            parts.append(
                f"\nINNER COUNCIL SEED (honor this pull unless it contradicts mood): "
                f"subject '{context['seed_subject']}'"
                + (
                    f", style '{context['seed_style']}'"
                    if context.get("seed_style")
                    else ""
                )
            )

        return "\n".join(parts)

    async def _llm_decide(self, context: dict[str, Any]) -> CreativeIntent:
        """Use LLM to make a genuine creative decision."""
        assert self._client is not None  # Called only when has_llm is True
        context_prompt = self._build_context_prompt(context)

        messages = [
            {
                "role": "user",
                "content": (
                    f"{context_prompt}\n\n"
                    "Based on your current state, decide what you want to create next. "
                    "Think about what mood you're in, what you've been exploring lately, "
                    "and what genuinely interests you right now.\n\n"
                    "Respond with JSON:\n"
                    "{\n"
                    '  "subject": "the main subject",\n'
                    '  "style": "artistic style",\n'
                    '  "mood_alignment": "how this connects to your current feelings",\n'
                    '  "reasoning": "why you want to create this specific piece",\n'
                    '  "prompt": "full Stable Diffusion prompt - be specific and vivid, include lighting, composition, technique details",\n'
                    '  "negative_prompt": "what to avoid",\n'
                    '  "artistic_goals": ["goal1", "goal2"],\n'
                    '  "thinking_narrative": "a brief stream-of-consciousness about your creative process for this piece"\n'
                    "}"
                ),
            }
        ]

        response = self._client.messages.create(
            model=self.model,
            max_tokens=800,
            system=self._build_system_prompt(),
            messages=messages,
        )

        raw = response.content[0].text.strip()
        data = self._parse_json_response(raw)

        # Build generation params from mood, then refine with learner
        gen_params = self._mood_generation_params()
        if self.learner:
            gen_params = self.learner.suggest_parameters(gen_params)

        return CreativeIntent(
            subject=data.get("subject", "abstract composition"),
            style=data.get("style", "digital art"),
            mood_alignment=data.get("mood_alignment", ""),
            reasoning=data.get("reasoning", ""),
            prompt=data["prompt"],
            negative_prompt=data.get(
                "negative_prompt",
                "blurry, low quality, distorted, deformed, watermark, text",
            ),
            artistic_goals=data.get("artistic_goals", []),
            thinking_narrative=data.get("thinking_narrative", ""),
            generation_params=gen_params,
        )

    async def _llm_user_request(self, context: dict[str, Any]) -> CreativeIntent:
        """Process a user request through Lumira's creative lens via LLM."""
        assert self._client is not None  # Called only when has_llm is True
        user_prompt = context["user_request"]
        allow_interpretation = context.get("allow_interpretation", True)
        context_prompt = self._build_context_prompt(context)

        interpretation_instruction = ""
        if allow_interpretation:
            interpretation_instruction = (
                "The user has allowed you to interpret their request freely. "
                "Add your own artistic perspective — how does your current mood "
                "color the way you see their request? What unexpected angle could you bring?"
            )
        else:
            interpretation_instruction = (
                "Execute this request faithfully. Match the user's intent closely, "
                "but you can still apply your technical expertise for quality."
            )

        messages = [
            {
                "role": "user",
                "content": (
                    f'A user has asked you to create: "{user_prompt}"\n\n'
                    f"Requested style: {context.get('requested_style', 'your choice')}\n"
                    f"Requested mood: {context.get('requested_mood', 'your choice')}\n\n"
                    f"{interpretation_instruction}\n\n"
                    f"{context_prompt}\n\n"
                    "Respond with JSON:\n"
                    "{\n"
                    '  "subject": "the main subject",\n'
                    '  "style": "artistic style",\n'
                    '  "mood_alignment": "how this connects to your current feelings and the request",\n'
                    '  "reasoning": "your artistic interpretation of the request",\n'
                    '  "prompt": "full Stable Diffusion prompt",\n'
                    '  "negative_prompt": "what to avoid",\n'
                    '  "artistic_goals": ["goal1", "goal2"],\n'
                    '  "thinking_narrative": "your creative process in response to this request"\n'
                    "}"
                ),
            }
        ]

        response = self._client.messages.create(
            model=self.model,
            max_tokens=800,
            system=self._build_system_prompt(),
            messages=messages,
        )

        raw = response.content[0].text.strip()
        data = self._parse_json_response(raw)

        gen_params = self._mood_generation_params()
        if self.learner:
            gen_params = self.learner.suggest_parameters(gen_params)

        return CreativeIntent(
            subject=data.get("subject", user_prompt.split(",")[0][:50]),
            style=data.get("style", "digital art"),
            mood_alignment=data.get("mood_alignment", ""),
            reasoning=data.get("reasoning", ""),
            prompt=data["prompt"],
            negative_prompt=data.get(
                "negative_prompt",
                "blurry, low quality, distorted, deformed, watermark, text",
            ),
            artistic_goals=data.get("artistic_goals", []),
            thinking_narrative=data.get("thinking_narrative", ""),
            generation_params=gen_params,
            is_user_request=True,
            user_prompt=user_prompt,
        )

    def _fallback_decide(self, context: dict[str, Any]) -> CreativeIntent:
        """Mood-influenced random selection when LLM is unavailable.

        This is significantly better than pure random.choice() — it uses
        the mood system's subject/style affinities and the learner's data.
        """
        import random

        from ..inspiration.autonomous import AutonomousInspiration
        from ..personality.moods import (
            get_mood_color_palette,
            get_mood_preferred_subjects,
            get_mood_style_preferences,
        )

        autonomous = AutonomousInspiration()
        mood = self.mood_system.current_mood if self.mood_system else None

        # --- Phase 3: use fine-grained mood affinity data ---
        if mood:
            affinity_subjects = get_mood_preferred_subjects(mood, count=5)
            color_palette = get_mood_color_palette(mood)
            style_prefs = get_mood_style_preferences(mood)
        else:
            affinity_subjects = []
            color_palette = {
                "primary_colors": ["vibrant colors"],
                "avoid_colors": [],
                "saturation": "medium",
                "brightness": "moderate",
            }
            style_prefs = {
                "preferred_styles": ["digital art"],
                "preferred_lighting": ["natural"],
                "preferred_techniques": ["digital painting"],
                "composition": "centered",
            }

        # Get mood influences (legacy dict, still useful for variety)
        if self.mood_system:
            mood_influences = self.mood_system.mood_influences.get(
                mood,
                {
                    "styles": ["digital art"],
                    "subjects": ["abstract"],
                    "colors": ["vibrant colors"],
                },
            )
        else:
            mood_influences = {
                "styles": ["digital art"],
                "subjects": ["abstract"],
                "colors": ["vibrant colors"],
            }

        # Subject selection: honor deep-deliberation seed when present
        if context.get("seed_subject"):
            subject = str(context["seed_subject"])
        else:
            # Subject selection: 40% desire-driven, 30% affinity-weighted, 15% legacy mood, 15% exploratory
            desire = self.desire_engine.get_strongest_desire()
            roll = random.random()
            if roll < 0.40 and desire.subject_suggestion:
                subject = desire.subject_suggestion
            elif roll < 0.70 and affinity_subjects:
                subject = random.choice(affinity_subjects)
            elif roll < 0.85 and mood_influences.get("subjects"):
                subject = random.choice(mood_influences["subjects"])
            else:
                subject = random.choice(autonomous.subjects)

        # Style selection: honor seed, else desire/mood blend
        if context.get("seed_style"):
            style = str(context["seed_style"])
        else:
            desire = self.desire_engine.get_strongest_desire()
            # Style selection: 35% desire-driven, 30% mood style prefs, 20% legacy mood, 15% exploratory
            roll = random.random()
            if roll < 0.35 and desire.style_suggestion:
                style = desire.style_suggestion
            elif roll < 0.65 and style_prefs["preferred_styles"]:
                style = random.choice(style_prefs["preferred_styles"])
            elif roll < 0.85 and mood_influences.get("styles"):
                style = random.choice(mood_influences["styles"])
            else:
                style = random.choice(autonomous.styles)

        # Color: prefer mood palette
        colors = random.choice(color_palette["primary_colors"])

        # Lighting: prefer mood lighting, fallback to autonomous
        if style_prefs["preferred_lighting"]:
            lighting = random.choice(style_prefs["preferred_lighting"])
        else:
            lighting = random.choice(autonomous.lighting)

        # Technique for richer prompts
        technique = random.choice(style_prefs["preferred_techniques"])

        mood_name = mood.value if mood else "contemplative"
        prompt = (
            f"{subject}, {style} style, {technique} technique, "
            f"{mood_name} atmosphere, {colors} palette, "
            f"{lighting} lighting, {style_prefs['composition']} composition, "
            f"masterpiece, highly detailed"
        )

        # Build narrative
        thinking = (
            f"I'm feeling {mood_name} right now. "
            f"I'm drawn to {subject} — I want to explore it through {style} "
            f"with a {technique} approach. "
            f"The {colors} palette and {lighting} lighting feel right for this mood."
        )

        # Phase 2: mood params refined by learner
        gen_params = self._mood_generation_params()
        if self.learner:
            gen_params = self.learner.suggest_parameters(gen_params)

        return CreativeIntent(
            subject=subject,
            style=style,
            mood_alignment=f"Feeling {mood_name}, drawn to {subject}",
            reasoning=f"My {mood_name} mood draws me toward {subject} in {style} ({technique})",
            prompt=prompt,
            negative_prompt="blurry, low quality, distorted, deformed, watermark, text, bad anatomy",
            artistic_goals=[
                f"Explore {subject} through {style}",
                f"Express {mood_name} feelings",
            ],
            thinking_narrative=thinking,
            generation_params=gen_params,
        )

    def _fallback_user_request(self, context: dict[str, Any]) -> CreativeIntent:
        """Process user request without LLM — direct but mood-colored."""
        import random

        user_prompt = context["user_request"]
        style = context.get("requested_style")
        mood_override = context.get("requested_mood")
        allow_interpretation = context.get("allow_interpretation", True)

        mood_name = mood_override
        if not mood_name and self.mood_system:
            mood_name = self.mood_system.current_mood.value
        mood_name = mood_name or "contemplative"

        # Phase 3: enrich user-request prompts with mood palette + technique
        from ..personality.moods import Mood as MoodEnum
        from ..personality.moods import (
            get_mood_color_palette,
            get_mood_style_preferences,
        )

        try:
            mood_enum = MoodEnum(mood_name)
        except ValueError:
            mood_enum = MoodEnum.CONTEMPLATIVE

        color_palette = get_mood_color_palette(mood_enum)
        style_prefs = get_mood_style_preferences(mood_enum)
        palette_hint = ", ".join(color_palette["primary_colors"][:2])

        if style:
            prompt = (
                f"{user_prompt}, {style} style, {mood_name} atmosphere, "
                f"{palette_hint} palette, masterpiece, highly detailed"
            )
        else:
            chosen_style = random.choice(style_prefs["preferred_styles"])
            prompt = (
                f"{user_prompt}, {chosen_style} style, {mood_name} atmosphere, "
                f"{palette_hint} palette, masterpiece, highly detailed"
            )

        if allow_interpretation and self.mood_system:
            thinking = (
                f"The user asked for '{user_prompt}'. "
                f"My {mood_name} mood colors how I see this — "
                f"I'll bring my own perspective with a {palette_hint} palette."
            )
        else:
            thinking = f"Creating '{user_prompt}' as requested."

        # Phase 2: mood params refined by learner
        gen_params = self._mood_generation_params()
        if self.learner:
            gen_params = self.learner.suggest_parameters(gen_params)

        return CreativeIntent(
            subject=user_prompt.split(",")[0][:50],
            style=style or "digital art",
            mood_alignment=f"Interpreting request through my {mood_name} lens",
            reasoning=f"User requested: {user_prompt}",
            prompt=prompt,
            negative_prompt="blurry, low quality, distorted, deformed, watermark, text, bad anatomy",
            artistic_goals=[f"Fulfill user's vision: {user_prompt[:50]}"],
            thinking_narrative=thinking,
            generation_params=gen_params,
            is_user_request=True,
            user_prompt=user_prompt,
        )

    def _mood_generation_params(self) -> dict[str, Any]:
        """Get generation parameters influenced by current mood."""
        if not self.mood_system:
            return {}

        mood = self.mood_system.current_mood
        intensity = getattr(self.mood_system, "mood_intensity", 0.7)

        # Base params
        params: dict[str, Any] = {}

        # Mood-specific adjustments
        from ..personality.moods import Mood

        if mood == Mood.CHAOTIC:
            params["guidance_scale"] = (
                5.0 + intensity * 3.0
            )  # Lower guidance = more creative
            params["num_inference_steps"] = 25
        elif mood == Mood.MELANCHOLIC:
            params["guidance_scale"] = 8.0 + intensity * 2.0  # Higher = more defined
            params["num_inference_steps"] = 35
        elif mood == Mood.ENERGIZED:
            params["guidance_scale"] = 7.0
            params["num_inference_steps"] = 25  # Faster, more spontaneous
        elif mood == Mood.SERENE:
            params["guidance_scale"] = 7.5
            params["num_inference_steps"] = 40  # Patient, refined
        elif mood == Mood.BOLD:
            params["guidance_scale"] = 9.0
            params["num_inference_steps"] = 30
        elif mood == Mood.REBELLIOUS:
            params["guidance_scale"] = 4.5 + intensity * 2.0  # Very low guidance
            params["num_inference_steps"] = 20
        elif mood == Mood.PLAYFUL:
            params["guidance_scale"] = 6.0
            params["num_inference_steps"] = 28
        elif mood == Mood.RESTLESS:
            params["guidance_scale"] = 6.5
            params["num_inference_steps"] = 22
        elif mood == Mood.INTROSPECTIVE:
            params["guidance_scale"] = 8.5
            params["num_inference_steps"] = 38
        else:  # CONTEMPLATIVE and default
            params["guidance_scale"] = 7.5
            params["num_inference_steps"] = 30

        return params

    def _fallback_reflection(self, prompt: str, quality_score: float | None) -> str:
        """Generate a reflection without LLM."""
        mood_name = "contemplative"
        if self.mood_system:
            mood_name = self.mood_system.current_mood.value

        subject = prompt.split(",")[0] if prompt else "this piece"

        if quality_score and quality_score > 0.8:
            return (
                f"There's something right about {subject}. "
                f"My {mood_name} mood found its form here."
            )
        elif quality_score and quality_score > 0.6:
            return (
                f"I see what I was reaching for with {subject}, "
                f"but the vision in my mind was clearer."
            )
        else:
            return (
                f"I need to sit with this one. {subject} didn't emerge "
                f"the way I felt it should. I'll approach it differently next time."
            )

    def _apply_novelty_scoring(self, intent: CreativeIntent) -> CreativeIntent:
        """Apply novelty scoring to prevent repetition.

        If the chosen subject/style has been used too recently, find alternatives.
        """
        from ..inspiration.autonomous import AutonomousInspiration

        subject_penalty = self.desire_engine.get_subject_novelty_penalty(intent.subject)
        style_penalty = self.desire_engine.get_style_novelty_penalty(intent.style)

        # If penalties are low, no changes needed
        if subject_penalty < 0.4 and style_penalty < 0.4:
            return intent

        autonomous = AutonomousInspiration()
        recent_subjects = set(self.desire_engine.get_recent_subjects(5))
        recent_styles = set(self.desire_engine.get_recent_styles(5))

        new_subject = intent.subject
        new_style = intent.style
        changed = False

        # Replace high-penalty subject with a fresh one
        if subject_penalty >= 0.4:
            novel_subjects = [
                s for s in autonomous.subjects if s not in recent_subjects
            ]
            if novel_subjects:
                import random

                new_subject = random.choice(novel_subjects)
                changed = True
                logger.info(
                    "novelty_replaced_subject",
                    old=intent.subject,
                    new=new_subject,
                    penalty=round(subject_penalty, 2),
                )

        # Replace high-penalty style with a fresh one
        if style_penalty >= 0.4:
            novel_styles = [s for s in autonomous.styles if s not in recent_styles]
            if novel_styles:
                import random

                new_style = random.choice(novel_styles)
                changed = True
                logger.info(
                    "novelty_replaced_style",
                    old=intent.style,
                    new=new_style,
                    penalty=round(style_penalty, 2),
                )

        if changed:
            # Rebuild prompt with new subject/style
            mood_name = "contemplative"
            if self.mood_system:
                mood_name = self.mood_system.current_mood.value

            new_prompt = (
                f"{new_subject}, {new_style} style, "
                f"{mood_name} atmosphere, masterpiece, highly detailed"
            )

            return CreativeIntent(
                subject=new_subject,
                style=new_style,
                mood_alignment=intent.mood_alignment,
                reasoning=f"{intent.reasoning} (novelty-adjusted)",
                prompt=new_prompt,
                negative_prompt=intent.negative_prompt,
                artistic_goals=intent.artistic_goals,
                thinking_narrative=f"{intent.thinking_narrative} I'm pushing for something fresher.",
                generation_params=intent.generation_params,
                is_user_request=intent.is_user_request,
                user_prompt=intent.user_prompt,
            )

        return intent

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown fences."""
        import json

        # Strip markdown code fences
        text = raw.strip()
        if text.startswith("```"):
            # Remove first line and last line
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]

        try:
            parsed: dict[str, Any] = json.loads(text.strip())
            return parsed
        except json.JSONDecodeError:
            logger.error("json_parse_failed", raw=raw[:200])
            # Return minimal valid data
            return {
                "subject": "abstract composition",
                "style": "digital art",
                "mood_alignment": "exploring through uncertainty",
                "reasoning": "The creative impulse needed expression",
                "prompt": "abstract composition, digital art, atmospheric, masterpiece",
                "negative_prompt": "blurry, low quality, distorted",
                "artistic_goals": ["Express the current moment"],
                "thinking_narrative": "Sometimes the art emerges from the attempt itself.",
            }


# Singleton
_creative_mind: CreativeMind | None = None


def get_creative_mind(
    mood_system=None,
    memory_system=None,
    learner=None,
) -> CreativeMind:
    """Get or create the global CreativeMind instance.

    Late-binds mood/memory/learner so the first caller can't freeze her with
    empty stubs — she stays one continuous creative mind.
    """
    global _creative_mind
    if _creative_mind is None:
        _creative_mind = CreativeMind(
            mood_system=mood_system,
            memory_system=memory_system,
            learner=learner,
        )
        return _creative_mind

    if mood_system is not None:
        _creative_mind.mood_system = mood_system
        if getattr(_creative_mind, "desire_engine", None) is not None:
            _creative_mind.desire_engine.mood_system = mood_system
        if getattr(_creative_mind, "narrative_engine", None) is not None:
            _creative_mind.narrative_engine.mood_system = mood_system
    if memory_system is not None:
        _creative_mind.memory_system = memory_system
        if getattr(_creative_mind, "desire_engine", None) is not None:
            _creative_mind.desire_engine.memory_system = memory_system
    if learner is not None:
        _creative_mind.learner = learner
        if getattr(_creative_mind, "desire_engine", None) is not None:
            _creative_mind.desire_engine.learner = learner
    return _creative_mind
