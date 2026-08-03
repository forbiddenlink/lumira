"""FastAPI middleware for error handling, logging, and CORS."""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from ..utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]


def resolve_allowed_origins(cors_origins: list[str] | None = None) -> list[str]:
    """Resolve allowed browser origins for CORS and WebSocket checks."""
    import os

    if cors_origins:
        return cors_origins

    try:
        from .dependencies import get_web_config

        config_origins = get_web_config().cors_origins
        if config_origins:
            return config_origins
    except Exception:
        pass

    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
    if allowed_origins_env:
        return [
            origin.strip()
            for origin in allowed_origins_env.split(",")
            if origin.strip()
        ]

    return DEFAULT_DEV_ORIGINS.copy()


def build_content_security_policy() -> str:
    """Build Content-Security-Policy header value."""
    csp_directives = [
        "default-src 'self'",
        # lucide is now self-hosted (static/js/lucide.min.js), so unpkg.com is
        # gone from script-src. 'unsafe-inline' stays: the inline studio
        # scripts in lumira.html still need it — a full nonce-based refactor
        # of those inline scripts is out of scope here.
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "frame-src 'none'",
        "manifest-src 'self'",
    ]
    return "; ".join(csp_directives)


def is_websocket_origin_allowed(
    origin: str | None,
    host: str | None,
    *,
    allowed_origins: list[str] | None = None,
    require_origin: bool = False,
) -> bool:
    """Validate WebSocket Origin header against allowed origins."""
    if origin is None:
        return not require_origin

    origins = resolve_allowed_origins(allowed_origins)
    if origin in origins:
        return True

    if host:
        for scheme in ("https", "http"):
            if origin == f"{scheme}://{host}":
                return True

    return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = build_content_security_policy()

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request/response logging middleware."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Log all requests and responses."""
        start_time = time.time()

        # Log request
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Log response
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            return response
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=duration_ms,
            )
            raise


def add_cors_middleware(app, cors_origins: list[str] | None = None):
    """Add CORS middleware with secure defaults.

    Args:
        app: The FastAPI application
        cors_origins: List of allowed origins from config. If empty/None,
                     uses secure localhost defaults for development.
                     Set to ["*"] to allow all origins.

    By default, only allows localhost origins for development.
    Set ALLOWED_ORIGINS environment variable or use config for production.
    Example: ALLOWED_ORIGINS=https://example.com,https://app.example.com
    """
    allowed_origins = resolve_allowed_origins(cors_origins)

    # Guard the credentials+wildcard footgun: with allow_credentials=True,
    # Starlette reflects the request Origin when "*" is present, granting any
    # site credentialed cross-origin access. Refuse to start in that config.
    if "*" in allowed_origins:
        raise ValueError(
            "CORS misconfiguration: allow_origins cannot be '*' while "
            "allow_credentials=True. Set an explicit ALLOWED_ORIGINS allowlist."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
