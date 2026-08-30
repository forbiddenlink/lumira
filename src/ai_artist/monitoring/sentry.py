"""Sentry error tracking integration.

Provides automatic error tracking, performance monitoring, and alerting.
Only activates if SENTRY_DSN is configured.
"""

from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

_sentry_initialized = False


def init_sentry(
    dsn: str | None = None,
    environment: str = "development",
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
) -> bool:
    """Initialize Sentry error tracking.

    Args:
        dsn: Sentry DSN (Data Source Name) - required for initialization
        environment: Environment name (development, staging, production)
        traces_sample_rate: Percentage of transactions to trace (0.0-1.0)
        profiles_sample_rate: Percentage of transactions to profile (0.0-1.0)

    Returns:
        True if Sentry was initialized successfully, False otherwise
    """
    global _sentry_initialized

    if _sentry_initialized:
        logger.debug("sentry_already_initialized")
        return True

    if not dsn:
        logger.debug("sentry_disabled", reason="no_dsn_configured")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            # Integrations
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                AsyncioIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=None,  # Capture all log levels
                    event_level="error",  # Only send errors and above as events
                ),
            ],
            # Additional options
            attach_stacktrace=True,
            send_default_pii=False,  # Don't send personally identifiable information
            max_breadcrumbs=50,
            before_send=_filter_sensitive_data,
        )

        _sentry_initialized = True
        logger.info(
            "sentry_initialized",
            environment=environment,
            traces_sample_rate=traces_sample_rate,
        )
        return True

    except ImportError:
        logger.warning(
            "sentry_unavailable",
            hint="Install with: pip install 'sentry-sdk[fastapi]'",
        )
        return False
    except Exception as e:
        logger.error("sentry_init_failed", error=str(e))
        return False


def _filter_sensitive_data(event: dict, hint: dict) -> dict | None:
    """Filter sensitive data from Sentry events.

    Args:
        event: The event dictionary to send to Sentry
        hint: Additional context about the event

    Returns:
        Modified event dict or None to drop the event
    """
    # Remove API keys from request headers
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        sensitive_headers = ["authorization", "x-api-key", "api-key"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "[REDACTED]"

    # Remove sensitive query parameters
    if "request" in event and "query_string" in event["request"]:
        qs = event["request"]["query_string"]
        if isinstance(qs, str):
            sensitive_params = ["api_key", "token", "password"]
            for param in sensitive_params:
                if param in qs.lower():
                    event["request"]["query_string"] = "[REDACTED]"
                    break

    return event


def capture_exception(error: Exception, **extra_context: Any) -> None:
    """Capture an exception to Sentry with optional context.

    Args:
        error: The exception to capture
        **extra_context: Additional context to attach to the event
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            # Add extra context
            for key, value in extra_context.items():
                scope.set_context(key, value)

            sentry_sdk.capture_exception(error)
    except Exception as e:
        logger.error("sentry_capture_failed", error=str(e))


def capture_message(message: str, level: str = "info", **extra_context: Any) -> None:
    """Capture a message to Sentry with optional context.

    Args:
        message: The message to capture
        level: Severity level (debug, info, warning, error, fatal)
        **extra_context: Additional context to attach to the event
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            # Add extra context
            for key, value in extra_context.items():
                scope.set_context(key, value)

            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.error("sentry_capture_failed", error=str(e))


def set_user(user_id: str | None = None, **user_data: Any) -> None:
    """Set user context for Sentry events.

    Args:
        user_id: User identifier
        **user_data: Additional user data (email, username, etc.)
    """
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        user_info = {"id": user_id} if user_id else {}
        user_info.update(user_data)
        sentry_sdk.set_user(user_info)
    except Exception as e:
        logger.error("sentry_set_user_failed", error=str(e))


def is_initialized() -> bool:
    """Check if Sentry has been initialized.

    Returns:
        True if Sentry is initialized and ready to use
    """
    return _sentry_initialized
