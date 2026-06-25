"""Tests for generation task registry and cancel endpoint."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from ai_artist.web.app import app
from ai_artist.web.generation_registry import cancel, is_active, register


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_cancel_unknown_session_returns_404(client):
    response = client.post("/api/cancel/does-not-exist")
    assert response.status_code == 404


def test_privacy_page_loads(client):
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "Privacy Policy" in response.text
    assert "AI-generated content" in response.text


@pytest.mark.asyncio
async def test_generation_registry_cancel():
    async def slow_job():
        await asyncio.sleep(30)

    task = asyncio.create_task(slow_job())
    register("test-session", task)
    assert is_active("test-session")
    assert cancel("test-session") is True

    with pytest.raises(asyncio.CancelledError):
        await task

    assert not is_active("test-session")
