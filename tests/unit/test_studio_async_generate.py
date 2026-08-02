"""Studio generation must not block the asyncio event loop."""

from __future__ import annotations

import asyncio
import time

import pytest

from ai_artist.web.lumira_routes import _run_in_thread

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_run_in_thread_keeps_event_loop_responsive():
    started = asyncio.Event()
    finished = asyncio.Event()

    def slow() -> str:
        started.set()
        time.sleep(0.25)
        finished.set()
        return "done"

    task = asyncio.create_task(_run_in_thread(slow))
    await started.wait()

    # While the worker blocks, the loop can still schedule other work.
    t0 = time.perf_counter()
    await asyncio.sleep(0.05)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.15
    assert not finished.is_set()

    assert await task == "done"
    assert finished.is_set()
