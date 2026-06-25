"""Tests for gallery publish / share-link flow."""

import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_artist.db.models import Base, GeneratedImage
from ai_artist.db.session import (
    create_db_engine,
    create_session_factory,
    get_db,
    set_session_factory,
)
from ai_artist.gallery.manager import GalleryManager
from ai_artist.web.app import app
from ai_artist.web.dependencies import set_gallery_manager


@pytest.fixture
def publish_client(tmp_path):
    """Test client with isolated DB and gallery directory."""
    gallery_path = tmp_path / "gallery"
    gallery_path.mkdir()
    image_dir = gallery_path / "2026" / "06" / "25"
    image_dir.mkdir(parents=True)

    img_path = image_dir / "share_me.png"
    Image.new("RGB", (64, 64), color="purple").save(img_path)
    metadata = {
        "prompt": "A shareable artwork",
        "created_at": "2026-06-25T12:00:00",
        "metadata": {"model": "test-model", "mood": "serene"},
    }
    img_path.with_suffix(".json").write_text(json.dumps(metadata))

    db_path = tmp_path / "publish.db"
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    set_session_factory(create_session_factory(db_path))
    set_gallery_manager(GalleryManager(gallery_path), str(gallery_path))

    yield TestClient(app), gallery_path, str(img_path.relative_to(gallery_path))

    set_session_factory(None)


class TestGalleryPublishAPI:
    """Tests for POST /api/gallery/publish."""

    def test_publish_by_path_creates_db_row_and_share_url(self, publish_client):
        client, _gallery_path, rel_path = publish_client
        response = client.post(
            "/api/gallery/publish",
            json={"path": str(rel_path)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["share_id"]
        assert data["share_url"].endswith(f"/share/{data['share_id']}")

        db = next(get_db())
        try:
            row = db.query(GeneratedImage).filter_by(share_id=data["share_id"]).first()
            assert row is not None
            assert row.is_public is True
            assert row.prompt == "A shareable artwork"
        finally:
            db.close()

    def test_publish_by_image_id(self, publish_client):
        client, _gallery_path, rel_path = publish_client
        first = client.post("/api/gallery/publish", json={"path": str(rel_path)})
        image_id = None
        db = next(get_db())
        try:
            row = db.query(GeneratedImage).first()
            assert row is not None
            image_id = row.id
        finally:
            db.close()

        response = client.post(
            "/api/gallery/publish",
            json={"image_id": image_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["share_url"] == first.json()["share_url"]

    def test_publish_requires_identifier(self, publish_client):
        client, _, _ = publish_client
        response = client.post("/api/gallery/publish", json={})
        assert response.status_code == 422

    def test_publish_invalid_path_returns_404(self, publish_client):
        client, _, _ = publish_client
        response = client.post(
            "/api/gallery/publish",
            json={"path": "missing/image.png"},
        )
        assert response.status_code == 404

    def test_list_images_includes_share_fields(self, publish_client):
        client, _gallery_path, rel_path = publish_client
        publish = client.post("/api/gallery/publish", json={"path": str(rel_path)})
        share_id = publish.json()["share_id"]

        db = next(get_db())
        try:
            assert db.query(GeneratedImage).count() >= 1
        finally:
            db.close()

        response = client.get("/api/images?limit=10")
        assert response.status_code == 200
        images = response.json()
        assert images
        match = next((img for img in images if img.get("share_id") == share_id), None)
        assert match is not None
        assert match["is_public"] is True
        assert match["share_url"].endswith(f"/share/{share_id}")
