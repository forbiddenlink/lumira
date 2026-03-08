"""Resilience and error recovery for 24/7 autonomous operation.

Provides:
- Circuit breaker pattern for API failures
- Automatic retry with exponential backoff
- Mood persistence across long gaps
- State backup and recovery
- Network resilience
- Graceful degradation
"""

import asyncio
import contextlib
import json
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, cast

from pydantic import BaseModel, Field

from ..utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# =============================================================================
# Circuit Breaker
# =============================================================================


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker for API calls and external services.

    Prevents cascading failures by tracking failures and temporarily
    stopping requests when a service is unhealthy.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        """Initialize circuit breaker.

        Args:
            name: Identifier for this circuit
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds to wait before testing recovery
            half_open_max_calls: Test calls allowed in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout)
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._half_open_calls = 0
        self._success_count = 0

        logger.info(
            "circuit_breaker_initialized",
            name=name,
            threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for recovery."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = datetime.now(UTC) - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("circuit_half_open", name=self.name)
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        self._success_count += 1

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                # Recovery confirmed
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(
                    "circuit_closed",
                    name=self.name,
                    after_successes=self._half_open_calls,
                )
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = datetime.now(UTC)

        if self._state == CircuitState.HALF_OPEN:
            # Failed during recovery test
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit_reopened",
                name=self.name,
                error=str(error) if error else None,
            )
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit_opened",
                name=self.name,
                failures=self._failure_count,
                error=str(error) if error else None,
            )

    def allow_request(self) -> bool:
        """Check if a request should be allowed."""
        state = self.state  # Triggers recovery check
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    async def call(
        self,
        func: Callable[..., T],
        *args: Any,
        fallback: T | None = None,
        **kwargs: Any,
    ) -> T | None:
        """Call a function with circuit breaker protection.

        Args:
            func: Async function to call
            fallback: Value to return if circuit is open
            *args, **kwargs: Arguments for func

        Returns:
            Result of func or fallback
        """
        if not self.allow_request():
            logger.debug("circuit_request_rejected", name=self.name)
            return fallback

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.record_success()
            return cast(T, result)
        except Exception as e:
            self.record_failure(e)
            if fallback is not None:
                return fallback
            raise

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": (
                self._last_failure_time.isoformat() if self._last_failure_time else None
            ),
        }


# =============================================================================
# Retry Logic
# =============================================================================


class RetryConfig(BaseModel):
    """Configuration for retry behavior."""

    max_retries: int = Field(default=3, ge=0, le=10)
    base_delay: float = Field(default=1.0, ge=0.1, le=60.0)
    max_delay: float = Field(default=60.0, ge=1.0, le=300.0)
    exponential_base: float = Field(default=2.0, ge=1.5, le=4.0)
    jitter: float = Field(default=0.1, ge=0.0, le=0.5)


async def retry_with_backoff(
    func: Callable[..., T],
    *args: Any,
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
    **kwargs: Any,
) -> T:
    """Execute a function with exponential backoff retry.

    Args:
        func: Async function to execute
        config: Retry configuration
        on_retry: Callback on each retry (attempt_number, exception)
        *args, **kwargs: Arguments for func

    Returns:
        Result of func

    Raises:
        Last exception if all retries fail
    """
    import random

    config = config or RetryConfig()
    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return cast(T, await func(*args, **kwargs))
            else:
                return cast(T, func(*args, **kwargs))
        except Exception as e:
            last_exception = e

            if attempt >= config.max_retries:
                logger.error(
                    "retry_exhausted",
                    attempts=attempt + 1,
                    error=str(e),
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base**attempt),
                config.max_delay,
            )
            # Add jitter
            jitter = delay * config.jitter * random.uniform(-1, 1)
            delay = max(0.1, delay + jitter)

            logger.warning(
                "retry_scheduled",
                attempt=attempt + 1,
                max_attempts=config.max_retries + 1,
                delay=round(delay, 2),
                error=str(e),
            )

            if on_retry:
                on_retry(attempt + 1, e)

            await asyncio.sleep(delay)

    # Should not reach here, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")


# =============================================================================
# State Persistence
# =============================================================================


class StateBackup(BaseModel):
    """Backup of Lumira's state for recovery."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mood: str
    mood_intensity: float
    energy: float
    recent_subjects: list[str] = Field(default_factory=list)
    recent_styles: list[str] = Field(default_factory=list)
    active_series: list[dict[str, Any]] = Field(default_factory=list)
    drive_states: dict[str, float] = Field(default_factory=dict)
    creation_count: int = 0
    last_creation_time: datetime | None = None


class StatePersistence:
    """Manages state persistence for recovery after restarts/crashes."""

    def __init__(
        self,
        backup_path: Path = Path("data/state_backup.json"),
        backup_interval_minutes: int = 15,
        max_backups: int = 24,  # Keep 24 backups (6 hours at 15min intervals)
    ):
        self.backup_path = backup_path
        self.backup_interval = timedelta(minutes=backup_interval_minutes)
        self.max_backups = max_backups
        self._last_backup: datetime | None = None
        self._backup_history: deque[StateBackup] = deque(maxlen=max_backups)

        self._load_backup_history()
        logger.info(
            "state_persistence_initialized",
            path=str(backup_path),
            interval_minutes=backup_interval_minutes,
        )

    def _load_backup_history(self) -> None:
        """Load backup history from disk."""
        if not self.backup_path.exists():
            return

        try:
            with open(self.backup_path) as f:
                data = json.load(f)

            if isinstance(data, list):
                for item in data[-self.max_backups :]:
                    self._backup_history.append(StateBackup(**item))
            elif isinstance(data, dict):
                # Single backup format
                self._backup_history.append(StateBackup(**data))

            logger.info(
                "backup_history_loaded",
                count=len(self._backup_history),
            )
        except Exception as e:
            logger.warning("backup_history_load_failed", error=str(e))

    def _save_backup_history(self) -> None:
        """Save backup history to disk."""
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = [b.model_dump(mode="json") for b in self._backup_history]
            with open(self.backup_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("backup_history_save_failed", error=str(e))

    def create_backup(
        self,
        mood_system: Any,
        desire_engine: Any | None = None,
        narrative_engine: Any | None = None,
        creation_count: int = 0,
    ) -> StateBackup:
        """Create a state backup.

        Args:
            mood_system: Current mood system
            desire_engine: Optional desire engine
            narrative_engine: Optional narrative engine
            creation_count: Total creations

        Returns:
            StateBackup instance
        """
        backup = StateBackup(
            mood=mood_system.current_mood.value,
            mood_intensity=getattr(mood_system, "mood_intensity", 0.7),
            energy=getattr(mood_system, "energy", 0.5),
            creation_count=creation_count,
        )

        # Add desire engine state
        if desire_engine:
            backup.drive_states = {
                name: drive.intensity for name, drive in desire_engine.drives.items()
            }
            backup.recent_subjects = desire_engine.get_recent_subjects(5)
            backup.recent_styles = desire_engine.get_recent_styles(5)

        # Add narrative engine state
        if narrative_engine:
            backup.active_series = [
                {
                    "series_id": s.series_id,
                    "title": s.title,
                    "theme": s.theme,
                    "progress": f"{len(s.completed_works)}/{s.planned_count}",
                }
                for s in narrative_engine.get_active_series()
            ]

        self._backup_history.append(backup)
        self._last_backup = datetime.now(UTC)
        self._save_backup_history()

        logger.info(
            "state_backup_created",
            mood=backup.mood,
            energy=backup.energy,
            creation_count=backup.creation_count,
        )

        return backup

    def should_backup(self) -> bool:
        """Check if a backup is due."""
        if self._last_backup is None:
            return True
        elapsed = datetime.now(UTC) - self._last_backup
        return elapsed >= self.backup_interval

    def get_latest_backup(self) -> StateBackup | None:
        """Get the most recent backup."""
        if self._backup_history:
            return self._backup_history[-1]
        return None

    def recover_mood_state(
        self,
        mood_system: Any,
        max_age_hours: float = 24.0,
    ) -> bool:
        """Recover mood state from backup if within age limit.

        Args:
            mood_system: Mood system to restore
            max_age_hours: Maximum age of backup to use

        Returns:
            True if recovery was performed
        """
        backup = self.get_latest_backup()
        if backup is None:
            logger.info("no_backup_for_recovery")
            return False

        age = datetime.now(UTC) - backup.timestamp
        max_age = timedelta(hours=max_age_hours)

        if age > max_age:
            logger.info(
                "backup_too_old_for_recovery",
                age_hours=age.total_seconds() / 3600,
                max_hours=max_age_hours,
            )
            return False

        # Restore mood with decay based on time gap
        try:
            from ..personality.moods import Mood

            # Find the mood enum value
            restored_mood = None
            for m in Mood:
                if m.value == backup.mood:
                    restored_mood = m
                    break

            if restored_mood is None:
                logger.warning("unknown_mood_in_backup", mood=backup.mood)
                return False

            # Apply time-based decay to intensity
            decay_factor = max(
                0.3, 1.0 - (age.total_seconds() / (max_age_hours * 3600))
            )
            restored_intensity = backup.mood_intensity * decay_factor

            # Set the mood (implementation depends on MoodSystem API)
            if hasattr(mood_system, "_current_mood"):
                mood_system._current_mood = restored_mood
            if hasattr(mood_system, "mood_intensity"):
                mood_system.mood_intensity = restored_intensity
            if hasattr(mood_system, "energy"):
                mood_system.energy = backup.energy * decay_factor

            logger.info(
                "mood_state_recovered",
                mood=backup.mood,
                original_intensity=backup.mood_intensity,
                restored_intensity=restored_intensity,
                decay_factor=decay_factor,
                gap_hours=age.total_seconds() / 3600,
            )

            return True

        except Exception as e:
            logger.error("mood_recovery_failed", error=str(e))
            return False


# =============================================================================
# Resilient Autonomous Runner
# =============================================================================


class ResilientAutonomyRunner:
    """Runs Lumira autonomously with full error recovery and resilience."""

    def __init__(
        self,
        scheduler: Any,
        mood_system: Any,
        desire_engine: Any | None = None,
        narrative_engine: Any | None = None,
        state_persistence: StatePersistence | None = None,
    ):
        self.scheduler = scheduler
        self.mood_system = mood_system
        self.desire_engine = desire_engine
        self.narrative_engine = narrative_engine
        self.state_persistence = state_persistence or StatePersistence()

        # Circuit breakers for external services
        self.circuits = {
            "replicate": CircuitBreaker(
                "replicate", failure_threshold=3, recovery_timeout=120
            ),
            "anthropic": CircuitBreaker(
                "anthropic", failure_threshold=5, recovery_timeout=60
            ),
        }

        # Retry configuration
        self.retry_config = RetryConfig(max_retries=3, base_delay=2.0)

        # Runtime stats
        self.creation_count = 0
        self.failure_count = 0
        self.last_success_time: datetime | None = None

        self._running = False
        self._task: asyncio.Task | None = None

        logger.info("resilient_autonomy_runner_initialized")

    async def start(self) -> None:
        """Start the resilient autonomous runner."""
        if self._running:
            logger.warning("runner_already_started")
            return

        # Recover state from backup
        self.state_persistence.recover_mood_state(
            self.mood_system,
            max_age_hours=24.0,
        )

        self._running = True
        self.scheduler.start()

        # Start background monitoring
        self._task = asyncio.create_task(self._monitoring_loop())

        logger.info("resilient_autonomy_started")

    async def stop(self) -> None:
        """Stop the autonomous runner gracefully."""
        self._running = False

        # Final backup before shutdown
        self.state_persistence.create_backup(
            mood_system=self.mood_system,
            desire_engine=self.desire_engine,
            narrative_engine=self.narrative_engine,
            creation_count=self.creation_count,
        )

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        self.scheduler.shutdown()
        logger.info("resilient_autonomy_stopped")

    async def _monitoring_loop(self) -> None:
        """Background loop for state backup and health monitoring."""
        while self._running:
            try:
                # Periodic state backup
                if self.state_persistence.should_backup():
                    self.state_persistence.create_backup(
                        mood_system=self.mood_system,
                        desire_engine=self.desire_engine,
                        narrative_engine=self.narrative_engine,
                        creation_count=self.creation_count,
                    )

                # Log health status
                logger.debug(
                    "autonomy_health_check",
                    creation_count=self.creation_count,
                    failure_count=self.failure_count,
                    circuits={name: c.state.value for name, c in self.circuits.items()},
                )

                await asyncio.sleep(60)  # Check every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitoring_loop_error", error=str(e))
                await asyncio.sleep(60)

    async def create_with_resilience(self, create_func: Callable) -> Any:
        """Execute a creation with full resilience.

        Args:
            create_func: Async function to create artwork

        Returns:
            Creation result or None on failure
        """
        # Check circuit breakers
        for name, circuit in self.circuits.items():
            if not circuit.allow_request():
                logger.warning(f"circuit_open_{name}", state=circuit.state.value)
                # Fall back to alternative if main circuit is open
                anthropic_circuit = self.circuits.get("anthropic")
                if (
                    name == "replicate"
                    and anthropic_circuit
                    and anthropic_circuit.allow_request()
                ):
                    logger.info("falling_back_to_local_generation")

        try:
            result = await retry_with_backoff(
                create_func,
                config=self.retry_config,
                on_retry=lambda attempt, e: logger.warning(
                    "creation_retry",
                    attempt=attempt,
                    error=str(e),
                ),
            )

            self.creation_count += 1
            self.last_success_time = datetime.now(UTC)

            # Record success on circuits
            for circuit in self.circuits.values():
                circuit.record_success()

            return result

        except Exception as e:
            self.failure_count += 1

            # Record failure on relevant circuit
            if "replicate" in str(e).lower():
                self.circuits["replicate"].record_failure(e)
            elif "anthropic" in str(e).lower():
                self.circuits["anthropic"].record_failure(e)

            logger.error(
                "resilient_creation_failed",
                error=str(e),
                total_failures=self.failure_count,
            )
            return None

    def get_health_status(self) -> dict[str, Any]:
        """Get overall health status."""
        return {
            "running": self._running,
            "creation_count": self.creation_count,
            "failure_count": self.failure_count,
            "success_rate": (
                self.creation_count / (self.creation_count + self.failure_count)
                if (self.creation_count + self.failure_count) > 0
                else 1.0
            ),
            "last_success": (
                self.last_success_time.isoformat() if self.last_success_time else None
            ),
            "circuits": {name: c.get_status() for name, c in self.circuits.items()},
            "last_backup": (
                (latest := self.state_persistence.get_latest_backup())
                and latest.timestamp.isoformat()
            ),
        }
