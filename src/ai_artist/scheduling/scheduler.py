"""Automated scheduling for artwork creation."""

import asyncio
from collections.abc import Callable
from datetime import UTC
from typing import Any, Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..inspiration.autonomous import AutonomousInspiration, WikipediaInspiration
from ..utils.logging import get_logger

logger = get_logger(__name__)


class CreationScheduler:
    """Schedule automated artwork creation with full autonomy!"""

    def __init__(self, autonomous_mode: bool = True):
        self.scheduler = AsyncIOScheduler()
        self.autonomous_mode = autonomous_mode

        # Traditional topic rotation (for legacy mode)
        self.topics = [
            "nature landscape",
            "abstract art",
            "urban architecture",
            "serene ocean",
            "mountain vista",
            "forest scene",
            "space nebula",
            "sunset sky",
        ]
        self.current_topic_index = 0

        # Autonomous inspiration generators
        self.autonomous = AutonomousInspiration()
        self.wikipedia = WikipediaInspiration()

        logger.info(
            "scheduler_initialized",
            autonomous_mode=autonomous_mode,
            traditional_topics=len(self.topics),
        )

    def get_next_topic(
        self,
        mode: Literal[
            "traditional", "surprise", "exploration", "fusion", "mashup", "auto"
        ] = "auto",
    ) -> str:
        """Get next topic - autonomous or traditional.

        Modes:
            - traditional: Rotate through predefined topics
            - surprise: Completely random AI-chosen prompt
            - exploration: AI explores random concepts
            - fusion: Mix multiple styles
            - mashup: Combine unexpected subjects
            - auto: AI picks the mode randomly!
        """
        if mode == "traditional":
            # Original behavior
            topic = self.topics[self.current_topic_index]
            self.current_topic_index = (self.current_topic_index + 1) % len(self.topics)
            logger.info(
                "topic_selected",
                topic=topic,
                mode="traditional",
                index=self.current_topic_index,
            )
            return str(topic)

        # Autonomous mode!
        actual_mode: Literal["surprise", "exploration", "fusion", "mashup"]
        if mode == "auto":
            # Let the AI pick the mode!
            random_mode = self.autonomous.get_random_mode()
            # get_random_mode returns one of the valid generation modes
            actual_mode = random_mode  # type: ignore[assignment]
            logger.info("auto_mode_selected", chosen_mode=actual_mode)
        else:
            # mode is already one of the valid generation modes
            actual_mode = mode  # type: ignore[assignment]

        # Generate autonomous prompt
        prompt = self.autonomous.generate_from_mode(actual_mode)
        logger.info("autonomous_topic_generated", prompt=prompt, mode=actual_mode)
        return prompt

    async def get_wikipedia_topic(self) -> str:
        """Get topic from random Wikipedia article."""
        topic = await self.wikipedia.generate_from_article()
        logger.info("wikipedia_topic_generated", topic=topic)
        return topic

    def add_daily_job(
        self,
        job_func: Callable,
        hour: int = 9,
        minute: int = 0,
        job_id: str = "daily_creation",
    ):
        """Schedule daily artwork creation."""
        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=f"Daily creation at {hour:02d}:{minute:02d}",
            replace_existing=True,
        )
        logger.info(
            "daily_job_scheduled",
            job_id=job_id,
            hour=hour,
            minute=minute,
        )

    def add_interval_job(
        self,
        job_func: Callable,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        job_id: str = "interval_creation",
    ):
        """Schedule artwork creation at intervals."""
        trigger = IntervalTrigger(
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )
        self.scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=f"Interval creation every {hours}h {minutes}m {seconds}s",
            replace_existing=True,
        )
        logger.info(
            "interval_job_scheduled",
            job_id=job_id,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )

    def add_weekly_job(
        self,
        job_func: Callable,
        day_of_week: str = "mon",
        hour: int = 9,
        minute: int = 0,
        job_id: str = "weekly_creation",
    ):
        """Schedule weekly artwork creation."""
        trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
        self.scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=f"Weekly creation on {day_of_week} at {hour:02d}:{minute:02d}",
            replace_existing=True,
        )
        logger.info(
            "weekly_job_scheduled",
            job_id=job_id,
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
        )

    def add_custom_cron_job(
        self,
        job_func: Callable,
        cron_expression: str,
        job_id: str = "custom_creation",
    ):
        """Schedule artwork creation with custom cron expression."""
        # Parse cron expression (minute hour day month day_of_week)
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError("Cron expression must have 5 parts")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        self.scheduler.add_job(
            job_func,
            trigger=trigger,
            id=job_id,
            name=f"Custom cron: {cron_expression}",
            replace_existing=True,
        )
        logger.info(
            "custom_job_scheduled",
            job_id=job_id,
            cron=cron_expression,
        )

    def remove_job(self, job_id: str):
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info("job_removed", job_id=job_id)
        except Exception as e:
            logger.error("job_removal_failed", job_id=job_id, error=str(e))

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            if next_run is None:
                # Try alternative attribute names
                next_run = getattr(job, "next_run", None)

            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": next_run.isoformat() if next_run else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("scheduler_started")

    def shutdown(self, wait: bool = True):
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("scheduler_shutdown")

    async def run_once(self, job_func: Callable):
        """Run a job immediately once."""
        logger.info("running_job_once")
        try:
            await job_func()
            logger.info("job_completed")
        except Exception as e:
            logger.error("job_failed", error=str(e))


class ScheduledArtist:
    """Wrapper for scheduled artwork creation."""

    def __init__(self, artist):
        self.artist = artist
        self.scheduler = CreationScheduler()
        logger.info("scheduled_artist_initialized")

    async def create_with_rotation(self):
        """Create artwork with topic rotation."""
        topic = self.scheduler.get_next_topic()
        logger.info("scheduled_creation_started", topic=topic)
        try:
            await self.artist.create_artwork(theme=topic)
            logger.info("scheduled_creation_complete", topic=topic)
        except Exception as e:
            logger.error("scheduled_creation_failed", topic=topic, error=str(e))

    async def create_batch(self, count: int = 3):
        """Create multiple artworks in a batch."""
        logger.info("batch_creation_started", count=count)
        for i in range(count):
            try:
                await self.create_with_rotation()
                if i < count - 1:
                    # Small delay between creations
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error("batch_creation_item_failed", index=i, error=str(e))
        logger.info("batch_creation_complete", count=count)

    def schedule_daily(self, hour: int = 9, minute: int = 0):
        """Schedule daily creation."""
        self.scheduler.add_daily_job(
            self.create_with_rotation,
            hour=hour,
            minute=minute,
        )

    def schedule_interval(self, hours: int = 6):
        """Schedule creation at intervals."""
        self.scheduler.add_interval_job(
            self.create_with_rotation,
            hours=hours,
        )

    def schedule_batch_daily(self, count: int = 3, hour: int = 9, minute: int = 0):
        """Schedule daily batch creation."""

        async def batch_job():
            await self.create_batch(count=count)

        self.scheduler.add_daily_job(
            batch_job,
            hour=hour,
            minute=minute,
            job_id=f"daily_batch_{count}",
        )

    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("scheduled_artist_started")

    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown()
        logger.info("scheduled_artist_shutdown")

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs."""
        jobs: list[dict] = self.scheduler.list_jobs()
        return jobs


# =============================================================================
# Desire-Aware Scheduler
# =============================================================================


class DesireAwareScheduler(CreationScheduler):
    """Scheduler that creates based on internal desires rather than fixed schedules.

    Makes scheduled creation feel intentional:
    - Creates when desire urgency is high ("Strong creative urge")
    - Creates when mood intensity is high ("Intense feeling to express")
    - Respects time-of-day rituals (morning = fresh ideas, evening = reflection)
    """

    # Time-of-day creative rituals
    TIME_RITUALS = {
        "morning": {  # 5-12
            "mood_bias": ["energized", "playful"],
            "creation_type": "fresh_ideas",
            "description": "Fresh morning energy for new explorations",
        },
        "afternoon": {  # 12-17
            "mood_bias": ["rebellious", "chaotic"],
            "creation_type": "experimental",
            "description": "Afternoon intensity for experimental work",
        },
        "evening": {  # 17-21
            "mood_bias": ["serene", "melancholic"],
            "creation_type": "reflection",
            "description": "Evening calm for reflective pieces",
        },
        "night": {  # 21-5
            "mood_bias": ["introspective", "contemplative"],
            "creation_type": "deep_work",
            "description": "Night stillness for introspective creation",
        },
    }

    # Thresholds for desire-driven creation
    DESIRE_URGENCY_THRESHOLD = 0.8
    MOOD_INTENSITY_THRESHOLD = 0.7

    def __init__(
        self,
        mood_system=None,
        desire_engine=None,
        autonomous_mode: bool = True,
    ):
        super().__init__(autonomous_mode=autonomous_mode)
        self.mood_system = mood_system
        self.desire_engine = desire_engine
        self._last_creation_check = None

        logger.info("desire_aware_scheduler_initialized")

    def _get_time_period(self) -> str:
        """Get current time period based on hour."""
        from datetime import datetime

        hour = datetime.now(UTC).hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def should_create_now(self) -> tuple[bool, str]:
        """Determine if Lumira should create right now based on internal state.

        Returns:
            (should_create, reason) tuple
        """
        reasons = []

        # Check desire urgency
        if self.desire_engine:
            desire = self.desire_engine.get_strongest_desire()
            if desire.urgency > self.DESIRE_URGENCY_THRESHOLD:
                reasons.append(
                    f"Strong {desire.drive_name} drive ({desire.urgency:.2f})"
                )

        # Check mood intensity
        if self.mood_system:
            intensity = getattr(self.mood_system, "mood_intensity", 0.5)
            mood = self.mood_system.current_mood.value
            if intensity > self.MOOD_INTENSITY_THRESHOLD:
                reasons.append(f"Intense {mood} feeling ({intensity:.2f})")

        # Check time-of-day alignment
        period = self._get_time_period()
        ritual = self.TIME_RITUALS.get(period, {})
        mood_bias = ritual.get("mood_bias", [])

        if self.mood_system and self.mood_system.current_mood.value in mood_bias:
            reasons.append(
                f"Time ritual alignment ({ritual.get('description', period)})"
            )

        # Decide
        if reasons:
            should = True
            reason = "; ".join(reasons)
        else:
            should = False
            reason = "No strong creative impulse right now"

        logger.debug(
            "should_create_check",
            should=should,
            reason=reason,
            period=period,
        )

        return should, reason

    def get_ritual_context(self) -> dict:
        """Get current time ritual context for creative decisions."""
        period = self._get_time_period()
        ritual = self.TIME_RITUALS.get(period, {})

        return {
            "period": period,
            "mood_bias": ritual.get("mood_bias", []),
            "creation_type": ritual.get("creation_type", "general"),
            "description": ritual.get("description", ""),
        }

    def add_desire_driven_job(
        self,
        job_func: Callable,
        check_interval_minutes: int = 30,
        job_id: str = "desire_driven_creation",
    ):
        """Add a job that only runs when internal desires warrant it.

        Instead of creating at fixed times, this checks every `check_interval_minutes`
        and only triggers creation if should_create_now() returns True.
        """

        async def conditional_job():
            should_create, reason = self.should_create_now()
            if should_create:
                logger.info(
                    "desire_driven_creation_triggered",
                    reason=reason,
                )
                await job_func()
            else:
                logger.debug(
                    "desire_driven_creation_skipped",
                    reason=reason,
                )

        self.add_interval_job(
            conditional_job,
            minutes=check_interval_minutes,
            job_id=job_id,
        )

        logger.info(
            "desire_driven_job_added",
            check_interval=check_interval_minutes,
            job_id=job_id,
        )

    def add_reflection_job(
        self,
        reflection_func: Callable,
        job_id: str = "daily_reflection",
    ):
        """Add a job for daily reflection at end of day."""
        # Schedule reflection for 10 PM
        self.add_daily_job(
            reflection_func,
            hour=22,
            minute=0,
            job_id=job_id,
        )

        logger.info("reflection_job_added", job_id=job_id)

    def add_weekly_synthesis_job(
        self,
        synthesis_func: Callable,
        job_id: str = "weekly_synthesis",
    ):
        """Add a job for weekly artistic synthesis."""
        self.add_weekly_job(
            synthesis_func,
            day_of_week="sun",
            hour=20,
            minute=0,
            job_id=job_id,
        )

        logger.info("weekly_synthesis_job_added", job_id=job_id)


class DesireAwareArtist:
    """Artist wrapper that creates based on internal desires."""

    def __init__(
        self,
        artist,
        mood_system=None,
        desire_engine=None,
        reflection_system=None,
    ):
        self.artist = artist
        self.mood_system = mood_system
        self.desire_engine = desire_engine
        self.reflection_system = reflection_system
        self.scheduler = DesireAwareScheduler(
            mood_system=mood_system,
            desire_engine=desire_engine,
        )

        logger.info("desire_aware_artist_initialized")

    async def create_when_inspired(self):
        """Create artwork only when internal state warrants it."""
        should, reason = self.scheduler.should_create_now()

        if not should:
            logger.info("creation_deferred", reason=reason)
            return None

        # Get context from time ritual
        ritual_context = self.scheduler.get_ritual_context()

        # Create with ritual-aligned theme if available
        theme = None
        if ritual_context["creation_type"] == "fresh_ideas":
            theme = "exploring something new"
        elif ritual_context["creation_type"] == "experimental":
            theme = "pushing boundaries"
        elif ritual_context["creation_type"] == "reflection":
            theme = "quiet contemplation"
        elif ritual_context["creation_type"] == "deep_work":
            theme = "introspective journey"

        logger.info(
            "inspired_creation_started",
            reason=reason,
            ritual=ritual_context["period"],
            theme=theme,
        )

        try:
            result = await self.artist.create_artwork(theme=theme)
            logger.info("inspired_creation_complete")
            return result
        except Exception as e:
            logger.error("inspired_creation_failed", error=str(e))
            return None

    async def perform_daily_reflection(self):
        """Perform end-of-day reflection."""
        if not self.reflection_system:
            logger.warning("no_reflection_system_available")
            return

        logger.info("daily_reflection_started")

        try:
            # End any current session
            if self.reflection_system._current_session_id:
                self.reflection_system.record_session_end()

            # Generate daily reflection
            reflection = self.reflection_system.generate_daily_reflection()

            logger.info(
                "daily_reflection_complete",
                date=reflection.date,
                patterns=len(reflection.patterns_noticed),
            )

            return reflection
        except Exception as e:
            logger.error("daily_reflection_failed", error=str(e))
            return None

    async def perform_weekly_synthesis(self):
        """Perform weekly artistic synthesis."""
        if not self.reflection_system:
            logger.warning("no_reflection_system_available")
            return

        logger.info("weekly_synthesis_started")

        try:
            synthesis = self.reflection_system.generate_weekly_synthesis()

            logger.info(
                "weekly_synthesis_complete",
                week=synthesis.week_start,
                period_name=synthesis.period_name,
            )

            return synthesis
        except Exception as e:
            logger.error("weekly_synthesis_failed", error=str(e))
            return None

    def schedule_desire_driven_creation(
        self,
        check_interval_minutes: int = 30,
    ):
        """Schedule creation that only triggers on strong internal desires."""
        self.scheduler.add_desire_driven_job(
            self.create_when_inspired,
            check_interval_minutes=check_interval_minutes,
        )

    def schedule_reflections(self):
        """Schedule daily and weekly reflections."""
        self.scheduler.add_reflection_job(self.perform_daily_reflection)
        self.scheduler.add_weekly_synthesis_job(self.perform_weekly_synthesis)

    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("desire_aware_artist_started")

    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown()
        logger.info("desire_aware_artist_shutdown")

    def list_jobs(self) -> list[dict[Any, Any]]:
        """List all scheduled jobs."""
        jobs: list[dict[Any, Any]] = self.scheduler.list_jobs()
        return jobs
