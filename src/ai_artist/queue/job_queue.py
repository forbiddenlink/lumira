"""Redis job queue manager for async image generation.

Provides a high-level interface for enqueueing and tracking generation jobs.
Supports priority queues and job status tracking.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import RQ, gracefully handle if not installed
try:
    from redis import Redis  # type: ignore[import-untyped]
    from rq import Queue
    from rq.job import Job

    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    Redis = None  # type: ignore[misc, assignment]
    Queue = None  # type: ignore[misc, assignment]
    Job = None  # type: ignore[misc, assignment]


class JobPriority(str, Enum):
    """Job priority levels."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class JobStatus(str, Enum):
    """Job status states."""

    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    DEFERRED = "deferred"
    SCHEDULED = "scheduled"
    CANCELED = "canceled"


@dataclass
class JobInfo:
    """Job information container."""

    id: str
    status: JobStatus
    result: Any | None = None
    progress: int = 0
    enqueued_at: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class GenerationQueue:
    """Async job queue for image generation.

    Supports multiple priority queues and job status tracking.
    Uses Redis as the backend for distributed processing.

    Example:
        >>> queue = GenerationQueue()
        >>> job_id = queue.enqueue_generation("a beautiful sunset", {"width": 1024})
        >>> status = queue.get_job_status(job_id)
        >>> print(status.progress)
    """

    # Queue names for different priorities
    QUEUE_HIGH = "generation-high"
    QUEUE_NORMAL = "generation"
    QUEUE_LOW = "generation-low"

    def __init__(
        self,
        redis_url: str | None = None,
        default_timeout: int = 600,  # 10 minutes
        result_ttl: int = 3600,  # 1 hour
    ) -> None:
        """Initialize the generation queue.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var
                or redis://localhost:6379
            default_timeout: Default job timeout in seconds
            result_ttl: How long to keep job results in seconds
        """
        if not RQ_AVAILABLE:
            logger.warning(
                "rq_not_available",
                message="RQ package not installed. Install with: pip install lumira[queue]",
            )
            self.enabled = False
            self.redis = None
            self.queues: dict[JobPriority, Any] = {}
            return

        self.enabled = True
        self.default_timeout = default_timeout
        self.result_ttl = result_ttl
        self.queues = {}

        # Get Redis URL from environment or use default
        redis_url_str: str = (
            redis_url or os.getenv("REDIS_URL") or "redis://localhost:6379"
        )

        try:
            self.redis = Redis.from_url(redis_url_str)
            # Test connection
            self.redis.ping()

            # Initialize priority queues
            self.queues = {
                JobPriority.HIGH: Queue(
                    self.QUEUE_HIGH,
                    connection=self.redis,
                    default_timeout=default_timeout,
                ),
                JobPriority.NORMAL: Queue(
                    self.QUEUE_NORMAL,
                    connection=self.redis,
                    default_timeout=default_timeout,
                ),
                JobPriority.LOW: Queue(
                    self.QUEUE_LOW,
                    connection=self.redis,
                    default_timeout=default_timeout,
                ),
            }

            logger.info(
                "queue_initialized",
                redis_url=redis_url_str.split("@")[-1],  # Hide credentials
                queues=list(self.queues.keys()),
            )
        except Exception as e:
            logger.error("queue_init_failed", error=str(e))
            self.enabled = False
            self.redis = None
            self.queues = {}

    def is_available(self) -> bool:
        """Check if the queue is available and connected."""
        if not self.enabled or not self.redis:
            return False
        try:
            self.redis.ping()
            return True
        except Exception:
            return False

    def enqueue_generation(
        self,
        prompt: str,
        params: dict[str, Any],
        priority: JobPriority | str = JobPriority.NORMAL,
        job_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        """Enqueue a generation job.

        Args:
            prompt: The generation prompt
            params: Generation parameters (width, height, steps, etc.)
            priority: Job priority (high, normal, low)
            job_id: Optional custom job ID
            meta: Optional metadata to attach to the job

        Returns:
            Job ID if successfully enqueued, None otherwise
        """
        if not self.enabled:
            logger.warning("queue_not_available", action="enqueue_generation")
            return None

        # Normalize priority
        if isinstance(priority, str):
            priority = JobPriority(priority.lower())

        queue = self.queues.get(priority)
        if not queue:
            logger.error("invalid_priority", priority=priority)
            return None

        try:
            # Prepare job arguments
            job_kwargs = {
                "job_timeout": self.default_timeout,
                "result_ttl": self.result_ttl,
                "meta": meta or {},
            }

            if job_id:
                job_kwargs["job_id"] = job_id

            # Enqueue the job
            job = queue.enqueue(
                "ai_artist.queue.worker.generate_image",
                prompt,
                params,
                **job_kwargs,
            )

            logger.info(
                "job_enqueued",
                job_id=job.id,
                priority=priority.value,
                prompt=prompt[:50] + "..." if len(prompt) > 50 else prompt,
            )

            return str(job.id)

        except Exception as e:
            logger.error("enqueue_failed", error=str(e))
            return None

    def get_job_status(self, job_id: str) -> JobInfo | None:
        """Get the status of a job.

        Args:
            job_id: The job ID to look up

        Returns:
            JobInfo if found, None otherwise
        """
        if not self.enabled or not self.redis:
            return None

        try:
            job = Job.fetch(job_id, connection=self.redis)

            # Map RQ status to our JobStatus
            status_map = {
                "queued": JobStatus.QUEUED,
                "started": JobStatus.STARTED,
                "finished": JobStatus.FINISHED,
                "failed": JobStatus.FAILED,
                "deferred": JobStatus.DEFERRED,
                "scheduled": JobStatus.SCHEDULED,
                "canceled": JobStatus.CANCELED,
            }

            rq_status = job.get_status()
            status = status_map.get(rq_status, JobStatus.QUEUED)

            # Extract timestamps
            enqueued_at = job.enqueued_at.isoformat() if job.enqueued_at else None
            started_at = job.started_at.isoformat() if job.started_at else None
            ended_at = job.ended_at.isoformat() if job.ended_at else None

            # Get error info if failed
            error = None
            if status == JobStatus.FAILED and job.exc_info:
                error = str(job.exc_info)

            return JobInfo(
                id=job.id,
                status=status,
                result=job.result,
                progress=job.meta.get("progress", 0),
                enqueued_at=enqueued_at,
                started_at=started_at,
                ended_at=ended_at,
                error=error,
                meta=job.meta,
            )

        except Exception as e:
            logger.warning("job_fetch_failed", job_id=job_id, error=str(e))
            return None

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job.

        Args:
            job_id: The job ID to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        if not self.enabled or not self.redis:
            return False

        try:
            job = Job.fetch(job_id, connection=self.redis)
            job.cancel()
            logger.info("job_cancelled", job_id=job_id)
            return True
        except Exception as e:
            logger.warning("job_cancel_failed", job_id=job_id, error=str(e))
            return False

    def get_queue_stats(self) -> dict[str, Any]:
        """Get statistics for all queues.

        Returns:
            Dictionary with queue statistics
        """
        if not self.enabled:
            return {"enabled": False}

        queue_stats: dict[str, Any] = {}
        stats: dict[str, Any] = {"enabled": True, "queues": queue_stats}

        for priority, queue in self.queues.items():
            priority_key = priority.value
            try:
                queue_stats[priority_key] = {
                    "name": queue.name,
                    "count": len(queue),
                    "started_jobs": queue.started_job_registry.count,
                    "finished_jobs": queue.finished_job_registry.count,
                    "failed_jobs": queue.failed_job_registry.count,
                }
            except Exception as e:
                queue_stats[priority_key] = {"error": str(e)}

        return stats

    def clear_queue(self, priority: JobPriority | str | None = None) -> int:
        """Clear jobs from queue(s).

        Args:
            priority: Specific queue to clear, or None for all queues

        Returns:
            Number of jobs cleared
        """
        if not self.enabled:
            return 0

        cleared = 0

        if priority:
            if isinstance(priority, str):
                priority = JobPriority(priority.lower())
            queues_to_clear = [self.queues.get(priority)]
        else:
            queues_to_clear = list(self.queues.values())

        for queue in queues_to_clear:
            if queue:
                try:
                    count = len(queue)
                    queue.empty()
                    cleared += count
                except Exception as e:
                    logger.warning("queue_clear_failed", error=str(e))

        logger.info("queues_cleared", count=cleared)
        return cleared


# Global queue instance (lazy initialization)
_queue_instance: GenerationQueue | None = None


def get_queue(redis_url: str | None = None) -> GenerationQueue:
    """Get or create the global queue instance.

    Args:
        redis_url: Optional Redis URL to use for initialization

    Returns:
        The global GenerationQueue instance
    """
    global _queue_instance

    if _queue_instance is None:
        _queue_instance = GenerationQueue(redis_url=redis_url)

    return _queue_instance
