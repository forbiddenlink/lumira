"""FastAPI middleware for error handling, logging, and CORS."""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from ..utils.logging import get_logger

logger = get_logger(__name__)


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
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Global error handling middleware."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Handle all exceptions and return appropriate responses."""
        try:
            response = await call_next(request)
            return response
        except ValueError as e:
            logger.warning("validation_error", error=str(e), path=request.url.path)
            return JSONResponse(
                status_code=400,
                content={"error": "Validation error", "detail": str(e)},
            )
        except FileNotFoundError as e:
            logger.warning("not_found", error=str(e), path=request.url.path)
            return JSONResponse(
                status_code=404,
                content={"error": "Resource not found", "detail": str(e)},
            )
        except Exception as e:
            logger.error(
                "unhandled_exception",
                error=str(e),
                error_type=type(e).__name__,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred",
                },
            )


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
    import os

    # Secure default: only localhost for development
    default_origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    # Priority: config -> environment variable -> defaults
    if cors_origins:
        allowed_origins = cors_origins
    else:
        # Allow override via environment variable for production
        allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
        if allowed_origins_env:
            allowed_origins = [
                origin.strip() for origin in allowed_origins_env.split(",")
            ]
        else:
            allowed_origins = default_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
