"""Tests for generation endpoint API key protection."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_artist.utils.config import WebConfig
from ai_artist.web.app import app
from ai_artist.web.dependencies import set_web_config


@pytest.fixture
def client():
    if (
        hasattr(app.state, "limiter")
        and app.state.limiter
        and hasattr(app.state.limiter, "_storage")
    ):
        app.state.limiter._storage.storage.clear()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_enabled():
    set_web_config(WebConfig(api_keys=[SecretStr("test-secret-key")]))
    yield
    set_web_config(WebConfig())


def test_preview_requires_api_key_when_configured(client, auth_enabled):
    response = client.post(
        "/api/lumira/preview",
        json={"prompt": "a quiet forest"},
    )
    assert response.status_code == 401


def test_preview_allows_valid_api_key(client, auth_enabled):
    response = client.post(
        "/api/lumira/preview",
        json={"prompt": "a quiet forest"},
        headers={"X-API-Key": "test-secret-key"},
    )
    # May fail for missing model, but auth must pass
    assert response.status_code != 401
    assert response.status_code != 403


def test_preview_open_in_dev_mode(client):
    set_web_config(WebConfig())
    response = client.post(
        "/api/lumira/preview",
        json={"prompt": "a quiet forest"},
    )
    assert response.status_code != 401


def test_health_details_returns_runtime_fields(client):
    response = client.get("/health/details")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "websocket_connections" in data
    assert "generation_queue" in data
    assert "gallery_initialized" in data


def test_monitoring_page_has_a11y_live_region(client):
    response = client.get("/monitoring")
    assert response.status_code == 200
    assert 'aria-live="polite"' in response.text
    assert 'role="status"' in response.text
