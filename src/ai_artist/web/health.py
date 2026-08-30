"""Health check and monitoring endpoints for FastAPI application."""

import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str
    uptime: float


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    status: str
    ready: bool
    checks: dict[str, bool | dict[str, Any]]
    timestamp: float


class LivenessResponse(BaseModel):
    """Liveness check response model."""

    status: str
    alive: bool


# Track application start time
_start_time = time.time()
_app_version = "2.0.0"


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.

    Returns 200 if the application is running.
    Useful for Docker health checks and load balancer pings.
    """
    uptime = time.time() - _start_time
    return HealthResponse(
        status="healthy",
        version=_app_version,
        uptime=uptime,
    )


@router.get("/health/live", response_model=LivenessResponse)
async def liveness_probe() -> LivenessResponse:
    """
    Kubernetes liveness probe.

    Returns 200 if the process is alive. Kubernetes will restart the pod
    if this fails repeatedly.

    This is a minimal check - just verifies the event loop is responsive.
    """
    return LivenessResponse(status="alive", alive=True)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_probe() -> JSONResponse:
    """
    Kubernetes readiness probe.

    Checks all critical dependencies are available before routing traffic.
    Returns 503 if any check fails, indicating the pod should not receive traffic.

    Checks:
    - Database connectivity
    - Disk space
    - Memory availability
    - Model pool status (if enabled)
    """
    checks: dict[str, bool | dict[str, Any]] = {}

    # Check database
    checks["database"] = await _check_database()

    # Check disk space
    checks["disk_space"] = await _check_disk_space()

    # Check memory
    checks["memory"] = await _check_memory()

    # Check model pool (if using it)
    checks["model_pool"] = await _check_model_pool()

    # Check if gallery directory is writable
    checks["gallery_writable"] = await _check_gallery_writable()

    # Overall readiness
    ready = all(
        check if isinstance(check, bool) else check.get("ok", False)
        for check in checks.values()
    )

    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        content={
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "checks": checks,
            "timestamp": time.time(),
        },
        status_code=status_code,
    )


async def _check_database() -> bool:
    """Check database connectivity.

    Reuses the process-wide session factory (a single pooled engine) rather
    than constructing a new engine per call, which previously leaked a
    connection pool + WAL setup on every readiness poll.
    """
    try:
        from sqlalchemy import text

        from ..db.session import get_session_factory

        session_factory = get_session_factory()
        session = session_factory()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
        return True
    except Exception as e:
        logger.warning("database_check_failed", error=str(e))
        return False


async def _check_disk_space(min_gb: float = 1.0) -> bool | dict[str, Any]:
    """Check if sufficient disk space is available."""
    try:
        gallery_path = Path("gallery")
        stat = shutil.disk_usage(gallery_path if gallery_path.exists() else ".")

        free_gb = stat.free / (1024**3)
        ok = free_gb >= min_gb

        return {
            "ok": ok,
            "free_gb": round(free_gb, 2),
            "threshold_gb": min_gb,
        }
    except Exception as e:
        logger.warning("disk_check_failed", error=str(e))
        return False


async def _check_memory(max_percent: float = 90.0) -> bool | dict[str, Any]:
    """Check if memory usage is within acceptable limits."""
    try:
        import psutil

        mem = psutil.virtual_memory()
        ok = mem.percent < max_percent

        return {
            "ok": ok,
            "used_percent": round(mem.percent, 1),
            "threshold_percent": max_percent,
            "available_gb": round(mem.available / (1024**3), 2),
        }
    except ImportError:
        # psutil not installed, skip check
        return True
    except Exception as e:
        logger.warning("memory_check_failed", error=str(e))
        return False


async def _check_model_pool() -> bool | dict[str, Any]:
    """Check model pool status if enabled."""
    try:
        from ..core.model_pool import get_model_pool

        pool = get_model_pool()
        status_info = pool.get_pool_status()

        return {
            "ok": True,
            "loaded_models": len(status_info["loaded_models"]),
            "warmed_models": len(status_info["warmup_complete"]),
        }
    except RuntimeError:
        # Model pool not initialized - not an error if not using it
        return {"ok": True, "enabled": False}
    except Exception as e:
        logger.warning("model_pool_check_failed", error=str(e))
        return {"ok": False, "error": str(e)}


async def _check_gallery_writable() -> dict[str, Any]:
    """Check if gallery directory is writable."""
    try:
        gallery_path = Path("gallery")
        gallery_path.mkdir(parents=True, exist_ok=True)

        # Try to create a temp file
        test_file = gallery_path / ".health_check"
        test_file.write_text("ok")
        test_file.unlink()

        return {"ok": True}
    except Exception as e:
        logger.warning("gallery_writable_check_failed", error=str(e))
        return {"ok": False, "error": str(e)}
