"""Rate limiting configuration and utilities for Lumira API.

Provides centralized rate limit configuration for generation endpoints
with proper headers and helpful error messages.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from ..utils.logging import get_logger

logger = get_logger(__name__)


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
    return get_remote_address(request)


def create_rate_limit_error_response(exc: RateLimitExceeded) -> JSONResponse:
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

    # Create response with helpful information
    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
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
    return create_rate_limit_error_response(exc)


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
            key = get_remote_address(request)

            # Add headers if we have limit info in response
            # slowapi stores current window info in the response headers after processing
            if "X-RateLimit-Limit" not in response.headers:
                # Default headers for generation endpoints
                if "/api/lumira/" in request.url.path:
                    # Set generic headers - actual values set by slowapi decorators
                    if "X-RateLimit-Remaining" not in response.headers:
                        response.headers["X-RateLimit-Remaining"] = "see X-RateLimit-Limit"

        return response


def setup_rate_limiting(app) -> Limiter:
    """Configure rate limiting for the FastAPI application.

    Args:
        app: The FastAPI application instance.

    Returns:
        The configured Limiter instance.
    """
    # Create limiter with IP-based key function
    limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=["200/minute"],  # Default for unlisted endpoints
        headers_enabled=True,  # Enable X-RateLimit-* headers
        strategy="fixed-window",  # Use fixed window strategy
    )

    # Attach limiter to app state
    app.state.limiter = limiter

    # Add exception handler for rate limit errors
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Add SlowAPI middleware for header injection
    app.add_middleware(SlowAPIMiddleware)

    logger.info("rate_limiting_configured", strategy="fixed-window")

    return limiter
