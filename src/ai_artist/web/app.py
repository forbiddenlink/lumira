"""FastAPI web gallery application with modern best practices."""

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import cast

import aiofiles
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.datastructures import UploadFile as StarletteUploadFile

from ..gallery.manager import GalleryManager
from ..utils.config import WebConfig
from ..utils.logging import get_logger
from .admin import router as admin_router
from .dependencies import (
    GalleryManagerDep,
    GalleryPathDep,
    get_web_config,
    require_api_key,
    set_gallery_manager,
    set_web_config,
)
from .exception_handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .feedback import router as feedback_router
from .gallery_routes import router as gallery_router
from .health import router as health_router
from .helpers import (
    calculate_gallery_stats,
    filter_by_search,
    is_valid_image,
    load_image_metadata,
)
from .lumira_routes import router as lumira_router
from .metrics_routes import router as metrics_router
from .middleware import (
    ErrorHandlingMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    add_cors_middleware,
)
from .prompt_routes import router as prompt_router
from .rate_limit import rate_limit_exceeded_handler
from .websocket import manager as ws_manager

# Error message constants
ERROR_INVALID_FILE_TYPE = "Invalid file type"
ERROR_IMAGE_NOT_FOUND = "Image not found"
ERROR_ACCESS_DENIED = "Access denied"
METADATA_FILE_SUFFIX = ".json"

# Concurrency control for image generation
# Only allow 1 concurrent generation to prevent VRAM exhaustion
_generation_semaphore = asyncio.Semaphore(1)
_generation_timeout_seconds = 300  # 5 minute timeout for generation
_generation_queue_size = 0  # Track queue depth

# Background task tracking to prevent premature garbage collection
_background_tasks: set = set()

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

logger = get_logger(__name__)


ExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]


class ImageMetadata(BaseModel):
    """Image metadata response model."""

    path: str
    filename: str
    prompt: str
    created_at: str
    featured: bool
    metadata: dict
    thumbnail_url: str
    full_url: str
    id: int | None = None
    share_id: str | None = None
    is_public: bool = False
    share_url: str | None = None


class GalleryStats(BaseModel):
    """Gallery statistics response model."""

    total_images: int
    featured_images: int
    total_prompts: int
    date_range: dict


class PromptTemplate(BaseModel):
    """Prompt template model."""

    id: str
    name: str
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    num_inference_steps: int = 30
    guidance_scale: float = 7.5
    created_at: str
    tags: list[str] = Field(default_factory=list)


class CreateTemplateRequest(BaseModel):
    """Create template request model."""

    name: str
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    num_inference_steps: int = 30
    guidance_scale: float = 7.5
    tags: list[str] = Field(default_factory=list)


class GenerationRequest(BaseModel):
    """Image generation request model."""

    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: str = Field(default="", max_length=1000)
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)
    num_inference_steps: int = Field(default=30, ge=1, le=150)
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)
    num_images: int = Field(default=1, ge=1, le=4)
    seed: int | None = None


class GenerationResponse(BaseModel):
    """Image generation response model."""

    session_id: str
    message: str
    status: str


def validate_generation_request(request: GenerationRequest) -> None:
    """Validate generation request parameters.

    Args:
        request: The generation request to validate

    Raises:
        HTTPException: If validation fails
    """
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=422, detail="Prompt cannot be empty")

    if (
        request.width < 512
        or request.width > 2048
        or request.height < 512
        or request.height > 2048
    ):
        raise HTTPException(
            status_code=422, detail="Dimensions must be between 512 and 2048"
        )

    if request.width % 8 != 0 or request.height % 8 != 0:
        raise HTTPException(status_code=422, detail="Dimensions must be multiples of 8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    # Initialize database tables on startup
    from ..db.models import Base
    from ..db.session import create_db_engine
    from .dependencies import _gallery_manager

    db_path = Path("data/ai_artist.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    logger.info("database_initialized", db_path=str(db_path))

    # Only initialize if not already set (e.g., by tests)
    if _gallery_manager is None:
        # Startup
        gallery_path = Path("gallery")
        gallery_manager_instance = GalleryManager(gallery_path)
        set_gallery_manager(gallery_manager_instance, str(gallery_path))
        logger.info("web_gallery_started", gallery_path=str(gallery_path))

    # Try to load web config from config file or environment
    try:
        from ..utils.config import load_config

        config_path = Path("config/config.yaml")
        if config_path.exists():
            config = load_config(config_path)
            web_config = config.web
            observability_config = config.observability
        else:
            # Load from environment variables (e.g., RAILWAY_API_KEY)
            web_config = WebConfig.from_env()
            observability_config = None

        set_web_config(web_config)
        logger.info(
            "web_config_loaded",
            api_keys_configured=len(web_config.api_keys) > 0,
            cors_origins=web_config.cors_origins,
        )

        # Initialize Sentry error tracking if configured
        if observability_config and observability_config.sentry_dsn:
            from ..monitoring import init_sentry

            init_sentry(
                dsn=observability_config.sentry_dsn.get_secret_value(),
                environment=observability_config.sentry_environment,
                traces_sample_rate=observability_config.sentry_traces_sample_rate,
                profiles_sample_rate=observability_config.sentry_profiles_sample_rate,
            )

    except Exception as e:
        logger.warning("web_config_load_failed", error=str(e))
        # Use default config (no auth required)
        set_web_config(WebConfig())

    # Initialize reflection scheduling for Lumira's hierarchical reflection system
    reflection_scheduler = None
    try:
        from ..personality.hierarchical_reflection import get_hierarchical_reflection
        from ..scheduling.scheduler import CreationScheduler

        reflection_system = get_hierarchical_reflection()
        reflection_scheduler = CreationScheduler()

        # Schedule daily reflection at 11 PM
        async def daily_reflection_task():
            from ..personality.enhanced_memory import get_memory_system

            memory = get_memory_system()
            episodes = memory.get_recent_episodes(limit=50)
            reflection_system.generate_daily_reflection(episodes=episodes)
            logger.info("daily_reflection_generated")

        reflection_scheduler.add_daily_job(
            daily_reflection_task,
            hour=23,
            minute=0,
            job_id="lumira_daily_reflection",
        )

        # Schedule weekly synthesis on Sundays at 10 PM
        async def weekly_synthesis_task():
            from ..personality.enhanced_memory import get_memory_system

            memory = get_memory_system()
            episodes = memory.get_recent_episodes(limit=200)
            reflection_system.generate_weekly_synthesis(episodes=episodes)
            logger.info("weekly_synthesis_generated")

        reflection_scheduler.add_weekly_job(
            weekly_synthesis_task,
            day_of_week="sun",
            hour=22,
            minute=0,
            job_id="lumira_weekly_synthesis",
        )

        reflection_scheduler.start()
        logger.info(
            "reflection_scheduling_initialized",
            jobs=len(reflection_scheduler.list_jobs()),
        )
    except Exception as e:
        logger.warning("reflection_scheduling_failed", error=str(e))

    yield

    # Shutdown
    logger.info("web_gallery_shutdown")
    if reflection_scheduler:
        reflection_scheduler.shutdown()
        logger.info("reflection_scheduler_shutdown")


# OpenAPI tag metadata for organizing endpoints
tags_metadata = [
    {
        "name": "lumira",
        "description": "Lumira's personality, mood, and creation endpoints. Control the autonomous AI artist.",
    },
    {
        "name": "gallery",
        "description": "Community gallery with public sharing, likes, comments, and collections.",
    },
    {
        "name": "images",
        "description": "Direct image management - list, serve, delete, and feature images.",
    },
    {
        "name": "generation",
        "description": "Image generation endpoints with WebSocket progress updates.",
    },
    {
        "name": "templates",
        "description": "Prompt template management for saving and reusing generation settings.",
    },
    {
        "name": "prompt",
        "description": "Advanced prompt utilities - emphasis parsing, matrix expansion, style presets.",
    },
    {
        "name": "feedback",
        "description": "User feedback and adaptive learning system.",
    },
    {
        "name": "admin",
        "description": "Admin dashboard and image upload endpoints. Requires API key.",
    },
    {
        "name": "health",
        "description": "Health checks, liveness, and readiness probes for Kubernetes.",
    },
    {
        "name": "metrics",
        "description": "Prometheus metrics endpoint for monitoring.",
    },
    {
        "name": "pages",
        "description": "HTML page endpoints - gallery views, Lumira studio, and PWA assets.",
    },
]

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Lumira API",
    description="""
Lumira is an autonomous AI artist system with personality, moods, memory, and creative independence.

## Features

- **Personality System**: 10 distinct moods influencing artistic output
- **Memory**: 3-layer episodic, semantic, and working memory
- **Image Generation**: SDXL, FLUX.2, LoRA, ControlNet support
- **Gallery**: Community features with likes, comments, collections
- **Adaptive Learning**: Multi-armed bandit learning from feedback

## Authentication

Admin endpoints require an `X-API-Key` header. In development mode (no keys configured),
all endpoints are accessible.

## WebSocket

Connect to `/ws` for real-time generation progress updates.
""",
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add rate limiter to app state
app.state.limiter = limiter

# Add exception handlers
# FastAPI accepts subtype-specific handlers at runtime; cast for static typing.
app.add_exception_handler(
    HTTPException,
    cast(ExceptionHandler, http_exception_handler),
)
app.add_exception_handler(
    RequestValidationError,
    cast(ExceptionHandler, validation_exception_handler),
)
app.add_exception_handler(
    Exception,
    cast(ExceptionHandler, general_exception_handler),
)
app.add_exception_handler(
    RateLimitExceeded,
    cast(ExceptionHandler, rate_limit_exceeded_handler),
)

# Add middleware (added in reverse order of execution)
# CORS must be added last so it processes requests first
# Note: CORS origins from config are applied during lifespan
add_cors_middleware(app)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ErrorHandlingMiddleware)

# Include routers
app.include_router(health_router)
app.include_router(lumira_router)
app.include_router(prompt_router)
app.include_router(feedback_router)
app.include_router(gallery_router)
app.include_router(metrics_router)
app.include_router(admin_router)

# Templates directory
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Static files directory
static_dir = Path(__file__).parent.parent.parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse, tags=["pages"])
async def root(request: Request):
    """Serve modern gallery homepage."""
    return templates.TemplateResponse(
        request,
        "gallery_modern.html",
        {"title": "Lumira — AI Art Gallery"},
    )


@app.get("/share/{share_id}", response_class=HTMLResponse, tags=["pages"])
async def share_page(request: Request, share_id: str):
    """Serve shared image page.

    Looks up the shared image and renders an OG-friendly share page.
    Falls back to a 404 page if the image is not found.
    """
    from sqlalchemy.orm import Session

    from ..db.models import GeneratedImage
    from ..db.session import get_db

    db_gen = get_db()
    db: Session = next(db_gen)
    try:
        image = (
            db.query(GeneratedImage)
            .filter(
                GeneratedImage.share_id == share_id,
                GeneratedImage.is_public.is_(True),
            )
            .first()
        )
    except Exception as e:
        logger.error("share_page_error", share_id=share_id, error=str(e))
        image = None
    finally:
        db_gen.close()

    if image:
        base_url = str(request.base_url).rstrip("/")
        image_url = f"{base_url}/api/images/file/{image.filename}"
        share_url = f"{base_url}/share/{share_id}"
        return templates.TemplateResponse(
            request,
            "share.html",
            {
                "title": f"Artwork by Lumira — {(image.prompt or 'AI Art')[:60]}",
                "image_url": image_url,
                "prompt": image.prompt or "AI-generated artwork",
                "share_id": share_id,
                "base_url": base_url,
                "share_url": share_url,
            },
        )

    # Image not found — render a friendly 404
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": "Artwork Not Found",
            "status_code": 404,
            "message": "This shared artwork could not be found. It may have been removed or made private.",
        },
        status_code=404,
    )


@app.get("/lumira", response_class=HTMLResponse, tags=["pages"])
async def lumira_page(request: Request):
    """Serve Lumira's creative studio.

    Personality, mood, and creation interface.
    """
    return templates.TemplateResponse(
        request,
        "lumira.html",
        {"title": "Lumira | Autonomous AI Artist"},
    )


@app.get("/monitoring", response_class=HTMLResponse, tags=["pages"])
async def monitoring_page(request: Request):
    """Operational monitoring dashboard for Lumira."""
    return templates.TemplateResponse(
        request,
        "monitoring.html",
        {"title": "Lumira Monitoring"},
    )


@app.get("/robots.txt", response_class=PlainTextResponse, tags=["pages"])
async def robots_txt(request: Request):
    """Serve robots.txt for search engine crawlers."""
    base_url = str(request.base_url).rstrip("/")
    robots_content = f"""# AI Artist Gallery robots.txt
User-agent: *
Allow: /
Disallow: /api/
Disallow: /test/

# Sitemap
Sitemap: {base_url}/sitemap.xml
"""
    return PlainTextResponse(content=robots_content, media_type="text/plain")


@app.get("/sitemap.xml", tags=["pages"])
async def sitemap_xml(request: Request):
    """Serve XML sitemap for search engine indexing."""
    base_url = str(request.base_url).rstrip("/")

    # Build sitemap with main pages
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{base_url}/</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{base_url}/lumira</loc>
        <changefreq>daily</changefreq>
        <priority>0.9</priority>
    </url>
    <url>
        <loc>{base_url}/classic</loc>
        <changefreq>weekly</changefreq>
        <priority>0.5</priority>
    </url>
</urlset>
"""
    return Response(content=sitemap_content, media_type="application/xml")


@app.get("/manifest.json", tags=["pages"])
async def manifest():
    """Serve PWA manifest file."""
    manifest_path = static_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    return FileResponse(manifest_path, media_type="application/manifest+json")


@app.get("/service-worker.js", tags=["pages"])
async def service_worker():
    """Serve service worker for PWA."""
    sw_path = static_dir / "service-worker.js"
    if not sw_path.exists():
        raise HTTPException(status_code=404, detail="Service worker not found")
    return FileResponse(sw_path, media_type="application/javascript")


@app.get("/offline.html", response_class=HTMLResponse, tags=["pages"])
async def offline_page():
    """Serve offline fallback page."""
    offline_path = static_dir / "offline.html"
    if not offline_path.exists():
        raise HTTPException(status_code=404, detail="Offline page not found")
    return FileResponse(offline_path)


@app.get("/classic", response_class=HTMLResponse, tags=["pages"])
async def classic_gallery(request: Request):
    """Serve classic gallery page."""
    return templates.TemplateResponse(
        request,
        "gallery.html",
        {"title": "AI Artist Gallery - Classic"},
    )


@app.get("/test/websocket", response_class=HTMLResponse, tags=["pages"])
async def test_websocket(request: Request):
    """Serve WebSocket test page — debug builds only."""
    config = get_web_config()
    if not getattr(config, "debug", False):
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse(
        request,
        "test_websocket.html",
        {"title": "WebSocket Test"},
    )


@app.get("/api/auth-mode", tags=["health"])
async def auth_mode():
    """Check if authentication is required for admin actions.

    Used by the frontend to hide admin-only UI controls in production.
    """
    config = get_web_config()
    return {"auth_required": len(config.api_keys) > 0}


@app.get("/api/images", response_model=list[ImageMetadata], tags=["images"])
@limiter.limit("60/minute")
async def list_images(
    request: Request,
    response: Response,
    gallery_manager: GalleryManagerDep,
    gallery_path: GalleryPathDep,
    featured: bool | None = Query(None, description="Filter by featured status"),
    limit: int = Query(50, ge=1, le=500, description="Number of images to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    search: str | None = Query(None, description="Search in prompts"),
    sort_by: str = Query("created_at", description="Sort field: created_at or score"),
    mood: str | None = Query(None, description="Filter by creation mood"),
):
    """List all images with metadata."""
    # Prevent caching to ensure fresh results
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # --- DB-first path (faster than full filesystem glob + stat per file) ---
    # Only used when not filtering by featured=True (featured not stored in DB)
    if featured is not True:
        try:
            from ..db.models import GeneratedImage
            from ..db.session import get_db

            db_gen = get_db()
            db = next(db_gen)
            try:
                if sort_by == "score":
                    query = db.query(GeneratedImage).order_by(
                        GeneratedImage.final_score.desc().nulls_last()
                    )
                else:
                    query = db.query(GeneratedImage).order_by(
                        GeneratedImage.created_at.desc()
                    )
                if search:
                    query = query.filter(GeneratedImage.prompt.ilike(f"%{search}%"))
                db_rows = query.all()
            finally:
                db_gen.close()

            if db_rows:
                gallery_base = Path(gallery_path)
                base_url = str(request.base_url).rstrip("/")
                results: list[ImageMetadata] = []
                for row in db_rows:
                    row_path = Path(row.filename)
                    if not row_path.exists():
                        continue
                    is_featured = "featured" in row.filename.replace("\\", "/")
                    if featured is False and is_featured:
                        continue
                    try:
                        rel = row_path.relative_to(gallery_base)
                    except ValueError:
                        rel = row_path
                    gen_params = row.generation_params or {}
                    from ..utils.metadata_helpers import enrich_generation_metadata

                    enriched = enrich_generation_metadata(
                        gen_params,
                        status=str(row.status) if row.status else None,
                    )
                    share_id = str(row.share_id) if row.share_id else None
                    is_public = bool(row.is_public)
                    results.append(
                        ImageMetadata(
                            path=str(rel),
                            filename=row_path.name,
                            prompt=row.prompt or "",
                            created_at=(
                                row.created_at.isoformat() if row.created_at else ""
                            ),
                            featured=is_featured,
                            metadata={
                                **enriched,
                                "model": row.model_id or "",
                                "final_score": row.final_score,
                            },
                            thumbnail_url=f"/api/images/file/{rel}",
                            full_url=f"/api/images/file/{rel}",
                            id=int(row.id),
                            share_id=share_id,
                            is_public=is_public,
                            share_url=(
                                f"{base_url}/share/{share_id}"
                                if share_id and is_public
                                else None
                            ),
                        )
                    )
                if mood:
                    results = [
                        r
                        for r in results
                        if (r.metadata.get("mood", "").lower() == mood.lower())
                    ]
                total_valid = len(results)
                paginated = results[offset : offset + limit]
                logger.info(
                    "images_listed_via_db",
                    total=len(db_rows),
                    valid=total_valid,
                    returned=len(paginated),
                    featured=featured,
                    search=search,
                )
                return paginated
        except Exception as db_err:
            logger.warning("db_list_images_failed_using_filesystem", error=str(db_err))
    # --- Filesystem fallback ---

    # Get image paths
    image_paths = gallery_manager.list_images(featured_only=bool(featured))
    total_images = len(image_paths)

    # Filter by search term if provided
    if search:
        image_paths = filter_by_search(image_paths, search)

    # Build response with validation (before pagination to get accurate metadata)
    results = []
    for img_path in image_paths:
        # Validate image
        is_valid, reason = is_valid_image(img_path, Path(gallery_path))
        if not is_valid:
            logger.debug("skipping_invalid_image", path=str(img_path), reason=reason)
            continue

        # Load metadata
        metadata = load_image_metadata(img_path, Path(gallery_path))
        if metadata:
            results.append(ImageMetadata(**metadata))
        else:
            logger.debug("skipping_image_no_metadata", path=str(img_path))

    # Sort by created_at to ensure newest first (more reliable than file mtime)
    # Use file path timestamp as fallback for any missing created_at
    results.sort(
        key=lambda x: x.created_at if x.created_at else "1970-01-01T00:00:00",
        reverse=True,
    )

    # Apply pagination after sorting
    total_valid = len(results)
    results = results[offset : offset + limit]

    logger.info(
        "images_listed",
        total=total_images,
        valid=total_valid,
        returned=len(results),
        featured=featured,
        search=search,
    )

    return results


@app.get("/api/images/file/{file_path:path}", tags=["images"])
@limiter.limit("60/minute")
async def get_image_file(
    request: Request,
    file_path: str,
    gallery_path: GalleryPathDep,
    download: bool = False,
):
    """Serve image file."""
    gallery_path_obj = Path(gallery_path)
    if not gallery_path_obj:
        raise HTTPException(status_code=503, detail="Gallery not initialized")

    # Validate file extension
    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    file_ext = Path(file_path).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=ERROR_INVALID_FILE_TYPE)

    full_path = gallery_path_obj / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=ERROR_IMAGE_NOT_FOUND)

    # Security: ensure path is within gallery
    try:
        full_path.resolve().relative_to(gallery_path_obj.resolve())
    except ValueError as e:
        raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED) from e

    # Detect MIME type from file extension
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = mime_types.get(file_ext, "image/png")

    # Images are immutable (filenames include timestamp/uuid) — cache aggressively
    stat = full_path.stat()
    etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        from fastapi.responses import Response as FastAPIResponse

        return FastAPIResponse(status_code=304)

    file_response = FileResponse(full_path, media_type=media_type)
    file_response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    file_response.headers["ETag"] = etag
    if download:
        file_response.headers["Content-Disposition"] = (
            f'attachment; filename="{full_path.name}"'
        )
    return file_response


@app.get("/api/stats", response_model=GalleryStats, tags=["images"])
@limiter.limit("60/minute")
async def get_stats(
    request: Request,
    gallery_manager: GalleryManagerDep,
):
    """Get gallery statistics."""
    featured_images = gallery_manager.list_images(featured_only=True)

    # Calculate stats using helper function
    stats = calculate_gallery_stats(gallery_manager)

    return GalleryStats(
        total_images=stats["total_images"],
        featured_images=len(featured_images),
        total_prompts=stats["total_prompts"],
        date_range=stats["date_range"],
    )


@app.delete("/api/images/{file_path:path}", tags=["images"])
@limiter.limit("60/minute")
async def delete_image(
    request: Request,
    file_path: str,
    gallery_path: GalleryPathDep,
    _api_key: str = Depends(require_api_key),
):
    """Delete an image and its metadata."""
    gallery_path_obj = Path(gallery_path)

    # Validate and resolve full paths
    full_image_path = gallery_path_obj / file_path
    metadata_path = full_image_path.with_suffix(METADATA_FILE_SUFFIX)

    # Security check
    try:
        full_image_path.resolve().relative_to(gallery_path_obj.resolve())
    except ValueError as e:
        raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED) from e

    # Delete image file
    if full_image_path.exists():
        full_image_path.unlink()
        logger.info("image_deleted", path=str(file_path))
    else:
        raise HTTPException(status_code=404, detail=ERROR_IMAGE_NOT_FOUND)

    # Delete metadata file if exists
    if metadata_path.exists():
        metadata_path.unlink()

    return {"message": "Image deleted successfully", "path": file_path}


@app.put("/api/images/{file_path:path}/featured", tags=["images"])
@limiter.limit("60/minute")
async def toggle_featured(
    request: Request,
    file_path: str,
    featured: bool,
    gallery_path: GalleryPathDep,
    _api_key: str = Depends(require_api_key),
):
    """Toggle featured status of an image."""
    gallery_path_obj = Path(gallery_path)
    full_image_path = gallery_path_obj / file_path
    metadata_path = full_image_path.with_suffix(METADATA_FILE_SUFFIX)

    # Security check
    try:
        full_image_path.resolve().relative_to(gallery_path_obj.resolve())
    except ValueError as e:
        raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED) from e

    # Check image exists
    if not full_image_path.exists():
        raise HTTPException(status_code=404, detail=ERROR_IMAGE_NOT_FOUND)

    # Load or create metadata (async file I/O)
    if metadata_path.exists():
        async with aiofiles.open(metadata_path) as f:
            content = await f.read()
            metadata = json.loads(content)
    else:
        metadata = {
            "prompt": "Unknown",
            "created_at": full_image_path.stat().st_mtime,
        }

    # Update featured status
    metadata["featured"] = featured

    # Save metadata (async file I/O)
    async with aiofiles.open(metadata_path, "w") as f:
        await f.write(json.dumps(metadata, indent=2))

    logger.info("image_featured_toggled", path=str(file_path), featured=featured)

    return {
        "message": "Featured status updated",
        "path": file_path,
        "featured": featured,
    }


# Admin Upload Endpoints
@app.post("/api/admin/upload-image", tags=["admin"])
@limiter.limit("100/minute")
async def upload_image(
    request: Request,
    gallery_path: GalleryPathDep,
    _api_key: str = Depends(require_api_key),
):
    """Upload a single image with optional metadata.

    Expects multipart/form-data with:
    - image: PNG/JPG file
    - metadata: Optional JSON string with prompt, model, etc.
    """
    # Parse multipart data manually since we need Depends
    form = await request.form()

    if "image" not in form:
        raise HTTPException(status_code=400, detail="No image file provided")

    image_value = form["image"]
    if not isinstance(image_value, StarletteUploadFile):
        raise HTTPException(status_code=400, detail="No image file provided")
    image_file: StarletteUploadFile = image_value

    metadata_value = form.get("metadata")
    metadata_str: str | None = (
        metadata_value if isinstance(metadata_value, str) else None
    )

    # Validate file type
    if not image_file.content_type or not image_file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=ERROR_INVALID_FILE_TYPE)

    # Read image data
    image_data = await image_file.read()

    # Parse metadata if provided
    metadata = {}
    if metadata_str:
        try:
            metadata = json.loads(metadata_str)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="Invalid metadata JSON") from e

    # Generate filename based on timestamp if not provided
    import hashlib

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_hash = hashlib.md5(image_data, usedforsecurity=False).hexdigest()[:8]
    filename = f"{timestamp}_{file_hash}.png"

    # Determine save path (featured or regular)
    gallery_path_obj = Path(gallery_path)
    year_month = datetime.now().strftime("%Y/%m")

    if metadata.get("featured"):
        save_dir = gallery_path_obj / year_month / "featured"
    else:
        save_dir = gallery_path_obj / year_month

    save_dir.mkdir(parents=True, exist_ok=True)
    image_path = save_dir / filename

    # Save image (async file I/O)
    async with aiofiles.open(image_path, "wb") as f:
        await f.write(image_data)

    # Save metadata if provided (async file I/O)
    if metadata:
        metadata_path = image_path.with_suffix(METADATA_FILE_SUFFIX)
        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(json.dumps(metadata, indent=2))

    logger.info("image_uploaded", path=str(image_path), size=len(image_data))

    return {
        "message": "Image uploaded successfully",
        "path": str(image_path.relative_to(gallery_path_obj)),
        "filename": filename,
    }


@app.post("/api/admin/upload-batch", tags=["admin"])
@limiter.limit("5/minute")
async def upload_batch(
    request: Request,
    gallery_path: GalleryPathDep,
    _api_key: str = Depends(require_api_key),
):
    """Upload multiple images in a single request.

    Expects multipart/form-data with multiple 'images' files.
    Each image can have corresponding metadata in 'metadata_<index>' field.
    """
    form = await request.form()

    # Collect all image files
    images: list[StarletteUploadFile] = []
    for key, value in form.items():
        if key.startswith("image") and isinstance(value, StarletteUploadFile):
            images.append(value)

    if not images:
        raise HTTPException(status_code=400, detail="No images provided")

    results = []
    errors = []

    for idx, image_file in enumerate(images):
        try:
            # Read and validate
            if not image_file.content_type or not image_file.content_type.startswith(
                "image/"
            ):
                errors.append({"index": idx, "error": "Invalid file type"})
                continue

            image_data = await image_file.read()

            # Check for corresponding metadata
            metadata = {}
            metadata_key = f"metadata_{idx}"
            metadata_value = form.get(metadata_key)
            if isinstance(metadata_value, str):
                with contextlib.suppress(json.JSONDecodeError):
                    metadata = json.loads(metadata_value)

            # Generate filename
            import hashlib

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_hash = hashlib.md5(image_data, usedforsecurity=False).hexdigest()[:8]
            filename = f"{timestamp}_{file_hash}_{idx}.png"

            # Save paths
            gallery_path_obj = Path(gallery_path)
            year_month = datetime.now().strftime("%Y/%m")

            if metadata.get("featured"):
                save_dir = gallery_path_obj / year_month / "featured"
            else:
                save_dir = gallery_path_obj / year_month

            save_dir.mkdir(parents=True, exist_ok=True)
            image_path = save_dir / filename

            # Save image (async file I/O)
            async with aiofiles.open(image_path, "wb") as f:
                await f.write(image_data)

            # Save metadata (async file I/O)
            if metadata:
                metadata_path = image_path.with_suffix(METADATA_FILE_SUFFIX)
                async with aiofiles.open(metadata_path, "w") as f:
                    await f.write(json.dumps(metadata, indent=2))

            results.append(
                {
                    "index": idx,
                    "path": str(image_path.relative_to(gallery_path_obj)),
                    "filename": filename,
                }
            )

        except Exception as e:
            errors.append({"index": idx, "error": str(e)})

    logger.info("batch_upload_completed", success=len(results), errors=len(errors))

    return {
        "message": f"Uploaded {len(results)} images",
        "success": results,
        "errors": errors,
    }


# Prompt Templates Storage
TEMPLATES_FILE = Path("config/prompt_templates.json")


def load_templates() -> list[dict]:
    """Load templates from JSON file."""
    if not TEMPLATES_FILE.exists():
        TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    try:
        with open(TEMPLATES_FILE) as f:
            templates: list[dict] = json.load(f)
            return templates
    except json.JSONDecodeError:
        return []


def save_templates(templates: list[dict]):
    """Save templates to JSON file."""
    TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(templates, f, indent=2)


@app.get("/api/templates", response_model=list[PromptTemplate], tags=["templates"])
@limiter.limit("60/minute")
async def get_templates(
    request: Request,
):
    """Get all prompt templates."""
    templates = load_templates()
    return templates


@app.post("/api/templates", response_model=PromptTemplate, tags=["templates"])
@limiter.limit("60/minute")
async def create_template(
    request: Request,
    template_request: CreateTemplateRequest,
    _api_key: str = Depends(require_api_key),
):
    """Create a new prompt template."""
    import uuid

    templates = load_templates()

    new_template = {
        "id": str(uuid.uuid4()),
        "name": template_request.name,
        "prompt": template_request.prompt,
        "negative_prompt": template_request.negative_prompt,
        "width": template_request.width,
        "height": template_request.height,
        "num_inference_steps": template_request.num_inference_steps,
        "guidance_scale": template_request.guidance_scale,
        "created_at": datetime.now().isoformat(),
        "tags": template_request.tags,
    }

    templates.append(new_template)
    save_templates(templates)

    logger.info(
        "template_created",
        template_id=new_template["id"],
        name=new_template["name"],
    )

    return new_template


@app.put(
    "/api/templates/{template_id}", response_model=PromptTemplate, tags=["templates"]
)
@limiter.limit("60/minute")
async def update_template(
    request: Request,
    template_id: str,
    template_request: CreateTemplateRequest,
    _api_key: str = Depends(require_api_key),
):
    """Update an existing prompt template."""
    templates = load_templates()

    for i, t in enumerate(templates):
        if t["id"] == template_id:
            templates[i] = {
                "id": template_id,
                "name": template_request.name,
                "prompt": template_request.prompt,
                "negative_prompt": template_request.negative_prompt,
                "width": template_request.width,
                "height": template_request.height,
                "num_inference_steps": template_request.num_inference_steps,
                "guidance_scale": template_request.guidance_scale,
                "created_at": t.get("created_at", datetime.now().isoformat()),
                "tags": template_request.tags,
            }
            save_templates(templates)
            logger.info("template_updated", template_id=template_id)
            return templates[i]

    raise HTTPException(status_code=404, detail="Template not found")


@app.delete("/api/templates/{template_id}", tags=["templates"])
@limiter.limit("60/minute")
async def delete_template(
    request: Request,
    template_id: str,
    _api_key: str = Depends(require_api_key),
):
    """Delete a prompt template."""
    templates = load_templates()
    templates = [t for t in templates if t["id"] != template_id]
    save_templates(templates)

    logger.info("template_deleted", template_id=template_id)

    return {"message": "Template deleted", "id": template_id}


@app.post("/api/gallery/cleanup", tags=["admin"])
@limiter.limit("60/minute")
async def cleanup_gallery(
    request: Request,
    gallery_manager: GalleryManagerDep,
    dry_run: bool = Query(True, description="If true, only report without deleting"),
    _api_key: str = Depends(require_api_key),
):
    """Scan and remove black/blank/invalid images from the gallery.

    Args:
        dry_run: If true (default), only report what would be deleted
    """
    stats = gallery_manager.cleanup_invalid_images(dry_run=dry_run)

    return {
        "message": "Cleanup complete" if not dry_run else "Dry run complete",
        "dry_run": dry_run,
        "stats": stats,
    }


@app.post("/api/generate", response_model=GenerationResponse, tags=["generation"])
@limiter.limit("5/minute")
async def generate_artwork(
    request: Request,
    generation_request: GenerationRequest,
    _api_key: str = Depends(require_api_key),
):
    """Start an artwork generation job.

    Returns a session ID that can be used to track progress via WebSocket.
    Uses a semaphore to limit concurrent generations and prevent VRAM
    exhaustion.
    Rate limited to 5 requests per minute due to expensive GPU operations.
    """
    import uuid

    from ..core.generator import ImageGenerator
    from ..curation.curator import is_black_or_blank
    from ..utils.config import load_config

    global _generation_queue_size

    # Validate request
    validate_generation_request(generation_request)

    # Generate unique session ID
    session_id = str(uuid.uuid4())

    # Start generation in background with concurrency control
    async def generate_task():
        global _generation_queue_size
        _generation_queue_size += 1

        try:
            # Acquire semaphore with timeout to prevent indefinite waiting
            try:
                async with asyncio.timeout(_generation_timeout_seconds):
                    async with _generation_semaphore:
                        await _run_generation()
            except TimeoutError:
                logger.error(
                    "generation_timeout",
                    session_id=session_id,
                    timeout_seconds=_generation_timeout_seconds,
                )
                await ws_manager.send_generation_error(
                    session_id=session_id,
                    error=(
                        f"Generation timed out after {_generation_timeout_seconds}s"
                    ),
                )
        finally:
            _generation_queue_size -= 1

    async def _run_generation():
        generator = None
        try:
            gallery_path_local = Path("gallery")
            config_path = Path("config/config.yaml")

            # Check if config exists - if not, we're in gallery-only mode
            if not config_path.exists():
                raise ValueError(
                    "Image generation is not available. This instance is "
                    "running in gallery-only mode. To enable generation, "
                    "provide a config/config.yaml file with model settings."
                )

            config = load_config(config_path)

            # Use context manager for automatic cleanup
            generator = ImageGenerator(
                model_id=config.model.base_model, device=config.model.device
            )
            generator.load_model()

            # Send progress update
            await ws_manager.broadcast(
                {
                    "type": "progress",
                    "session_id": session_id,
                    "status": "generating",
                    "message": "Model loaded, generating images...",
                }
            )

            # Generate images
            images = generator.generate(
                prompt=generation_request.prompt,
                negative_prompt=generation_request.negative_prompt,
                width=generation_request.width,
                height=generation_request.height,
                num_inference_steps=generation_request.num_inference_steps,
                guidance_scale=generation_request.guidance_scale,
                num_images=generation_request.num_images,
                seed=generation_request.seed,
            )

            # Save only valid images
            # (black/blank already filtered by generator)
            image_paths = []

            now = datetime.now()
            for i, img in enumerate(images):
                # Double-check validity before saving
                is_invalid, reason = is_black_or_blank(img)
                if is_invalid:
                    logger.warning(
                        "skipping_invalid_image_on_save",
                        session_id=session_id,
                        index=i,
                        reason=reason,
                    )
                    continue

                filename = f"{session_id}_{i}.png"
                save_path = (
                    gallery_path_local
                    / str(now.year)
                    / f"{now.month:02d}"
                    / "archive"
                    / filename
                )
                save_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(save_path)
                image_paths.append(str(save_path))

                # Save metadata
                metadata_path = save_path.with_suffix(METADATA_FILE_SUFFIX)
                metadata_path.write_text(
                    json.dumps(
                        {
                            "prompt": generation_request.prompt,
                            "negative_prompt": (generation_request.negative_prompt),
                            "width": generation_request.width,
                            "height": generation_request.height,
                            "steps": generation_request.num_inference_steps,
                            "guidance_scale": (generation_request.guidance_scale),
                            "seed": generation_request.seed,
                            "created_at": now.isoformat(),
                            "session_id": session_id,
                        },
                        indent=2,
                    )
                )

            if image_paths:
                await ws_manager.send_generation_complete(
                    session_id=session_id,
                    image_paths=image_paths,
                    metadata={"prompt": generation_request.prompt},
                )
            else:
                await ws_manager.send_generation_error(
                    session_id=session_id,
                    error=(
                        "All generated images were invalid (black/blank). "
                        "Try different settings."
                    ),
                )

        except asyncio.CancelledError:
            from .generation_registry import notify_cancelled

            await notify_cancelled(session_id, ws_manager)
            raise
        except Exception as e:
            logger.error("generation_failed", session_id=session_id, error=str(e))
            await ws_manager.send_generation_error(session_id=session_id, error=str(e))
        finally:
            # Cleanup generator resources
            if generator:
                generator.unload()

    # Start background task and keep reference to prevent GC
    from .generation_registry import register as register_generation_task

    task = asyncio.create_task(generate_task())
    register_generation_task(session_id, task)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return GenerationResponse(
        session_id=session_id,
        message="Generation started. Connect to WebSocket to track progress.",
        status="started",
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    client_id = f"client_{id(websocket)}"
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            # Receive messages from client (for subscriptions, etc.)
            data = await websocket.receive_json()

            # Handle different message types
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "subscribe":
                # Client wants to subscribe to specific events
                session_id = data.get("session_id")
                if session_id:
                    logger.info("client_subscribed", session_id=session_id)
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, client_id)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        await ws_manager.disconnect(websocket, client_id)


@app.post("/api/cancel/{session_id}", tags=["generation"])
async def cancel_generation(session_id: str):
    """Cancel an in-flight image generation by session ID."""
    from .generation_registry import cancel, is_active

    if not is_active(session_id):
        raise HTTPException(
            status_code=404,
            detail="No active generation found for this session",
        )

    cancel(session_id)
    return {"success": True, "message": "Generation cancelled", "session_id": session_id}


@app.get("/privacy", response_class=HTMLResponse, tags=["pages"])
async def privacy_page(request: Request):
    """Privacy policy for the Lumira web gallery and studio."""
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {"title": "Privacy Policy | Lumira"},
    )


@app.get("/health/details", tags=["health"])
async def health_details():
    """Detailed health and runtime diagnostics endpoint."""
    from .dependencies import _gallery_manager

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "gallery_initialized": _gallery_manager is not None,
        "websocket_connections": len(ws_manager.active_connections),
        "generation_queue": {
            "active": _generation_queue_size,
            "max_concurrent": 1,
            "timeout_seconds": _generation_timeout_seconds,
        },
    }


if __name__ == "__main__":
    import os

    import uvicorn

    # Use PORT environment variable if available (Railway sets this)
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # nosec B104
