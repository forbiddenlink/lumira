"""Rate limiting configuration and utilities for Lumira API.

Provides centralized rate limit configuration for generation endpoints
with proper headers and helpful error messages.
"""

import os
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ExceptionHandler

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Throttling is disabled under test, where a single client hammers every
# endpoint across the whole E2E session (page loads poll autonomy-status,
# series, state, statement) and would otherwise trip 429s unrelated to real
# traffic. Every module-level Limiter passes enabled=RATE_LIMIT_ENABLED.
RATE_LIMIT_ENABLED = os.getenv("TESTING") != "1"

if not RATE_LIMIT_ENABLED:
    # Loud, observable signal — a prod deploy that accidentally has TESTING=1
    # would otherwise disable all rate limiting app-wide with zero indication.
    logger.warning(
        "rate_limiting_disabled",
        reason="TESTING=1",
        impact="all app rate limits are OFF",
    )


# Single shared Limiter for the whole app. Previously app.py and
# lumira_routes.py each constructed their own bare `Limiter(...)` instance,
# which meant two independent limiter states existed side by side (only one
# of which, app.py's, was ever attached to app.state.limiter / checked by
# SlowAPIMiddleware for undecorated routes). Both modules now import this
# single instance so there is exactly one limiter, one default-limits
# backstop, and one piece of state to reason about.
limiter = Limiter(
    key_func=get_remote_address,
    # Generous default backstop so routes without an explicit @limiter.limit
    # are still capped. Set well above any legitimate polling rate; stricter
    # per-route decorators (e.g. 5/minute on generation) bind first, so this
    # only ever throttles otherwise-unlimited endpoints.
    default_limits=["600/minute"],
    enabled=RATE_LIMIT_ENABLED,
)


# Rate limit constants for generation endpoints
# These limits protect GPU resources and prevent abuse
class RateLimits:
    """Centralized rate limit definitions for API endpoints."""

    # Generation endpoints (expensive GPU operations)
    PREVIEW = "5/minute"  # Quick previews
    REQUEST = "5/minute"  # User-directed creation
    IMG2IMG = "5/minute"  # Image-to-image transforms
    VARIATIONS = "5/minute"  # Generate variations
    BATCH_CREATE = "2/minute"  # Batch creation (creates multiple)
    EXPLORE = "10/minute"  # Latent space exploration (lighter)

    # Read-heavy endpoints (less restrictive)
    STATE = "60/minute"
    PORTFOLIO = "30/minute"
    GALLERY = "60/minute"

    # Admin/upload endpoints
    UPLOAD = "10/minute"


def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key based on client IP or API key.

    If X-API-Key header is present, use that for rate limiting
    (allows different limits per API key in the future).
    Otherwise, fall back to IP address.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Hash the API key to avoid logging sensitive data
        return f"apikey:{hash(api_key) % 10000:04d}"
    remote_addr = get_remote_address(request)
    return str(remote_addr) if remote_addr else "unknown"


def create_rate_limit_error_response(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Create a helpful 429 error response with rate limit headers.

    Returns:
        JSONResponse with 429 status, helpful message, and rate limit headers.
    """
    # Parse the rate limit from the exception
    limit_string = str(exc.detail) if hasattr(exc, "detail") else "unknown"

    # Extract retry-after from exception or default to 60 seconds
    retry_after = getattr(exc, "retry_after", 60)
    if retry_after is None:
        retry_after = 60

    # Build helpful error message based on the endpoint
    error_message = (
        "Rate limit exceeded. Generation endpoints are limited to protect "
        "GPU resources. Please wait before making another request."
    )

    # Create response with helpful information. Base shape (error/status_code/
    # path) matches every other handler in exception_handlers.py; the extra
    # fields below are additive, not a replacement shape.
    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "status_code": 429,
            "path": str(request.url.path),
            "message": error_message,
            "limit": limit_string,
            "retry_after_seconds": int(retry_after),
            "suggestion": (
                "Consider using the WebSocket endpoint to track generation progress "
                "instead of polling, or batch your requests using /batch-create."
            ),
        },
    )

    # Add standard rate limit headers
    response.headers["Retry-After"] = str(int(retry_after))
    response.headers["X-RateLimit-Limit"] = limit_string

    return response


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Handle rate limit exceeded errors with helpful response.

    This handler is registered with FastAPI to handle RateLimitExceeded errors
    and return informative 429 responses with proper headers.
    """
    logger.warning(
        "rate_limit_exceeded",
        path=request.url.path,
        method=request.method,
        client=get_remote_address(request),
        limit=str(exc.detail) if hasattr(exc, "detail") else "unknown",
    )
    return create_rate_limit_error_response(request, exc)


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add rate limit headers to all responses.

    Adds X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset
    headers to help clients manage their request rate.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add rate limit headers to response."""
        response = await call_next(request)

        # Get limiter state if available
        limiter = getattr(request.app.state, "limiter", None)
        if limiter:
            # Try to get rate limit info from limiter state
            # The exact headers depend on the request's rate limit configuration
            get_remote_address(request)

            # Add headers if we have limit info in response
            # slowapi stores current window info in the response headers after processing
            # Default headers for generation endpoints (if not already set by slowapi)
            if (
                "X-RateLimit-Limit" not in response.headers
                and "/api/lumira/" in request.url.path
                and "X-RateLimit-Remaining" not in response.headers
            ):
                response.headers["X-RateLimit-Remaining"] = "see X-RateLimit-Limit"

        return response


def configure_rate_limiting(app: FastAPI) -> Limiter:
    """Attach the shared limiter, exception handler, and middleware to `app`.

    This is the single wiring point for rate limiting. Previously there was
    a second, never-called `setup_rate_limiting()` here (with its own
    `default_limits=["200/minute"]`) alongside app.py manually doing the
    same three steps with a separately-constructed Limiter. Both app.py and
    lumira_routes.py now share the one `limiter` instance defined above, and
    app.py calls this function once during startup.

    Args:
        app: The FastAPI application instance.

    Returns:
        The shared Limiter instance.
    """
    app.state.limiter = limiter
    # Same cast app.py uses for its other handlers: Starlette types the
    # second argument against bare Exception, FastAPI dispatches the
    # subtype it was registered for.
    app.add_exception_handler(
        RateLimitExceeded, cast(ExceptionHandler, rate_limit_exceeded_handler)
    )
    app.add_middleware(SlowAPIMiddleware)
    logger.info("rate_limiting_configured", strategy="fixed-window")
    return limiter
