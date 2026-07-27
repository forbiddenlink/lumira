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


def test_preview_open_in_explicit_dev_mode(client):
    # dev_mode must be explicitly enabled for the unauthenticated bypass.
    set_web_config(WebConfig(dev_mode=True))
    response = client.post(
        "/api/lumira/preview",
        json={"prompt": "a quiet forest"},
    )
    assert response.status_code != 401
    assert response.status_code != 503


def test_preview_refused_when_unconfigured(client):
    # Fail-closed: no keys AND no explicit dev_mode -> refuse, don't fail open.
    set_web_config(WebConfig())
    response = client.post(
        "/api/lumira/preview",
        json={"prompt": "a quiet forest"},
    )
    assert response.status_code == 503


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


def test_image_download_sets_content_disposition(client, tmp_path):
    from ai_artist.web.dependencies import set_gallery_manager
    from ai_artist.gallery.manager import GalleryManager

    gallery_dir = tmp_path / "gallery"
    gallery_dir.mkdir()
    img = gallery_dir / "2026/06/25/test.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\x89PNG\r\n")

    set_gallery_manager(GalleryManager(gallery_dir), str(gallery_dir))

    response = client.get(
        "/api/images/file/2026/06/25/test.png",
        params={"download": True},
    )
    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "").lower()
