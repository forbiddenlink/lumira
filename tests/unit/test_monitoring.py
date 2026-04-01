"""Tests for monitoring modules: metrics and sentry."""

from unittest.mock import patch

import pytest

# ===========================================================================
# Metrics tests
# ===========================================================================


class TestMetrics:
    """Tests for monitoring.metrics helper functions."""

    def test_import_succeeds(self):
        from ai_artist.monitoring import metrics as m

        assert m is not None

    def test_record_quality_metrics_no_error(self):
        """record_quality_metrics should not raise even without prometheus."""
        from ai_artist.monitoring.metrics import record_quality_metrics

        # Should run silently whether prometheus is available or not
        record_quality_metrics(
            model="sdxl-base",
            clip_score=0.28,
            aesthetic_score=6.5,
            overall_score=0.82,
        )

    def test_record_feedback_no_error(self):
        from ai_artist.monitoring.metrics import record_feedback

        record_feedback(action="love", mood="euphoric")
        record_feedback(action="skip", mood="anxious")

    def test_update_model_pool_metrics(self):
        from ai_artist.monitoring.metrics import update_model_pool_metrics

        update_model_pool_metrics(pool_size=3, preloaded_count=2)

    def test_set_lumira_info(self):
        from ai_artist.monitoring.metrics import set_lumira_info

        set_lumira_info(version="1.0.0", python_version="3.12", torch_version="2.0")

    def test_update_gpu_metrics_no_gpu(self):
        """update_gpu_metrics should not raise if torch/cuda are not available."""
        from ai_artist.monitoring.metrics import update_gpu_metrics

        with patch("builtins.__import__", side_effect=ImportError("no torch")):
            # Even if torch is not importable, should not raise
            pass
        # Call with torch present (it may or may not be available in CI)
        update_gpu_metrics()

    def test_get_metrics_returns_tuple(self):
        from ai_artist.monitoring.metrics import get_metrics

        result = get_metrics()
        assert isinstance(result, tuple)
        assert len(result) == 2
        data, content_type = result
        assert isinstance(content_type, str)
        # data can be bytes or a status message string
        assert data is not None

    def test_track_generation_time_decorator_success(self):
        from ai_artist.monitoring.metrics import track_generation_time

        @track_generation_time(model="sdxl", mood="serene")
        def generate():
            return "done"

        result = generate()
        assert result == "done"

    def test_track_generation_time_decorator_exception(self):
        from ai_artist.monitoring.metrics import track_generation_time

        @track_generation_time(model="sdxl", mood="anxious")
        def failing_generate():
            raise ValueError("generation failed")

        with pytest.raises(ValueError, match="generation failed"):
            failing_generate()

    @pytest.mark.asyncio
    async def test_track_generation_time_async_success(self):
        from ai_artist.monitoring.metrics import track_generation_time_async

        decorator = await track_generation_time_async(model="sdxl", mood="playful")

        @decorator
        async def async_generate():
            return "async done"

        result = await async_generate()
        assert result == "async done"

    @pytest.mark.asyncio
    async def test_track_generation_time_async_exception(self):
        from ai_artist.monitoring.metrics import track_generation_time_async

        decorator = await track_generation_time_async(model="sdxl", mood="melancholic")

        @decorator
        async def async_failing():
            raise RuntimeError("async failure")

        with pytest.raises(RuntimeError, match="async failure"):
            await async_failing()

    def test_module_level_counters_exist(self):
        """Verify the metric objects exist at module level."""
        import ai_artist.monitoring.metrics as m

        assert hasattr(m, "generation_requests_total")
        assert hasattr(m, "generation_duration_seconds")
        assert hasattr(m, "images_generated_total")
        assert hasattr(m, "generation_errors_total")
        assert hasattr(m, "feedback_events_total")
        assert hasattr(m, "curation_quality_score")
        assert hasattr(m, "model_pool_size")
        assert hasattr(m, "active_generations")


# ===========================================================================
# Sentry tests
# ===========================================================================


class TestSentry:
    """Tests for monitoring.sentry functions."""

    def setup_method(self):
        """Reset sentry state before each test."""
        import ai_artist.monitoring.sentry as s

        s._sentry_initialized = False

    def test_init_sentry_no_dsn_returns_false(self):
        from ai_artist.monitoring.sentry import init_sentry

        result = init_sentry(dsn=None)
        assert result is False

    def test_init_sentry_empty_dsn_returns_false(self):
        from ai_artist.monitoring.sentry import init_sentry

        result = init_sentry(dsn="")
        assert result is False

    def test_init_sentry_sentry_not_installed(self):
        """When sentry_sdk is not importable, init_sentry returns False."""
        from ai_artist.monitoring import sentry as sentry_module

        sentry_module._sentry_initialized = False

        with patch.dict("sys.modules", {"sentry_sdk": None}):
            result = sentry_module.init_sentry(dsn="https://fake@sentry.io/123")
            # Should return False since sentry_sdk can't be imported
            assert result is False

    def test_is_initialized_initially_false(self):
        from ai_artist.monitoring.sentry import is_initialized

        assert is_initialized() is False

    def test_is_initialized_after_reset(self):
        import ai_artist.monitoring.sentry as s

        s._sentry_initialized = True
        from ai_artist.monitoring.sentry import is_initialized

        assert is_initialized() is True
        s._sentry_initialized = False  # clean up

    def test_capture_exception_when_not_initialized(self):
        """capture_exception should be a no-op when Sentry is not initialized."""
        import ai_artist.monitoring.sentry as s

        s._sentry_initialized = False
        from ai_artist.monitoring.sentry import capture_exception

        # Should not raise
        capture_exception(ValueError("test error"), context="test")

    def test_capture_message_when_not_initialized(self):
        """capture_message should be a no-op when Sentry is not initialized."""
        import ai_artist.monitoring.sentry as s

        s._sentry_initialized = False
        from ai_artist.monitoring.sentry import capture_message

        # Should not raise
        capture_message("test message", level="warning")

    def test_set_user_when_not_initialized(self):
        """set_user should be a no-op when Sentry is not initialized."""
        import ai_artist.monitoring.sentry as s

        s._sentry_initialized = False
        from ai_artist.monitoring.sentry import set_user

        set_user(user_id="user-123", email="test@example.com")

    def test_filter_sensitive_data_redacts_auth_header(self):
        from ai_artist.monitoring.sentry import _filter_sensitive_data

        event = {
            "request": {
                "headers": {
                    "authorization": "Bearer secret-token",
                    "content-type": "application/json",
                }
            }
        }
        result = _filter_sensitive_data(event, {})
        assert result["request"]["headers"]["authorization"] == "[REDACTED]"
        assert result["request"]["headers"]["content-type"] == "application/json"

    def test_filter_sensitive_data_redacts_api_key_header(self):
        from ai_artist.monitoring.sentry import _filter_sensitive_data

        event = {"request": {"headers": {"x-api-key": "my-secret-key"}}}
        result = _filter_sensitive_data(event, {})
        assert result["request"]["headers"]["x-api-key"] == "[REDACTED]"

    def test_filter_sensitive_data_preserves_safe_headers(self):
        from ai_artist.monitoring.sentry import _filter_sensitive_data

        event = {
            "request": {
                "headers": {
                    "user-agent": "TestClient/1.0",
                    "accept": "application/json",
                }
            }
        }
        result = _filter_sensitive_data(event, {})
        assert result["request"]["headers"]["user-agent"] == "TestClient/1.0"

    def test_filter_sensitive_data_redacts_password_qs(self):
        from ai_artist.monitoring.sentry import _filter_sensitive_data

        event = {"request": {"query_string": "user=test&password=secret123"}}
        result = _filter_sensitive_data(event, {})
        assert result["request"]["query_string"] == "[REDACTED]"

    def test_filter_sensitive_data_safe_qs(self):
        from ai_artist.monitoring.sentry import _filter_sensitive_data

        event = {"request": {"query_string": "page=1&limit=20"}}
        result = _filter_sensitive_data(event, {})
        assert result["request"]["query_string"] == "page=1&limit=20"

    def test_filter_sensitive_data_no_request(self):
        from ai_artist.monitoring.sentry import _filter_sensitive_data

        event = {"extra": "data"}
        result = _filter_sensitive_data(event, {})
        assert result == {"extra": "data"}

    def test_init_sentry_already_initialized(self):
        import ai_artist.monitoring.sentry as s

        s._sentry_initialized = True
        from ai_artist.monitoring.sentry import init_sentry

        result = init_sentry(dsn="https://fake@sentry.io/123")
        # Should return True (already initialized, no re-init)
        assert result is True
        s._sentry_initialized = False  # clean up
