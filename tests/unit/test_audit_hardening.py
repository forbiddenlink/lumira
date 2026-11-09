"""Regression tests for the owner-only write routes and input bounds.

Each route below mutates shared state (deletes, cancels, evolves, spends on
the LLM) and must refuse an anonymous caller once an API key is configured.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_artist.utils.config import WebConfig
from ai_artist.web.app import app
from ai_artist.web.dependencies import set_web_config

KEY = "test-secret-key"

OWNER_ROUTES = [
    ("delete", "/api/gallery/image/abc123"),
    ("post", "/api/gallery/collections"),
    ("post", "/api/lumira/evolve"),
    ("delete", "/api/lumira/job/some-job"),
    ("delete", "/api/lumira/reference-image/some-ref"),
    ("post", "/api/cancel/some-session"),
    ("get", "/api/lumira/artist-statement?regenerate=true"),
]


@pytest.fixture
def client():
    limiter = getattr(app.state, "limiter", None)
    if limiter is not None and hasattr(limiter, "_storage"):
        limiter._storage.storage.clear()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_enabled():
    set_web_config(WebConfig(api_keys=[SecretStr(KEY)]))
    yield
    set_web_config(WebConfig())


@pytest.mark.parametrize(("method", "path"), OWNER_ROUTES)
def test_owner_route_refuses_anonymous(client, auth_enabled, method, path):
    kwargs = {"json": {"name": "x"}} if path.endswith("/collections") else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401, (path, response.status_code)


@pytest.mark.parametrize(("method", "path"), OWNER_ROUTES)
def test_owner_route_refuses_wrong_key(client, auth_enabled, method, path):
    kwargs = {"json": {"name": "x"}} if path.endswith("/collections") else {}
    response = getattr(client, method)(path, headers={"X-API-Key": "wrong"}, **kwargs)
    assert response.status_code == 403, (path, response.status_code)


@pytest.mark.parametrize(("method", "path"), OWNER_ROUTES)
def test_owner_route_accepts_valid_key(client, auth_enabled, method, path):
    kwargs = {"json": {"name": "x"}} if path.endswith("/collections") else {}
    response = getattr(client, method)(path, headers={"X-API-Key": KEY}, **kwargs)
    # The route may 404 on a fake id, but auth itself must pass.
    assert response.status_code not in (401, 403, 503), (path, response.status_code)


def test_cached_artist_statement_stays_public(client, auth_enabled):
    response = client.get("/api/lumira/artist-statement")
    assert response.status_code != 401


def test_matrix_rejects_oversized_combinations(client):
    response = client.post(
        "/api/prompt/matrix",
        json={"prompt": "a {red|blue} bird", "max_combinations": 10_000},
    )
    assert response.status_code == 422


def test_matrix_rejects_oversized_prompt(client):
    response = client.post(
        "/api/prompt/matrix",
        json={"prompt": "a" * 2001},
    )
    assert response.status_code == 422


class TestDevModeNeverOnRailway:
    def test_debug_implies_dev_mode_locally(self, monkeypatch):
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
        monkeypatch.setenv("DEBUG", "true")
        assert WebConfig.from_env().dev_mode is True

    @pytest.mark.parametrize("var", ["RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME"])
    def test_dev_mode_refused_on_railway(self, monkeypatch, var):
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
        monkeypatch.setenv(var, "production")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("LUMIRA_DEV_MODE", "1")
        assert WebConfig.from_env().dev_mode is False
