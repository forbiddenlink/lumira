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
    ("delete", "/api/gallery/comments/999999"),
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
    # The route may 404 on a fake id, or 503 when a backing service such as
    # the Redis job queue is absent (CI), but auth itself must pass.
    assert response.status_code not in (401, 403), (path, response.status_code)
    if response.status_code == 503:
        assert "authentication" not in response.text.lower(), (path, response.text)


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


class TestClientIp:
    """Rate-limit identity must not be forgeable through X-Forwarded-For."""

    @staticmethod
    def _request(xff: str | None, peer: str = "10.0.0.9"):
        from starlette.requests import Request

        headers = [(b"x-forwarded-for", xff.encode())] if xff else []
        return Request({"type": "http", "headers": headers, "client": (peer, 1234)})

    def test_railway_uses_rightmost_hop(self, monkeypatch):
        from ai_artist.web.rate_limit import client_ip

        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
        req = self._request("6.6.6.6, 203.0.113.7")
        assert client_ip(req) == "203.0.113.7"

    def test_local_ignores_forwarded_header(self, monkeypatch):
        from ai_artist.web.rate_limit import client_ip

        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        assert client_ip(self._request("6.6.6.6")) == "10.0.0.9"

    def test_railway_without_header_falls_back_to_peer(self, monkeypatch):
        from ai_artist.web.rate_limit import client_ip

        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
        assert client_ip(self._request(None)) == "10.0.0.9"


def test_owner_can_delete_comment(client, auth_enabled, tmp_path, monkeypatch):
    from ai_artist.db import session as db_session_module
    from ai_artist.db.models import Base, GalleryComment, GeneratedImage
    from ai_artist.db.session import create_session_factory, set_session_factory

    monkeypatch.setattr(db_session_module, "_session_factory", None)
    factory = create_session_factory(tmp_path / "c.db")
    Base.metadata.create_all(factory.kw["bind"])
    set_session_factory(factory)
    with factory() as s:
        img = GeneratedImage(filename="g/x.png", prompt="p", model_id="m", tags=[])
        s.add(img)
        s.flush()
        s.add(GalleryComment(image_id=img.id, session_id="s", text="spam"))
        s.commit()
        cid = s.query(GalleryComment).one().id

    r = client.delete(f"/api/gallery/comments/{cid}", headers={"X-API-Key": KEY})
    assert r.status_code == 200, r.text
    with factory() as s:
        assert s.query(GalleryComment).count() == 0
    assert (
        client.delete(
            f"/api/gallery/comments/{cid}", headers={"X-API-Key": KEY}
        ).status_code
        == 404
    )
    monkeypatch.setattr(db_session_module, "_session_factory", None)
