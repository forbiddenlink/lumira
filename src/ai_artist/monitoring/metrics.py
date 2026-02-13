"""
Prometheus metrics for Aria AI Artist.

Tracks generation performance, quality scores, user feedback,
and system resource usage for production monitoring.
"""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

import structlog

logger = structlog.get_logger(__name__)

# Try to import prometheus_client, fallback gracefully if not available
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info
    from prometheus_client import generate_latest as prometheus_generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning(
        "prometheus_client_not_installed",
        hint="Install with: pip install prometheus-client",
    )
    PROMETHEUS_AVAILABLE = False

    # Mock classes for when prometheus is not available
    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def inc(self, amount: float = 1) -> None:
            pass

        def labels(self, **kwargs: Any) -> Any:
            return self

    class Gauge:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def set(self, value: float) -> None:
            pass

        def inc(self, amount: float = 1) -> None:
            pass

        def dec(self, amount: float = 1) -> None:
            pass

        def labels(self, **kwargs: Any) -> Any:
            return self

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, amount: float) -> None:
            pass

        def labels(self, **kwargs: Any) -> Any:
            return self

    class Info:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def info(self, data: dict[str, str]) -> None:
            pass

    prometheus_generate_latest = cast(Callable[..., bytes], None)

    CONTENT_TYPE_LATEST = "text/plain"


# =============================================================================
# Generation Metrics
# =============================================================================

generation_requests_total = Counter(
    "aria_generation_requests_total",
    "Total number of image generation requests",
    ["model", "mood", "status"],
)

generation_duration_seconds = Histogram(
    "aria_generation_duration_seconds",
    "Time spent generating images",
    ["model", "mood"],
    buckets=[1, 3, 5, 10, 20, 30, 60, 120, 300],
)

generation_steps = Histogram(
    "aria_generation_steps",
    "Number of inference steps per generation",
    ["model"],
    buckets=[10, 20, 30, 40, 50, 75, 100],
)

images_generated_total = Counter(
    "aria_images_generated_total",
    "Total number of images generated",
    ["model", "mood"],
)

generation_errors_total = Counter(
    "aria_generation_errors_total",
    "Total number of generation errors",
    ["model", "error_type"],
)

# =============================================================================
# Curation Metrics
# =============================================================================

curation_quality_score = Histogram(
    "aria_curation_quality_score",
    "Image quality scores from curator",
    ["model"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

curation_clip_score = Histogram(
    "aria_curation_clip_score",
    "CLIP similarity scores",
    ["model"],
    buckets=[0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4],
)

curation_aesthetic_score = Histogram(
    "aria_curation_aesthetic_score",
    "Aesthetic quality scores",
    ["model"],
    buckets=[4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0],
)

curation_duration_seconds = Histogram(
    "aria_curation_duration_seconds",
    "Time spent evaluating images",
    buckets=[0.5, 1, 2, 3, 5, 10],
)

# =============================================================================
# Learning Metrics
# =============================================================================

feedback_events_total = Counter(
    "aria_feedback_events_total",
    "Total user feedback events",
    ["action", "mood"],
)

learning_model_score = Gauge(
    "aria_learning_model_score",
    "Learned score for each model",
    ["model"],
)

learning_samples_total = Counter(
    "aria_learning_samples_total",
    "Total learning samples collected",
    ["model"],
)

# =============================================================================
# System Metrics
# =============================================================================

model_pool_size = Gauge(
    "aria_model_pool_size",
    "Number of models in the pool",
)

model_pool_preloaded = Gauge(
    "aria_model_pool_preloaded",
    "Number of preloaded models ready",
)

active_generations = Gauge(
    "aria_active_generations",
    "Number of currently active generations",
)

gpu_memory_allocated_bytes = Gauge(
    "aria_gpu_memory_allocated_bytes",
    "GPU memory allocated in bytes",
)

gpu_memory_reserved_bytes = Gauge(
    "aria_gpu_memory_reserved_bytes",
    "GPU memory reserved in bytes",
)

# =============================================================================
# Application Info
# =============================================================================

aria_info = Info(
    "aria_application",
    "Aria application information",
)


# =============================================================================
# Metrics Helpers
# =============================================================================


def track_generation_time(model: str, mood: str = "default") -> Callable:
    """
    Decorator to track generation duration.

    Usage:
        @track_generation_time(model_id, mood)
        def generate_image():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                generation_errors_total.labels(
                    model=model, error_type=type(e).__name__
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                generation_duration_seconds.labels(model=model, mood=mood).observe(
                    duration
                )
                generation_requests_total.labels(
                    model=model, mood=mood, status=status
                ).inc()

        return wrapper

    return decorator


async def track_generation_time_async(model: str, mood: str = "default") -> Callable:
    """
    Decorator to track async generation duration.

    Usage:
        @track_generation_time_async(model_id, mood)
        async def generate_image():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                generation_errors_total.labels(
                    model=model, error_type=type(e).__name__
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                generation_duration_seconds.labels(model=model, mood=mood).observe(
                    duration
                )
                generation_requests_total.labels(
                    model=model, mood=mood, status=status
                ).inc()

        return wrapper

    return decorator


def record_quality_metrics(
    model: str,
    clip_score: float,
    aesthetic_score: float,
    overall_score: float,
) -> None:
    """Record quality metrics from curation."""
    curation_quality_score.labels(model=model).observe(overall_score)
    curation_clip_score.labels(model=model).observe(clip_score)
    curation_aesthetic_score.labels(model=model).observe(aesthetic_score)


def record_feedback(action: str, mood: str = "default") -> None:
    """Record user feedback event."""
    feedback_events_total.labels(action=action, mood=mood).inc()


def update_gpu_metrics() -> None:
    """Update GPU memory metrics if torch is available."""
    try:
        import torch

        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated()
            reserved = torch.cuda.memory_reserved()
            gpu_memory_allocated_bytes.set(allocated)
            gpu_memory_reserved_bytes.set(reserved)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("gpu_metrics_update_failed", error=str(e))


def update_model_pool_metrics(pool_size: int, preloaded_count: int) -> None:
    """Update model pool metrics."""
    model_pool_size.set(pool_size)
    model_pool_preloaded.set(preloaded_count)


def set_aria_info(version: str, python_version: str, torch_version: str) -> None:
    """Set application info metrics."""
    aria_info.info(
        {
            "version": version,
            "python_version": python_version,
            "torch_version": torch_version,
        }
    )


# =============================================================================
# Metrics Export
# =============================================================================


def get_metrics() -> tuple[bytes, str]:
    """
    Get Prometheus metrics in exposition format.

    Returns:
        Tuple of (metrics_data, content_type)
    """
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not installed\n", "text/plain"

    return prometheus_generate_latest(), CONTENT_TYPE_LATEST


def is_metrics_available() -> bool:
    """Check if Prometheus metrics are available."""
    return PROMETHEUS_AVAILABLE
