"""API routes for advanced prompt utilities."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..utils.logging import get_logger
from ..utils.prompt_emphasis import PromptEmphasis
from ..utils.prompt_matrix import PromptMatrix
from ..utils.style_presets import StylePresetsManager
from .rate_limit import RATE_LIMIT_ENABLED

logger = get_logger(__name__)

router = APIRouter(prefix="/api/prompt", tags=["prompt"])
limiter = Limiter(key_func=get_remote_address, enabled=RATE_LIMIT_ENABLED)

# Initialize utilities
prompt_emphasis = PromptEmphasis()
prompt_matrix = PromptMatrix()
style_presets = StylePresetsManager(Path("config/style_presets.json"))


class EmphasisRequest(BaseModel):
    """Request model for emphasis parsing."""

    prompt: str


class EmphasisResponse(BaseModel):
    """Response model for emphasis parsing."""

    original: str
    parsed: str
    format: str = "compel"


class MatrixRequest(BaseModel):
    """Request model for prompt matrix generation."""

    prompt: str
    max_combinations: int = 100


class MatrixResponse(BaseModel):
    """Response model for prompt matrix generation."""

    original: str
    combinations: list[str]
    count: int


class StylePresetResponse(BaseModel):
    """Response model for style preset."""

    name: str
    description: str
    positive: str
    negative: str
    category: str


class ApplyStyleRequest(BaseModel):
    """Request model for applying style preset."""

    preset_name: str
    user_prompt: str


class ApplyStyleResponse(BaseModel):
    """Response model for applying style preset."""

    preset_name: str
    original_prompt: str
    enhanced_prompt: str
    negative: str
    category: str


@router.post("/emphasis", response_model=EmphasisResponse)
@limiter.limit("60/minute")
async def parse_emphasis(request: Request, emphasis_request: EmphasisRequest):
    """Parse emphasis syntax in prompts.

    Converts AUTOMATIC1111-style (text:weight) syntax to Compel format.

    Examples:
    - (masterpiece:1.5) -> (masterpiece)1.5+
    - (high quality) -> (high quality)1.1+
    - (bad:0.8) -> (bad)0.8-
    """
    try:
        parsed = prompt_emphasis.apply_emphasis_to_compel(emphasis_request.prompt)
        return EmphasisResponse(
            original=emphasis_request.prompt,
            parsed=parsed,
        )
    except Exception as e:
        logger.error("emphasis_parse_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/matrix", response_model=MatrixResponse)
@limiter.limit("30/minute")
async def generate_matrix(request: Request, matrix_request: MatrixRequest):
    """Generate all combinations from prompt matrix syntax.

    Uses {option1|option2} syntax to create combinatorial prompts.

    Example:
    - Input: "a {red|blue} {cat|dog}"
    - Output: ["a red cat", "a red dog", "a blue cat", "a blue dog"]
    """
    try:
        # Validate syntax first
        is_valid, error = prompt_matrix.validate_syntax(matrix_request.prompt)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid syntax: {error}")

        # Count combinations cheaply BEFORE expanding, to avoid a
        # combinatorial-explosion DoS (parse_prompt materializes the full
        # Cartesian product in memory).
        combo_count = prompt_matrix.count_combinations(matrix_request.prompt)
        if combo_count > matrix_request.max_combinations:
            raise HTTPException(
                status_code=400,
                detail=f"Too many combinations ({combo_count}). Maximum is {matrix_request.max_combinations}.",
            )

        # Safe to expand now.
        combinations = prompt_matrix.parse_prompt(matrix_request.prompt)

        return MatrixResponse(
            original=matrix_request.prompt,
            combinations=combinations,
            count=len(combinations),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("matrix_generation_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/styles", response_model=list[StylePresetResponse])
@limiter.limit("60/minute")
async def list_style_presets(
    request: Request,
    category: str | None = Query(None, description="Filter by category"),
):
    """List all available style presets."""
    try:
        all_presets = style_presets.list_presets()

        # Filter by category if provided
        if category:
            all_presets = [
                p
                for p in all_presets
                if p.category and category.lower() == p.category.lower()
            ]

        return [
            StylePresetResponse(
                name=preset.name,
                description=preset.description,
                positive=preset.positive,
                negative=preset.negative,
                category=preset.category,
            )
            for preset in all_presets
        ]
    except Exception as e:
        logger.error("list_presets_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/styles/{preset_name}", response_model=StylePresetResponse)
@limiter.limit("60/minute")
async def get_style_preset(request: Request, preset_name: str):
    """Get a specific style preset by name."""
    try:
        preset = style_presets.get_preset(preset_name)
        if not preset:
            raise HTTPException(
                status_code=404, detail=f"Style preset '{preset_name}' not found"
            )

        return StylePresetResponse(
            name=preset.name,
            description=preset.description,
            positive=preset.positive,
            negative=preset.negative,
            category=preset.category,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_preset_failed", preset_name=preset_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/styles/apply", response_model=ApplyStyleResponse)
@limiter.limit("60/minute")
async def apply_style_preset(request: Request, apply_request: ApplyStyleRequest):
    """Apply a style preset to user prompt.

    Combines the user's prompt with the style's template and settings.
    """
    try:
        preset = style_presets.get_preset(apply_request.preset_name)
        if not preset:
            raise HTTPException(
                status_code=404,
                detail=f"Style preset '{apply_request.preset_name}' not found",
            )

        # Apply preset to user prompt (returns tuple of positive and negative)
        enhanced_positive, enhanced_negative = style_presets.apply_preset(
            apply_request.preset_name,
            apply_request.user_prompt,
        )

        return ApplyStyleResponse(
            preset_name=apply_request.preset_name,
            original_prompt=apply_request.user_prompt,
            enhanced_prompt=enhanced_positive,
            negative=enhanced_negative,
            category=preset.category,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("apply_preset_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
