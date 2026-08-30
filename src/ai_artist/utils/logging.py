"""Structured logging configuration using structlog."""

import contextvars
import logging
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, cast

import structlog

# Context variable for request ID tracking
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


def get_request_id() -> str:
    """Get the current request ID or generate a new one."""
    request_id = request_id_var.get()
    if not request_id:
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)
    return request_id


def set_request_id(request_id: str | None = None) -> str:
    """Set a specific request ID or generate a new one."""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)
    return request_id


def add_request_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Add request ID to log entries."""
    event_dict["request_id"] = get_request_id()
    return event_dict


def configure_logging(
    log_level: str = "INFO",
    log_file: Path | None = None,
    json_logs: bool = False,
    enable_rotation: bool = True,
) -> None:
    """Configure structured logging with request IDs and performance tracking.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logs (enables file logging)
        json_logs: Use JSON format (for production)
        enable_rotation: Enable log rotation (max 10MB, 5 backups)
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_request_id,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add appropriate renderer based on mode
    if json_logs or log_file:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=cast(Any, processors),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Add file handler with rotation if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        handler: logging.Handler
        if enable_rotation:
            # Rotating file handler: max 10MB, keep 5 backups
            handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
            )
        else:
            handler = logging.FileHandler(log_file)

        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.root.addHandler(handler)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]


class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(self, logger: structlog.BoundLogger, operation: str) -> None:
        self.logger = logger
        self.operation = operation
        self.start_time: float | None = None

    def __enter__(self) -> "PerformanceTimer":
        self.start_time = time.time()
        self.logger.debug("operation_started", operation=self.operation)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # __enter__ always sets this; 0.0 keeps the log line honest if some
        # caller reaches __exit__ without it rather than raising here.
        duration = time.time() - (self.start_time or time.time())
        if exc_type is None:
            self.logger.info(
                "operation_completed",
                operation=self.operation,
                duration_seconds=round(duration, 2),
            )
        else:
            self.logger.error(
                "operation_failed",
                operation=self.operation,
                duration_seconds=round(duration, 2),
                error=str(exc_val),
            )
