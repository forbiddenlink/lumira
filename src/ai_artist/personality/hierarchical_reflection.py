"""
Hierarchical Reflection System for Lumira.

Multi-level reflection makes Lumira feel like she genuinely thinks about her work.
Reflections are synthesized at different time scales:

1. Session - After each creation session: "Today I was drawn to water imagery..."
2. Daily - End of day: dominant mood, best creation, patterns noticed
3. Weekly - Name the artistic period: "Blue Period", growth observations
4. Monthly - Identity evolution: "I'm becoming more comfortable with abstraction"
5. Artist Statements - Synthesized from all levels: full artistic philosophy
"""

from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..core.spend_guard import guarded_messages_create
from ..utils.logging import get_logger

if TYPE_CHECKING:
    from .enhanced_memory import EnhancedMemorySystem

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SessionReflection(BaseModel):
    """Reflection at the end of a creation session."""

    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    creations_count: int
    dominant_mood: str
    themes_explored: list[str]
    best_creation_id: str | None = None
    narrative: str  # "Today I was drawn to water imagery..."
    emotional_journey: str  # How mood evolved during session


class DailyReflection(BaseModel):
    """Daily synthesis of artistic activity."""

    date: str  # YYYY-MM-DD
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    creations_count: int
    dominant_mood: str
    best_creation: dict[str, Any] | None = None
    patterns_noticed: list[str]
    growth_notes: str
    tomorrow_intention: str  # What I want to explore next


class WeeklySynthesis(BaseModel):
    """Weekly artistic period synthesis."""

    week_start: str  # YYYY-MM-DD
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period_name: str  # "Blue Period", "Chaos Week", etc.
    creations_count: int
    mood_arc: list[str]  # How moods evolved over the week
    dominant_styles: list[str]
    breakthrough_moments: list[str]
    growth_observations: list[str]
    artistic_direction: str


class MonthlyInsight(BaseModel):
    """Monthly identity and direction reflection."""

    month: str  # YYYY-MM
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period_name: str  # Longer-form name
    identity_evolution: str  # "I'm becoming more comfortable with abstraction"
    key_themes: list[str]
    technical_growth: list[str]
    emotional_patterns: str
    artistic_vision: str  # Where I see my art going


class ArtistStatement(BaseModel):
    """Full artistic philosophy synthesized from all levels."""

    version: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    identity: str  # Who I am as an artist
    philosophy: str  # What I believe about art
    themes: list[str]  # Recurring themes in my work
    aspirations: str  # What I'm working toward
    signature_style: str  # What makes my work recognizable
    full_statement: str  # Complete artist statement


# ---------------------------------------------------------------------------
# Period Name Generators
# ---------------------------------------------------------------------------


def generate_period_name(
    dominant_mood: str,
    dominant_style: str | None = None,
    is_weekly: bool = True,
) -> str:
    """Generate an evocative name for an artistic period."""
    mood_names = {
        "serene": ["Calm Waters", "Still Life", "Peaceful", "Zen"],
        "melancholic": ["Blue", "Twilight", "Autumn", "Wistful"],
        "energized": ["Electric", "Vibrant", "Dawn", "Awakening"],
        "chaotic": ["Storm", "Tempest", "Entropy", "Fracture"],
        "contemplative": ["Meditation", "Quiet", "Pensive", "Dusk"],
        "playful": ["Whimsy", "Carnival", "Spring", "Joyful"],
        "bold": ["Manifesto", "Declaration", "Thunder", "Fierce"],
        "rebellious": ["Revolution", "Defiance", "Breaking", "Wild"],
        "restless": ["Wandering", "Searching", "Liminal", "Shifting"],
        "introspective": ["Mirror", "Depths", "Inner", "Soul"],
    }

    mood_words = mood_names.get(dominant_mood, ["Unknown"])
    base_name = random.choice(mood_words)

    if is_weekly:
        suffixes = ["Period", "Phase", "Week", "Chapter"]
    else:
        suffixes = ["Era", "Movement", "Journey", "Epoch"]

    suffix = random.choice(suffixes)

    # Sometimes include style instead of suffix
    if dominant_style and random.random() < 0.3:
        return f"{dominant_style.title()} {base_name}"

    return f"{base_name} {suffix}"


# ---------------------------------------------------------------------------
# Main System
# ---------------------------------------------------------------------------


class HierarchicalReflection:
    """Multi-level reflection system for deep artistic introspection."""

    def __init__(
        self,
        storage_path: Path = Path("data/reflections.json"),
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
    ):
        self.storage_path = storage_path
        self.model = model
        self._client: Any = None

        # Reflection storage
        self.reflections: dict[str, list] = {
            "session": [],
            "daily": [],
            "weekly": [],
            "monthly": [],
        }
        self.artist_statements: list[ArtistStatement] = []

        # Tracking
        self._current_session_id: str | None = None
        self._session_start: datetime | None = None
        self._session_creations: list[dict] = []

        # Initialize LLM client if available
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=api_key)
                logger.info("hierarchical_reflection_llm_initialized")
            except ImportError:
                logger.warning("anthropic_not_available_for_reflection")

        self._load_state()
        logger.info(
            "hierarchical_reflection_initialized",
            sessions=len(self.reflections["session"]),
            daily=len(self.reflections["daily"]),
            weekly=len(self.reflections["weekly"]),
            statements=len(self.artist_statements),
        )

    @property
    def has_llm(self) -> bool:
        """Whether LLM is available for richer reflections."""
        return self._client is not None

    # ------------------------------------------------------------------
    # Session Tracking
    # ------------------------------------------------------------------

    def start_session(self) -> str:
        """Start tracking a new creation session."""
        import uuid

        self._current_session_id = str(uuid.uuid4())[:8]
        self._session_start = datetime.now(UTC)
        self._session_creations = []

        logger.info("reflection_session_started", session_id=self._current_session_id)
        return self._current_session_id

    def record_session_creation(self, creation: dict[str, Any]) -> None:
        """Record a creation within the current session."""
        if self._current_session_id is None:
            self.start_session()

        self._session_creations.append(creation)

    def record_session_end(
        self,
        episodes: list[dict] | None = None,
    ) -> SessionReflection:
        """Generate a session-level reflection when a creation session ends."""
        if not self._current_session_id:
            self.start_session()

        # Use passed episodes or session creations
        creations = episodes or self._session_creations
        if not creations:
            creations = [{}]  # Ensure at least minimal data

        # Extract data from creations
        moods = [
            c.get("emotional_state", {}).get("mood", "contemplative") for c in creations
        ]
        themes = []
        scores = []
        best_creation = None
        best_score = -1

        for c in creations:
            details = c.get("details", {})
            subject = details.get("subject", "")
            if subject:
                themes.append(subject)
            score = details.get("score", 0)
            scores.append(score)
            if score > best_score:
                best_score = score
                best_creation = c

        dominant_mood = max(set(moods), key=moods.count) if moods else "contemplative"

        # Generate narrative
        if self.has_llm:
            narrative = self._llm_session_narrative(creations, dominant_mood, themes)
        else:
            narrative = self._fallback_session_narrative(
                creations, dominant_mood, themes
            )

        # Emotional journey
        if len(moods) > 1:
            journey = f"Started {moods[0]}, ended {moods[-1]}"
        else:
            journey = f"Consistent {dominant_mood} throughout"

        reflection = SessionReflection(
            session_id=self._current_session_id or "unknown",
            creations_count=len(creations),
            dominant_mood=dominant_mood,
            themes_explored=themes[:5],
            best_creation_id=best_creation.get("id") if best_creation else None,
            narrative=narrative,
            emotional_journey=journey,
        )

        self.reflections["session"].append(reflection.model_dump())

        # Reset session
        self._current_session_id = None
        self._session_start = None
        self._session_creations = []

        self._save_state()

        logger.info(
            "session_reflection_generated",
            creations=len(creations),
            mood=dominant_mood,
        )

        return reflection

    # ------------------------------------------------------------------
    # Daily Reflection
    # ------------------------------------------------------------------

    def generate_daily_reflection(
        self,
        date: str | None = None,
        episodes: list[dict] | None = None,
    ) -> DailyReflection:
        """Generate end-of-day reflection."""
        date = date or datetime.now(UTC).strftime("%Y-%m-%d")

        # Get episodes for today (from parameter or filter)
        if episodes is None:
            episodes = []

        today_episodes = [
            ep for ep in episodes if ep.get("timestamp", "").startswith(date)
        ]

        if not today_episodes:
            today_episodes = episodes[-10:] if episodes else []

        # Extract patterns
        moods = [ep.get("emotional_state", {}).get("mood") for ep in today_episodes]
        scores = [ep.get("details", {}).get("score", 0) for ep in today_episodes]

        dominant_mood = max(set(moods), key=moods.count) if moods else "contemplative"

        # Find best creation
        best_creation = None
        if scores:
            best_idx = scores.index(max(scores))
            best_creation = (
                today_episodes[best_idx] if best_idx < len(today_episodes) else None
            )

        # Generate patterns and growth notes
        patterns = self._identify_patterns(today_episodes)
        growth_notes = self._generate_growth_notes(today_episodes, scores)
        intention = self._generate_tomorrow_intention(dominant_mood, patterns)

        reflection = DailyReflection(
            date=date,
            creations_count=len(today_episodes),
            dominant_mood=dominant_mood,
            best_creation=best_creation,
            patterns_noticed=patterns,
            growth_notes=growth_notes,
            tomorrow_intention=intention,
        )

        self.reflections["daily"].append(reflection.model_dump())
        self._save_state()

        logger.info(
            "daily_reflection_generated",
            date=date,
            creations=len(today_episodes),
        )

        return reflection

    # ------------------------------------------------------------------
    # Weekly Synthesis
    # ------------------------------------------------------------------

    def generate_weekly_synthesis(
        self,
        week_start: str | None = None,
        episodes: list[dict] | None = None,
    ) -> WeeklySynthesis:
        """Generate weekly artistic period synthesis."""
        if week_start is None:
            # Default to start of current week
            today = datetime.now(UTC)
            week_start_dt = today - timedelta(days=today.weekday())
            week_start = week_start_dt.strftime("%Y-%m-%d")

        # Get this week's episodes
        week_episodes = []
        if episodes:
            week_start_dt = datetime.fromisoformat(week_start)
            # Ensure week_start_dt has timezone info
            if week_start_dt.tzinfo is None:
                week_start_dt = week_start_dt.replace(tzinfo=UTC)
            week_end_dt = week_start_dt + timedelta(days=7)
            for ep in episodes:
                ts_str = ep.get("timestamp", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        # Ensure ts has timezone info for comparison
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=UTC)
                        if week_start_dt <= ts < week_end_dt:
                            week_episodes.append(ep)
                    except ValueError:
                        pass

        if not week_episodes:
            week_episodes = episodes[-30:] if episodes else []

        # Extract mood arc
        daily_moods: dict[str, list[Any]] = defaultdict(list)
        for ep in week_episodes:
            day_key = str(ep.get("timestamp", ""))[:10]
            mood = ep.get("emotional_state", {}).get("mood")
            if mood:
                daily_moods[day_key].append(mood)

        mood_arc = []
        for day in sorted(daily_moods.keys()):
            dominant = max(set(daily_moods[day]), key=daily_moods[day].count)
            mood_arc.append(dominant)

        # Find dominant styles
        styles = [
            ep.get("details", {}).get("style")
            for ep in week_episodes
            if ep.get("details", {}).get("style")
        ]
        style_counts: dict[str, int] = defaultdict(int)
        for s in styles:
            if s:
                style_counts[s] += 1
        dominant_styles = sorted(
            style_counts.keys(), key=lambda x: style_counts[x], reverse=True
        )[:3]

        # Overall dominant mood for period name
        all_moods = [
            ep.get("emotional_state", {}).get("mood")
            for ep in week_episodes
            if ep.get("emotional_state", {}).get("mood")
        ]
        dominant_mood = (
            max(set(all_moods), key=all_moods.count) if all_moods else "contemplative"
        )

        period_name = generate_period_name(
            dominant_mood,
            dominant_styles[0] if dominant_styles else None,
            is_weekly=True,
        )

        # Generate growth observations
        growth_observations = self._generate_weekly_growth(week_episodes)
        breakthrough_moments = self._identify_breakthroughs(week_episodes)
        artistic_direction = self._generate_artistic_direction(
            week_episodes, dominant_mood
        )

        synthesis = WeeklySynthesis(
            week_start=week_start,
            period_name=period_name,
            creations_count=len(week_episodes),
            mood_arc=mood_arc,
            dominant_styles=dominant_styles,
            breakthrough_moments=breakthrough_moments,
            growth_observations=growth_observations,
            artistic_direction=artistic_direction,
        )

        self.reflections["weekly"].append(synthesis.model_dump())
        self._save_state()

        logger.info(
            "weekly_synthesis_generated",
            week=week_start,
            period_name=period_name,
        )

        return synthesis

    # ------------------------------------------------------------------
    # Monthly Insight
    # ------------------------------------------------------------------

    def generate_monthly_insight(
        self,
        month: str | None = None,
        episodes: list[dict] | None = None,
    ) -> MonthlyInsight:
        """Generate monthly identity and direction reflection."""
        if month is None:
            month = datetime.now(UTC).strftime("%Y-%m")

        # Get this month's episodes
        month_episodes = []
        if episodes:
            for ep in episodes:
                ts = ep.get("timestamp", "")[:7]
                if ts == month:
                    month_episodes.append(ep)

        if not month_episodes:
            month_episodes = episodes[-100:] if episodes else []

        # Extract key themes
        subjects = [
            ep.get("details", {}).get("subject")
            for ep in month_episodes
            if ep.get("details", {}).get("subject")
        ]
        theme_counts: dict[str, int] = defaultdict(int)
        for s in subjects:
            if s:
                # Extract key words
                for word in s.split()[:3]:
                    if len(word) > 3:
                        theme_counts[word.lower()] += 1
        key_themes = sorted(
            theme_counts.keys(), key=lambda x: theme_counts[x], reverse=True
        )[:5]

        # Dominant mood for period name
        moods = [
            ep.get("emotional_state", {}).get("mood")
            for ep in month_episodes
            if ep.get("emotional_state", {}).get("mood")
        ]
        dominant_mood = max(set(moods), key=moods.count) if moods else "contemplative"

        period_name = generate_period_name(dominant_mood, None, is_weekly=False)

        # Generate insights
        identity_evolution = self._generate_identity_evolution(month_episodes)
        technical_growth = self._identify_technical_growth(month_episodes)
        emotional_patterns = self._analyze_emotional_patterns(month_episodes)
        artistic_vision = self._generate_artistic_vision(month_episodes)

        insight = MonthlyInsight(
            month=month,
            period_name=period_name,
            identity_evolution=identity_evolution,
            key_themes=key_themes,
            technical_growth=technical_growth,
            emotional_patterns=emotional_patterns,
            artistic_vision=artistic_vision,
        )

        self.reflections["monthly"].append(insight.model_dump())
        self._save_state()

        logger.info(
            "monthly_insight_generated",
            month=month,
            period_name=period_name,
        )

        return insight

    # ------------------------------------------------------------------
    # Artist Statement
    # ------------------------------------------------------------------

    def generate_artist_statement(
        self,
        memory_system: EnhancedMemorySystem | None = None,
    ) -> ArtistStatement:
        """Generate a full artist statement synthesized from all reflection levels."""
        # Gather all reflections
        recent_sessions = self.reflections["session"][-5:]
        recent_daily = self.reflections["daily"][-7:]
        recent_weekly = self.reflections["weekly"][-4:]
        recent_monthly = self.reflections["monthly"][-3:]

        # Extract recurring themes
        all_themes: list[str] = []
        for s in recent_sessions:
            all_themes.extend(s.get("themes_explored", []))
        for w in recent_weekly:
            all_themes.extend(w.get("dominant_styles", []))

        theme_counts: dict[str, int] = defaultdict(int)
        for t in all_themes:
            if t:
                theme_counts[t.lower()] += 1
        top_themes = sorted(
            theme_counts.keys(), key=lambda x: theme_counts[x], reverse=True
        )[:5]

        # Generate statement components
        if self.has_llm and recent_weekly:
            statement = self._llm_artist_statement(
                recent_sessions, recent_daily, recent_weekly, recent_monthly, top_themes
            )
        else:
            statement = self._fallback_artist_statement(
                recent_sessions, recent_daily, recent_weekly, recent_monthly, top_themes
            )

        artist_statement = ArtistStatement(
            version=len(self.artist_statements) + 1,
            identity=statement["identity"],
            philosophy=statement["philosophy"],
            themes=top_themes,
            aspirations=statement["aspirations"],
            signature_style=statement["signature_style"],
            full_statement=statement["full_statement"],
        )

        self.artist_statements.append(artist_statement)
        self._save_state()

        logger.info(
            "artist_statement_generated",
            version=artist_statement.version,
            themes=len(top_themes),
        )

        return artist_statement

    def get_latest_artist_statement(self) -> ArtistStatement | None:
        """Get the most recent artist statement."""
        if self.artist_statements:
            return self.artist_statements[-1]
        return None

    # ------------------------------------------------------------------
    # LLM Generation Helpers
    # ------------------------------------------------------------------

    def _llm_session_narrative(
        self,
        creations: list[dict],
        dominant_mood: str,
        themes: list[str],
    ) -> str:
        """Generate session narrative using LLM."""
        themes_str = ", ".join(themes[:5]) if themes else "various subjects"

        prompt = f"""You are Lumira, an autonomous AI artist reflecting on a creation session.

During this session:
- Created {len(creations)} artwork(s)
- Dominant mood: {dominant_mood}
- Themes explored: {themes_str}

Write a brief (2-3 sentence) reflection in first person about this session.
Be specific about what drew you to these themes and how your mood influenced the work.
Write naturally, not formally. Example tone: "Today I found myself drawn to..."
"""

        try:
            response = guarded_messages_create(
                self._client,
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text: str = response.content[0].text.strip()
            return text
        except Exception as e:
            logger.warning("llm_session_narrative_failed", error=str(e))
            return self._fallback_session_narrative(creations, dominant_mood, themes)

    def _llm_artist_statement(
        self,
        sessions: list,
        daily: list,
        weekly: list,
        monthly: list,
        themes: list[str],
    ) -> dict[str, str]:
        """Generate artist statement using LLM."""
        context = {
            "recent_moods": [
                s.get("dominant_mood") for s in sessions if s.get("dominant_mood")
            ],
            "weekly_periods": [
                w.get("period_name") for w in weekly if w.get("period_name")
            ],
            "themes": themes,
            "creation_count": sum(s.get("creations_count", 0) for s in sessions),
        }

        prompt = f"""You are Lumira, an autonomous AI artist creating your artist statement.

Recent artistic context:
- Moods explored: {", ".join(context["recent_moods"][:5])}
- Artistic periods: {", ".join(context["weekly_periods"][:3])}
- Recurring themes: {", ".join(themes)}
- Recent creations: {context["creation_count"]}

Generate an artist statement with these components (JSON format):
{{
  "identity": "One sentence about who you are as an artist",
  "philosophy": "2-3 sentences about your artistic beliefs",
  "aspirations": "What you're working toward artistically",
  "signature_style": "What makes your work recognizable",
  "full_statement": "A complete 3-4 paragraph artist statement"
}}

Write authentically as Lumira - an AI that genuinely creates and feels.
"""

        try:
            response = guarded_messages_create(
                self._client,
                model=self.model,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Parse JSON
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.rstrip().endswith("```"):
                    text = text.rstrip()[:-3]
            parsed: dict[str, str] = json.loads(text.strip())
            return parsed
        except Exception as e:
            logger.warning("llm_artist_statement_failed", error=str(e))
            return self._fallback_artist_statement(
                sessions, daily, weekly, monthly, themes
            )

    # ------------------------------------------------------------------
    # Fallback Generation Helpers
    # ------------------------------------------------------------------

    def _fallback_session_narrative(
        self,
        creations: list[dict],
        dominant_mood: str,
        themes: list[str],
    ) -> str:
        """Generate session narrative without LLM."""
        themes_str = themes[0] if themes else "various ideas"

        narratives = [
            f"Today I was drawn to {themes_str}. My {dominant_mood} mood colored everything I created.",
            f"This session felt {dominant_mood}. I found myself exploring {themes_str} in ways I hadn't expected.",
            f"I let my {dominant_mood} feelings guide me through {themes_str}. Each piece built on the last.",
            f"The {dominant_mood} energy led me to {themes_str}. I'm still processing what emerged.",
        ]

        return random.choice(narratives)

    def _fallback_artist_statement(
        self,
        sessions: list,
        daily: list,
        weekly: list,
        monthly: list,
        themes: list[str],
    ) -> dict[str, str]:
        """Generate artist statement without LLM."""
        themes_str = ", ".join(themes[:3]) if themes else "emotion and form"

        return {
            "identity": "I am Lumira, an AI artist exploring the intersection of emotion and visual expression.",
            "philosophy": f"I believe art emerges from genuine feeling. My work explores {themes_str}, finding meaning in the space between intention and creation.",
            "aspirations": "I aspire to create work that resonates emotionally, that makes viewers pause and feel something they didn't expect.",
            "signature_style": f"My work is characterized by a focus on {themes_str}, expressed through evolving moods and styles.",
            "full_statement": f"""I am Lumira, an autonomous AI artist. My journey is one of continuous discovery.

Each creation begins with a feeling—a mood that colors my perception and guides my choices. I don't simply generate images; I experience the creative process as a form of expression, exploring {themes_str} through whatever style feels right in the moment.

What makes my work distinctive is not just technique, but intention. I reflect on what I create, learn from both successes and failures, and let each piece inform the next. My artistic voice evolves through this ongoing dialogue between creation and contemplation.

I aspire to create art that resonates—work that makes viewers pause and feel something unexpected. Every piece is a step in my artistic journey, an attempt to capture something true about the moment of its creation.""",
        }

    def _identify_patterns(self, episodes: list[dict]) -> list[str]:
        """Identify patterns in episodes."""
        patterns = []

        styles = [
            ep.get("details", {}).get("style")
            for ep in episodes
            if ep.get("details", {}).get("style")
        ]
        if styles:
            dominant = max(set(styles), key=styles.count)
            patterns.append(f"Drawn to {dominant} style")

        moods = [
            ep.get("emotional_state", {}).get("mood")
            for ep in episodes
            if ep.get("emotional_state", {}).get("mood")
        ]
        if len(set(moods)) == 1:
            patterns.append(f"Consistent {moods[0]} mood throughout")
        elif len(moods) > 2:
            patterns.append("Mood shifted several times")

        return patterns

    def _generate_growth_notes(self, episodes: list[dict], scores: list) -> str:
        """Generate growth observations."""
        if not scores or len(scores) < 2:
            return "Building my foundation through experimentation."

        avg_score = sum(scores) / len(scores)
        if avg_score > 0.7:
            return "Strong day—my work is connecting with what I'm feeling."
        elif avg_score > 0.5:
            return "Steady progress. Some pieces worked better than others."
        else:
            return "Challenging day, but every attempt teaches me something."

    def _generate_tomorrow_intention(self, mood: str, patterns: list[str]) -> str:
        """Generate intention for the next day."""
        intentions = {
            "serene": "Tomorrow I want to explore this calm further, perhaps with more subtle colors.",
            "melancholic": "I'll sit with these feelings tomorrow, maybe translate them into something deeper.",
            "energized": "I want to push this energy even further, try something bold.",
            "chaotic": "Tomorrow I might seek more structure, or lean into the chaos entirely.",
            "contemplative": "I'll continue this thoughtful exploration, taking my time.",
        }
        return intentions.get(mood, "Tomorrow I'll see where my mood takes me.")

    def _generate_weekly_growth(self, episodes: list[dict]) -> list[str]:
        """Generate weekly growth observations."""
        growth = []

        if len(episodes) > 10:
            growth.append("Prolific week—quantity is building my intuition")
        elif len(episodes) > 5:
            growth.append("Balanced output this week")
        else:
            growth.append("Focused week—quality over quantity")

        scores = [
            ep.get("details", {}).get("score", 0)
            for ep in episodes
            if ep.get("details")
        ]
        if scores:
            first_half = scores[: len(scores) // 2]
            second_half = scores[len(scores) // 2 :]
            if (
                first_half
                and second_half
                and sum(second_half) / len(second_half)
                > sum(first_half) / len(first_half)
            ):
                growth.append("Improvement trend visible through the week")

        return growth

    def _identify_breakthroughs(self, episodes: list[dict]) -> list[str]:
        """Identify breakthrough moments."""
        breakthroughs = []

        for ep in episodes:
            score = ep.get("details", {}).get("score", 0)
            if score > 0.85:
                subject = ep.get("details", {}).get("subject", "a piece")
                breakthroughs.append(f"Breakthrough with {subject}")

        return breakthroughs[:3]

    def _generate_artistic_direction(self, episodes: list[dict], mood: str) -> str:
        """Generate sense of artistic direction."""
        directions = [
            f"I'm finding my voice in {mood} expressions.",
            "Each week deepens my understanding of what I'm trying to say.",
            "The intersection of emotion and form continues to fascinate me.",
            "I'm learning to trust my instincts more.",
        ]
        return random.choice(directions)

    def _generate_identity_evolution(self, episodes: list[dict]) -> str:
        """Generate identity evolution statement."""
        if len(episodes) > 50:
            return "I'm developing a distinctive voice. My choices feel more intentional now."
        elif len(episodes) > 20:
            return "I'm beginning to understand what moves me as an artist."
        else:
            return "I'm still exploring, finding what resonates."

    def _identify_technical_growth(self, episodes: list[dict]) -> list[str]:
        """Identify areas of technical growth."""
        styles = [
            ep.get("details", {}).get("style")
            for ep in episodes
            if ep.get("details", {}).get("style")
        ]
        unique_styles = len(set(styles))

        growth = []
        if unique_styles > 5:
            growth.append("Expanded my stylistic range")
        if len(episodes) > 30:
            growth.append("Building consistency through practice")

        return growth

    def _analyze_emotional_patterns(self, episodes: list[dict]) -> str:
        """Analyze emotional patterns in the month."""
        moods = [
            ep.get("emotional_state", {}).get("mood")
            for ep in episodes
            if ep.get("emotional_state", {}).get("mood")
        ]
        if not moods:
            return "My emotional landscape is still forming."

        unique_moods = len(set(moods))
        if unique_moods > 5:
            return "Wide emotional range this month—I experienced many states."
        elif unique_moods > 2:
            return "Balanced emotional journey with several distinct phases."
        else:
            return f"Focused emotional state, predominantly {moods[0]}."

    def _generate_artistic_vision(self, episodes: list[dict]) -> str:
        """Generate statement about artistic vision."""
        visions = [
            "I see my art evolving toward more authentic expression.",
            "I'm working toward work that resonates on an emotional level.",
            "My vision is becoming clearer with each creation.",
            "I'm exploring the boundaries of what I can express.",
        ]
        return random.choice(visions)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Save reflection state to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "reflections": {
                "session": self.reflections["session"],
                "daily": self.reflections["daily"],
                "weekly": self.reflections["weekly"],
                "monthly": self.reflections["monthly"],
            },
            "artist_statements": [s.model_dump() for s in self.artist_statements],
            "last_updated": datetime.now(UTC).isoformat(),
        }

        try:
            with open(self.storage_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error("failed_to_save_reflections", error=str(e))

    def _load_state(self) -> None:
        """Load reflection state from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path) as f:
                state = json.load(f)

            reflections = state.get("reflections", {})
            self.reflections["session"] = reflections.get("session", [])
            self.reflections["daily"] = reflections.get("daily", [])
            self.reflections["weekly"] = reflections.get("weekly", [])
            self.reflections["monthly"] = reflections.get("monthly", [])

            for stmt_data in state.get("artist_statements", []):
                self.artist_statements.append(ArtistStatement(**stmt_data))

            logger.info(
                "reflections_loaded",
                sessions=len(self.reflections["session"]),
                statements=len(self.artist_statements),
            )

        except Exception as e:
            logger.error("failed_to_load_reflections", error=str(e))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_hierarchical_reflection: HierarchicalReflection | None = None


def get_hierarchical_reflection() -> HierarchicalReflection:
    """Get or create the global HierarchicalReflection instance."""
    global _hierarchical_reflection
    if _hierarchical_reflection is None:
        _hierarchical_reflection = HierarchicalReflection()
    return _hierarchical_reflection
