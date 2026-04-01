"""Tests for HTML page routes."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_artist.db.models import Base, GeneratedImage
from ai_artist.db.session import create_db_engine, create_session_factory
from ai_artist.web.app import app


class TestPages:
    """Tests for server-rendered page responses."""

    def test_root_page_exposes_search_and_gallery_shell(self):
        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert 'id="search"' in response.text
        assert 'id="gallery"' in response.text

    def test_lumira_page_exposes_live_status_regions(self):
        client = TestClient(app)
        response = client.get("/lumira")

        assert response.status_code == 200
        assert 'id="mood-text"' in response.text
        assert 'id="loader-status"' in response.text
        assert 'aria-live="polite"' in response.text

    def test_share_page_missing_uses_error_template(self):
        client = TestClient(app)
        response = client.get("/share/does-not-exist", headers={"accept": "text/html"})

        assert response.status_code == 404
        assert "Artwork Not Found" in response.text
        assert "error-glyph" in response.text
        assert "Creative Studio" in response.text

    def test_share_page_renders_copy_link_and_absolute_meta(self, tmp_path):
        db_path = tmp_path / "share_page.db"
        engine = create_db_engine(db_path)
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(db_path)

        session = session_factory()
        try:
            image = GeneratedImage(
                filename="gallery/2026/test-share.png",
                prompt="A luminous test scene",
                model_id="test-model",
                is_public=True,
                share_id="share-page-test",
            )
            session.add(image)
            session.commit()
        finally:
            session.close()

        def override_get_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        with patch("ai_artist.db.session.get_db", override_get_db):
            client = TestClient(app)
            response = client.get("/share/share-page-test")

        assert response.status_code == 200
        assert 'id="copy-link-btn"' in response.text
        assert 'content="http://testserver/share/share-page-test"' in response.text
        assert (
            'content="http://testserver/api/images/file/gallery/2026/test-share.png"'
            in response.text
        )
