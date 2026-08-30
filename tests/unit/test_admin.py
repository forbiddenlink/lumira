"""Tests for the admin console: auth split, payload contract, degradation.

The dashboard template reads these payloads by key name. Before this suite
existed, ``/admin/stats`` had never returned the ``moods`` key the template
asked for, and nothing caught it -- the console just rendered "Error loading
stats" forever. The contract tests below fail if a field the template consumes
stops being served.
"""

import builtins
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_artist.db.models import Base, GeneratedImage
from ai_artist.db.session import (
    create_db_engine,
    create_session_factory,
    set_session_factory,
)
from ai_artist.utils.config import WebConfig
from ai_artist.web.app import app
from ai_artist.web.dependencies import set_web_config


@pytest.fixture(autouse=True)
def admin_db(tmp_path):
    """Isolated database holding one row, for every test in this module.

    /admin/stats reads the generated_images table. Without a schema these
    tests only ever exercised the 500 path, which is what they did on CI
    while passing locally against a developer database.
    """
    db_path = tmp_path / "admin.db"
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    factory = create_session_factory(db_path)
    set_session_factory(factory)

    session = factory()
    try:
        session.add(
            GeneratedImage(
                filename="2026/08/30/curated_piece.png",
                prompt="a quiet twilight meadow",
                model_id="test-model",
                final_score=0.82,
                status="curated",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    finally:
        session.close()

    yield
    set_session_factory(None)


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


@pytest.fixture
def dev_mode():
    set_web_config(WebConfig(dev_mode=True))
    yield
    set_web_config(WebConfig())


class TestAdminAuthSplit:
    """The HTML shell is reachable from a browser; the data behind it is not."""

    def test_shell_reachable_without_api_key(self, client, auth_enabled):
        # A top-level navigation cannot carry an X-API-Key header, so gating
        # the shell made the console unreachable in any keyed deployment.
        response = client.get("/admin/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_shell_renders_no_data(self, client, auth_enabled):
        # Serving the shell unauthenticated is only safe while it stays empty:
        # it must take no DB dependency and ship only placeholder states.
        import inspect

        from ai_artist.web.admin import admin_dashboard

        params = inspect.signature(admin_dashboard).parameters
        assert list(params) == ["request"]

        body = client.get("/admin/").text
        assert "Admin Dashboard" in body
        assert body.count("Loading") >= 4

    @pytest.mark.parametrize("path", ["/admin/stats", "/admin/performance"])
    def test_data_routes_require_key(self, client, auth_enabled, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ["/admin/stats", "/admin/performance"])
    def test_data_routes_accept_valid_key(self, client, auth_enabled, path):
        response = client.get(path, headers={"X-API-Key": "test-secret-key"})
        assert response.status_code not in (401, 403)

    def test_cache_clear_requires_key(self, client, auth_enabled):
        assert client.post("/admin/cache/clear").status_code == 401


class TestStatsContract:
    """Field names the dashboard template reads from /admin/stats."""

    def test_exposes_totals_and_status_breakdown(self, client, dev_mode):
        payload = client.get("/admin/stats").json()
        assert payload["total_artworks"] == 1
        assert payload["statuses"] == {"curated": 1}

    def test_recent_items_carry_the_fields_the_template_renders(self, client, dev_mode):
        recent = client.get("/admin/stats").json()["recent"]
        assert len(recent) == 1
        for item in recent:
            assert "prompt" in item
            assert "status" in item
            assert "final_score" in item


class TestSystemInfo:
    def test_reports_availability_and_metrics(self, client, dev_mode):
        payload = client.get("/admin/system").json()
        assert payload["available"] is True
        assert 0.0 <= payload["cpu_percent"] <= 100.0
        assert "percent" in payload["memory"]
        assert "available" in payload["gpu"]

    def test_degrades_when_psutil_is_missing(self, client, dev_mode, monkeypatch):
        # The gallery-only deployment installs no ML stack, which is how psutil
        # used to arrive. Absence must degrade, not 500.
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        response = client.get("/admin/system")
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is False
        assert "psutil" in payload["detail"]
