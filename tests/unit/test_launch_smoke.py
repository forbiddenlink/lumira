"""Launch-readiness smoke tests for core HTTP and WebSocket surfaces."""

import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_artist.db.models import Base, GeneratedImage
from ai_artist.db.session import create_db_engine, create_session_factory, set_session_factory
from ai_artist.gallery.manager import GalleryManager
from ai_artist.web.app import app
from ai_artist.web.dependencies import set_gallery_manager


@pytest.fixture
def smoke_client(tmp_path):
    """App client with isolated gallery and database."""
    gallery_path = tmp_path / "gallery"
    gallery_path.mkdir()
    image_dir = gallery_path / "2026" / "06"
    image_dir.mkdir(parents=True)
    img_path = image_dir / "smoke.png"
    Image.new("RGB", (32, 32), color="orange").save(img_path)
    img_path.with_suffix(".json").write_text(
        json.dumps({"prompt": "smoke test artwork", "created_at": "2026-06-25T12:00:00"}),
        encoding="utf-8",
    )

    db_path = tmp_path / "smoke.db"
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    set_session_factory(create_session_factory(db_path))
    set_gallery_manager(GalleryManager(gallery_path), str(gallery_path))

    yield TestClient(app), str(img_path.relative_to(gallery_path))

    set_session_factory(None)


class TestLaunchSmoke:
    """High-level checks that key user journeys respond correctly."""

    @pytest.mark.parametrize(
        "path,needle",
        [
            ("/", "gallery"),
            ("/lumira", "gallery-grid"),
            ("/privacy", "Privacy"),
            ("/monitoring", "WebSocket"),
        ],
    )
    def test_core_pages_load(self, smoke_client, path, needle):
        client, _ = smoke_client
        response = client.get(path)
        assert response.status_code == 200
        assert needle in response.text

    def test_health_and_auth_mode(self, smoke_client):
        client, _ = smoke_client
        assert client.get("/health").status_code == 200
        data = client.get("/api/auth-mode").json()
        assert "auth_required" in data

    def test_images_list_and_security_headers(self, smoke_client):
        client, rel_path = smoke_client
        response = client.get("/api/images?limit=5")
        assert response.status_code == 200
        assert response.headers.get("Cache-Control", "").startswith("no-cache")
        assert "connect-src 'self'" in response.headers.get(
            "Content-Security-Policy", ""
        )

        images = response.json()
        if images:
            assert images[0]["path"]

        file_resp = client.get(f"/api/images/file/{rel_path}")
        assert file_resp.status_code == 200

    def test_publish_share_and_websocket(self, smoke_client):
        client, rel_path = smoke_client
        publish = client.post("/api/gallery/publish", json={"path": rel_path})
        assert publish.status_code == 200
        share_id = publish.json()["share_id"]

        share_page = client.get(f"/share/{share_id}")
        assert share_page.status_code == 200
        assert share_id in share_page.text

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"

    def test_cancel_unknown_session_returns_404(self, smoke_client):
        client, _ = smoke_client
        response = client.post("/api/cancel/not-a-real-session")
        assert response.status_code == 404
