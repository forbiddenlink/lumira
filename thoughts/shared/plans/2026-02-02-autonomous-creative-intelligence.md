# Lumira: Autonomous Creative Intelligence Upgrade

## Vision
Transform Lumira from a "beautifully-engineered random image generator with art personality flavor" into a **truly autonomous creative AI agent** that feels, desires, remembers, learns, and creates with intention.

## Architecture Audit Summary

### What Works Well
- **Infrastructure**: Robust FastAPI app, WebSocket streaming, Redis queue, APScheduler
- **Generation Pipeline**: 3 generators (local SD, FLUX, Replicate cloud), ControlNet, IP-Adapter, LoRA
- **Personality Scaffolding**: 10 moods, style axes, episodic memory, XP system, ReAct thinking
- **Curation**: CLIP-based quality scoring, ensemble curation

### What's Broken / Missing
1. **Creative decisions are 100% `random.choice()`** — mood doesn't influence what's created
2. **AdaptiveLearner exists but is NEVER called** — records nothing, influences nothing
3. **No LLM integration** — zero Claude/GPT for prompt enhancement or creative reasoning
4. **Cognition system is decorative** — streams poetic narration but doesn't actually decide anything
5. **No feedback loop** — quality scores don't feed back into future decisions
6. **No thematic coherence** — each creation is isolated, no series or narrative arcs
7. **No user request interface** — users can't ask Lumira to create something specific
8. **EvolutionaryInspiration exists but is never instantiated or called**

---

## Implementation Phases

### Phase 1: LLM Creative Brain (Claude Integration) ✅ COMPLETE
**Goal**: Give Lumira a real mind that reasons about what to create and why.
**Status**: Implemented `src/ai_artist/intelligence/creative_mind.py` with CreativeMind class.
Replaces random.choice() with Claude-powered or mood-influenced fallback decisions.
Config added to `config/config.yaml`. `anthropic` package installed.

**New file**: `src/ai_artist/intelligence/creative_mind.py`

```
CreativeMind class:
  - __init__(api_key, mood_system, memory_system, learner)
  - async decide_what_to_create(context) -> CreativeIntent
  - async enhance_prompt(raw_prompt, mood, style_axes) -> str
  - async reflect_on_creation(image_metadata, quality_score) -> Reflection
  - async process_user_request(user_prompt) -> CreativeIntent
```

**CreativeIntent model**:
```python
class CreativeIntent(BaseModel):
    subject: str
    style: str
    mood_alignment: str  # How this connects to current mood
    reasoning: str       # Why Lumira wants to create this
    prompt: str          # The enhanced generation prompt
    negative_prompt: str
    artistic_goals: list[str]  # What she's trying to achieve
    references: list[str]      # Past works that inspire this
```

**How it works**:
- Claude receives: current mood + style axes + recent memories + learning stats + time of day
- Claude returns: a `CreativeIntent` with real reasoning about WHY this subject/style
- The prompt is Claude-enhanced (not just "subject, style, colors, masterpiece")
- After generation, Claude reflects on the result and stores insights

**Config addition** to `config.yaml`:
```yaml
intelligence:
  provider: "anthropic"  # or "openai", "local"
  model: "claude-sonnet-4-20250514"
  api_key_env: "ANTHROPIC_API_KEY"  # Read from env var
  temperature: 0.8
  max_tokens: 1024
  enabled: true
  fallback_to_random: true  # If API fails, use random
```

**Files to modify**:
- `src/ai_artist/web/lumira_routes.py` — `create_artwork()` calls `creative_mind.decide_what_to_create()`
- `src/ai_artist/web/lumira_routes.py` — `generate_async()` uses enhanced prompts
- `config/config.yaml` — Add intelligence config section

---

### Phase 2: Wire the Feedback Loop ✅ COMPLETE
**Goal**: Connect quality metrics → AdaptiveLearner → future decisions.
**Status**: Fixed datetime.utcnow() deprecation. Wired learner.record_feedback() after generation.
Wired learner.suggest_parameters() into generation pipeline (both create_artwork and user_request).
Learning stats included in LLM context prompts.

**Changes to `adaptive_learner.py`**:
- Fix `datetime.utcnow()` → `datetime.now(timezone.utc)`
- Add `record_generation_result(prompt, params, quality_score, mood)` for auto-feedback from curation
- Add `get_successful_patterns() -> dict` returning best subjects/styles/moods

**Changes to `lumira_routes.py`**:
- After image generation + curation score: call `learner.record_feedback()` automatically
- Before generation: call `learner.suggest_parameters()` to optimize steps/guidance/size
- Pass learner data to CreativeMind for context

**Changes to `autonomous.py`**:
- Add `filter_by_mood(mood, subjects) -> list` — mood-appropriate subject filtering
- Add `weight_by_success(subjects, learner) -> list` — weight subjects by past success
- Replace `random.choice()` with `weighted_random_choice()` using learner scores

**New flow**:
```
Create → Generate → Score → Record Feedback → Learn
                                                  ↓
                              Next Create ← Suggest Parameters
```

---

### Phase 3: Mood→Creation Deep Coupling ✅ COMPLETE
**Goal**: Mood genuinely drives what Lumira wants to create.
**Status**: Added MOOD_SUBJECT_AFFINITY, MOOD_COLOR_PALETTE, MOOD_STYLE_PREFERENCES dicts.
Added get_mood_preferred_subjects(), get_mood_color_palette(), get_mood_style_preferences() functions.
CreativeMind's fallback and LLM paths both use deep mood coupling.

**Mood-Subject Affinity Map** (in `moods.py`):
```python
MOOD_SUBJECT_AFFINITY = {
    Mood.MELANCHOLIC: {
        "preferred": ["rain", "fog", "abandoned", "solitude", "twilight", "fading"],
        "avoided": ["celebration", "fireworks", "bright crowds"],
        "weight": 0.7  # 70% chance to pick from preferred
    },
    Mood.ENERGIZED: {
        "preferred": ["lightning", "dance", "explosion", "speed", "fire", "sunrise"],
        "avoided": ["still life", "meditation", "silence"],
        "weight": 0.7
    },
    # ... for all 10 moods
}
```

**Mood→Generation Parameters**:
- MELANCHOLIC → lower saturation, muted palette, slower steps
- ENERGIZED → higher contrast, bold colors, dynamic compositions
- CONTEMPLATIVE → softer focus, quieter scenes, balanced tones
- CHAOTIC → high contrast, unusual angles, experimental styles

**Changes to `moods.py`**:
- Add `get_generation_params_for_mood(mood) -> dict` returning guidance_scale, steps adjustments
- Add `get_preferred_subjects(mood) -> list[str]` 
- Add `get_avoided_subjects(mood) -> list[str]`

**Mood transitions trigger creative desire**:
- When mood shifts (e.g., SERENE → MELANCHOLIC), Lumira feels the urge to create something that processes that transition
- The CreativeMind receives mood transition events and can decide to create autonomously

---

### Phase 4: Autonomous Desire Engine ✅ COMPLETE
**Goal**: Lumira creates because she WANTS to, not on a timer.
**Status**: Created `src/ai_artist/intelligence/desire_engine.py` with 6 creative drives:
novelty, mastery, emotional_expression, thematic_continuation, exploration, recognition.
Drives build intensity over time and decay when satisfied.
Integrated into CreativeMind's decision-making (40% subject, 35% style influence).

**New file**: `src/ai_artist/intelligence/desire_engine.py`

```python
class DesireEngine:
    """Generates internal creative desires based on state."""
    
    def __init__(self, mood_system, memory_system, creative_mind):
        self.desire_queue: list[CreativeDesire] = []
        self.last_creation_time: datetime
        self.creative_energy: float = 0.5  # 0-1
    
    async def tick(self) -> CreativeDesire | None:
        """Called periodically. Returns a desire if Lumira wants to create."""
        # Desires arise from:
        # 1. Mood intensity (strong emotions → urge to create)
        # 2. Time since last creation (creative restlessness)
        # 3. Unprocessed experiences (new memories want expression)
        # 4. External triggers (time of day, mood transitions)
        # 5. Creative energy level (builds over time, depletes on creation)
    
    async def process_external_stimulus(self, stimulus: dict) -> CreativeDesire | None:
        """Process external input (user request, trending topic, etc.)."""
```

**CreativeDesire model**:
```python
class CreativeDesire(BaseModel):
    urgency: float  # 0-1, how strongly she wants to create
    trigger: str    # What sparked the desire
    theme: str      # What she wants to explore
    emotion: str    # The feeling driving the creation
    constraints: dict  # Any self-imposed artistic constraints
```

**Integration with scheduler**:
- Replace fixed-time scheduling with desire-driven creation
- Scheduler polls `desire_engine.tick()` every 5-15 minutes
- When urgency > threshold, trigger autonomous creation
- Creative energy builds over time, depletes on creation (prevents spam)

---

### Phase 5: User Request Interface ✅ COMPLETE
**Goal**: Users can ask Lumira to create specific things.
**Status**: Added POST /lumira/request endpoint in lumira_routes.py.
Added "Request a Creation" UI section to lumira.html with prompt, style, mood, interpretation toggle.
Added floating creation FAB to gallery_modern.html.
21 new tests written and passing (615 total, 0 failures).

**New endpoint**: `POST /lumira/request`
```python
class UserRequest(BaseModel):
    prompt: str          # What the user wants
    style: str | None    # Optional style preference
    mood: str | None     # Optional mood preference
    allow_interpretation: bool = True  # Let Lumira add her own twist
```

**How it works**:
1. User sends: "Draw me a dragon in a crystal cave"
2. CreativeMind receives request + current mood + personality
3. If `allow_interpretation=True`, Lumira adds her own artistic interpretation:
   - "A dragon in a crystal cave... but with my melancholic mood, I see it as the dragon guarding its last memory"
4. Enhanced prompt is generated incorporating both user intent AND Lumira's personality
5. Generation proceeds with personality-influenced parameters

**Changes to `lumira_routes.py`**:
- New `/lumira/request` endpoint
- Modify UI templates to add prompt input field

**Changes to templates** (`lumira.html`, `gallery_modern.html`):
- Add text input for user prompts
- "Create for me" button vs "Let Lumira decide" button
- Show Lumira's interpretation of the request

---

### Phase 6: Thematic Series & Narrative
**Goal**: Lumira creates connected series of works, not isolated images.

**New file**: `src/ai_artist/intelligence/narrative.py`

```python
class NarrativeEngine:
    """Manages thematic series and creative arcs."""
    
    def __init__(self, creative_mind, memory_system):
        self.active_series: list[ThematicSeries] = []
    
    async def should_continue_series(self) -> ThematicSeries | None:
        """Check if Lumira wants to continue an existing series."""
    
    async def should_start_series(self, intent: CreativeIntent) -> bool:
        """Check if a creation should start a new series."""

class ThematicSeries(BaseModel):
    title: str
    theme: str
    works: list[str]  # Image IDs
    planned_count: int  # How many works Lumira envisions
    narrative_arc: str  # The story being told
    mood_trajectory: list[str]  # How mood should evolve across the series
```

---

## Implementation Priority

### Sprint 1 (Do Now): Phases 1 + 2
- Create `intelligence/creative_mind.py` with Claude integration
- Wire `AdaptiveLearner` into the generation pipeline
- Modify `create_artwork()` to use CreativeMind instead of random.choice()
- Add config for Anthropic API key
- Add fallback to random when LLM unavailable

### Sprint 2: Phases 3 + 5 
- Deep mood→creation coupling
- User request interface
- UI updates for prompt input

### Sprint 3: Phases 4 + 6
- Desire engine replacing timer-based scheduling  
- Thematic series and narrative arcs

---

## Key Design Decisions

1. **Claude as the brain, not the generator**: Claude reasons about WHAT to create and WHY; Stable Diffusion/FLUX generates the actual image
2. **Graceful degradation**: If Claude API is unavailable, fall back to current random behavior (but log it)
3. **Personality is NOT prompt-engineered into Claude**: The mood/style axis system feeds parameters into the Claude prompt, making Lumira's personality emerge from her systems, not from a system prompt
4. **Learning is always recording**: Even when LLM is unavailable, quality scores still feed back into the learner
5. **User requests are interpreted, not blindly followed**: Lumira adds her own artistic voice to user requests (unless `allow_interpretation=False`)
