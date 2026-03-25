"""
Exception handlers for FastAPI application.

Provides centralized exception handling for common error types.
"""

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ..utils.logging import get_logger

logger = get_logger(__name__)

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


def _render_error_html(status_code: int, title: str, message: str) -> HTMLResponse:
    """Render a styled HTML error page."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Lumira</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, sans-serif; background: #0a0e17; color: #e6edf3; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }}
.error-box {{ text-align: center; max-width: 500px; }}
.code {{ font-size: 96px; font-weight: 800; background: linear-gradient(135deg, #58a6ff, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; line-height: 1; }}
h1 {{ font-size: 24px; margin: 16px 0 12px; font-weight: 700; }}
p {{ color: #8b949e; font-size: 16px; line-height: 1.6; margin-bottom: 32px; }}
a {{ display: inline-block; padding: 12px 32px; background: linear-gradient(135deg, #58a6ff, #a855f7); color: white; text-decoration: none; border-radius: 12px; font-weight: 700; transition: transform 0.2s; }}
a:hover {{ transform: translateY(-2px); }}
.links {{ margin-top: 16px; }}
.links a {{ background: transparent; border: 1px solid #21262d; color: #8b949e; margin: 0 8px; padding: 8px 20px; font-size: 14px; }}
</style>
</head>
<body>
<div class="error-box">
<div class="code">{status_code}</div>
<h1>{title}</h1>
<p>{message}</p>
<a href="/">Back to Gallery</a>
<div class="links">
<a href="/lumira">Creative Studio</a>
</div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=status_code)


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
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
        return _render_error_html(exc.status_code, title, default_msg)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path),
        },
    )


async def validation_exception_handler(
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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "detail": safe_errors,
            "path": str(request.url.path),
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> Response:
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
            500,
            "Something Went Wrong",
            "We hit an unexpected error. Please try again in a moment.",
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "path": str(request.url.path),
        },
    )
