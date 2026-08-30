"""Unit tests for web middleware."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_artist.web.middleware import (
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


class TestContentSecurityPolicyNonce:
    """script-src is nonce-based, and nothing reintroduces 'unsafe-inline'.

    'unsafe-inline' existed because the templates carried 98 inline on*=
    handler attributes, which a nonce cannot cover. Those are delegated
    listeners now, so the directive can name a nonce instead -- and with
    'unsafe-inline' gone, a browser that understands nonces will refuse any
    script the server did not stamp.
    """

    def test_script_src_names_a_nonce_and_not_unsafe_inline(self):
        from fastapi.testclient import TestClient

        from ai_artist.web.app import app

        response = TestClient(app).get("/privacy")
        csp = response.headers["Content-Security-Policy"]
        script_src = next(d for d in csp.split(";") if "script-src" in d)

        assert "'unsafe-inline'" not in script_src
        assert "'nonce-" in script_src

    def test_nonce_is_fresh_for_every_response(self):
        import re

        from fastapi.testclient import TestClient

        from ai_artist.web.app import app

        client = TestClient(app)

        def nonce_of(path: str) -> str:
            csp = client.get(path).headers["Content-Security-Policy"]
            match = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
            assert match, csp
            return match.group(1)

        first, second = nonce_of("/privacy"), nonce_of("/privacy")
        assert first != second
        # token_urlsafe(16) -> 22 characters.
        assert len(first) >= 20

    def test_rendered_pages_carry_the_nonce_from_their_own_header(self):
        import re

        from fastapi.testclient import TestClient

        from ai_artist.web.app import app

        response = TestClient(app).get("/lumira")
        nonce = re.search(
            r"'nonce-([A-Za-z0-9_-]+)'", response.headers["Content-Security-Policy"]
        ).group(1)

        assert f'nonce="{nonce}"' in response.text
        # An unrendered {{ csp_nonce }} or an empty one would be blocked.
        assert 'nonce=""' not in response.text
        assert "{{ csp_nonce }}" not in response.text

    def test_no_template_reintroduces_an_inline_handler(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        pattern = re.compile(
            r"\son(?:click|input|change|submit|mouseover|mouseout|keydown|keyup"
            r"|focus|blur|load|error)\s*=",
            re.IGNORECASE,
        )
        offenders = []
        for html in list(
            (root / "src" / "ai_artist" / "web" / "templates").rglob("*.html")
        ) + [root / "static" / "offline.html"]:
            for lineno, line in enumerate(
                html.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    offenders.append(f"{html.name}:{lineno}")

        assert not offenders, (
            "inline handlers cannot be covered by a CSP nonce; use a "
            "data-action attribute and the page's delegated listener:\n  "
            + "\n  ".join(offenders)
        )

    def test_every_inline_script_block_is_nonced(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        offenders = []
        for html in (root / "src" / "ai_artist" / "web" / "templates").rglob("*.html"):
            if "<script>" in html.read_text(encoding="utf-8"):
                offenders.append(html.name)

        assert not offenders, f"inline <script> without a nonce: {offenders}"
