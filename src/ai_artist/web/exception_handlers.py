"""
Exception handlers for FastAPI application.

Provides centralized exception handling for common error types.
"""

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..utils.logging import get_logger

logger = get_logger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTPException errors with structured logging.

    Args:
        request: The incoming request
        exc: The HTTPException that was raised

    Returns:
        JSONResponse with error details
    """
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url.path),
    )

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


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions with logging and safe error response.

    Args:
        request: The incoming request
        exc: The exception that was raised

    Returns:
        JSONResponse with generic error message
    """
    logger.error(
        "unhandled_exception",
        path=str(request.url.path),
        error=str(exc),
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "path": str(request.url.path),
        },
    )
