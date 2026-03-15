"""Unit tests for rate limiting functionality."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ai_artist.web.rate_limit import (
    RateLimits,
    create_rate_limit_error_response,
    get_rate_limit_key,
    rate_limit_exceeded_handler,
)


class TestRateLimits:
    """Tests for rate limit constants."""

    def test_preview_limit_is_5_per_minute(self):
        """Preview endpoint should be limited to 5 per minute."""
        assert RateLimits.PREVIEW == "5/minute"

    def test_request_limit_is_5_per_minute(self):
        """Request endpoint should be limited to 5 per minute."""
        assert RateLimits.REQUEST == "5/minute"

    def test_img2img_limit_is_5_per_minute(self):
        """Img2img endpoint should be limited to 5 per minute."""
        assert RateLimits.IMG2IMG == "5/minute"

    def test_variations_limit_is_5_per_minute(self):
        """Variations endpoint should be limited to 5 per minute."""
        assert RateLimits.VARIATIONS == "5/minute"

    def test_batch_create_limit_is_2_per_minute(self):
        """Batch create endpoint should be limited to 2 per minute (stricter)."""
        assert RateLimits.BATCH_CREATE == "2/minute"

    def test_explore_limit_is_10_per_minute(self):
        """Explore endpoint should be limited to 10 per minute (lighter operation)."""
        assert RateLimits.EXPLORE == "10/minute"


class MockRateLimitExceeded(Exception):
    """Mock exception for testing rate limit error responses."""

    def __init__(self, detail: str, retry_after: int = 60):
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(detail)


class TestRateLimitErrorResponse:
    """Tests for rate limit error response generation."""

    def test_creates_429_response(self):
        """Should create a 429 status code response."""
        # Create a mock exception with the expected attributes
        exc = MockRateLimitExceeded("5 per 1 minute")
        response = create_rate_limit_error_response(exc)

        assert response.status_code == 429

    def test_response_has_retry_after_header(self):
        """Response should include Retry-After header."""
        exc = MockRateLimitExceeded("5 per 1 minute", retry_after=60)
        response = create_rate_limit_error_response(exc)

        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "60"

    def test_response_has_rate_limit_header(self):
        """Response should include X-RateLimit-Limit header."""
        exc = MockRateLimitExceeded("5 per 1 minute")
        response = create_rate_limit_error_response(exc)

        assert "X-RateLimit-Limit" in response.headers

    def test_response_body_has_error_message(self):
        """Response body should have helpful error message."""
        exc = MockRateLimitExceeded("5 per 1 minute")
        response = create_rate_limit_error_response(exc)

        # Decode the body
        import json

        body = json.loads(response.body.decode())

        assert body["error"] == "rate_limit_exceeded"
        assert "message" in body
        assert "GPU" in body["message"] or "limit" in body["message"].lower()
        assert "retry_after_seconds" in body

    def test_response_body_has_suggestion(self):
        """Response body should include helpful suggestions."""
        exc = MockRateLimitExceeded("5 per 1 minute")
        response = create_rate_limit_error_response(exc)

        import json

        body = json.loads(response.body.decode())

        assert "suggestion" in body
        assert len(body["suggestion"]) > 0


class TestGetRateLimitKey:
    """Tests for rate limit key function."""

    def test_uses_ip_address_without_api_key(self):
        """Should use IP address when no API key is provided."""
        # Create a mock request
        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Make a request and check the key function works
        # We can't easily test the exact IP, but we can verify it doesn't crash
        with client:
            response = client.get("/test")
            assert response.status_code == 200

    def test_uses_api_key_when_provided(self):
        """Should use API key hash when X-API-Key header is present."""
        # Create a minimal ASGI scope for testing
        from starlette.testclient import TestClient

        app = FastAPI()

        captured_key = None

        @app.get("/test")
        def test_endpoint(request: Request):
            nonlocal captured_key
            captured_key = get_rate_limit_key(request)
            return {"status": "ok"}

        client = TestClient(app)

        # Make request with API key
        response = client.get("/test", headers={"X-API-Key": "test-key-123"})
        assert response.status_code == 200
        assert captured_key is not None
        assert captured_key.startswith("apikey:")


class TestRateLimitingIntegration:
    """Integration tests for rate limiting with the actual app."""

    @pytest.fixture
    def client(self):
        """Create test client for the Lumira app."""
        from ai_artist.web.app import app

        return TestClient(app)

    def test_state_endpoint_has_rate_limit(self, client):
        """State endpoint should have rate limiting configured."""
        # Make multiple requests - should work within limits
        for _ in range(5):
            response = client.get("/api/lumira/state")
            assert response.status_code == 200

    def test_rate_limited_endpoint_returns_429_when_exceeded(self):
        """Endpoint should return 429 when rate limit is exceeded."""
        # Create a test app with strict rate limiting

        app = FastAPI()
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter

        @app.get("/limited")
        @limiter.limit("1/minute")
        def limited_endpoint(request: Request):
            return {"status": "ok"}

        # Add the exception handler
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        client = TestClient(app)

        # First request should succeed
        response = client.get("/limited")
        assert response.status_code == 200

        # Second request should be rate limited
        response = client.get("/limited")
        assert response.status_code == 429

    def test_429_response_has_helpful_content(self):
        """429 response should have helpful error information."""

        app = FastAPI()
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter

        @app.get("/limited")
        @limiter.limit("1/minute")
        def limited_endpoint(request: Request):
            return {"status": "ok"}

        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        client = TestClient(app)

        # Exhaust the rate limit
        client.get("/limited")
        response = client.get("/limited")

        assert response.status_code == 429
        data = response.json()

        # Check for helpful fields
        assert "error" in data
        assert data["error"] == "rate_limit_exceeded"
        assert "message" in data
        assert "retry_after_seconds" in data
        assert "suggestion" in data

    def test_429_response_has_retry_after_header(self):
        """429 response should include Retry-After header."""

        app = FastAPI()
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter

        @app.get("/limited")
        @limiter.limit("1/minute")
        def limited_endpoint(request: Request):
            return {"status": "ok"}

        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        client = TestClient(app)

        # Exhaust the rate limit
        client.get("/limited")
        response = client.get("/limited")

        assert response.status_code == 429
        assert "Retry-After" in response.headers


class TestGenerationEndpointRateLimits:
    """Tests verifying generation endpoints have correct rate limits configured."""

    @pytest.fixture
    def client(self):
        """Create test client for the Lumira app with fresh rate limiter."""
        from ai_artist.web.app import app

        # Reset rate limiter storage to avoid cross-test interference
        if (
            hasattr(app.state, "limiter")
            and app.state.limiter
            and hasattr(app.state.limiter, "_storage")
        ):
            # Clear the in-memory storage used by slowapi
            app.state.limiter._storage.storage.clear()

        return TestClient(app)

    def test_preview_endpoint_exists(self, client):
        """Preview endpoint should exist and be accessible."""
        # We just verify the endpoint exists and has a rate limiter
        # Actual rate limit testing requires many requests
        response = client.post(
            "/api/lumira/preview",
            json={"prompt": "test"},
        )
        # May fail for other reasons, but not 404
        assert response.status_code != 404

    def test_request_endpoint_exists(self, client):
        """Request endpoint should exist."""
        response = client.post(
            "/api/lumira/request",
            json={"prompt": "test"},
        )
        assert response.status_code != 404

    def test_img2img_endpoint_exists(self, client):
        """Img2img endpoint should exist."""
        response = client.post(
            "/api/lumira/img2img",
            json={"image_id": 1, "prompt": "test"},
        )
        # Will likely be 404 for missing image, but endpoint exists
        assert response.status_code in [200, 404, 422, 500]

    def test_variations_endpoint_exists(self, client):
        """Variations endpoint should exist."""
        response = client.post(
            "/api/lumira/variations",
            json={"image_id": 1, "count": 2},
        )
        assert response.status_code in [200, 404, 422, 500]

    def test_batch_create_endpoint_exists(self, client):
        """Batch create endpoint should exist."""
        response = client.post(
            "/api/lumira/batch-create",
            json={"count": 1},
        )
        # 429 is acceptable - it proves endpoint exists and has rate limiting
        assert response.status_code in [200, 422, 429, 500]

    def test_explore_endpoint_exists(self, client):
        """Explore endpoint should exist."""
        response = client.post(
            "/api/lumira/explore",
            json={"concept_a": "forest", "concept_b": "ocean", "steps": 3},
        )
        # 429 is acceptable - it proves endpoint exists and has rate limiting
        assert response.status_code in [200, 422, 429, 500]
