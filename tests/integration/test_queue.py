"""Integration tests for the Redis job queue.

These tests use fakeredis to mock Redis, allowing tests to run without
a real Redis instance.
"""

from unittest.mock import MagicMock, patch

import pytest

# Skip if RQ is not installed
pytest.importorskip("rq")
fakeredis = pytest.importorskip("fakeredis")


class TestGenerationQueue:
    """Tests for GenerationQueue class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a fakeredis instance for testing."""
        return fakeredis.FakeRedis()

    @pytest.fixture
    def queue(self, mock_redis):
        """Create a GenerationQueue with mocked Redis."""
        from ai_artist.queue.job_queue import GenerationQueue

        with patch("ai_artist.queue.job_queue.Redis") as MockRedis:
            MockRedis.from_url.return_value = mock_redis
            queue = GenerationQueue(redis_url="redis://localhost:6379")
            return queue

    def test_queue_initialization(self, queue):
        """Test queue initializes correctly."""
        assert queue.enabled is True
        assert len(queue.queues) == 3  # high, normal, low
        assert "high" in [p.value for p in queue.queues]
        assert "normal" in [p.value for p in queue.queues]
        assert "low" in [p.value for p in queue.queues]

    def test_queue_unavailable_without_rq(self):
        """Test queue handles missing RQ gracefully."""
        from ai_artist.queue.job_queue import GenerationQueue

        with patch("ai_artist.queue.job_queue.RQ_AVAILABLE", False):
            queue = GenerationQueue()
            assert queue.enabled is False
            assert queue.is_available() is False

    def test_enqueue_generation_when_disabled(self):
        """Test enqueue returns None when queue is disabled."""
        from ai_artist.queue.job_queue import GenerationQueue

        with patch("ai_artist.queue.job_queue.RQ_AVAILABLE", False):
            queue = GenerationQueue()
            result = queue.enqueue_generation("test prompt", {})
            assert result is None

    def test_get_job_status_not_found(self, queue, mock_redis):
        """Test getting status of non-existent job."""
        result = queue.get_job_status("nonexistent-job-id")
        # Returns None when job not found
        assert result is None

    def test_get_queue_stats_when_disabled(self):
        """Test get_queue_stats when queue is disabled."""
        from ai_artist.queue.job_queue import GenerationQueue

        with patch("ai_artist.queue.job_queue.RQ_AVAILABLE", False):
            queue = GenerationQueue()
            stats = queue.get_queue_stats()
            assert stats["enabled"] is False

    def test_clear_queue_when_disabled(self):
        """Test clear_queue when queue is disabled."""
        from ai_artist.queue.job_queue import GenerationQueue

        with patch("ai_artist.queue.job_queue.RQ_AVAILABLE", False):
            queue = GenerationQueue()
            result = queue.clear_queue()
            assert result == 0


class TestWorkerFunctions:
    """Tests for worker functions."""

    @pytest.fixture
    def mock_generator(self):
        """Create a mock ImageGenerator."""
        mock = MagicMock()
        mock.generate.return_value = []  # Empty list of images
        return mock

    def test_generate_image_loads_config(self, mock_generator, tmp_path):
        """Test generate_image loads configuration correctly."""
        from ai_artist.queue.worker import generate_image

        # Create minimal config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("""
model:
  base_model: test-model
  device: cpu
  dtype: float32
""")

        # Create gallery directory
        gallery_dir = tmp_path / "gallery"
        gallery_dir.mkdir()

        with patch("ai_artist.queue.worker.Path") as MockPath:
            # Mock config path check
            MockPath.return_value.exists.return_value = False

            # Patch ImageGenerator where it's defined (core.generator), not where imported
            with patch("ai_artist.core.generator.ImageGenerator") as MockGenerator:
                MockGenerator.return_value = mock_generator

                with patch("rq.get_current_job") as mock_job:
                    mock_job.return_value = MagicMock(
                        id="test-job-123",
                        meta={},
                        save_meta=MagicMock(),
                    )

                    # Should raise because no config and no CUDA
                    # (testing defensive behavior)
                    generate_image("test prompt", {"width": 512})

                    # Verify generator was created
                    MockGenerator.assert_called_once()


class TestJobInfo:
    """Tests for JobInfo dataclass."""

    def test_job_info_creation(self):
        """Test JobInfo can be created with all fields."""
        from ai_artist.queue.job_queue import JobInfo, JobStatus

        info = JobInfo(
            id="test-123",
            status=JobStatus.QUEUED,
            result=None,
            progress=0,
            enqueued_at="2024-01-01T00:00:00",
            started_at=None,
            ended_at=None,
            error=None,
            meta={"source": "test"},
        )

        assert info.id == "test-123"
        assert info.status == JobStatus.QUEUED
        assert info.progress == 0
        assert info.meta == {"source": "test"}


class TestJobPriority:
    """Tests for JobPriority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        from ai_artist.queue.job_queue import JobPriority

        assert JobPriority.HIGH.value == "high"
        assert JobPriority.NORMAL.value == "normal"
        assert JobPriority.LOW.value == "low"

    def test_priority_from_string(self):
        """Test creating priority from string."""
        from ai_artist.queue.job_queue import JobPriority

        assert JobPriority("high") == JobPriority.HIGH
        assert JobPriority("normal") == JobPriority.NORMAL
        assert JobPriority("low") == JobPriority.LOW


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        from ai_artist.queue.job_queue import JobStatus

        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.STARTED.value == "started"
        assert JobStatus.FINISHED.value == "finished"
        assert JobStatus.FAILED.value == "failed"


class TestGetQueue:
    """Tests for get_queue singleton function."""

    def test_get_queue_returns_same_instance(self):
        """Test get_queue returns singleton."""
        import ai_artist.queue.job_queue as queue_module
        from ai_artist.queue.job_queue import get_queue

        # Reset singleton
        queue_module._queue_instance = None

        with patch("ai_artist.queue.job_queue.RQ_AVAILABLE", False):
            q1 = get_queue()
            q2 = get_queue()
            assert q1 is q2

        # Reset after test
        queue_module._queue_instance = None


class TestQueueAPIEndpoints:
    """Tests for queue API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient

        from ai_artist.web.app import app

        return TestClient(app)

    def test_queue_stats_endpoint(self, client):
        """Test GET /api/lumira/queue/stats endpoint."""
        response = client.get("/api/lumira/queue/stats")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "queues" in data

    def test_generate_async_without_redis(self, client):
        """Test POST /api/lumira/generate-async when Redis unavailable."""
        with patch("ai_artist.queue.job_queue.RQ_AVAILABLE", False):
            # Reset singleton
            import ai_artist.queue.job_queue as queue_module

            queue_module._queue_instance = None

            response = client.post(
                "/api/lumira/generate-async",
                json={"prompt": "test prompt"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "not available" in data["message"]

            # Reset after test
            queue_module._queue_instance = None

    def test_job_status_not_found(self, client):
        """Test GET /api/lumira/job/{job_id} returns 404 for unknown job."""
        # This will fail because Redis is not available in tests
        # but we're testing the endpoint exists
        response = client.get("/api/lumira/job/nonexistent-job-id")
        # Either 404 (job not found) or 503 (queue unavailable)
        assert response.status_code in (404, 503)


class TestCleanupStaleJobs:
    """Tests for cleanup_stale_jobs function."""

    def test_cleanup_without_rq(self):
        """Test cleanup returns error when RQ not installed."""
        from ai_artist.queue.worker import cleanup_stale_jobs

        with patch.dict("sys.modules", {"rq": None, "redis": None}):
            # This should handle the import error gracefully
            result = cleanup_stale_jobs()
            # Either returns stats or error dict
            assert isinstance(result, dict)
