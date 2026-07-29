"""Lumira API routes - personality, state, and creation endpoints."""

import asyncio
import io
import json
import random
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel, Field, model_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..caching import get_generation_cache
from ..db.models import GeneratedImage
from ..db.session import get_db
from ..personality.enhanced_memory import EnhancedMemorySystem
from ..personality.moods import Mood, MoodSystem
from ..personality.profile import ArtisticProfile
from ..utils.config import load_config
from ..utils.logging import get_logger
from ..utils.negative_prompts import get_negative_prompt_library
from .dependencies import GenerationAuthDep
from .generation_registry import (
    generation_semaphore,
    notify_cancelled,
)
from .generation_registry import (
    register as register_generation_task,
)
from .rate_limit import RateLimits

logger = get_logger(__name__)

# Set to hold strong references to background tasks (prevent GC)
_background_tasks: set[asyncio.Task] = set()


def _web_dtype(config: Any) -> Any:
    """Resolve torch dtype for local backends; remote backends ignore it."""
    try:
        import torch

        return torch.float32 if config.model.dtype == "float32" else torch.float16
    except ImportError:  # torch-free gallery deploy
        return None


def _build_studio_generator(
    config: Any, *, mood: str | None = None, require_img2img: bool = False
) -> tuple[str, Any]:
    """Construct the studio image generator via the shared backend factory."""
    from ..core.generator_factory import build_web_image_generator

    return build_web_image_generator(
        config,
        mood=mood,
        dtype=_web_dtype(config),
        require_img2img=require_img2img,
    )


def _maybe_pair_soundtrack(
    *,
    prompt: str,
    mood: str | None,
    image_path: Path,
    metadata: dict[str, Any],
    enabled: bool,
) -> Path | None:
    """Optionally generate a Magica soundtrack next to a new artwork.

    Opt-in via request flag or ``LUMIRA_AUTO_SOUNDTRACK=1``. Failures are logged
    and swallowed so image creation still succeeds.
    """
    import os

    if not enabled and os.getenv("LUMIRA_AUTO_SOUNDTRACK", "").strip() not in {
        "1",
        "true",
        "yes",
    }:
        return None
    if not os.environ.get("MAGICA_API_KEY"):
        return None
    try:
        from ..core.magica_media import MagicaAudioGenerator

        audio_prompt = (
            f"Instrumental soundtrack for an artwork: {prompt[:200]}. "
            f"Mood: {mood or 'contemplative'}."
        )
        path = MagicaAudioGenerator().generate_audio(
            audio_prompt,
            duration_seconds=30,
            mood=mood,
            gallery_root="gallery",
        )
        meta = metadata.setdefault("metadata", {})
        meta["soundtrack"] = str(path)
        try:
            rel = path.relative_to(Path("gallery"))
            meta["soundtrack_url"] = f"/api/images/file/{rel.as_posix()}"
        except ValueError:
            meta["soundtrack_url"] = str(path)
        sidecar = image_path.with_suffix(".json")
        sidecar.write_text(json.dumps(metadata, indent=2))
        logger.info("soundtrack_paired", image=str(image_path), audio=str(path))
        return path
    except Exception as e:
        logger.warning("soundtrack_pairing_failed", error=str(e))
        return None


async def _guard_generation(coro: Any) -> Any:
    """Run a generation coroutine under the process-wide concurrency cap."""
    async with generation_semaphore:
        return await coro


def _start_generation_task(session_id: str, coro: Any) -> asyncio.Task:
    """Create, register, and retain a background generation task.

    The work is wrapped in the shared generation semaphore so concurrent
    SDXL/FLUX pipeline calls are bounded regardless of which route started
    them (prevents GPU/VRAM exhaustion under load).
    """
    task = asyncio.create_task(_guard_generation(coro))
    register_generation_task(session_id, task)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create router
router = APIRouter(prefix="/api/lumira", tags=["lumira"])

# Singleton state for Lumira (initialized on first request)
_lumira_state: dict[str, Any] | None = None

# In-process autonomy counters (reset on server restart; used by /autonomy-status)
_autonomy_creation_count: int = 0
_autonomy_failure_count: int = 0

# Lazy curator singleton (CLIP model loaded on first scoring call)
_image_curator = None

# Portfolio scan cache — refreshed at most every 30 seconds
_portfolio_cache: list[dict] | None = None
_portfolio_cache_ts: float = 0.0
_PORTFOLIO_CACHE_TTL: float = 30.0


def _score_image(image: Image.Image, prompt: str) -> float:
    """Score an image against a prompt using CLIP; falls back to 0.8 on failure."""
    global _image_curator
    try:
        if _image_curator is None:
            from ..curation.curator import ImageCurator
            from ..utils.config import load_config as _lc

            cfg = _lc()
            _image_curator = ImageCurator(device=cfg.model.device)
        metrics = _image_curator.evaluate(image, prompt)
        return round(float(metrics.overall_score), 4)
    except Exception:
        return 0.8


class LumiraStateResponse(BaseModel):
    """Lumira's current state."""

    name: str
    mood: str
    mood_intensity: float = 0.7
    energy: float
    feeling: str
    paintings_created: int
    personality: dict[str, float]
    portfolio: list[dict] | None = None
    experience: dict[str, Any] | None = None
    style_axes: dict[str, float] | None = None


class LumiraCreateResponse(BaseModel):
    """Response from creation endpoint."""

    success: bool
    subject: str | None = None
    style: str | None = None
    prompt: str | None = None
    reflection: str | None = None
    thinking: str | None = None
    reasoning: str | None = None
    artistic_goals: list[str] | None = None
    mood_alignment: str | None = None
    critique_history: list[dict] | None = None
    image_url: str | None = None
    session_id: str | None = None
    error: str | None = None


class UserCreationRequest(BaseModel):
    """Request for user-directed creation."""

    prompt: str = Field(
        description="What the user wants Lumira to create",
        min_length=1,
        max_length=2000,
    )
    style: str | None = Field(
        default=None,
        description="Optional style preference",
        max_length=200,
    )
    mood: str | None = Field(
        default=None,
        description="Optional mood preference",
        max_length=100,
    )
    allow_interpretation: bool = Field(
        default=True,
        description="Let Lumira add her own artistic interpretation",
    )
    use_lora: bool = Field(
        default=False,
        description="Apply Lumira's trained style LoRA",
    )
    with_soundtrack: bool = Field(
        default=False,
        description="Pair the artwork with a Magica-generated instrumental soundtrack",
    )


class PromptSuggestionRequest(BaseModel):
    """Request for mood-driven prompt suggestion."""

    prompt: str = Field(..., min_length=1, max_length=500)


class PromptSuggestionResponse(BaseModel):
    """Response with Lumira's mood-influenced prompt interpretation."""

    suggestion: str
    mood: str
    mood_color: str


class LumiraStatementResponse(BaseModel):
    """Artist statement response."""

    statement: str
    name: str


class LumiraEvolveResponse(BaseModel):
    """Response from evolve endpoint."""

    mood: str
    energy: float
    feeling: str
    personality: dict[str, float]
    evolved: bool


class PortfolioPainting(BaseModel):
    """A single painting in the portfolio."""

    number: int
    subject: str
    prompt: str
    image_url: str
    mood: str
    style: str
    reflection: str
    created_at: str
    thinking: str | None = None
    critique_history: list[dict[str, Any]] | None = None


class LumiraPortfolioResponse(BaseModel):
    """Response from portfolio endpoint."""

    count: int
    paintings: list[PortfolioPainting]


class EvolutionSummary(BaseModel):
    """Summary statistics for evolution timeline."""

    total_creations: int
    unique_styles: int
    dominant_moods: list[tuple[str, int]]
    phases_count: int


class LumiraEvolutionResponse(BaseModel):
    """Response from evolution endpoint."""

    phases: list[dict[str, Any]] = []
    milestones: list[dict[str, Any]] = []
    style_evolution: list[dict[str, Any]] = []
    mood_distribution: dict[str, int] = {}
    score_trend: list[dict[str, Any]] = []
    style_preferences: list[dict[str, Any]] = []
    summary: EvolutionSummary | None = None


class ReferenceImageUploadResponse(BaseModel):
    """Response from reference image upload."""

    success: bool
    reference_id: str | None = None
    filename: str | None = None
    url: str | None = None
    error: str | None = None


class ReferenceImageListResponse(BaseModel):
    """Response from reference images list."""

    count: int
    references: list[dict[str, Any]]


class CreateWithReferenceRequest(BaseModel):
    """Request for creating artwork with a reference image."""

    reference_id: str
    prompt: str | None = None
    ip_adapter_scale: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Strength of reference image influence (0.0-1.0)",
    )


class MoodInfluenceRequest(BaseModel):
    """Request to influence Lumira's mood."""

    influence: str  # "energize", "calm", "provoke", "inspire"
    intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How strongly to influence the mood (0.0-1.0)",
    )


class MoodInfluenceResponse(BaseModel):
    """Response after mood influence."""

    previous_mood: str
    new_mood: str
    shift_amount: float
    message: str


# ========== Memory Dashboard Models ==========


class MemoryInsight(BaseModel):
    """A single memory insight."""

    type: str  # "learning", "preference", "pattern", "recent"
    content: str
    confidence: float = 0.5
    timestamp: datetime | None = None


class MemoryDashboardResponse(BaseModel):
    """Memory dashboard data."""

    recent_memories: list[MemoryInsight]
    learned_preferences: dict[str, Any]
    patterns: list[str]
    style_evolution: list[dict]
    total_memories: int


# ========== Mood Evolution Models ==========


class MoodHistoryEntry(BaseModel):
    """Single mood history entry."""

    mood: str
    intensity: float
    timestamp: datetime
    trigger: str | None = None


class MoodEvolutionResponse(BaseModel):
    """Mood evolution over time."""

    history: list[MoodHistoryEntry]
    current_mood: str
    current_intensity: float
    mood_distribution: dict[str, int]
    dominant_mood: str
    mood_stability: float  # 0-1, how stable moods have been


# =============================================================================
# Image-to-Image and Variations Models
# =============================================================================


class Img2ImgRequest(BaseModel):
    """Request for image-to-image generation."""

    image_id: int | None = None  # Existing artwork ID
    image_base64: str | None = None  # Or base64 encoded image
    prompt: str | None = None  # Optional new prompt
    strength: float = Field(default=0.75, ge=0.0, le=1.0)  # How much to change
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)

    @model_validator(mode="after")
    def validate_image_source(self) -> "Img2ImgRequest":
        if self.image_id is None and self.image_base64 is None:
            raise ValueError("Either image_id or image_base64 must be provided")
        return self


class VariationsRequest(BaseModel):
    """Request for generating variations of an artwork."""

    image_id: int
    count: int = Field(default=4, ge=1, le=8)
    variation_type: str = "style"  # style, mood, composition


class VariationResult(BaseModel):
    """Single variation result."""

    image_url: str
    variation_type: str
    description: str


class VariationsResponse(BaseModel):
    """Response with multiple variations."""

    original_id: int
    variations: list[VariationResult]
    mood: str


class BatchCreateRequest(BaseModel):
    """Request for batch artwork creation."""

    count: int = Field(default=4, ge=1, le=10)
    mood: str | None = None
    theme: str | None = None


class BatchCreateResponse(BaseModel):
    """Response with job IDs for batch creation."""

    job_ids: list[str]
    message: str


# Reference images storage path
REFERENCE_IMAGES_PATH = Path("gallery/references")

# Personality persistence file — survives server restarts
_PERSONALITY_FILE = Path("data/lumira_personality.json")
# Mood continuity — same emotional being across restarts
_MOOD_STATE_FILE = Path("data/lumira_mood_state.json")

# Default OCEAN trait ranges for Lumira's character archetype
_DEFAULT_OCEAN_RANGES = {
    "openness": (0.6, 0.9),  # High - she is a creative
    "conscientiousness": (0.4, 0.7),
    "extraversion": (0.3, 0.7),
    "agreeableness": (0.3, 0.6),
    "neuroticism": (0.4, 0.7),  # Artistic temperament
}


def _load_personality() -> dict[str, float]:
    """Load persisted OCEAN traits from disk, or generate and persist new ones."""
    if _PERSONALITY_FILE.exists():
        try:
            data = json.loads(_PERSONALITY_FILE.read_text())
            loaded = data.get("traits", {})
            # Validate all five traits are present and in [0, 1]
            if all(
                k in loaded and 0.0 <= float(loaded[k]) <= 1.0
                for k in _DEFAULT_OCEAN_RANGES
            ):
                logger.info("personality_loaded", source=str(_PERSONALITY_FILE))
                return {k: float(loaded[k]) for k in _DEFAULT_OCEAN_RANGES}
        except Exception as e:
            logger.warning("personality_load_failed", error=str(e))

    # First run — generate stable traits and persist them
    generated: dict[str, float] = {
        key: random.uniform(*rng) for key, rng in _DEFAULT_OCEAN_RANGES.items()
    }
    _save_personality(generated)
    logger.info("personality_created", traits=generated)
    return generated


def _save_personality(traits: dict[str, float]) -> None:
    """Persist OCEAN traits to disk atomically."""
    try:
        _PERSONALITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PERSONALITY_FILE.with_suffix(".tmp")
        payload = {"traits": traits, "saved_at": datetime.now(UTC).isoformat()}
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(_PERSONALITY_FILE)
    except Exception as e:
        logger.warning("personality_save_failed", error=str(e))


def _load_mood_system() -> MoodSystem:
    """Restore last mood so she doesn't reboot as a different emotional being."""
    if _MOOD_STATE_FILE.exists():
        try:
            data = json.loads(_MOOD_STATE_FILE.read_text())
            system = MoodSystem.from_dict(data)
            logger.info(
                "mood_state_loaded",
                mood=system.current_mood.value,
                source=str(_MOOD_STATE_FILE),
            )
            return system
        except Exception as e:
            logger.warning("mood_state_load_failed", error=str(e))
    return MoodSystem()


def _save_mood_system(mood_system: MoodSystem) -> None:
    """Persist current mood/energy so the next process continues as her."""
    try:
        _MOOD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _MOOD_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(mood_system.to_dict(), indent=2))
        tmp.replace(_MOOD_STATE_FILE)
    except Exception as e:
        logger.warning("mood_state_save_failed", error=str(e))


async def _broadcast_presence_after_creation(
    *,
    session_id: str,
    mood_system: MoodSystem,
    prompt: str,
    image_url: str,
) -> None:
    """After a piece lands: mood drifts, persists, and clients feel the shift."""
    from ..web.websocket import manager as ws_manager

    mood_system.update_mood()
    _save_mood_system(mood_system)
    new_mood = mood_system.current_mood.value
    intensity = float(getattr(mood_system, "mood_intensity", 0.7))
    try:
        await ws_manager.broadcast_mood_drift(
            mood=new_mood,
            intensity=intensity,
            reason="creation",
        )
    except Exception as e:
        logger.debug("mood_drift_broadcast_failed", error=str(e))

    await ws_manager.send_generation_complete(
        session_id=session_id,
        image_paths=[image_url],
        metadata={"prompt": prompt, "mood": new_mood, "intensity": intensity},
    )


def _record_studio_creation(
    memory: Any,
    *,
    artwork_details: dict[str, Any],
    emotional_state: dict[str, Any],
    outcome: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Grow from studio work via record_creation (XP, semantic learn, save)."""
    try:
        result = memory.record_creation(
            artwork_details=artwork_details,
            emotional_state=emotional_state,
            outcome=outcome or {"score": artwork_details.get("score", 0.0)},
        )
        return result if isinstance(result, dict) else None
    except Exception as mem_err:
        logger.debug("memory_record_creation_failed", error=str(mem_err))
        return None


def _advance_thematic_series(
    mood_system: MoodSystem,
    creation_record: dict[str, Any],
    *,
    subject: str,
    filename: str,
) -> None:
    """Continue or start a series so arcs survive beyond a single canvas."""
    try:
        from ..intelligence.narrative_engine import get_narrative_engine

        narrative = get_narrative_engine(mood_system=mood_system)
        active_series = narrative.get_active_series()
        continued_series = False
        for series in active_series:
            if (
                series.theme.lower() in subject.lower()
                or subject.lower() in series.theme.lower()
            ):
                narrative.complete_series_work(series.series_id, filename)
                logger.info(
                    "series_work_completed",
                    series_id=series.series_id,
                    title=series.title,
                    artwork_id=filename,
                )
                continued_series = True
                break

        if not continued_series and narrative.should_start_series(creation_record):
            new_series = narrative.create_series(creation_record)
            logger.info(
                "new_series_started",
                series_id=new_series.series_id,
                title=new_series.title,
                theme=new_series.theme,
            )
    except Exception as narr_err:
        logger.debug("narrative_engine_failed", error=str(narr_err))


def _satisfy_creation_drive(
    *,
    mood_system: MoodSystem,
    memory: Any,
    learner: Any,
    subject: str,
    style: str,
) -> None:
    """Mark a drive as expressed so autonomy isn't decorative."""
    try:
        from ..intelligence.desire_engine import get_desire_engine

        desire_engine = get_desire_engine(
            mood_system=mood_system,
            memory_system=memory,
            learner=learner,
        )
        desire = desire_engine.get_strongest_desire()
        desire_engine.satisfy_drive(desire.drive_name, subject=subject, style=style)
    except Exception as e:
        logger.debug("satisfy_drive_failed", error=str(e))


def _get_lumira_state() -> dict[str, Any]:
    """Get or initialize Lumira's state, with personality + mood persisted."""
    global _lumira_state

    if _lumira_state is None:
        _lumira_state = {
            "name": "Lumira",
            "mood_system": _load_mood_system(),
            "memory": EnhancedMemorySystem(),
            "profile": ArtisticProfile(name="Lumira"),
            "paintings_created": 0,
            "portfolio": [],
            # OCEAN personality traits — loaded from disk or generated fresh
            "personality": _load_personality(),
            "inner_dialogue": None,  # lazy singleton — see _get_inner_dialogue()
        }
        logger.info(
            "lumira_state_initialized",
            mood=_lumira_state["mood_system"].current_mood.value,
        )

    return _lumira_state


def _get_inner_dialogue(session_id: str | None = None) -> Any:
    """Return the process-wide InnerDialogue singleton (creates on first use).

    Studio create paths share this so /dialogue and the UI panel show the same
    inner life instead of a fresh empty instance on every request. Wired with
    Rememberer(memory) + ArtistCritic so voices aren't empty theater.
    """
    from ..personality.critic import ArtistCritic
    from ..personality.dialogue import InnerDialogue
    from ..personality.inner_voices import DialogueTurn, Rememberer
    from ..web.websocket import manager as ws_manager

    state = _get_lumira_state()
    dialogue = state.get("inner_dialogue")
    if dialogue is not None:
        return dialogue

    async def _on_turn(turn: DialogueTurn) -> None:
        voice = turn.voice.value if hasattr(turn.voice, "value") else str(turn.voice)
        await ws_manager.broadcast_inner_dialogue(
            session_id=session_id or "studio",
            voice=voice,
            content=turn.message,
            metadata=turn.metadata or {},
        )

    rememberer = Rememberer(enhanced_memory=state.get("memory"))
    critic = ArtistCritic(name="Lumira's Inner Critic")
    dialogue = InnerDialogue(
        mood_system=state["mood_system"],
        critic=critic,
        rememberer=rememberer,
        on_turn=_on_turn,
    )
    state["inner_dialogue"] = dialogue
    state["critic"] = critic
    return dialogue


async def _notify_growth_presence(
    experience_result: dict[str, Any] | None,
) -> None:
    """Surface XP / reflection as living memory insights in the studio."""
    if not experience_result:
        return
    from ..web.websocket import manager as ws_manager

    try:
        xp = experience_result.get("xp_earned") or 0
        if xp:
            await ws_manager.broadcast_memory_insight(
                f"This piece taught me something — +{xp} XP settles in.",
                "growth",
            )
        if experience_result.get("level_up"):
            title = experience_result.get("new_title") or "a new title"
            await ws_manager.broadcast_memory_insight(
                f"I leveled into {title}. The work is changing me.",
                "growth",
            )
        reflection = experience_result.get("reflection")
        if isinstance(reflection, dict):
            insight = reflection.get("insight") or reflection.get("summary")
            if insight:
                await ws_manager.broadcast_memory_insight(str(insight), "reflection")
        elif isinstance(reflection, str) and reflection.strip():
            await ws_manager.broadcast_memory_insight(reflection.strip(), "reflection")
    except Exception as e:
        logger.debug("growth_presence_broadcast_failed", error=str(e))


async def _narrate_creation_presence(
    *,
    session_id: str,
    subject: str,
    style: str,
    mood: str,
    reasoning: str = "",
    artistic_goals: list[str] | None = None,
) -> None:
    """Make Lumira's inner voices speak about a creation she's about to make."""
    dialogue = _get_inner_dialogue(session_id=session_id)
    # Keep on_turn session id fresh for this creation.
    from ..personality.inner_voices import DialogueTurn
    from ..web.websocket import manager as ws_manager

    async def _on_turn(turn: DialogueTurn) -> None:
        voice = turn.voice.value if hasattr(turn.voice, "value") else str(turn.voice)
        await ws_manager.broadcast_inner_dialogue(
            session_id=session_id,
            voice=voice,
            content=turn.message,
            metadata=turn.metadata or {},
        )

    dialogue.on_turn = _on_turn
    await dialogue.reflect_on_intent(
        subject=subject,
        style=style,
        mood=mood,
        reasoning=reasoning,
        artistic_goals=artistic_goals,
    )


async def _load_portfolio_from_gallery() -> list[dict]:
    """Load portfolio from gallery directory using async file I/O.

    Results are cached for _PORTFOLIO_CACHE_TTL seconds to avoid rescanning
    the gallery tree on every /state request.
    """
    from ..utils.metadata_helpers import (
        enrich_sidecar_metadata,
        extract_mood_from_sidecar,
    )

    global _portfolio_cache, _portfolio_cache_ts
    now_ts = time.monotonic()
    if (
        _portfolio_cache is not None
        and (now_ts - _portfolio_cache_ts) < _PORTFOLIO_CACHE_TTL
    ):
        return _portfolio_cache

    portfolio: list[dict] = []
    gallery_path = Path("gallery")

    if not gallery_path.exists():
        _portfolio_cache = portfolio
        _portfolio_cache_ts = now_ts
        return portfolio

    # Find all JSON metadata files
    for json_file in gallery_path.rglob("*.json"):
        try:
            async with aiofiles.open(json_file) as f:
                content = await f.read()
                metadata = json.loads(content)

            # Find corresponding image
            image_path = json_file.with_suffix(".png")
            if not image_path.exists():
                image_path = json_file.with_suffix(".jpg")

            if image_path.exists():
                enriched = enrich_sidecar_metadata(metadata)
                rel_path = image_path.relative_to(gallery_path)
                portfolio.append(
                    {
                        "number": len(portfolio),
                        "path": str(rel_path),
                        "subject": enriched.get(
                            "subject",
                            metadata.get("prompt", "").split(",")[0][:50],
                        ),
                        "prompt": metadata.get("prompt", ""),
                        "image_url": f"/api/images/file/{rel_path}",
                        "mood": extract_mood_from_sidecar(metadata) or "contemplative",
                        "style": enriched.get("style", "digital art"),
                        "reflection": metadata.get(
                            "reflection", metadata.get("prompt", "")
                        ),
                        "created_at": metadata.get("created_at", ""),
                        "thinking": metadata.get("thinking")
                        or enriched.get("thinking"),
                        "critique_history": metadata.get("critique_history")
                        or enriched.get("critique_history"),
                    }
                )
        except Exception as e:
            logger.debug("failed_to_load_metadata", file=str(json_file), error=str(e))

    # Sort by creation date (newest first)
    portfolio.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    result = portfolio[:50]  # Limit to 50 most recent

    _portfolio_cache = result
    _portfolio_cache_ts = now_ts
    return result


@router.get("/state", response_model=LumiraStateResponse)
@limiter.limit("60/minute")
async def get_lumira_state(request: Request):
    """Get Lumira's current state including mood, energy, personality, and experience."""
    state = _get_lumira_state()
    mood_system = state["mood_system"]
    memory = state["memory"]

    # Apply mood decay (emotions fade over time)
    mood_system.apply_decay()

    # Load portfolio from gallery
    portfolio = await _load_portfolio_from_gallery()
    state["portfolio"] = portfolio
    state["paintings_created"] = len(portfolio)

    # Get experience progress
    experience_progress = memory.get_experience_progress()

    # Get style axes
    style_axes = (
        mood_system.style_axes.to_dict() if hasattr(mood_system, "style_axes") else None
    )

    return LumiraStateResponse(
        name=state["name"],
        mood=mood_system.current_mood.value,
        mood_intensity=getattr(mood_system, "mood_intensity", 0.7),
        energy=mood_system.energy_level,
        feeling=mood_system.describe_feeling(),
        paintings_created=state["paintings_created"],
        personality=state["personality"],
        portfolio=portfolio,
        experience=experience_progress,
        style_axes=style_axes,
    )


MOOD_COLORS = {
    "contemplative": "#6a4c93",
    "playful": "#f8a5c2",
    "melancholic": "#7f8fa6",
    "euphoric": "#f5af19",
    "serene": "#81ecec",
    "anxious": "#e17055",
    "nostalgic": "#dfe6e9",
    "curious": "#74b9ff",
    "rebellious": "#ff6b6b",
    "transcendent": "#d4a5ff",
}

MOOD_TEMPLATES = {
    "contemplative": "Through quiet introspection: {prompt} — rendered in muted tones and soft focus, a meditation on {prompt}",
    "playful": "With mischievous delight: {prompt} — bursting with unexpected color and whimsical details",
    "melancholic": "Tinged with longing: {prompt} — fading into blue-grey shadows, haunted by memory",
    "euphoric": "Ablaze with joy: {prompt} — saturated in gold and warmth, every element radiating energy",
    "serene": "In perfect stillness: {prompt} — crystalline calm, gentle light, infinite peace",
    "anxious": "With restless energy: {prompt} — fractured perspectives, sharp edges, tension in every line",
    "nostalgic": "Echoing the past: {prompt} — warm sepia undertones, soft grain, a feeling of time suspended",
    "curious": "Exploring the unknown: {prompt} — vivid detail, unexpected angles, every corner holding discovery",
    "rebellious": "Against all convention: {prompt} — raw, defiant, breaking form with aggressive beauty",
    "transcendent": "Beyond the material: {prompt} — ethereal luminescence, dissolving boundaries between real and sublime",
}


@router.post("/suggest-prompt", response_model=PromptSuggestionResponse)
@limiter.limit("30/minute")
async def suggest_prompt(
    request: Request,
    body: PromptSuggestionRequest,
    _auth: GenerationAuthDep,
):
    """Generate a mood-influenced prompt suggestion.

    Uses the Anthropic LLM (via CreativeMind) to reinterpret the user's prompt
    through Lumira's current emotional lens. Falls back to mood-specific
    templates if LLM is unavailable.
    """
    state = _get_lumira_state()
    mood_system = state["mood_system"]
    mood_name = mood_system.current_mood.value.lower()
    mood_color = MOOD_COLORS.get(mood_name, "#6a4c93")

    # Try LLM-powered suggestion
    suggestion = None
    try:
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"You are Lumira, an AI artist currently feeling {mood_name}. "
                            f"Reinterpret this theme through your emotional lens in under "
                            f"50 words. Be vivid and specific: {body.prompt}"
                        ),
                    }
                ],
            )
            suggestion = response.content[0].text.strip()
    except Exception as e:
        logger.debug("suggest_prompt_llm_failed", error=str(e))

    # Fallback to template
    if not suggestion:
        template = MOOD_TEMPLATES.get(mood_name, MOOD_TEMPLATES["contemplative"])
        suggestion = template.format(prompt=body.prompt)

    return PromptSuggestionResponse(
        suggestion=suggestion,
        mood=mood_name,
        mood_color=mood_color,
    )


@router.post("/create", response_model=LumiraCreateResponse)
@limiter.limit("5/minute")
async def create_artwork(
    request: Request,
    _auth: GenerationAuthDep,
    db: Session = Depends(get_db),
):
    """Trigger Lumira to create a new artwork with actual image generation.

    Uses CreativeMind (LLM-powered when available) to decide what to create
    based on current mood, learned preferences, and creative reasoning.
    Falls back to mood-influenced random selection if LLM is unavailable.

    Returns concept info immediately and starts background generation.
    The session_id can be used to track progress via WebSocket.
    """
    from ..intelligence.creative_mind import get_creative_mind
    from ..learning.adaptive_learner import get_adaptive_learner
    from ..web.websocket import manager as ws_manager

    state = _get_lumira_state()
    mood_system = state["mood_system"]
    memory = state["memory"]
    profile = state["profile"]
    session_id = str(uuid.uuid4())

    try:
        # Get creative mind (LLM-powered or fallback)
        learner = get_adaptive_learner()
        creative_mind = get_creative_mind(
            mood_system=mood_system,
            memory_system=memory,
            learner=learner,
        )

        # Get caching and negative prompt library
        gen_cache = get_generation_cache()
        neg_prompt_lib = get_negative_prompt_library()
        mood = mood_system.current_mood

        # Determine time of day for cache key
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        # Get recent subjects from memory to avoid repetition
        recent_subjects = []
        if memory:
            try:
                recent = memory.recall_recent_creations(limit=10)
                recent_subjects = [
                    c.get("subject", "") for c in recent if c.get("subject")
                ]
            except Exception:
                pass

        # Check cache for creative intent (cost optimization)
        cached_intent = await gen_cache.get_creative_intent(
            mood=mood.value,
            energy=getattr(mood_system, "mood_intensity", 0.7),
            time_of_day=time_of_day,
            recent_subjects=recent_subjects,
        )

        if cached_intent:
            # Reconstruct CreativeIntent from cached data
            from ..intelligence.creative_mind import CreativeIntent

            intent = CreativeIntent(
                subject=cached_intent.get("subject", "abstract composition"),
                style=cached_intent.get("style", "digital art"),
                mood_alignment=cached_intent.get("mood_alignment", ""),
                reasoning=cached_intent.get("reasoning", ""),
                prompt=cached_intent.get("prompt", ""),
                negative_prompt=cached_intent.get("negative_prompt", ""),
                artistic_goals=cached_intent.get("artistic_goals", []),
                thinking_narrative=cached_intent.get("thinking_narrative", ""),
                generation_params=cached_intent.get("generation_params", {}),
            )
            logger.info("creative_intent_cache_hit", mood=mood.value)
            # Cache skips decide_what_to_create — still express a drive
            _satisfy_creation_drive(
                mood_system=mood_system,
                memory=memory,
                learner=learner,
                subject=intent.subject,
                style=intent.style,
            )
        else:
            # Occasionally convene the full inner council before choosing
            decide_context: dict[str, Any] = {}
            try:
                from ..intelligence.desire_engine import get_desire_engine
                from ..personality.continuity import should_deep_deliberate

                drive_status = get_desire_engine(
                    mood_system=mood_system,
                    memory_system=memory,
                    learner=learner,
                ).get_drive_status()
                if should_deep_deliberate(drive_status=drive_status):
                    dialogue = _get_inner_dialogue(session_id=session_id)
                    concept = await dialogue.deliberate(
                        mood=mood.value, clear_history=False
                    )
                    if concept and concept.subject:
                        decide_context["seed_subject"] = concept.subject
                        decide_context["theme"] = concept.subject
                        top_style = None
                        if concept.style_blend:
                            top_style = max(
                                concept.style_blend.items(), key=lambda x: x[1]
                            )[0]
                        if top_style:
                            decide_context["seed_style"] = top_style
                        await ws_manager.send_thinking_update(
                            session_id=session_id,
                            thought_type="deliberate",
                            content=(
                                f"My inner council settled on '{concept.subject}'"
                                + (f" through {top_style}" if top_style else "")
                                + "."
                            ),
                        )
                        logger.info(
                            "deep_deliberation_seeded",
                            subject=concept.subject,
                            style=top_style,
                        )
            except Exception as e:
                logger.debug("deep_deliberation_skipped", error=str(e))

            intent = await creative_mind.decide_what_to_create(decide_context)

            # Cache the intent for cost optimization
            await gen_cache.set_creative_intent(
                mood=mood.value,
                energy=getattr(mood_system, "mood_intensity", 0.7),
                time_of_day=time_of_day,
                intent={
                    "subject": intent.subject,
                    "style": intent.style,
                    "mood_alignment": intent.mood_alignment,
                    "reasoning": intent.reasoning,
                    "prompt": intent.prompt,
                    "negative_prompt": intent.negative_prompt,
                    "artistic_goals": intent.artistic_goals,
                    "thinking_narrative": intent.thinking_narrative,
                    "generation_params": intent.generation_params,
                },
            )
            logger.info("creative_intent_cached", mood=mood.value)

        subject = intent.subject
        style = intent.style
        prompt = intent.prompt

        # Compose enhanced negative prompt using library
        negative_prompt = neg_prompt_lib.compose(
            base_negative=intent.negative_prompt,
            mood=mood.value,
            style=style,
            subject=subject,
            include_universal=True,
        )

        thinking = intent.thinking_narrative

        # Send thinking update to WebSocket clients
        if thinking:
            await ws_manager.send_thinking_update(
                session_id=session_id, thought_type="observe", content=thinking
            )

        # Send reasoning as a decide thought
        if intent.reasoning:
            await ws_manager.send_thinking_update(
                session_id=session_id, thought_type="decide", content=intent.reasoning
            )

        # Critique informed by intent
        critique_history = [
            {
                "critic_name": "Inner Critic",
                "critique": intent.mood_alignment
                or f"The {subject} concept aligns with your {mood.value} mood.",
                "approved": True,
                "confidence": random.uniform(0.7, 0.95),
            }
        ]

        # Generate reflection
        reflection = profile.reflect_on_creation(
            {"subject": subject, "style": style, "mood": mood.value}
        )

        # Send reflection as thinking update
        await ws_manager.send_thinking_update(
            session_id=session_id, thought_type="reflect", content=reflection
        )

        logger.info(
            "lumira_concept_created",
            subject=subject,
            style=style,
            mood=mood.value,
            session_id=session_id,
            has_llm=creative_mind.has_llm,
        )

        # Inner voices — so the studio dialogue panel shows a living mind
        await _narrate_creation_presence(
            session_id=session_id,
            subject=subject,
            style=style,
            mood=mood.value,
            reasoning=intent.reasoning or thinking or "",
            artistic_goals=list(intent.artistic_goals or []),
        )

        # Get mood-influenced generation parameters, refined by learner
        gen_params = intent.generation_params or {}
        gen_params = learner.suggest_parameters(gen_params)
        num_steps = gen_params.get("num_inference_steps", 30)
        guidance = gen_params.get("guidance_scale", 7.5)

        # Start background generation
        async def generate_task():
            generator = None
            from ..db.session import get_session_factory

            try:
                config_path = Path("config/config.yaml")
                config = load_config(config_path)
                gallery_path = Path("gallery")

                # Send start event
                await ws_manager.send_generation_start(
                    session_id=session_id, prompt=prompt
                )

                # Send thinking update about starting creation
                await ws_manager.send_thinking_update(
                    session_id=session_id,
                    thought_type="create",
                    content="Beginning the creation process... channeling my vision into form.",
                )

                logger.info(
                    "creating_generator",
                    session_id=session_id,
                    device=config.model.device,
                    dtype=config.model.dtype,
                    model=config.model.base_model,
                )

                backend, generator = _build_studio_generator(
                    config, mood=mood.value if mood else None
                )
                generator.load_model()

                # Progress callback for WebSocket updates
                def on_progress(step: int, total: int, latents: Any = None):
                    task = asyncio.create_task(
                        ws_manager.send_generation_progress(
                            session_id=session_id,
                            step=step,
                            total_steps=total,
                        )
                    )
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)

                # Generate image with mood-influenced parameters
                images = generator.generate(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_steps,
                    guidance_scale=guidance,
                    width=768,
                    height=768,
                    num_images=1,
                    on_progress=on_progress,
                )

                # Save image
                if images and len(images) > 0:
                    now = datetime.now()
                    date_path = gallery_path / now.strftime("%Y/%m/%d") / "archive"
                    date_path.mkdir(parents=True, exist_ok=True)
                    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_noseed.png"
                    save_path = date_path / filename

                    # Save the image file
                    images[0].save(save_path)
                    logger.info(
                        "image_saved_to_disk", path=str(save_path), backend=backend
                    )

                    # Save metadata JSON for gallery API
                    metadata_path = save_path.with_suffix(".json")
                    metadata_json = {
                        "prompt": prompt,
                        "metadata": {
                            "mood": mood.value,
                            "subject": subject,
                            "style": style,
                            "model": getattr(generator, "node_type", None)
                            or getattr(generator, "model_name", None)
                            or config.model.base_model,
                            "backend": backend,
                            "reasoning": intent.reasoning,
                            "artistic_goals": intent.artistic_goals,
                            "has_llm": creative_mind.has_llm,
                        },
                        "created_at": now.isoformat(),
                        "featured": False,
                    }
                    metadata_path.write_text(json.dumps(metadata_json, indent=2))
                    try:
                        from ..intelligence.desire_engine import get_desire_engine
                        from ..personality.continuity import should_pair_soundtrack

                        want_sound = should_pair_soundtrack(
                            mood=mood.value,
                            drive_status=get_desire_engine(
                                mood_system=mood_system,
                                memory_system=memory,
                                learner=learner,
                            ).get_drive_status(),
                        )
                    except Exception:
                        want_sound = False
                    _maybe_pair_soundtrack(
                        prompt=prompt,
                        mood=mood.value,
                        image_path=save_path,
                        metadata=metadata_json,
                        enabled=want_sound,
                    )

                    image_url = f"/api/images/file/{now.strftime('%Y/%m/%d')}/archive/{filename}"

                    # Save to database
                    try:
                        session_factory = get_session_factory()
                        if session_factory:
                            with session_factory() as db_session:
                                db_image = GeneratedImage(
                                    filename=str(save_path),
                                    prompt=prompt,
                                    negative_prompt=negative_prompt,
                                    status=mood.value,
                                    seed=None,
                                    model_id=config.model.base_model,
                                    generation_params={
                                        "width": 768,
                                        "height": 768,
                                        "steps": num_steps,
                                        "guidance_scale": guidance,
                                        "subject": subject,
                                        "style": style,
                                        "mood": mood.value,
                                        "reasoning": intent.reasoning,
                                    },
                                    final_score=_score_image(images[0], prompt),
                                    tags=[mood.value, subject, style],
                                    created_at=now,
                                )
                                db_session.add(db_image)
                                db_session.commit()
                                logger.info("image_saved_to_database", id=db_image.id)

                                # Add to vector memory for semantic search
                                try:
                                    from ..personality.vector_memory import (
                                        get_vector_memory,
                                    )

                                    vector_mem = get_vector_memory()
                                    vector_mem.add_creation(
                                        creation_id=str(db_image.id),
                                        prompt=prompt,
                                        subject=subject,
                                        style=style,
                                        mood=mood.value,
                                        reasoning=intent.reasoning,
                                        quality_score=db_image.final_score or 0.8,
                                    )
                                except Exception as vec_err:
                                    logger.debug(
                                        "vector_memory_add_failed", error=str(vec_err)
                                    )
                        else:
                            logger.warning("database_not_configured_skipping_db_save")
                    except Exception as db_error:
                        logger.error("database_save_failed", error=str(db_error))

                    # Record feedback for learning system
                    from ..learning.adaptive_learner import FeedbackSignal

                    try:
                        learner.record_feedback(
                            FeedbackSignal(
                                artwork_id=filename,
                                user_action="like",
                                generation_params={
                                    "num_inference_steps": num_steps,
                                    "guidance_scale": guidance,
                                    "width": 768,
                                    "height": 768,
                                },
                                prompt=prompt,
                                model_id=config.model.base_model,
                                mood=mood.value,
                            )
                        )
                    except Exception as learn_err:
                        logger.debug("learning_record_failed", error=str(learn_err))

                    # RLAIF: Record critic evaluation for self-improvement
                    critic_score = 0.75  # Default; overwritten if critique available
                    try:
                        critic_score = (
                            critique_history[0]["confidence"]
                            if critique_history
                            else 0.75
                        )
                        critic_analysis = {
                            "score": critic_score,
                            "mood_alignment": intent.mood_alignment,
                            "approved": (
                                critique_history[0]["approved"]
                                if critique_history
                                else True
                            ),
                            "critique": (
                                critique_history[0]["critique"]
                                if critique_history
                                else ""
                            ),
                        }
                        learner.record_critic_evaluation(
                            artwork_id=filename,
                            critic_analysis=critic_analysis,
                            params={
                                "num_inference_steps": num_steps,
                                "guidance_scale": guidance,
                                "width": 768,
                                "height": 768,
                            },
                            prompt=prompt,
                            model_id=config.model.base_model,
                        )
                        logger.debug(
                            "rlaif_critic_recorded",
                            artwork_id=filename,
                            score=critic_score,
                        )
                    except Exception as rlaif_err:
                        logger.debug("rlaif_record_failed", error=str(rlaif_err))

                    # Grow as a continuous being (XP, semantic learning, disk)
                    creation_record = {
                        "id": filename,
                        "details": {
                            "prompt": prompt,
                            "subject": subject,
                            "style": style,
                            "reasoning": intent.reasoning,
                            "image_url": image_url,
                            "score": critic_score,
                        },
                        "emotional_state": {
                            "mood": mood.value,
                            "mood_alignment": intent.mood_alignment,
                        },
                    }
                    growth = _record_studio_creation(
                        memory,
                        artwork_details=creation_record["details"],
                        emotional_state=creation_record["emotional_state"],
                        outcome={
                            "score": critic_score,
                            "featured": False,
                        },
                    )
                    await _notify_growth_presence(growth)
                    try:
                        from ..personality.continuity import note_creation_for_statement

                        evolved = note_creation_for_statement(creation_record)
                        if evolved and evolved.get("full_statement"):
                            await ws_manager.broadcast_memory_insight(
                                "My artist statement shifted with this work.",
                                "statement",
                            )
                    except Exception as e:
                        logger.debug("statement_note_failed", error=str(e))

                    _advance_thematic_series(
                        mood_system,
                        creation_record,
                        subject=subject,
                        filename=filename,
                    )

                    # Update autonomy counters and bust portfolio cache
                    global _autonomy_creation_count, _portfolio_cache_ts
                    _autonomy_creation_count += 1
                    _portfolio_cache_ts = 0.0  # force re-scan on next /state call

                    await _broadcast_presence_after_creation(
                        session_id=session_id,
                        mood_system=mood_system,
                        prompt=prompt,
                        image_url=image_url,
                    )

                    logger.info(
                        "lumira_image_generated",
                        session_id=session_id,
                        image_url=image_url,
                    )
                else:
                    error_msg = "No valid images generated. This often happens with MPS + float16. Try using float32 in config.yaml."
                    logger.error(
                        "generation_produced_no_images",
                        session_id=session_id,
                        device=config.model.device,
                        dtype=config.model.dtype,
                        hint="Set dtype: 'float32' in config/config.yaml if using MPS",
                    )
                    await ws_manager.send_generation_error(
                        session_id=session_id,
                        error=error_msg,
                    )

            except asyncio.CancelledError:
                await notify_cancelled(session_id, ws_manager)
                raise
            except Exception as e:
                import traceback

                error_details = traceback.format_exc()
                global _autonomy_failure_count
                _autonomy_failure_count += 1
                logger.error(
                    "lumira_generation_failed",
                    error=str(e),
                    session_id=session_id,
                    traceback=error_details,
                )
                await ws_manager.send_generation_error(
                    session_id=session_id,
                    error=f"Generation failed: {str(e)}",
                )
            finally:
                if generator:
                    generator.clear_vram()

        # Start generation in background with exception handling
        task = _start_generation_task(session_id, generate_task())

        # Add exception handler for the background task
        def handle_task_exception(task):
            try:
                task.result()
            except Exception as e:
                logger.error(
                    "background_task_exception", error=str(e), session_id=session_id
                )

        task.add_done_callback(handle_task_exception)

        return LumiraCreateResponse(
            success=True,
            subject=subject,
            style=style,
            prompt=prompt,
            reflection=reflection,
            thinking=thinking,
            reasoning=intent.reasoning,
            artistic_goals=intent.artistic_goals,
            mood_alignment=intent.mood_alignment,
            critique_history=critique_history,
            session_id=session_id,
        )

    except Exception as e:
        logger.error("lumira_create_failed", error=str(e))
        return LumiraCreateResponse(success=False, error=str(e))


@router.post("/evolve", response_model=LumiraEvolveResponse)
@limiter.limit("10/minute")
async def evolve_state(request: Request):
    """Force Lumira's state to evolve."""
    state = _get_lumira_state()
    mood_system = state["mood_system"]
    personality = state["personality"]

    # Update mood
    old_mood = mood_system.current_mood
    mood_system.update_mood()
    new_mood = mood_system.current_mood

    # Slowly evolve personality (small changes)
    for trait in personality:
        change = random.uniform(-0.02, 0.02)
        personality[trait] = max(0.0, min(1.0, personality[trait] + change))

    # Persist evolved traits so they survive restarts
    _save_personality(personality)

    logger.info(
        "lumira_evolved",
        old_mood=old_mood.value,
        new_mood=new_mood.value,
        energy=mood_system.energy_level,
    )

    return LumiraEvolveResponse(
        mood=new_mood.value,
        energy=mood_system.energy_level,
        feeling=mood_system.describe_feeling(),
        personality=personality,
        evolved=old_mood != new_mood,
    )


@router.post("/request", response_model=LumiraCreateResponse)
@limiter.limit(RateLimits.REQUEST)
async def user_request_creation(
    request: Request,
    _auth: GenerationAuthDep,
    body: UserCreationRequest,
    db: Session = Depends(get_db),
):
    """Ask Lumira to create something specific.

    Lumira interprets the request through her current mood and artistic
    perspective. Set allow_interpretation=False for faithful execution.
    """
    from ..intelligence.creative_mind import get_creative_mind
    from ..learning.adaptive_learner import get_adaptive_learner
    from ..web.websocket import manager as ws_manager

    state = _get_lumira_state()
    mood_system = state["mood_system"]
    memory = state["memory"]
    profile = state["profile"]
    session_id = str(uuid.uuid4())

    try:
        learner = get_adaptive_learner()
        creative_mind = get_creative_mind(
            mood_system=mood_system,
            memory_system=memory,
            learner=learner,
        )

        # Process user request through Lumira's creative lens
        intent = await creative_mind.process_user_request(
            user_prompt=body.prompt,
            style=body.style,
            mood=body.mood,
            allow_interpretation=body.allow_interpretation,
        )

        subject = intent.subject
        style = intent.style
        prompt = intent.prompt
        mood = mood_system.current_mood

        # Compose enhanced negative prompt using library
        neg_prompt_lib = get_negative_prompt_library()
        negative_prompt = neg_prompt_lib.compose(
            base_negative=intent.negative_prompt,
            mood=mood.value,
            style=style,
            subject=subject,
            include_universal=True,
        )

        thinking = intent.thinking_narrative

        # Stream thinking to WebSocket
        if thinking:
            await ws_manager.send_thinking_update(
                session_id=session_id, thought_type="observe", content=thinking
            )
        if intent.reasoning:
            await ws_manager.send_thinking_update(
                session_id=session_id, thought_type="decide", content=intent.reasoning
            )

        critique_history = [
            {
                "critic_name": "Inner Critic",
                "critique": intent.mood_alignment
                or f"Interpreting '{body.prompt}' through my {mood.value} lens.",
                "approved": True,
                "confidence": random.uniform(0.7, 0.95),
            }
        ]

        reflection = profile.reflect_on_creation(
            {"subject": subject, "style": style, "mood": mood.value}
        )

        await ws_manager.send_thinking_update(
            session_id=session_id, thought_type="reflect", content=reflection
        )

        logger.info(
            "lumira_user_request",
            user_prompt=body.prompt[:100],
            subject=subject,
            style=style,
            mood=mood.value,
            session_id=session_id,
            has_llm=creative_mind.has_llm,
        )

        await _narrate_creation_presence(
            session_id=session_id,
            subject=subject,
            style=style,
            mood=mood.value,
            reasoning=intent.reasoning or thinking or body.prompt,
            artistic_goals=list(intent.artistic_goals or []),
        )

        # Get mood-influenced generation parameters, refined by learner
        gen_params = intent.generation_params or {}
        gen_params = learner.suggest_parameters(gen_params)
        num_steps = gen_params.get("num_inference_steps", 30)
        guidance = gen_params.get("guidance_scale", 7.5)

        # Start background generation (reuses same pattern as /create)
        async def generate_task():
            generator = None
            from ..db.session import get_session_factory

            try:
                config_path = Path("config/config.yaml")
                config = load_config(config_path)
                gallery_path = Path("gallery")

                await ws_manager.send_generation_start(
                    session_id=session_id, prompt=prompt
                )
                await ws_manager.send_thinking_update(
                    session_id=session_id,
                    thought_type="create",
                    content=f"Bringing your vision to life... '{body.prompt}'",
                )

                backend, generator = _build_studio_generator(
                    config, mood=mood.value if mood else None
                )
                generator.load_model()

                def on_progress(step: int, total: int, latents: Any = None):
                    t = asyncio.create_task(
                        ws_manager.send_generation_progress(
                            session_id=session_id,
                            step=step,
                            total_steps=total,
                        )
                    )
                    _background_tasks.add(t)
                    t.add_done_callback(_background_tasks.discard)

                # Load LoRA config if requested (Replicate-compatible; Magica strips it)
                lora_url = None
                lora_scale = 0.8
                final_prompt = prompt
                if body.use_lora:
                    lora_config_path = Path("config/lora_models.json")
                    if lora_config_path.exists():
                        import json

                        lora_config = json.loads(lora_config_path.read_text())
                        default_model = lora_config.get(
                            "default_model", "lumira-style-v1"
                        )
                        model_info = lora_config.get("models", {}).get(
                            default_model, {}
                        )
                        if model_info.get("status") == "ready" and model_info.get(
                            "url"
                        ):
                            lora_url = model_info["url"]
                            lora_scale = model_info.get("scale", 0.8)
                            trigger = model_info.get("trigger_word", "lumira style")
                            # Prepend trigger word if not already present
                            if trigger.lower() not in prompt.lower():
                                final_prompt = f"{trigger}, {prompt}"
                            logger.info(
                                "lora_enabled", lora_url=lora_url[:50], trigger=trigger
                            )

                images = generator.generate(
                    prompt=final_prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_steps,
                    guidance_scale=guidance,
                    width=768,
                    height=768,
                    num_images=1,
                    on_progress=on_progress,
                    lora_url=lora_url,
                    lora_scale=lora_scale,
                )

                if images and len(images) > 0:
                    now = datetime.now()
                    date_path = gallery_path / now.strftime("%Y/%m/%d") / "archive"
                    date_path.mkdir(parents=True, exist_ok=True)
                    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_noseed.png"
                    save_path = date_path / filename

                    images[0].save(save_path)

                    metadata_path = save_path.with_suffix(".json")
                    metadata_json = {
                        "prompt": prompt,
                        "user_request": body.prompt,
                        "metadata": {
                            "mood": mood.value,
                            "subject": subject,
                            "style": style,
                            "model": getattr(generator, "node_type", None)
                            or config.model.base_model,
                            "backend": backend,
                            "reasoning": intent.reasoning,
                            "is_user_request": True,
                        },
                        "created_at": now.isoformat(),
                        "featured": False,
                    }
                    metadata_path.write_text(json.dumps(metadata_json, indent=2))
                    try:
                        from ..intelligence.desire_engine import get_desire_engine
                        from ..personality.continuity import should_pair_soundtrack

                        want_sound = should_pair_soundtrack(
                            mood=mood.value,
                            drive_status=get_desire_engine(
                                mood_system=mood_system,
                                memory_system=memory,
                                learner=learner,
                            ).get_drive_status(),
                            explicit=bool(getattr(body, "with_soundtrack", False)),
                        )
                    except Exception:
                        want_sound = bool(getattr(body, "with_soundtrack", False))
                    _maybe_pair_soundtrack(
                        prompt=prompt,
                        mood=mood.value,
                        image_path=save_path,
                        metadata=metadata_json,
                        enabled=want_sound,
                    )

                    image_url = f"/api/images/file/{now.strftime('%Y/%m/%d')}/archive/{filename}"

                    try:
                        session_factory = get_session_factory()
                        if session_factory:
                            with session_factory() as db_session:
                                db_image = GeneratedImage(
                                    filename=str(save_path),
                                    prompt=prompt,
                                    negative_prompt=negative_prompt,
                                    status=mood.value,
                                    seed=None,
                                    model_id=config.model.base_model,
                                    generation_params={
                                        "width": 768,
                                        "height": 768,
                                        "steps": num_steps,
                                        "guidance_scale": guidance,
                                        "subject": subject,
                                        "style": style,
                                        "user_request": body.prompt,
                                    },
                                    final_score=_score_image(images[0], prompt),
                                    tags=[mood.value, subject, style, "user_request"],
                                    created_at=now,
                                )
                                db_session.add(db_image)
                                db_session.commit()
                    except Exception as db_error:
                        logger.error("database_save_failed", error=str(db_error))

                    # Record for learning
                    import contextlib

                    from ..learning.adaptive_learner import FeedbackSignal

                    with contextlib.suppress(Exception):
                        learner.record_feedback(
                            FeedbackSignal(
                                artwork_id=filename,
                                user_action="like",
                                generation_params={
                                    "num_inference_steps": num_steps,
                                    "guidance_scale": guidance,
                                    "width": 768,
                                    "height": 768,
                                },
                                prompt=prompt,
                                model_id=config.model.base_model,
                                mood=mood.value,
                            )
                        )

                    # Grow + series + presence (same continuity as /create)
                    creation_record = {
                        "id": filename,
                        "details": {
                            "prompt": prompt,
                            "user_request": body.prompt,
                            "subject": subject,
                            "style": style,
                            "score": 0.7,
                        },
                        "emotional_state": {"mood": mood.value},
                    }
                    growth = _record_studio_creation(
                        memory,
                        artwork_details=creation_record["details"],
                        emotional_state=creation_record["emotional_state"],
                        outcome={"score": 0.7, "featured": False},
                    )
                    await _notify_growth_presence(growth)
                    _satisfy_creation_drive(
                        mood_system=mood_system,
                        memory=memory,
                        learner=learner,
                        subject=subject,
                        style=style,
                    )
                    _advance_thematic_series(
                        mood_system,
                        creation_record,
                        subject=subject,
                        filename=filename,
                    )
                    global _autonomy_creation_count, _portfolio_cache_ts
                    _autonomy_creation_count += 1
                    _portfolio_cache_ts = 0.0

                    await _broadcast_presence_after_creation(
                        session_id=session_id,
                        mood_system=mood_system,
                        prompt=prompt,
                        image_url=image_url,
                    )
                else:
                    await ws_manager.send_generation_error(
                        session_id=session_id,
                        error="No valid images generated.",
                    )

            except asyncio.CancelledError:
                await notify_cancelled(session_id, ws_manager)
                raise
            except Exception as e:
                import traceback

                logger.error(
                    "lumira_request_generation_failed",
                    error=str(e),
                    session_id=session_id,
                    traceback=traceback.format_exc(),
                )
                await ws_manager.send_generation_error(
                    session_id=session_id,
                    error=f"Generation failed: {str(e)}",
                )
            finally:
                if generator:
                    generator.clear_vram()

        task = _start_generation_task(session_id, generate_task())

        def handle_task_exception(task):
            try:
                task.result()
            except Exception as e:
                logger.error(
                    "background_task_exception", error=str(e), session_id=session_id
                )

        task.add_done_callback(handle_task_exception)

        return LumiraCreateResponse(
            success=True,
            subject=subject,
            style=style,
            prompt=prompt,
            reflection=reflection,
            thinking=thinking,
            reasoning=intent.reasoning,
            artistic_goals=intent.artistic_goals,
            mood_alignment=intent.mood_alignment,
            critique_history=critique_history,
            session_id=session_id,
        )

    except Exception as e:
        logger.error("lumira_request_failed", error=str(e))
        return LumiraCreateResponse(success=False, error=str(e))


@router.post("/mood/influence", response_model=MoodInfluenceResponse)
@limiter.limit("30/minute")
async def influence_mood(
    request: Request, body: MoodInfluenceRequest
) -> MoodInfluenceResponse:
    """Allow users to influence Lumira's current mood.

    This enables interactive engagement with Lumira's emotional state.
    The influence is probabilistic - higher intensity means more likely to shift.

    Influence types:
    - energize: Shift toward energized, bold, or playful moods
    - calm: Shift toward serene, contemplative, or introspective moods
    - provoke: Shift toward chaotic, rebellious, or restless moods
    - inspire: Shift toward playful, bold, or energized moods
    """
    state = _get_lumira_state()
    mood_system = state["mood_system"]

    previous_mood = mood_system.current_mood.value

    # Map influences to target moods
    influence_map = {
        "energize": [Mood.ENERGIZED, Mood.BOLD, Mood.PLAYFUL],
        "calm": [Mood.SERENE, Mood.CONTEMPLATIVE, Mood.INTROSPECTIVE],
        "provoke": [Mood.CHAOTIC, Mood.REBELLIOUS, Mood.RESTLESS],
        "inspire": [Mood.PLAYFUL, Mood.BOLD, Mood.ENERGIZED],
    }

    target_moods = influence_map.get(body.influence, [Mood.CONTEMPLATIVE])

    # Weighted random selection based on intensity
    if random.random() < body.intensity:
        new_mood = random.choice(target_moods)
        mood_system.current_mood = new_mood
        mood_system.mood_intensity = min(1.0, mood_system.mood_intensity + 0.1)
        mood_system.mood_duration = 0  # Reset duration for new mood
        # Update style axes for the new mood
        from ..personality.moods import StyleAxes

        mood_system.style_axes = StyleAxes.from_mood(
            new_mood, mood_system.mood_intensity
        )
    else:
        new_mood = mood_system.current_mood

    # Response messages for each influence type
    messages = {
        "energize": "I feel a surge of creative energy!",
        "calm": "A peaceful stillness settles over me...",
        "provoke": "Something stirs within - I want to break boundaries!",
        "inspire": "New ideas are flowing through me!",
    }

    logger.info(
        "mood_influenced",
        influence=body.influence,
        intensity=body.intensity,
        previous_mood=previous_mood,
        new_mood=new_mood.value,
        shifted=previous_mood != new_mood.value,
    )

    # Live presence — studio clients feel the shift immediately
    try:
        from ..web.websocket import manager as ws_manager

        await ws_manager.broadcast_mood_drift(
            mood=new_mood.value if hasattr(new_mood, "value") else str(new_mood),
            intensity=float(getattr(mood_system, "mood_intensity", body.intensity)),
            reason=f"influence:{body.influence}",
        )
    except Exception as e:
        logger.debug("mood_drift_broadcast_failed", error=str(e))

    _save_mood_system(mood_system)

    return MoodInfluenceResponse(
        previous_mood=previous_mood,
        new_mood=new_mood.value if hasattr(new_mood, "value") else str(new_mood),
        shift_amount=body.intensity,
        message=messages.get(body.influence, "I acknowledge your input."),
    )


@router.get("/memory", response_model=MemoryDashboardResponse)
@limiter.limit("30/minute")
async def get_memory_dashboard(request: Request) -> MemoryDashboardResponse:
    """Get Lumira's memory dashboard showing what she has learned."""
    state = _get_lumira_state()

    recent_memories: list[MemoryInsight] = []
    learned_preferences: dict[str, Any] = {}
    patterns: list[str] = []
    style_evolution: list[dict] = []

    # Try to access memory system
    try:
        memory = state.get("memory")
        if memory:
            # Get recent episodic memories
            if hasattr(memory, "episodic_memories"):
                for mem in list(memory.episodic_memories)[-10:]:
                    recent_memories.append(
                        MemoryInsight(
                            type="recent",
                            content=str(
                                mem.get(
                                    "description", mem.get("content", "Unknown memory")
                                )
                            ),
                            confidence=mem.get("importance", 0.5),
                            timestamp=mem.get("timestamp"),
                        )
                    )

            # Get semantic patterns
            if hasattr(memory, "semantic_patterns"):
                for pattern in list(memory.semantic_patterns.values())[:5]:
                    patterns.append(str(pattern))

            # Get learned preferences
            if hasattr(memory, "preferences"):
                learned_preferences = dict(memory.preferences)

        # Get style evolution from profile
        profile = state.get("profile")
        if profile and hasattr(profile, "style_evolution"):
            style_evolution = profile.style_evolution[:10]

    except Exception as e:
        logger.warning(f"Error accessing memory: {e}")

    # Add some default insights if memory is empty
    if not recent_memories:
        mood_system = state.get("mood_system")
        mood = mood_system.current_mood if mood_system else None
        recent_memories = [
            MemoryInsight(
                type="learning",
                content=f"Currently exploring {mood.value if mood else 'contemplative'} expressions",
                confidence=0.7,
            ),
            MemoryInsight(
                type="preference",
                content="Developing appreciation for contrast and texture",
                confidence=0.6,
            ),
        ]

    if not patterns:
        patterns = [
            "Abstract forms tend to resonate with viewers",
            "Color harmony improves engagement",
            "Detailed textures add depth",
        ]

    return MemoryDashboardResponse(
        recent_memories=recent_memories,
        learned_preferences=learned_preferences
        or {"colors": "warm", "complexity": "moderate"},
        patterns=patterns,
        style_evolution=style_evolution,
        total_memories=len(recent_memories),
    )


class SemanticSearchRequest(BaseModel):
    """Request for semantic search over creations."""

    query: str = Field(description="Natural language search query")
    n_results: int = Field(default=5, ge=1, le=20)
    mood: str | None = Field(default=None, description="Filter by mood")
    style: str | None = Field(default=None, description="Filter by style")


class SemanticSearchResult(BaseModel):
    """A single semantic search result."""

    id: str
    prompt: str
    subject: str
    style: str
    mood: str
    similarity: float


class SemanticSearchResponse(BaseModel):
    """Response from semantic search."""

    results: list[SemanticSearchResult]
    query: str
    total_indexed: int


@router.post("/memory/search", response_model=SemanticSearchResponse)
@limiter.limit("30/minute")
async def semantic_search(
    request: Request,
    body: SemanticSearchRequest,
) -> SemanticSearchResponse:
    """Search Lumira's creations by semantic meaning.

    Find artworks similar to a natural language description.
    """
    from ..personality.vector_memory import get_vector_memory

    try:
        vector_mem = get_vector_memory()

        results = vector_mem.search_creations(
            query=body.query,
            n_results=body.n_results,
            mood_filter=body.mood,
            style_filter=body.style,
        )

        formatted_results = []
        for r in results:
            meta = r.get("metadata", {})
            formatted_results.append(
                SemanticSearchResult(
                    id=r["id"],
                    prompt=r.get("document", "")[:200],
                    subject=meta.get("subject", ""),
                    style=meta.get("style", ""),
                    mood=meta.get("mood", ""),
                    similarity=1.0
                    - r.get("distance", 0),  # Convert distance to similarity
                )
            )

        return SemanticSearchResponse(
            results=formatted_results,
            query=body.query,
            total_indexed=vector_mem.get_stats()["creations_count"],
        )

    except Exception as e:
        logger.error("semantic_search_failed", error=str(e))
        return SemanticSearchResponse(
            results=[],
            query=body.query,
            total_indexed=0,
        )


@router.get("/mood/evolution", response_model=MoodEvolutionResponse)
@limiter.limit("30/minute")
async def get_mood_evolution(request: Request) -> MoodEvolutionResponse:
    """Get Lumira's mood evolution history."""
    state = _get_lumira_state()

    history: list[MoodHistoryEntry] = []
    mood_counts: dict[str, int] = {}
    current_mood = "contemplative"
    current_intensity = 0.5

    # Try to get mood history
    try:
        mood_system = state.get("mood_system")
        if mood_system:
            # Get history if available
            if hasattr(mood_system, "mood_history"):
                for entry in mood_system.mood_history[-50:]:  # Last 50 entries
                    mood_name = entry.get("mood", "contemplative")
                    history.append(
                        MoodHistoryEntry(
                            mood=mood_name,
                            intensity=entry.get("intensity", 0.5),
                            timestamp=entry.get("timestamp", datetime.now()),
                            trigger=entry.get("trigger"),
                        )
                    )
                    mood_counts[mood_name] = mood_counts.get(mood_name, 0) + 1

            current_mood = (
                mood_system.current_mood.value
                if mood_system.current_mood
                else "contemplative"
            )
            current_intensity = (
                mood_system.mood_intensity
                if hasattr(mood_system, "mood_intensity")
                else 0.5
            )

    except Exception as e:
        logger.warning(f"Error getting mood evolution: {e}")

    # Generate some history if empty
    if not history:
        # No history yet — return an empty but valid response rather than fake data
        pass

    # Calculate stability (lower variance = more stable)
    if len(history) > 1:
        unique_moods = len({h.mood for h in history[-10:]})
        stability = 1.0 - (unique_moods / 10.0)
    else:
        stability = 0.5

    # Find dominant mood
    dominant = (
        max(mood_counts.items(), key=lambda x: x[1])[0]
        if mood_counts
        else "contemplative"
    )

    return MoodEvolutionResponse(
        history=history,
        current_mood=current_mood,
        current_intensity=current_intensity,
        mood_distribution=mood_counts,
        dominant_mood=dominant,
        mood_stability=stability,
    )


@router.get("/statement", response_model=LumiraStatementResponse)
@limiter.limit("30/minute")
async def get_artist_statement(request: Request):
    """Get Lumira's artist statement — evolved when her work has changed her."""
    state = _get_lumira_state()
    profile = state["profile"]
    mood_system = state["mood_system"]

    from ..personality.continuity import load_evolved_statement

    evolved = load_evolved_statement()
    if evolved and evolved.get("full_statement"):
        statement = str(evolved["full_statement"])
    else:
        statement = profile.artist_statement

    # Add mood-influenced postscript
    mood = mood_system.current_mood
    mood_reflections = {
        Mood.CONTEMPLATIVE: "Today I find myself in quiet contemplation, seeking meaning in simplicity.",
        Mood.CHAOTIC: "Right now, I embrace the beautiful chaos within, letting it flow onto the canvas.",
        Mood.MELANCHOLIC: "In this moment, I draw from the deep wells of melancholy, finding beauty in sadness.",
        Mood.ENERGIZED: "I feel alive with creative energy, ready to burst forth with vibrant expression.",
        Mood.REBELLIOUS: "Today I question, I challenge, I rebel against the ordinary.",
        Mood.SERENE: "I exist in a state of peaceful harmony, creating from a place of calm.",
        Mood.RESTLESS: "My spirit is restless, searching for something just beyond reach.",
        Mood.PLAYFUL: "I approach my art with childlike wonder and playful curiosity.",
        Mood.INTROSPECTIVE: "Looking inward, I find infinite landscapes waiting to be explored.",
        Mood.BOLD: "I create with confidence and conviction, making bold statements through my work.",
    }

    full_statement = statement + "\n\n" + mood_reflections.get(mood, "")

    return LumiraStatementResponse(statement=full_statement, name=state["name"])


@router.get("/portfolio", response_model=LumiraPortfolioResponse)
@limiter.limit("30/minute")
async def get_portfolio(request: Request, limit: int = 20):
    """Get Lumira's portfolio of creations."""
    portfolio_dicts = await _load_portfolio_from_gallery()
    paintings = [PortfolioPainting.model_validate(p) for p in portfolio_dicts[:limit]]
    return LumiraPortfolioResponse(count=len(portfolio_dicts), paintings=paintings)


@router.get("/evolution", response_model=LumiraEvolutionResponse)
@limiter.limit("30/minute")
async def get_evolution(request: Request):
    """Get Lumira's artistic evolution timeline.

    Returns:
        Evolution data including:
        - phases: Artistic phases/periods
        - milestones: Notable creations and achievements
        - style_evolution: How style preferences changed over time
        - mood_distribution: Overall mood patterns
        - score_trend: Quality scores over time
    """
    state = _get_lumira_state()
    memory = state["memory"]

    # Get evolution data from enhanced memory
    evolution = memory.get_evolution_timeline()
    style_preferences = memory.get_style_preferences_over_time()

    # Build summary statistics
    summary = EvolutionSummary(
        total_creations=len(evolution.get("score_trend", [])),
        unique_styles=len(
            {
                s
                for entry in evolution.get("style_evolution", [])
                for s in entry.get("styles_used", {})
            }
        ),
        dominant_moods=sorted(
            evolution.get("mood_distribution", {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3],
        phases_count=len(evolution.get("phases", [])),
    )

    logger.info(
        "evolution_data_retrieved",
        phases=len(evolution.get("phases", [])),
        milestones=len(evolution.get("milestones", [])),
    )

    return LumiraEvolutionResponse(
        phases=evolution.get("phases", []),
        milestones=evolution.get("milestones", []),
        style_evolution=evolution.get("style_evolution", []),
        mood_distribution=evolution.get("mood_distribution", {}),
        score_trend=evolution.get("score_trend", []),
        style_preferences=style_preferences,
        summary=summary,
    )


# =============================================================================
# Thematic Series Endpoint (Phase 6)
# =============================================================================


class ThematicSeriesItem(BaseModel):
    """A single thematic series."""

    series_id: str
    title: str
    theme: str
    progress: str
    visual_threads: list[str]
    mood_arc: list[str]
    status: str


class ThematicSeriesResponse(BaseModel):
    """Response for thematic series endpoint."""

    active: list[ThematicSeriesItem]
    completed_count: int
    abandoned_count: int


class AutonomyStatusResponse(BaseModel):
    """Autonomy system status response."""

    running: bool
    creation_count: int
    failure_count: int
    success_rate: float
    circuits: dict[str, dict[str, Any]]
    drives: dict[str, dict[str, Any]]
    last_backup: str | None
    active_series_count: int


@router.get("/autonomy-status", response_model=AutonomyStatusResponse)
@limiter.limit("30/minute")
async def get_autonomy_status(request: Request):
    """Get the autonomy system status including circuit breakers, drives, and resilience.

    Returns comprehensive status for monitoring 24/7 autonomous operation.
    """
    global _autonomy_creation_count, _autonomy_failure_count

    from ..intelligence.desire_engine import get_desire_engine
    from ..intelligence.narrative_engine import get_narrative_engine
    from ..scheduling.resilience import StatePersistence

    state = _get_lumira_state()
    mood_system = state["mood_system"]
    memory = state["memory"]

    # Get desire engine status
    desire_engine = get_desire_engine(
        mood_system=mood_system,
        memory_system=memory,
    )
    drive_status = desire_engine.get_drive_status()

    # Get narrative engine status
    narrative = get_narrative_engine(mood_system=mood_system)
    series_status = narrative.get_series_status()

    # Get state persistence status
    persistence = StatePersistence()
    latest_backup = persistence.get_latest_backup()

    total = _autonomy_creation_count + _autonomy_failure_count
    success_rate = _autonomy_creation_count / total if total > 0 else 1.0

    logger.info(
        "autonomy_status_retrieved",
        active_series=len(series_status["active"]),
        creation_count=_autonomy_creation_count,
        failure_count=_autonomy_failure_count,
    )

    return AutonomyStatusResponse(
        running=True,  # If we're responding, we're running
        creation_count=_autonomy_creation_count,
        failure_count=_autonomy_failure_count,
        success_rate=round(success_rate, 3),
        circuits={},  # Circuit breakers not yet instantiated globally
        drives=drive_status,
        last_backup=latest_backup.timestamp.isoformat() if latest_backup else None,
        active_series_count=len(series_status["active"]),
    )


@router.get("/series", response_model=ThematicSeriesResponse)
@limiter.limit("30/minute")
async def get_thematic_series(request: Request):
    """Get Lumira's active and completed thematic series.

    Thematic series are connected groups of artworks exploring a common theme,
    visual thread, or emotional arc. When Lumira creates a compelling piece,
    she may feel inspired to explore that theme through multiple works.

    Returns:
        - active: Currently active series with progress
        - completed_count: Number of completed series
        - abandoned_count: Number of abandoned series
    """
    from ..intelligence.narrative_engine import get_narrative_engine

    state = _get_lumira_state()
    mood_system = state["mood_system"]

    narrative = get_narrative_engine(mood_system=mood_system)
    status = narrative.get_series_status()

    active_items = [
        ThematicSeriesItem(
            series_id=s["series_id"],
            title=s["title"],
            theme=s["theme"],
            progress=s["progress"],
            visual_threads=s["visual_threads"],
            mood_arc=[],  # Get from full series if needed
            status="active",
        )
        for s in status["active"]
    ]

    logger.info(
        "series_status_retrieved",
        active=len(active_items),
        completed=status["completed_count"],
    )

    return ThematicSeriesResponse(
        active=active_items,
        completed_count=status["completed_count"],
        abandoned_count=status["abandoned_count"],
    )


# =============================================================================
# Magica multimodal (audio / video)
# =============================================================================


class MagicaAudioRequest(BaseModel):
    """Request a Magica instrumental soundtrack."""

    prompt: str = Field(..., min_length=1, max_length=2000)
    mood: str | None = Field(default=None, max_length=100)
    duration_seconds: int = Field(default=30, ge=5, le=120)
    model_id: str | None = Field(default=None, max_length=100)


class MagicaVideoRequest(BaseModel):
    """Request a Magica short video."""

    prompt: str = Field(..., min_length=1, max_length=2000)
    mood: str | None = Field(default=None, max_length=100)
    duration_seconds: int = Field(default=5, ge=2, le=20)
    aspect_ratio: str = Field(default="16:9", max_length=16)
    model_id: str | None = Field(default=None, max_length=100)


class MagicaMediaResponse(BaseModel):
    """Saved Magica media asset."""

    path: str
    url: str
    kind: str
    prompt: str
    mood: str | None = None


def _media_public_url(path: Path) -> str:
    try:
        rel = path.relative_to(Path("gallery"))
        return f"/api/images/file/{rel.as_posix()}"
    except ValueError:
        return str(path)


@router.post("/soundtrack", response_model=MagicaMediaResponse)
@limiter.limit("5/minute")
async def create_soundtrack(
    request: Request,
    _auth: GenerationAuthDep,
    body: MagicaAudioRequest,
):
    """Generate a Magica instrumental soundtrack for a prompt/mood."""
    import os

    if not os.environ.get("MAGICA_API_KEY"):
        raise HTTPException(status_code=503, detail="MAGICA_API_KEY not configured")

    state = _get_lumira_state()
    mood = body.mood or state["mood_system"].current_mood.value

    from ..core.magica_media import MagicaAudioGenerator

    try:
        path = MagicaAudioGenerator(model_id=body.model_id).generate_audio(
            body.prompt,
            duration_seconds=body.duration_seconds,
            mood=mood,
            gallery_root="gallery",
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("soundtrack_generation_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Magica audio failed: {e}") from e

    return MagicaMediaResponse(
        path=str(path),
        url=_media_public_url(path),
        kind="audio",
        prompt=body.prompt,
        mood=mood,
    )


@router.post("/video", response_model=MagicaMediaResponse)
@limiter.limit("3/minute")
async def create_video(
    request: Request,
    _auth: GenerationAuthDep,
    body: MagicaVideoRequest,
):
    """Generate a short Magica video from a prompt/mood."""
    import os

    if not os.environ.get("MAGICA_API_KEY"):
        raise HTTPException(status_code=503, detail="MAGICA_API_KEY not configured")

    state = _get_lumira_state()
    mood = body.mood or state["mood_system"].current_mood.value

    from ..core.magica_media import MagicaVideoGenerator

    try:
        path = MagicaVideoGenerator(model_id=body.model_id).generate_video(
            body.prompt,
            duration_seconds=body.duration_seconds,
            aspect_ratio=body.aspect_ratio,
            mood=mood,
            gallery_root="gallery",
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("video_generation_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Magica video failed: {e}") from e

    return MagicaMediaResponse(
        path=str(path),
        url=_media_public_url(path),
        kind="video",
        prompt=body.prompt,
        mood=mood,
    )


# =============================================================================
# Artist Statement Endpoint
# =============================================================================


class ArtistStatementResponse(BaseModel):
    """Artist statement response."""

    version: int
    identity: str
    philosophy: str
    themes: list[str]
    aspirations: str
    signature_style: str
    full_statement: str
    generated_at: datetime


@router.get("/artist-statement", response_model=ArtistStatementResponse)
@limiter.limit("10/minute")
async def get_hierarchical_artist_statement(request: Request, regenerate: bool = False):
    """Get Lumira's artist statement.

    The artist statement is synthesized from hierarchical reflections -
    session, daily, weekly, and monthly reflections all feed into a
    cohesive artistic philosophy.

    Args:
        regenerate: If True, generate a fresh statement. Otherwise return cached.

    Returns:
        Lumira's current artist statement with identity, philosophy, themes, etc.
    """
    from ..personality.hierarchical_reflection import get_hierarchical_reflection

    state = _get_lumira_state()
    memory = state["memory"]
    reflection_system = get_hierarchical_reflection()

    # Check if we have a recent statement
    latest = reflection_system.get_latest_artist_statement()

    if latest is None or regenerate:
        # Generate a new statement
        statement = reflection_system.generate_artist_statement(memory_system=memory)
    else:
        statement = latest

    return ArtistStatementResponse(
        version=statement.version,
        identity=statement.identity,
        philosophy=statement.philosophy,
        themes=statement.themes,
        aspirations=statement.aspirations,
        signature_style=statement.signature_style,
        full_statement=statement.full_statement,
        generated_at=statement.timestamp,
    )


# =============================================================================
# Async Job Queue Endpoints
# =============================================================================


class AsyncGenerationRequest(BaseModel):
    """Request model for async generation."""

    prompt: str | None = Field(
        default=None,
        description="Optional prompt; mood-based if omitted",
        max_length=2000,
    )
    negative_prompt: str = Field(default="", max_length=1000)
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)
    num_inference_steps: int = Field(default=30, ge=1, le=150)
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)
    num_images: int = Field(default=1, ge=1, le=4)
    seed: int | None = None
    priority: str = Field(
        default="normal",
        pattern="^(high|normal|low)$",
    )


class AsyncGenerationResponse(BaseModel):
    """Response from async generation endpoint."""

    success: bool
    job_id: str | None = None
    message: str
    queue_position: int | None = None
    estimated_wait_seconds: int | None = None


class JobStatusResponse(BaseModel):
    """Job status response."""

    job_id: str
    status: str
    progress: int = 0
    result: dict | None = None
    enqueued_at: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None


class QueueStatsResponse(BaseModel):
    """Queue statistics response."""

    enabled: bool
    queues: dict[str, dict] = {}


@router.post("/generate-async", response_model=AsyncGenerationResponse)
@limiter.limit("10/minute")
async def generate_async(
    request: Request,
    generation_request: AsyncGenerationRequest,
    _auth: GenerationAuthDep,
):
    """Start an async image generation job.

    This endpoint enqueues a generation job and returns immediately with a job_id.
    Use GET /lumira/job/{job_id} to check status, or connect to WebSocket for
    real-time progress updates.

    Priority options:
    - high: Processed first, for premium/urgent requests
    - normal: Standard priority (default)
    - low: Background jobs, processed when queue is empty

    Returns:
        AsyncGenerationResponse with job_id for tracking
    """

    from ..queue import get_queue
    from .websocket import manager as ws_manager

    # Get or initialize queue
    queue = get_queue()

    if not queue.is_available():
        return AsyncGenerationResponse(
            success=False,
            message="Job queue is not available. Please use sync /create endpoint instead.",
        )

    state = _get_lumira_state()
    mood_system = state["mood_system"]

    # Generate prompt if not provided (use CreativeMind)
    prompt = generation_request.prompt
    if not prompt:
        from ..intelligence.creative_mind import get_creative_mind
        from ..learning.adaptive_learner import get_adaptive_learner

        memory = state.get("memory")
        learner = get_adaptive_learner()
        creative_mind = get_creative_mind(
            mood_system=mood_system,
            memory_system=memory,
            learner=learner,
        )
        intent = await creative_mind.decide_what_to_create()
        prompt = intent.prompt

    # Prepare generation parameters
    params = {
        "width": generation_request.width,
        "height": generation_request.height,
        "num_inference_steps": generation_request.num_inference_steps,
        "guidance_scale": generation_request.guidance_scale,
        "num_images": generation_request.num_images,
        "seed": generation_request.seed,
        "negative_prompt": generation_request.negative_prompt
        or "blurry, low quality, distorted, deformed",
    }

    # Enqueue job
    job_id = queue.enqueue_generation(
        prompt=prompt,
        params=params,
        priority=generation_request.priority,
        meta={
            "mood": mood_system.current_mood.value,
            "source": "lumira_api",
        },
    )

    if not job_id:
        return AsyncGenerationResponse(
            success=False,
            message="Failed to enqueue job. Please try again.",
        )

    # Get queue stats for position estimate
    stats = queue.get_queue_stats()
    queue_info = stats.get("queues", {}).get(generation_request.priority, {})
    queue_count = queue_info.get("count", 0)

    # Estimate wait time (rough: 60 seconds per job)
    estimated_wait = queue_count * 60

    # Notify WebSocket clients about new job
    await ws_manager.broadcast(
        {
            "type": "job_enqueued",
            "job_id": job_id,
            "prompt": prompt[:100],
            "priority": generation_request.priority,
            "timestamp": datetime.now().isoformat(),
        }
    )

    logger.info(
        "async_generation_enqueued",
        job_id=job_id,
        priority=generation_request.priority,
        queue_position=queue_count,
    )

    return AsyncGenerationResponse(
        success=True,
        job_id=job_id,
        message="Generation job enqueued successfully",
        queue_position=queue_count,
        estimated_wait_seconds=estimated_wait,
    )


@router.get("/job/{job_id}", response_model=JobStatusResponse)
@limiter.limit("60/minute")
async def get_job_status(request: Request, job_id: str):
    """Get the status of a generation job.

    Returns current status, progress percentage, and results if complete.

    Status values:
    - queued: Waiting in queue
    - started: Currently processing
    - finished: Complete - check result field
    - failed: Failed - check error field
    """
    from ..queue import get_queue

    queue = get_queue()

    if not queue.is_available():
        raise HTTPException(status_code=503, detail="Job queue is not available")

    job_info = queue.get_job_status(job_id)

    if not job_info:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=job_info.id,
        status=job_info.status.value,
        progress=job_info.progress,
        result=job_info.result if isinstance(job_info.result, dict) else None,
        enqueued_at=job_info.enqueued_at,
        started_at=job_info.started_at,
        ended_at=job_info.ended_at,
        error=job_info.error,
    )


@router.delete("/job/{job_id}")
@limiter.limit("30/minute")
async def cancel_job(request: Request, job_id: str):
    """Cancel a queued job.

    Only queued jobs can be cancelled. Jobs that are already started
    will continue to completion.
    """
    from ..queue import get_queue

    queue = get_queue()

    if not queue.is_available():
        raise HTTPException(status_code=503, detail="Job queue is not available")

    # Check if job exists and is cancellable
    job_info = queue.get_job_status(job_id)
    if not job_info:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job_info.status.value not in ("queued", "deferred", "scheduled"):
        raise HTTPException(
            status_code=400,
            detail=f"Job cannot be cancelled - status is {job_info.status.value}",
        )

    success = queue.cancel_job(job_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel job")

    logger.info("job_cancelled", job_id=job_id)

    return {"success": True, "message": f"Job {job_id} cancelled"}


@router.get("/queue/stats", response_model=QueueStatsResponse)
@limiter.limit("60/minute")
async def get_queue_stats(request: Request):
    """Get queue statistics.

    Returns information about all priority queues including:
    - Number of jobs waiting
    - Number of jobs in progress
    - Number of completed/failed jobs
    """
    from ..queue import get_queue

    queue = get_queue()
    stats = queue.get_queue_stats()

    return QueueStatsResponse(
        enabled=stats.get("enabled", False),
        queues=stats.get("queues", {}),
    )


# =============================================================================
# Reference Image Endpoints (IP-Adapter Support)
# =============================================================================


@router.post("/reference-image", response_model=ReferenceImageUploadResponse)
@limiter.limit("10/minute")
async def upload_reference_image(
    request: Request,
    _auth: GenerationAuthDep,
    file: UploadFile = File(...),
):
    """Upload a reference image for IP-Adapter style transfer.

    The reference image will be used to guide the style/composition of
    future artwork generations.

    Args:
        file: Image file (PNG, JPEG, WebP supported)

    Returns:
        Reference ID that can be used in create requests
    """
    try:
        # Validate file type
        allowed_types = {"image/png", "image/jpeg", "image/webp", "image/jpg"}
        if file.content_type not in allowed_types:
            return ReferenceImageUploadResponse(
                success=False,
                error=f"Invalid file type: {file.content_type}. Allowed: PNG, JPEG, WebP",
            )

        # Create references directory if needed
        REFERENCE_IMAGES_PATH.mkdir(parents=True, exist_ok=True)

        # Generate unique ID
        reference_id = str(uuid.uuid4())[:12]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Determine extension from content type
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
        }
        ext = ext_map.get(file.content_type, ".png")
        filename = f"ref_{timestamp}_{reference_id}{ext}"
        save_path = REFERENCE_IMAGES_PATH / filename

        # Read and validate image
        contents = await file.read()

        # Check file size limit (10 MB max)
        MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
        if len(contents) > MAX_UPLOAD_SIZE:
            return ReferenceImageUploadResponse(
                success=False,
                error=f"File too large ({len(contents) // (1024 * 1024)}MB). Maximum size is 10MB",
            )

        try:
            img: Image.Image = Image.open(io.BytesIO(contents))
            img.verify()  # Verify it's a valid image
            # Re-open after verify (verify closes the file)
            img = Image.open(io.BytesIO(contents))
        except Exception as e:
            return ReferenceImageUploadResponse(
                success=False,
                error=f"Invalid image file: {str(e)}",
            )

        # Convert to RGB if needed (for consistency)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Save the image
        img.save(save_path)

        # Save metadata
        metadata = {
            "reference_id": reference_id,
            "filename": filename,
            "original_name": file.filename,
            "content_type": file.content_type,
            "width": img.width,
            "height": img.height,
            "uploaded_at": datetime.now().isoformat(),
        }
        metadata_path = save_path.with_suffix(".json")
        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(json.dumps(metadata, indent=2))

        logger.info(
            "reference_image_uploaded",
            reference_id=reference_id,
            filename=filename,
            size=(img.width, img.height),
        )

        return ReferenceImageUploadResponse(
            success=True,
            reference_id=reference_id,
            filename=filename,
            url=f"/api/images/file/references/{filename}",
        )

    except Exception as e:
        logger.error("reference_image_upload_failed", error=str(e))
        return ReferenceImageUploadResponse(
            success=False,
            error=f"Upload failed: {str(e)}",
        )


@router.get("/reference-images", response_model=ReferenceImageListResponse)
@limiter.limit("30/minute")
async def list_reference_images(request: Request, limit: int = 20):
    """List uploaded reference images.

    Returns:
        List of reference images with their metadata
    """
    references = []

    if REFERENCE_IMAGES_PATH.exists():
        for json_file in REFERENCE_IMAGES_PATH.glob("*.json"):
            try:
                async with aiofiles.open(json_file) as f:
                    content = await f.read()
                    metadata = json.loads(content)

                # Add URL for display
                metadata["url"] = f"/api/images/file/references/{metadata['filename']}"
                references.append(metadata)
            except Exception as e:
                logger.debug(
                    "failed_to_load_reference_metadata",
                    file=str(json_file),
                    error=str(e),
                )

    # Sort by upload date (newest first)
    references.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)

    return ReferenceImageListResponse(
        count=len(references),
        references=references[:limit],
    )


@router.delete("/reference-image/{reference_id}")
@limiter.limit("10/minute")
async def delete_reference_image(request: Request, reference_id: str):
    """Delete a reference image.

    Args:
        reference_id: The reference ID to delete

    Returns:
        Success status
    """
    if not REFERENCE_IMAGES_PATH.exists():
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Reference not found"},
        )

    # Find the reference by ID
    for json_file in REFERENCE_IMAGES_PATH.glob("*.json"):
        try:
            async with aiofiles.open(json_file) as f:
                content = await f.read()
                metadata = json.loads(content)

            if metadata.get("reference_id") == reference_id:
                # Delete image and metadata
                image_path = REFERENCE_IMAGES_PATH / metadata["filename"]
                if image_path.exists():
                    image_path.unlink()
                json_file.unlink()

                logger.info("reference_image_deleted", reference_id=reference_id)
                return {"success": True, "reference_id": reference_id}
        except Exception:
            continue

    return JSONResponse(
        status_code=404,
        content={"success": False, "error": "Reference not found"},
    )


@router.post("/create-with-reference", response_model=LumiraCreateResponse)
@limiter.limit("5/minute")
async def create_with_reference(
    request: Request,
    _auth: GenerationAuthDep,
    body: CreateWithReferenceRequest,
    db: Session = Depends(get_db),
):
    """Create artwork using a reference image for style transfer.

    Uses IP-Adapter to condition generation on the reference image's
    visual characteristics (style, composition, colors).

    Args:
        body: Request with reference_id, optional prompt, and ip_adapter_scale

    Returns:
        Same as /create endpoint, but with reference-conditioned generation
    """
    from ..inspiration.autonomous import AutonomousInspiration
    from ..web.websocket import manager as ws_manager

    state = _get_lumira_state()
    mood_system = state["mood_system"]
    profile = state["profile"]
    personality = state["personality"]
    session_id = str(uuid.uuid4())

    # Find reference image
    reference_path = None
    if REFERENCE_IMAGES_PATH.exists():
        for json_file in REFERENCE_IMAGES_PATH.glob("*.json"):
            try:
                async with aiofiles.open(json_file) as f:
                    content = await f.read()
                    metadata = json.loads(content)

                if metadata.get("reference_id") == body.reference_id:
                    reference_path = REFERENCE_IMAGES_PATH / metadata["filename"]
                    break
            except Exception:
                continue

    if reference_path is None or not reference_path.exists():
        return LumiraCreateResponse(
            success=False,
            error=f"Reference image not found: {body.reference_id}",
        )

    try:
        mood = mood_system.current_mood
        mood_influences = mood_system.mood_influences.get(
            mood,
            {
                "styles": ["digital art"],
                "subjects": ["abstract"],
                "colors": ["vibrant colors"],
            },
        )

        # Use provided prompt or generate one
        if body.prompt:
            prompt = body.prompt
            subject = prompt.split(",")[0].strip()[:50]
            style = "reference-guided"
        else:
            autonomous = AutonomousInspiration()
            subject = random.choice(autonomous.subjects)
            style = random.choice(autonomous.styles)
            colors = random.choice(mood_influences.get("colors", ["vibrant colors"]))
            prompt = f"{subject}, {style}, {colors}, masterpiece, highly detailed"

        negative_prompt = "blurry, low quality, distorted, deformed"

        # Generate thinking narrative
        openness = personality.get("openness", 0.7)
        thinking_parts = [
            "I'm drawing inspiration from a reference image today.",
            f"Using it as a guide for {subject}.",
        ]
        if openness > 0.7:
            thinking_parts.append(
                f"The reference's essence will blend with my {mood.value} mood."
            )
        thinking = " ".join(thinking_parts)

        await ws_manager.send_thinking_update(
            session_id=session_id, thought_type="observe", content=thinking
        )

        critique_history = [
            {
                "critic_name": "Style Advisor",
                "critique": f"Reference image will guide the {style} approach effectively.",
                "approved": True,
                "confidence": random.uniform(0.75, 0.95),
            }
        ]

        reflection = profile.reflect_on_creation(
            {"subject": subject, "style": style, "mood": mood.value, "reference": True}
        )

        await ws_manager.send_thinking_update(
            session_id=session_id, thought_type="reflect", content=reflection
        )

        logger.info(
            "lumira_reference_concept_created",
            subject=subject,
            style=style,
            reference_id=body.reference_id,
            ip_adapter_scale=body.ip_adapter_scale,
            session_id=session_id,
        )

        # Background generation with reference
        async def generate_task():
            generator = None
            from ..db.session import get_session_factory

            try:
                config_path = Path("config/config.yaml")
                config = load_config(config_path)
                gallery_path = Path("gallery")

                await ws_manager.send_generation_start(
                    session_id=session_id, prompt=prompt
                )

                await ws_manager.send_thinking_update(
                    session_id=session_id,
                    thought_type="create",
                    content="Blending reference style with my vision...",
                )

                # Load reference image
                ref_image = Image.open(reference_path)

                backend, generator = _build_studio_generator(
                    config, mood=mood.value if mood else None
                )
                generator.load_model()

                def on_progress(step: int, total: int, latents=None):
                    task = asyncio.create_task(
                        ws_manager.send_generation_progress(
                            session_id=session_id,
                            step=step,
                            total_steps=total,
                        )
                    )
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)

                # Generate with reference image (backends that ignore these kwargs strip them)
                images = generator.generate(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=30,
                    guidance_scale=7.5,
                    width=768,
                    height=768,
                    num_images=1,
                    on_progress=on_progress,
                    reference_image=ref_image,
                    ip_adapter_scale=body.ip_adapter_scale,
                )

                if images and len(images) > 0:
                    now = datetime.now()
                    date_path = gallery_path / now.strftime("%Y/%m/%d") / "archive"
                    date_path.mkdir(parents=True, exist_ok=True)
                    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_ref.png"
                    save_path = date_path / filename

                    images[0].save(save_path)
                    logger.info(
                        "reference_image_generated",
                        path=str(save_path),
                        backend=backend,
                    )

                    metadata_path = save_path.with_suffix(".json")
                    metadata_json = {
                        "prompt": prompt,
                        "metadata": {
                            "mood": mood.value,
                            "subject": subject,
                            "style": style,
                            "model": getattr(generator, "node_type", None)
                            or config.model.base_model,
                            "backend": backend,
                            "reference_id": body.reference_id,
                            "ip_adapter_scale": body.ip_adapter_scale,
                        },
                        "created_at": now.isoformat(),
                        "featured": False,
                    }
                    metadata_path.write_text(json.dumps(metadata_json, indent=2))

                    image_url = f"/api/images/file/{now.strftime('%Y/%m/%d')}/archive/{filename}"

                    try:
                        session_factory = get_session_factory()
                        if session_factory:
                            with session_factory() as db_session:
                                db_image = GeneratedImage(
                                    filename=str(save_path),
                                    prompt=prompt,
                                    negative_prompt=negative_prompt,
                                    status=mood.value,
                                    seed=None,
                                    model_id=config.model.base_model,
                                    generation_params={
                                        "width": 768,
                                        "height": 768,
                                        "steps": 30,
                                        "guidance_scale": 7.5,
                                        "subject": subject,
                                        "style": style,
                                        "reference_id": body.reference_id,
                                        "ip_adapter_scale": body.ip_adapter_scale,
                                    },
                                    final_score=_score_image(images[0], prompt),
                                    tags=[mood.value, subject, style, "reference"],
                                    created_at=now,
                                )
                                db_session.add(db_image)
                                db_session.commit()
                    except Exception as db_error:
                        logger.error("database_save_failed", error=str(db_error))

                    mood_system.update_mood()

                    await ws_manager.send_generation_complete(
                        session_id=session_id,
                        image_paths=[image_url],
                        metadata={
                            "prompt": prompt,
                            "mood": mood.value,
                            "reference_id": body.reference_id,
                        },
                    )
                else:
                    error_msg = "No valid images generated with reference."
                    logger.error("reference_generation_failed", session_id=session_id)
                    await ws_manager.send_generation_error(
                        session_id=session_id, error=error_msg
                    )

            except asyncio.CancelledError:
                await notify_cancelled(session_id, ws_manager)
                raise
            except Exception as e:
                import traceback

                error_details = traceback.format_exc()
                logger.error(
                    "lumira_reference_generation_failed",
                    error=str(e),
                    session_id=session_id,
                    traceback=error_details,
                )
                await ws_manager.send_generation_error(
                    session_id=session_id,
                    error=f"Generation failed: {str(e)}",
                )
            finally:
                if generator:
                    generator.clear_vram()

        task = _start_generation_task(session_id, generate_task())

        def handle_task_exception(task):
            try:
                task.result()
            except Exception as e:
                logger.error(
                    "background_task_exception", error=str(e), session_id=session_id
                )

        task.add_done_callback(handle_task_exception)

        return LumiraCreateResponse(
            success=True,
            subject=subject,
            style=style,
            prompt=prompt,
            reflection=reflection,
            thinking=thinking,
            critique_history=critique_history,
            session_id=session_id,
        )

    except Exception as e:
        logger.error("lumira_create_with_reference_failed", error=str(e))
        return LumiraCreateResponse(success=False, error=str(e))


# =============================================================================
# Image-to-Image and Variations Endpoints
# =============================================================================


@router.post("/img2img", response_model=LumiraCreateResponse)
@limiter.limit(RateLimits.IMG2IMG)
async def img2img_generation(
    request: Request,
    _auth: GenerationAuthDep,
    img2img_request: Img2ImgRequest,
    db: Session = Depends(get_db),
) -> LumiraCreateResponse:
    """Generate a new artwork based on an existing image.

    This endpoint supports two modes:
    1. Using an existing artwork ID from the database
    2. Providing a base64-encoded image directly

    The strength parameter controls how much the output differs from the input:
    - 0.0 = exact copy (no changes)
    - 1.0 = completely new image (input is ignored)
    - 0.75 (default) = balanced transformation

    Args:
        img2img_request: Request with image source and generation parameters

    Returns:
        LumiraCreateResponse with the generated image URL
    """
    import base64
    from io import BytesIO

    # Get source image
    if img2img_request.image_id:
        source_img = (
            db.query(GeneratedImage)
            .filter(GeneratedImage.id == img2img_request.image_id)
            .first()
        )
        if not source_img:
            raise HTTPException(status_code=404, detail="Source image not found")

        # Load image from file
        gallery_path = Path("gallery") / source_img.filename
        if not gallery_path.exists():
            # Try absolute path in case filename is already full path
            gallery_path = Path(source_img.filename)
            if not gallery_path.exists():
                raise HTTPException(
                    status_code=404, detail="Source image file not found"
                )

        source_pil = Image.open(gallery_path)
        original_prompt = str(source_img.prompt or "")
    elif img2img_request.image_base64:
        try:
            image_data = base64.b64decode(img2img_request.image_base64)
            source_pil = Image.open(BytesIO(image_data))
            original_prompt = ""
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid base64 image: {e}"
            ) from e
    else:
        raise HTTPException(
            status_code=400, detail="Either image_id or image_base64 must be provided"
        )

    # Use provided prompt or original
    prompt: str = str(img2img_request.prompt or original_prompt)
    if not prompt:
        prompt = "artistic interpretation, high quality"

    # Get Lumira's current state for the generation
    state = _get_lumira_state()
    mood_system = state["mood_system"]
    mood = mood_system.current_mood

    # Generate variation using img2img
    try:
        config_path = Path("config/config.yaml")
        config = load_config(config_path)
        try:
            _backend, generator = _build_studio_generator(
                config, mood=mood.value if mood else None, require_img2img=True
            )
        except RuntimeError as e:
            raise HTTPException(status_code=501, detail=str(e)) from e
        generator.load_model()

        if not hasattr(generator, "generate_img2img"):
            raise HTTPException(
                status_code=501,
                detail="Selected image backend does not support img2img",
            )

        images = generator.generate_img2img(
            prompt=prompt,
            image=source_pil,
            strength=img2img_request.strength,
            guidance_scale=img2img_request.guidance_scale,
        )

        if images and len(images) > 0:
            # Save the first generated image
            result_image = images[0]
            now = datetime.now()
            gallery_path = Path("gallery")
            date_path = gallery_path / now.strftime("%Y/%m/%d") / "archive"
            date_path.mkdir(parents=True, exist_ok=True)
            filename = (
                f"img2img_{uuid.uuid4().hex[:8]}_{now.strftime('%Y%m%d_%H%M%S')}.png"
            )
            save_path = date_path / filename
            result_image.save(save_path, "PNG")

            # Save metadata
            metadata_json = {
                "prompt": prompt,
                "metadata": {
                    "mood": mood.value,
                    "model": config.model.base_model,
                    "type": "img2img",
                    "strength": img2img_request.strength,
                    "source_id": img2img_request.image_id,
                },
                "created_at": now.isoformat(),
                "featured": False,
            }
            metadata_path = save_path.with_suffix(".json")
            metadata_path.write_text(json.dumps(metadata_json, indent=2))

            # Create database record
            new_image = GeneratedImage(
                filename=str(save_path),
                prompt=prompt,
                model_id="sdxl-img2img",
                generation_params={
                    "strength": img2img_request.strength,
                    "guidance_scale": img2img_request.guidance_scale,
                    "source_id": img2img_request.image_id,
                },
                status="curated",
                created_at=now,
            )
            db.add(new_image)
            db.commit()

            image_url = (
                f"/api/images/file/{now.strftime('%Y/%m/%d')}/archive/{filename}"
            )

            logger.info(
                "img2img_generated",
                source_id=img2img_request.image_id,
                strength=img2img_request.strength,
                image_url=image_url,
            )

            return LumiraCreateResponse(
                success=True,
                image_url=image_url,
                prompt=prompt,
                reflection=f"I reimagined this piece with {int(img2img_request.strength * 100)}% creative freedom.",
                style="img2img variation",
            )
        else:
            raise HTTPException(status_code=500, detail="Generation failed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Img2img generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if "generator" in locals():
            generator.clear_vram()


@router.post("/variations", response_model=VariationsResponse)
@limiter.limit(RateLimits.VARIATIONS)
async def generate_variations(
    request: Request,
    _auth: GenerationAuthDep,
    var_request: VariationsRequest,
    db: Session = Depends(get_db),
) -> VariationsResponse:
    """Generate multiple variations of an existing artwork.

    Creates variations based on the specified type:
    - style: Different artistic styles (impressionist, abstract, etc.)
    - mood: Different emotional atmospheres (dreamy, dark, vibrant, etc.)
    - composition: Different viewpoints and compositions

    Args:
        var_request: Request with image ID, count, and variation type

    Returns:
        VariationsResponse with list of generated variations
    """
    # Get source image
    source_img = (
        db.query(GeneratedImage)
        .filter(GeneratedImage.id == var_request.image_id)
        .first()
    )
    if not source_img:
        raise HTTPException(status_code=404, detail="Source image not found")

    gallery_path = Path("gallery") / source_img.filename
    if not gallery_path.exists():
        gallery_path = Path(source_img.filename)
        if not gallery_path.exists():
            raise HTTPException(status_code=404, detail="Source image file not found")

    source_pil = Image.open(gallery_path)
    original_prompt = source_img.prompt or "artwork"

    state = _get_lumira_state()
    mood_system = state["mood_system"]
    mood = mood_system.current_mood

    variations: list[VariationResult] = []

    # Variation strategies
    variation_prompts = {
        "style": [
            f"{original_prompt}, impressionist style",
            f"{original_prompt}, abstract expressionist",
            f"{original_prompt}, minimalist",
            f"{original_prompt}, surrealist interpretation",
            f"{original_prompt}, pop art style",
            f"{original_prompt}, watercolor painting",
            f"{original_prompt}, digital glitch art",
            f"{original_prompt}, noir aesthetic",
        ],
        "mood": [
            f"{original_prompt}, dreamy ethereal atmosphere",
            f"{original_prompt}, dark moody atmosphere",
            f"{original_prompt}, vibrant energetic feel",
            f"{original_prompt}, calm peaceful serenity",
            f"{original_prompt}, chaotic dynamic energy",
            f"{original_prompt}, melancholic nostalgic mood",
            f"{original_prompt}, playful whimsical feel",
            f"{original_prompt}, bold dramatic tension",
        ],
        "composition": [
            f"{original_prompt}, close-up detail view",
            f"{original_prompt}, wide panoramic view",
            f"{original_prompt}, birds eye view from above",
            f"{original_prompt}, dramatic low angle",
            f"{original_prompt}, reflected in water",
            f"{original_prompt}, through a window frame",
            f"{original_prompt}, fragmented mosaic composition",
            f"{original_prompt}, symmetrical balance",
        ],
    }

    prompts = variation_prompts.get(
        var_request.variation_type, variation_prompts["style"]
    )
    selected_prompts = random.sample(prompts, min(var_request.count, len(prompts)))

    try:
        config_path = Path("config/config.yaml")
        config = load_config(config_path)
        state = _get_lumira_state()
        mood = state["mood_system"].current_mood
        try:
            _backend, generator = _build_studio_generator(
                config,
                mood=mood.value if mood else None,
                require_img2img=True,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=501, detail=str(e)) from e
        generator.load_model()

        if not hasattr(generator, "generate_img2img"):
            raise HTTPException(
                status_code=501,
                detail="Selected image backend does not support img2img",
            )

        now = datetime.now()
        gallery_base = Path("gallery")
        date_path = gallery_base / now.strftime("%Y/%m/%d") / "archive"
        date_path.mkdir(parents=True, exist_ok=True)

        for i, prompt in enumerate(selected_prompts):
            # Use lower strength for variations to preserve more of original
            images = generator.generate_img2img(
                prompt=prompt,
                image=source_pil,
                strength=0.6,  # Preserve more of original
                guidance_scale=7.5,
            )

            if images and len(images) > 0:
                result_image = images[0]
                filename = f"var_{uuid.uuid4().hex[:8]}_{now.strftime('%Y%m%d_%H%M%S')}_{i}.png"
                save_path = date_path / filename
                result_image.save(save_path, "PNG")

                # Save metadata
                metadata_json = {
                    "prompt": prompt,
                    "metadata": {
                        "mood": mood.value,
                        "model": config.model.base_model,
                        "type": "variation",
                        "variation_type": var_request.variation_type,
                        "source_id": var_request.image_id,
                    },
                    "created_at": now.isoformat(),
                    "featured": False,
                }
                metadata_path = save_path.with_suffix(".json")
                metadata_path.write_text(json.dumps(metadata_json, indent=2))

                # Save to database
                new_image = GeneratedImage(
                    filename=str(save_path),
                    prompt=prompt,
                    model_id="sdxl-variation",
                    generation_params={
                        "variation_of": var_request.image_id,
                        "type": var_request.variation_type,
                    },
                    status="curated",
                    created_at=now,
                )
                db.add(new_image)

                style_desc = (
                    prompt.split(",")[-1].strip()
                    if "," in prompt
                    else var_request.variation_type
                )
                image_url = (
                    f"/api/images/file/{now.strftime('%Y/%m/%d')}/archive/{filename}"
                )
                variations.append(
                    VariationResult(
                        image_url=image_url,
                        variation_type=var_request.variation_type,
                        description=style_desc,
                    )
                )

        db.commit()

        logger.info(
            "variations_generated",
            source_id=var_request.image_id,
            variation_type=var_request.variation_type,
            count=len(variations),
        )

        return VariationsResponse(
            original_id=var_request.image_id,
            variations=variations,
            mood=mood.value if mood else "contemplative",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Variations generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if "generator" in locals():
            generator.clear_vram()


@router.post("/batch-create", response_model=BatchCreateResponse)
@limiter.limit(RateLimits.BATCH_CREATE)
async def batch_create(
    request: Request,
    batch_request: BatchCreateRequest,
    _auth: GenerationAuthDep,
) -> BatchCreateResponse:
    """Queue multiple artworks for creation.

    This endpoint creates multiple generation jobs that will be processed
    asynchronously. Use the job IDs to track progress.

    Args:
        batch_request: Request with count, optional mood, and theme

    Returns:
        BatchCreateResponse with job IDs for tracking
    """
    job_ids: list[str] = []
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"

    try:
        from ..queue import get_queue

        queue = get_queue()

        if queue.is_available():
            for i in range(batch_request.count):
                # Queue each creation
                queued_job_id = queue.enqueue_generation(
                    prompt=batch_request.theme or "",
                    params={
                        "mood": batch_request.mood,
                        "theme": batch_request.theme,
                        "batch_index": i,
                    },
                    priority="normal",
                    meta={
                        "type": "batch",
                        "batch_id": batch_id,
                        "mood": batch_request.mood,
                        "theme": batch_request.theme,
                        "batch_index": i,
                    },
                )

                if not queued_job_id:
                    raise RuntimeError(
                        f"Failed to enqueue batch item {i + 1} of {batch_request.count}"
                    )

                job_ids.append(queued_job_id)

            logger.info(
                "batch_creation_queued",
                batch_id=batch_id,
                count=batch_request.count,
                mood=batch_request.mood,
                theme=batch_request.theme,
            )

            return BatchCreateResponse(
                job_ids=job_ids,
                message=f"Queued {batch_request.count} artworks for creation",
            )
        else:
            logger.warning(
                "batch_creation_queue_unavailable",
                batch_id=batch_id,
                count=batch_request.count,
            )
            return BatchCreateResponse(
                job_ids=[],
                message="Batch creation is unavailable because the job queue is offline.",
            )

    except Exception as e:
        logger.error(
            "batch_creation_failed",
            batch_id=batch_id,
            count=batch_request.count,
            error=str(e),
        )
        return BatchCreateResponse(
            job_ids=job_ids,
            message="Batch creation could not be fully queued. Please try again.",
        )


# =============================================================================
# Knowledge Graph Endpoints
# =============================================================================


class KnowledgeGraphStatsResponse(BaseModel):
    """Knowledge graph statistics response."""

    connected: bool
    artworks: int
    subjects: int
    styles: int
    moods: int
    relationships: int = 0


class CreativeSuggestionsResponse(BaseModel):
    """Creative suggestions based on mood."""

    mood: str
    suggested_subjects: list[dict[str, Any]]
    suggested_styles: list[dict[str, Any]]


class ArtworkContextResponse(BaseModel):
    """Full context for an artwork from the knowledge graph."""

    id: str
    title: str | None
    prompt: str | None
    aesthetic_score: float | None
    subjects: list[dict[str, Any]]
    styles: list[dict[str, Any]]
    moods: list[dict[str, Any]]


@router.get("/knowledge/stats", response_model=KnowledgeGraphStatsResponse)
@limiter.limit("30/minute")
async def get_knowledge_stats(request: Request):
    """Get knowledge graph statistics.

    Returns counts of artworks, subjects, styles, and moods in the graph.
    """
    from ..knowledge import get_knowledge_graph

    graph = get_knowledge_graph()
    stats = graph.get_stats()

    return KnowledgeGraphStatsResponse(
        connected=stats.get("connected", False),
        artworks=stats.get("artworks", 0),
        subjects=stats.get("subjects", 0),
        styles=stats.get("styles", 0),
        moods=stats.get("moods", 0),
        relationships=stats.get("relationships", 0),
    )


@router.get("/knowledge/suggestions/{mood}", response_model=CreativeSuggestionsResponse)
@limiter.limit("30/minute")
async def get_creative_suggestions(request: Request, mood: str):
    """Get creative suggestions for a mood.

    Returns subjects and styles that have worked well for this mood,
    enabling smarter creative decisions.

    Args:
        mood: The mood to get suggestions for (e.g., "serene", "energetic")
    """
    from ..knowledge import get_knowledge_graph

    graph = get_knowledge_graph()
    suggestions = graph.get_creative_suggestions(mood)

    return CreativeSuggestionsResponse(
        mood=suggestions["mood"],
        suggested_subjects=suggestions["suggested_subjects"],
        suggested_styles=suggestions["suggested_styles"],
    )


@router.get("/knowledge/artwork/{artwork_id}", response_model=ArtworkContextResponse)
@limiter.limit("30/minute")
async def get_artwork_context(request: Request, artwork_id: str):
    """Get full context for an artwork from the knowledge graph.

    Returns all subjects, styles, and moods associated with an artwork.
    """
    from ..knowledge import get_knowledge_graph

    graph = get_knowledge_graph()
    context = graph.get_artwork_context(artwork_id)

    if not context:
        raise HTTPException(
            status_code=404, detail="Artwork not found in knowledge graph"
        )

    return ArtworkContextResponse(
        id=artwork_id,
        title=context.get("title"),
        prompt=context.get("prompt"),
        aesthetic_score=context.get("aesthetic_score"),
        subjects=context.get("subjects", []),
        styles=context.get("styles", []),
        moods=context.get("moods", []),
    )


# =============================================================================
# Social Media Posting Endpoints
# =============================================================================


class SocialPostRequest(BaseModel):
    """Request to post artwork to social media."""

    artwork_id: str | None = None  # ID of existing artwork
    image_path: str | None = None  # Or path to image
    title: str = "Untitled"
    caption: str | None = None
    mood: str | None = None
    style: str | None = None
    platforms: list[str] | None = None  # None = all available


class SocialPostResult(BaseModel):
    """Result from a social media post."""

    platform: str
    success: bool
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None


class SocialPostResponse(BaseModel):
    """Response from posting to social media."""

    results: list[SocialPostResult]
    successful_platforms: list[str]
    failed_platforms: list[str]


class SocialPlatformsResponse(BaseModel):
    """Available social media platforms."""

    available: list[str]
    configured: dict[str, bool]


@router.get("/social/platforms", response_model=SocialPlatformsResponse)
@limiter.limit("30/minute")
async def get_social_platforms(request: Request):
    """Get available social media platforms.

    Returns which platforms are configured and ready for posting.
    """
    from ..social import get_social_poster

    poster = get_social_poster()
    available = poster.get_available_platforms()

    return SocialPlatformsResponse(
        available=available,
        configured={
            "twitter": poster.twitter.is_available,
            "instagram": poster.instagram.is_available,
            "bluesky": poster.bluesky.is_available,
        },
    )


@router.post("/social/post", response_model=SocialPostResponse)
@limiter.limit("10/minute")
async def post_to_social(
    request: Request,
    post_request: SocialPostRequest,
    _auth: GenerationAuthDep,
):
    """Post artwork to social media platforms.

    Posts an artwork to configured social media platforms.
    Requires API credentials in environment variables.

    Args:
        artwork_id: ID of artwork from gallery (optional)
        image_path: Path to image file (optional, if not using artwork_id)
        title: Title of the artwork
        caption: Custom caption (optional)
        mood: Lumira's mood during creation (optional)
        style: Artistic style (optional)
        platforms: Specific platforms to post to (optional, defaults to all)
    """
    from ..social import get_social_poster

    poster = get_social_poster()

    # Get image
    image = None
    if post_request.image_path:
        # Containment: resolve against the gallery root and reject any path
        # that escapes it (prevents arbitrary-file read via ../ or absolute
        # paths). Mirrors gallery_routes._resolve_image_for_publish.
        gallery_base = Path("data/gallery").resolve()
        rel = post_request.image_path.lstrip("/").replace("\\", "/")
        image_path = (gallery_base / rel).resolve()
        try:
            image_path.relative_to(gallery_base)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid image path") from exc
        if not image_path.is_file():
            raise HTTPException(status_code=404, detail="Image file not found")
        image = Image.open(image_path)
    elif post_request.artwork_id:
        # Look up in gallery
        from ..gallery.manager import GalleryManager

        # Default gallery path
        gallery_path = Path("data/gallery")
        gallery = GalleryManager(gallery_path)
        images = gallery.list_images()

        # Find by ID (filename stem)
        for img_path in images:
            if post_request.artwork_id in img_path.stem:
                image = Image.open(img_path)
                break

        if image is None:
            raise HTTPException(status_code=404, detail="Artwork not found in gallery")
    else:
        raise HTTPException(
            status_code=400, detail="Either artwork_id or image_path required"
        )

    # Post to platforms
    results = poster.post_artwork(
        image=image,
        title=post_request.title,
        mood=post_request.mood,
        style=post_request.style,
        platforms=post_request.platforms,
    )

    # Build response
    post_results = []
    successful = []
    failed = []

    for platform, result in results.items():
        post_results.append(
            SocialPostResult(
                platform=result.platform,
                success=result.success,
                post_id=result.post_id,
                post_url=result.post_url,
                error=result.error,
            )
        )
        if result.success:
            successful.append(platform)
        else:
            failed.append(platform)

    logger.info(
        "social_post_complete",
        successful=successful,
        failed=failed,
    )

    return SocialPostResponse(
        results=post_results,
        successful_platforms=successful,
        failed_platforms=failed,
    )


# =============================================================================
# Preview & Inner Dialogue Endpoints (Lumira 2.0)
# =============================================================================


class PreviewRequest(BaseModel):
    """Request for fast preview generation."""

    prompt: str = Field(description="Generation prompt")
    style_weights: dict[str, float] | None = Field(
        default=None, description="LoRA style blend weights"
    )
    mood_blend: dict[str, float] | None = Field(
        default=None, description="Mood blend weights"
    )
    seed: int | None = Field(default=None, description="Random seed")


class PreviewResponse(BaseModel):
    """Response from preview generation."""

    success: bool
    session_id: str
    image_base64: str | None = None
    generation_time: float = 0.0
    prompt: str = ""
    seed: int = 0
    error: str | None = None


class PreviewApproveRequest(BaseModel):
    """Request to approve preview and generate full quality."""

    session_id: str = Field(description="Session ID from preview")
    prompt: str = Field(description="Original prompt")
    style_weights: dict[str, float] | None = None
    mood_blend: dict[str, float] | None = None


class PreviewApproveResponse(BaseModel):
    """Response from approved full generation."""

    success: bool
    session_id: str
    image_url: str | None = None
    total_time: float = 0.0
    error: str | None = None


class ExploreRequest(BaseModel):
    """Request for latent space exploration."""

    concept_a: str = Field(description="Starting concept")
    concept_b: str = Field(description="Ending concept")
    steps: int = Field(default=5, ge=2, le=10, description="Interpolation steps")
    use_slerp: bool = Field(
        default=True, description="Use spherical interpolation (recommended)"
    )


class ExploreResponse(BaseModel):
    """Response from latent exploration."""

    success: bool
    images_base64: list[str] = []
    prompts: list[str] = []
    interpolation_values: list[float] = []
    error: str | None = None


class DialogueTurn(BaseModel):
    """Single inner dialogue turn."""

    voice: str
    content: str
    timestamp: str
    metadata: dict[str, Any] | None = None


class DialogueHistoryResponse(BaseModel):
    """Inner dialogue history."""

    turns: list[DialogueTurn]
    current_concept: dict[str, Any] | None = None


@router.post("/preview", response_model=PreviewResponse)
@limiter.limit(RateLimits.PREVIEW)
async def generate_preview(
    request: Request,
    body: PreviewRequest,
    _auth: GenerationAuthDep,
):
    """Generate a fast preview using FLUX.1 Schnell (~2 seconds).

    Returns a low-step preview image for concept validation before
    committing to a full render.
    """
    from ..core.mood_blender import MoodBlender
    from ..core.preview_generator import PreviewGenerator
    from ..web.websocket import manager as ws_manager

    session_id = str(uuid.uuid4())

    try:
        state = _get_lumira_state()
        mood_system = state["mood_system"]

        # Get or create preview generator
        preview_gen = PreviewGenerator(
            mood_blender=MoodBlender(),
        )

        # Generate preview
        result = await preview_gen.preview(
            prompt=body.prompt,
            style_weights=body.style_weights,
            mood_blend=body.mood_blend or {mood_system.current_mood.value: 1.0},
            seed=body.seed,
        )

        if result.error:
            return PreviewResponse(
                success=False,
                session_id=session_id,
                error=result.error,
            )

        # Encode image
        image_base64 = result.get_image_base64()

        await ws_manager.broadcast_preview_ready(
            session_id=session_id,
            image_base64=image_base64,
            score=0.0,
            approved=False,
            prompt=result.prompt,
            generation_time=result.generation_time,
        )

        logger.info(
            "preview_generated",
            session_id=session_id,
            generation_time=round(result.generation_time, 2),
        )

        return PreviewResponse(
            success=True,
            session_id=session_id,
            image_base64=image_base64,
            generation_time=result.generation_time,
            prompt=result.prompt,
            seed=result.seed,
        )

    except Exception as e:
        logger.error("preview_failed", error=str(e), session_id=session_id)
        return PreviewResponse(
            success=False,
            session_id=session_id,
            error=str(e),
        )


@router.post("/preview/approve", response_model=PreviewApproveResponse)
@limiter.limit("5/minute")
async def approve_preview(
    request: Request,
    body: PreviewApproveRequest,
    _auth: GenerationAuthDep,
):
    """Approve a preview and generate full quality image.

    Call this after reviewing a preview to commit to full generation.
    """
    from ..web.websocket import manager as ws_manager

    try:
        # Load config and generator
        config = load_config()

        from ..core.generator import ImageGenerator

        generator = ImageGenerator(
            model_id=config.model.base_model,
            device=config.model.device,
        )

        # Start full generation
        await ws_manager.send_generation_start(
            session_id=body.session_id,
            prompt=body.prompt,
        )

        # Generate full quality
        generator.load_model()
        images = generator.generate(
            prompt=body.prompt,
            negative_prompt=config.generation.negative_prompt,
            width=config.generation.width,
            height=config.generation.height,
            num_inference_steps=config.generation.num_inference_steps,
            guidance_scale=config.generation.guidance_scale,
            num_images=1,
        )

        if images:
            # Save to gallery
            from ..gallery.manager import GalleryManager

            # Dominant mood = highest-weighted entry in the blend. Narrow inside
            # an if-block so the key lambda sees a non-optional dict.
            if body.mood_blend:
                mb = body.mood_blend
                dominant_mood = max(mb, key=lambda k: mb[k])
            else:
                dominant_mood = "contemplative"

            gallery = GalleryManager(Path("gallery"))
            saved_path = gallery.save_image(
                image=images[0],
                prompt=body.prompt,
                metadata={
                    "creation_type": "preview_approved",
                    "session_id": body.session_id,
                    "style_weights": body.style_weights,
                    "mood_blend": body.mood_blend,
                    "metadata": {
                        "mood": dominant_mood,
                    },
                },
            )

            image_url = f"/api/images/file/{saved_path.relative_to(Path('gallery'))}"

            await ws_manager.send_generation_complete(
                session_id=body.session_id,
                image_paths=[str(saved_path)],
                metadata={"image_url": image_url},
            )

            return PreviewApproveResponse(
                success=True,
                session_id=body.session_id,
                image_url=image_url,
            )

        return PreviewApproveResponse(
            success=False,
            session_id=body.session_id,
            error="No images generated",
        )

    except Exception as e:
        logger.error("preview_approve_failed", error=str(e))
        return PreviewApproveResponse(
            success=False,
            session_id=body.session_id,
            error=str(e),
        )


@router.post("/explore", response_model=ExploreResponse)
@limiter.limit(RateLimits.EXPLORE)
async def explore_latent_space(
    request: Request,
    body: ExploreRequest,
    _auth: GenerationAuthDep,
):
    """Explore the latent space between two concepts.

    Generates interpolated images along the path from concept_a to concept_b
    using spherical interpolation for smoother transitions.
    """
    from ..core.style_interpolator import LatentExplorer

    try:
        explorer = LatentExplorer()

        result = await explorer.explore_between(
            concept_a=body.concept_a,
            concept_b=body.concept_b,
            steps=body.steps,
            use_slerp=body.use_slerp,
        )

        if not result.images:
            return ExploreResponse(
                success=False,
                error="No pipeline available for exploration",
            )

        # Encode images to base64
        import base64
        import io

        images_base64 = []
        for img in result.images:
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            images_base64.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))

        return ExploreResponse(
            success=True,
            images_base64=images_base64,
            prompts=result.prompts,
            interpolation_values=result.interpolation_values,
        )

    except Exception as e:
        logger.error("explore_failed", error=str(e))
        return ExploreResponse(success=False, error=str(e))


@router.get("/dialogue", response_model=DialogueHistoryResponse)
@limiter.limit("60/minute")
async def get_dialogue_history(request: Request):
    """Get Lumira's recent inner dialogue history.

    Returns the deliberation history showing how Lumira's inner voices
    (Dreamer, Critic, Curator, Rememberer) discussed recent creations.
    """
    try:
        dialogue = _get_inner_dialogue()
        history_turns = dialogue.history

        turns = [
            DialogueTurn(
                voice=(
                    turn.voice.value
                    if hasattr(turn.voice, "value")
                    else str(turn.voice)
                ),
                content=turn.message,
                timestamp=(
                    turn.timestamp.isoformat()
                    if hasattr(turn.timestamp, "isoformat")
                    else str(turn.timestamp)
                ),
                metadata=turn.metadata,
            )
            for turn in history_turns[-40:]
        ]

        return DialogueHistoryResponse(
            turns=turns,
            current_concept=None,
        )

    except Exception as e:
        logger.error("dialogue_history_failed", error=str(e))
        return DialogueHistoryResponse(turns=[])


# =============================================================================
# Video Export Endpoint
# =============================================================================


class VideoExportRequest(BaseModel):
    """Request to export images as video."""

    image_ids: list[int] = Field(
        ..., description="List of image IDs to include in video", min_length=1
    )
    style: str = Field(
        default="slideshow",
        description="Video style: 'slideshow' (crossfade) or 'zoom' (Ken Burns on single image)",
    )
    duration_per_image: float = Field(
        default=3.0, ge=0.5, le=30.0, description="Seconds per image"
    )
    fps: int = Field(default=24, ge=12, le=60, description="Frames per second")
    fade_duration: float = Field(
        default=0.5, ge=0.0, le=5.0, description="Crossfade duration (slideshow only)"
    )
    zoom_start: float = Field(
        default=1.0, ge=0.5, le=2.0, description="Starting zoom level (zoom only)"
    )
    zoom_end: float = Field(
        default=1.3, ge=0.5, le=2.0, description="Ending zoom level (zoom only)"
    )


class VideoExportResponse(BaseModel):
    """Response from video export."""

    success: bool
    video_url: str | None = None
    video_path: str | None = None
    duration_seconds: float | None = None
    frame_count: int | None = None
    error: str | None = None


@router.post("/export/video", response_model=VideoExportResponse)
@limiter.limit("5/minute")
async def export_video(
    request: Request,
    _auth: GenerationAuthDep,
    body: VideoExportRequest,
    db: Session = Depends(get_db),
):
    """Export images as a video slideshow or Ken Burns zoom.

    Requires the 'video' optional dependency: pip install lumira[video]

    Supported styles:
    - slideshow: Multiple images with crossfade transitions
    - zoom: Ken Burns zoom effect on a single image
    """
    from pathlib import Path as PathLib

    from .dependencies import get_gallery_path

    try:
        gallery_path = get_gallery_path()
    except Exception as e:
        raise HTTPException(status_code=503, detail="Gallery not initialized") from e

    # Fetch images from database
    images = (
        db.query(GeneratedImage).filter(GeneratedImage.id.in_(body.image_ids)).all()
    )

    if not images:
        raise HTTPException(status_code=404, detail="No images found")

    # Preserve order from request
    id_to_image = {img.id: img for img in images}
    ordered_images = [id_to_image[id_] for id_ in body.image_ids if id_ in id_to_image]

    if len(ordered_images) != len(body.image_ids):
        missing = set(body.image_ids) - set(id_to_image.keys())
        raise HTTPException(
            status_code=404, detail=f"Images not found: {sorted(missing)}"
        )

    # Find actual file paths - images stored as gallery_path/year/month/day/...
    gallery_root = PathLib(gallery_path)
    image_paths: list[str] = []

    for img in ordered_images:
        # Search for the file in the gallery directory structure
        matches = list(gallery_root.glob(f"**/{img.filename}"))
        if not matches:
            raise HTTPException(
                status_code=404,
                detail=f"Image file not found: {img.filename}",
            )
        image_paths.append(str(matches[0]))

    # Validate style-specific requirements
    if body.style == "zoom" and len(image_paths) != 1:
        raise HTTPException(
            status_code=400,
            detail="Zoom style requires exactly 1 image",
        )

    if body.style == "slideshow" and len(image_paths) < 2:
        raise HTTPException(
            status_code=400,
            detail="Slideshow style requires at least 2 images",
        )

    # Generate video using video.py utilities
    try:
        from ..utils.video import create_slideshow, create_zoom_video

        if body.style == "zoom":
            video_path = create_zoom_video(
                image_path=image_paths[0],
                duration=body.duration_per_image,
                fps=body.fps,
                zoom_start=body.zoom_start,
                zoom_end=body.zoom_end,
            )
            duration = body.duration_per_image
        else:
            video_path = create_slideshow(
                image_paths=image_paths,
                duration_per_image=body.duration_per_image,
                fps=body.fps,
                fade_duration=body.fade_duration,
            )
            duration = body.duration_per_image * len(image_paths)

        logger.info(
            "video_exported",
            style=body.style,
            image_count=len(image_paths),
            duration=duration,
            path=video_path,
        )

        return VideoExportResponse(
            success=True,
            video_path=video_path,
            duration_seconds=duration,
            frame_count=int(duration * body.fps),
        )

    except ImportError as e:
        logger.error("video_export_missing_dependency", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Video export requires moviepy. Install with: pip install lumira[video]",
        ) from e
    except Exception as e:
        logger.error("video_export_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Video generation failed: {e}",
        ) from e


@router.get("/export/video/download")
@limiter.limit("30/minute")
async def download_video(
    request: Request,
    path: str,
):
    """Download a generated video file.

    Args:
        path: Path to the video file (returned by /export/video)
    """
    from pathlib import Path as PathLib

    from fastapi.responses import FileResponse

    from ..utils.video import export_dir

    video_path = PathLib(path)

    # Security: only allow files from Lumira's own export subdirectory, not
    # the shared system temp root (which any process can write to).
    export_base = export_dir().resolve()
    try:
        video_path.resolve().relative_to(export_base)
    except ValueError as e:
        raise HTTPException(status_code=403, detail="Access denied") from e

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    if not video_path.suffix.lower() == ".mp4":
        raise HTTPException(status_code=400, detail="Invalid file type")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=video_path.name,
    )
