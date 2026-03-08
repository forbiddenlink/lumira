"""Tests for scheduling system."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_artist.scheduling.scheduler import (
    CreationScheduler,
    DesireAwareArtist,
    DesireAwareScheduler,
    ScheduledArtist,
)


@pytest.fixture
def scheduler():
    """Create a test scheduler."""
    return CreationScheduler()


@pytest.fixture
def mock_artist():
    """Create a mock artist."""
    artist = MagicMock()
    artist.create_artwork = AsyncMock()
    return artist


@pytest.fixture
def scheduled_artist(mock_artist):
    """Create a scheduled artist."""
    return ScheduledArtist(mock_artist)


class TestCreationScheduler:
    """Test CreationScheduler class."""

    def test_initialization(self, scheduler):
        """Test scheduler initialization."""
        assert scheduler.scheduler is not None
        assert len(scheduler.topics) == 8
        assert scheduler.current_topic_index == 0

    def test_get_next_topic(self, scheduler):
        """Test topic rotation in traditional mode."""
        first_topic = scheduler.get_next_topic(mode="traditional")
        assert first_topic == "nature landscape"
        assert scheduler.current_topic_index == 1

        second_topic = scheduler.get_next_topic(mode="traditional")
        assert second_topic == "abstract art"
        assert scheduler.current_topic_index == 2

    def test_topic_wraps_around(self, scheduler):
        """Test topic rotation wraps around in traditional mode."""
        # Get all topics
        for _ in range(8):
            scheduler.get_next_topic(mode="traditional")

        # Should wrap to first topic
        assert scheduler.current_topic_index == 0
        topic = scheduler.get_next_topic(mode="traditional")
        assert topic == "nature landscape"

    def test_auto_mode_generates_topic(self, scheduler):
        """Test auto mode generates autonomous topics."""
        topic = scheduler.get_next_topic(mode="auto")
        # Auto mode returns generated prompts, not predefined topics
        assert isinstance(topic, str)
        assert len(topic) > 0

    def test_add_daily_job(self, scheduler):
        """Test adding daily job."""
        job_func = AsyncMock()
        scheduler.add_daily_job(job_func, hour=9, minute=30, job_id="test_daily")

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_daily"
        assert "09:30" in jobs[0]["name"]

    def test_add_interval_job(self, scheduler):
        """Test adding interval job."""
        job_func = AsyncMock()
        scheduler.add_interval_job(
            job_func, hours=2, minutes=30, job_id="test_interval"
        )

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_interval"

    def test_add_weekly_job(self, scheduler):
        """Test adding weekly job."""
        job_func = AsyncMock()
        scheduler.add_weekly_job(
            job_func, day_of_week="mon", hour=10, minute=0, job_id="test_weekly"
        )

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_weekly"

    def test_remove_job(self, scheduler):
        """Test removing a job."""
        job_func = AsyncMock()
        scheduler.add_daily_job(job_func, job_id="removable")
        assert len(scheduler.list_jobs()) == 1

        scheduler.remove_job("removable")
        assert len(scheduler.list_jobs()) == 0

    def test_list_jobs_empty(self, scheduler):
        """Test listing jobs when none exist."""
        jobs = scheduler.list_jobs()
        assert jobs == []

    @pytest.mark.asyncio
    async def test_run_once(self, scheduler):
        """Test running a job once."""
        job_func = AsyncMock()
        await scheduler.run_once(job_func)
        job_func.assert_called_once()


class TestScheduledArtist:
    """Test ScheduledArtist class."""

    def test_initialization(self, scheduled_artist, mock_artist):
        """Test scheduled artist initialization."""
        assert scheduled_artist.artist == mock_artist
        assert scheduled_artist.scheduler is not None

    @pytest.mark.asyncio
    async def test_create_with_rotation(self, scheduled_artist, mock_artist):
        """Test creation with topic rotation (now uses autonomous mode)."""
        await scheduled_artist.create_with_rotation()

        mock_artist.create_artwork.assert_called_once()
        call_args = mock_artist.create_artwork.call_args
        # Autonomous mode generates varied topics, just verify a theme was passed
        assert "theme" in call_args.kwargs
        assert isinstance(call_args.kwargs["theme"], str)
        assert len(call_args.kwargs["theme"]) > 0

    @pytest.mark.asyncio
    async def test_create_batch(self, scheduled_artist, mock_artist):
        """Test batch creation."""
        await scheduled_artist.create_batch(count=3)

        assert mock_artist.create_artwork.call_count == 3

    @pytest.mark.asyncio
    async def test_create_batch_with_error(self, scheduled_artist, mock_artist):
        """Test batch creation continues after error."""
        # First call succeeds, second fails, third succeeds
        mock_artist.create_artwork.side_effect = [
            None,
            Exception("Test error"),
            None,
        ]

        await scheduled_artist.create_batch(count=3)

        # Should attempt all 3 despite error
        assert mock_artist.create_artwork.call_count == 3

    def test_schedule_daily(self, scheduled_artist):
        """Test scheduling daily creation."""
        scheduled_artist.schedule_daily(hour=10, minute=30)

        jobs = scheduled_artist.list_jobs()
        assert len(jobs) == 1
        assert "10:30" in jobs[0]["name"]

    def test_schedule_interval(self, scheduled_artist):
        """Test scheduling interval creation."""
        scheduled_artist.schedule_interval(hours=6)

        jobs = scheduled_artist.list_jobs()
        assert len(jobs) == 1
        assert "6h" in jobs[0]["name"]

    def test_schedule_batch_daily(self, scheduled_artist):
        """Test scheduling daily batch creation."""
        scheduled_artist.schedule_batch_daily(count=3, hour=9, minute=0)

        jobs = scheduled_artist.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_batch_3"

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self, scheduled_artist):
        """Test starting and shutting down scheduler."""
        import asyncio

        # Start scheduler in background
        scheduled_artist.start()
        await asyncio.sleep(0.1)  # Let scheduler start
        assert scheduled_artist.scheduler.scheduler.running

        scheduled_artist.shutdown()
        await asyncio.sleep(0.2)  # Allow time for shutdown
        assert not scheduled_artist.scheduler.scheduler.running


# =============================================================================
# Desire-Aware Scheduling Tests
# =============================================================================


@pytest.fixture
def mock_mood_system():
    """Create a mock mood system."""
    mood = MagicMock()
    mood.current_mood = MagicMock()
    mood.current_mood.value = "serene"
    mood.mood_intensity = 0.8
    return mood


@pytest.fixture
def mock_desire_engine():
    """Create a mock desire engine."""
    from ai_artist.intelligence.desire_engine import CreativeDesire

    engine = MagicMock()
    engine.get_strongest_desire = MagicMock(
        return_value=CreativeDesire(
            drive_name="emotional_expression",
            subject_suggestion="ocean",
            urgency=0.85,
            reasoning="Strong creative urge",
        )
    )
    return engine


class TestDesireAwareScheduler:
    """Test DesireAwareScheduler class."""

    @pytest.fixture
    def scheduler(self, mock_mood_system, mock_desire_engine):
        """Create a desire-aware scheduler."""
        return DesireAwareScheduler(
            mood_system=mock_mood_system,
            desire_engine=mock_desire_engine,
        )

    def test_initialization(self, scheduler):
        """Test scheduler initialization."""
        assert scheduler.mood_system is not None
        assert scheduler.desire_engine is not None
        assert scheduler.TIME_RITUALS is not None

    def test_get_time_period(self, scheduler):
        """Test time period detection."""
        period = scheduler._get_time_period()
        assert period in ["morning", "afternoon", "evening", "night"]

    def test_should_create_now_high_urgency(self, scheduler, mock_desire_engine):
        """Test should_create_now with high desire urgency."""
        # Set high urgency
        mock_desire_engine.get_strongest_desire.return_value.urgency = 0.9

        should, reason = scheduler.should_create_now()

        # Should want to create due to high urgency
        assert should is True
        assert "drive" in reason.lower() or "feeling" in reason.lower()

    def test_should_create_now_high_intensity(
        self, scheduler, mock_mood_system, mock_desire_engine
    ):
        """Test should_create_now with high mood intensity."""
        # Low urgency but high intensity
        mock_desire_engine.get_strongest_desire.return_value.urgency = 0.3
        mock_mood_system.mood_intensity = 0.9

        should, reason = scheduler.should_create_now()

        assert should is True
        assert "feeling" in reason.lower() or "intense" in reason.lower()

    def test_should_create_now_low_everything(
        self, scheduler, mock_mood_system, mock_desire_engine
    ):
        """Test should_create_now when nothing is urgent."""
        mock_desire_engine.get_strongest_desire.return_value.urgency = 0.3
        mock_mood_system.mood_intensity = 0.3
        mock_mood_system.current_mood.value = "contemplative"  # Not in any time bias

        should, reason = scheduler.should_create_now()

        assert should is False
        assert "no strong" in reason.lower()

    def test_get_ritual_context(self, scheduler):
        """Test getting ritual context."""
        context = scheduler.get_ritual_context()

        assert "period" in context
        assert "mood_bias" in context
        assert "creation_type" in context
        assert "description" in context

    def test_add_desire_driven_job(self, scheduler):
        """Test adding desire-driven job."""
        job_func = AsyncMock()
        scheduler.add_desire_driven_job(
            job_func,
            check_interval_minutes=15,
            job_id="test_desire_job",
        )

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_desire_job"

    def test_add_reflection_job(self, scheduler):
        """Test adding reflection job."""
        job_func = AsyncMock()
        scheduler.add_reflection_job(job_func, job_id="test_reflection")

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_reflection"

    def test_add_weekly_synthesis_job(self, scheduler):
        """Test adding weekly synthesis job."""
        job_func = AsyncMock()
        scheduler.add_weekly_synthesis_job(job_func, job_id="test_synthesis")

        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_synthesis"


class TestDesireAwareArtist:
    """Test DesireAwareArtist class."""

    @pytest.fixture
    def artist(self, mock_artist, mock_mood_system, mock_desire_engine):
        """Create a desire-aware artist."""
        return DesireAwareArtist(
            artist=mock_artist,
            mood_system=mock_mood_system,
            desire_engine=mock_desire_engine,
        )

    def test_initialization(self, artist, mock_artist):
        """Test artist initialization."""
        assert artist.artist == mock_artist
        assert artist.scheduler is not None
        assert isinstance(artist.scheduler, DesireAwareScheduler)

    @pytest.mark.asyncio
    async def test_create_when_inspired_creates(
        self, artist, mock_artist, mock_desire_engine
    ):
        """Test create_when_inspired triggers creation when inspired."""
        # High urgency should trigger creation
        mock_desire_engine.get_strongest_desire.return_value.urgency = 0.9

        await artist.create_when_inspired()

        mock_artist.create_artwork.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_when_inspired_skips(
        self, artist, mock_artist, mock_desire_engine, mock_mood_system
    ):
        """Test create_when_inspired skips when not inspired."""
        # Low urgency and low intensity
        mock_desire_engine.get_strongest_desire.return_value.urgency = 0.3
        mock_mood_system.mood_intensity = 0.3
        mock_mood_system.current_mood.value = "contemplative"

        result = await artist.create_when_inspired()

        mock_artist.create_artwork.assert_not_called()
        assert result is None

    def test_schedule_desire_driven_creation(self, artist):
        """Test scheduling desire-driven creation."""
        artist.schedule_desire_driven_creation(check_interval_minutes=30)

        jobs = artist.list_jobs()
        assert len(jobs) == 1

    def test_schedule_reflections(self, artist):
        """Test scheduling reflections."""
        artist.reflection_system = MagicMock()
        artist.schedule_reflections()

        jobs = artist.list_jobs()
        # Should have daily + weekly
        assert len(jobs) == 2
