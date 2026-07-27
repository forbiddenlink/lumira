"""Unit tests for web middleware."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_artist.web.middleware import (
    ErrorHandlingMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    add_cors_middleware,
    build_content_security_policy,
    is_websocket_origin_allowed,
    resolve_allowed_origins,
)


class TestSecurityHeadersMiddleware:
    """Tests for security header injection."""

    def test_adds_expected_security_headers(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/ok")

        assert response.status_code == 200
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
        assert "ws:" not in response.headers["Content-Security-Policy"]

    def test_build_content_security_policy_excludes_global_ws(self):
        policy = build_content_security_policy()
        assert "connect-src 'self'" in policy
        assert "ws:" not in policy

    def test_is_websocket_origin_allowed_same_host(self):
        assert is_websocket_origin_allowed(
            "http://localhost:8000",
            "localhost:8000",
            allowed_origins=["http://localhost:8000"],
        )

    def test_is_websocket_origin_allowed_requires_origin_in_production_mode(self):
        assert (
            is_websocket_origin_allowed(
                None,
                "localhost:8000",
                require_origin=True,
            )
            is False
        )

    def test_resolve_allowed_origins_env_override(self):
        with patch.dict(
            "os.environ",
            {"ALLOWED_ORIGINS": "https://lumira.example.com"},
        ):
            assert resolve_allowed_origins() == ["https://lumira.example.com"]


class TestErrorHandlingMiddleware:
    """Tests for global error handling middleware."""

    def test_value_error_returns_400(self):
        app = FastAPI()
        app.add_middleware(ErrorHandlingMiddleware)

        @app.get("/boom")
        def boom():
            raise ValueError("bad input")

        client = TestClient(app)
        response = client.get("/boom")

        assert response.status_code == 400
        assert response.json() == {"error": "Validation error", "detail": "bad input"}

    def test_file_not_found_returns_404(self):
        app = FastAPI()
        app.add_middleware(ErrorHandlingMiddleware)

        @app.get("/missing")
        def missing():
            raise FileNotFoundError("not here")

        client = TestClient(app)
        response = client.get("/missing")

        assert response.status_code == 404
        assert response.json() == {
            "error": "Resource not found",
            "detail": "not here",
        }

    def test_unhandled_exception_returns_500(self):
        app = FastAPI()
        app.add_middleware(ErrorHandlingMiddleware)

        @app.get("/error")
        def error():
            raise RuntimeError("unexpected")

        client = TestClient(app)
        response = client.get("/error")

        assert response.status_code == 500
        assert response.json() == {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
        }


class TestRequestLoggingMiddleware:
    """Tests for request logging middleware."""

    def test_logs_request_start_and_completion(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        with patch("ai_artist.web.middleware.logger.info") as mock_info:
            client = TestClient(app)
            response = client.get("/ok")

        assert response.status_code == 200
        assert mock_info.call_count >= 2
        event_names = [call.args[0] for call in mock_info.call_args_list]
        assert "request_started" in event_names
        assert "request_completed" in event_names

    def test_logs_request_failure(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/fail")
        def fail():
            raise RuntimeError("broken")

        with patch("ai_artist.web.middleware.logger.error") as mock_error:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/fail")

        assert response.status_code == 500
        assert mock_error.called
        assert mock_error.call_args.args[0] == "request_failed"


class TestCorsMiddleware:
    """Tests for CORS setup helper."""

    def test_add_cors_middleware_uses_explicit_origins(self):
        app = FastAPI()
        add_cors_middleware(app, cors_origins=["https://example.com"])

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.options(
            "/ok",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://example.com"

    def test_add_cors_middleware_uses_environment_origins(self):
        app = FastAPI()

        with patch.dict(
            "os.environ",
            {"ALLOWED_ORIGINS": "https://app.example.com,https://admin.example.com"},
        ):
            add_cors_middleware(app)

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.options(
            "/ok",
            headers={
                "Origin": "https://admin.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"]
            == "https://admin.example.com"
        )

    def test_add_cors_middleware_falls_back_to_localhost_defaults(self):
        app = FastAPI()

        with patch.dict("os.environ", {}, clear=True):
            add_cors_middleware(app)

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.options(
            "/ok",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )
