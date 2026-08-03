"""
Exception handlers for FastAPI application.

Provides centralized exception handling for common error types.
"""

from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from ..utils.logging import get_logger

logger = get_logger(__name__)
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)

# Friendly messages for common status codes
_STATUS_MESSAGES = {
    404: (
        "Page Not Found",
        "The page you're looking for doesn't exist or has been moved.",
    ),
    500: (
        "Something Went Wrong",
        "We hit an unexpected error. Please try again in a moment.",
    ),
    403: ("Access Denied", "You don't have permission to view this page."),
    429: ("Too Many Requests", "You're making requests too quickly. Please slow down."),
}


def _wants_html(request: Request) -> bool:
    """Check if the client prefers HTML over JSON."""
    accept = request.headers.get("accept", "")
    # API paths always get JSON
    if str(request.url.path).startswith("/api/"):
        return False
    return "text/html" in accept


def _render_error_html(
    request: Request, status_code: int, title: str, message: str
) -> Response:
    """Render the shared error template for browser-facing failures."""
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": title,
            "status_code": status_code,
            "message": message,
        },
        status_code=status_code,
    )


def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """
    Handle HTTPException errors with structured logging.

    Returns HTML for browser requests, JSON for API requests.
    """
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url.path),
    )

    if _wants_html(request):
        title, default_msg = _STATUS_MESSAGES.get(
            exc.status_code, ("Error", str(exc.detail))
        )
        return _render_error_html(request, exc.status_code, title, default_msg)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path),
        },
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle request validation errors with detailed error messages.

    Args:
        request: The incoming request
        exc: The validation error that was raised

    Returns:
        JSONResponse with validation error details
    """
    safe_errors = []
    for err in exc.errors():
        safe_err = {}
        for k, v in err.items():
            if k == "ctx":
                safe_err[k] = {ck: str(cv) for ck, cv in v.items()}
            else:
                safe_err[k] = v
        safe_errors.append(safe_err)

    logger.warning(
        "validation_error",
        path=str(request.url.path),
        errors=safe_errors,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "Validation error",
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "detail": safe_errors,
            "path": str(request.url.path),
        },
    )


def general_exception_handler(request: Request, exc: Exception) -> Response:
    """
    Handle unexpected exceptions with logging and safe error response.

    Returns HTML for browser requests, JSON for API requests.
    """
    logger.error(
        "unhandled_exception",
        path=str(request.url.path),
        error=str(exc),
        exc_info=True,
    )

    if _wants_html(request):
        return _render_error_html(
            request,
            500,
            "Something Went Wrong",
            "We hit an unexpected error. Please try again in a moment.",
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "path": str(request.url.path),
        },
    )
