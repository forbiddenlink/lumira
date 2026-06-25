"""Track in-flight generation tasks for cancellation by session ID."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

_tasks: dict[str, asyncio.Task] = {}


def register(session_id: str, task: asyncio.Task) -> None:
    """Register a background generation task for a session."""
    _tasks[session_id] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if _tasks.get(session_id) is done_task:
            _tasks.pop(session_id, None)

    task.add_done_callback(_cleanup)
    logger.debug("generation_task_registered", session_id=session_id)


def cancel(session_id: str) -> bool:
    """Request cancellation of an active generation task."""
    task = _tasks.get(session_id)
    if task is None or task.done():
        return False
    task.cancel()
    logger.info("generation_task_cancel_requested", session_id=session_id)
    return True


def is_active(session_id: str) -> bool:
    """Return True if a generation task is still running for the session."""
    task = _tasks.get(session_id)
    return task is not None and not task.done()


async def notify_cancelled(session_id: str, ws_manager: Any) -> None:
    """Broadcast cancellation to WebSocket clients."""
    with contextlib.suppress(Exception):
        await ws_manager.send_generation_error(
            session_id=session_id,
            error="Generation cancelled",
        )
