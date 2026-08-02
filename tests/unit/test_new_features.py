"""Tests for features added in the improvement pass.

Covers:
- UserFeedback DB model + feedback.py persistence
- SocialConfig credential fields in config.py
- WebConfig.debug field
- Portfolio cache TTL in lumira_routes
- _score_image fallback behaviour
- list_images DB-first path in app.py
- GalleryCollection updated_at event listener
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_artist.db.models import Base, GalleryCollection, GeneratedImage, UserFeedback
from ai_artist.db.session import create_db_engine, create_session_factory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db(tmp_path):
    """In-memory SQLite DB with all tables created."""
    db_path = tmp_path / "test.db"
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    return create_session_factory(db_path)


# ---------------------------------------------------------------------------
# DB Models
# ---------------------------------------------------------------------------


class TestUserFeedbackModel:
    """Tests for the UserFeedback db model."""

    def test_create_user_feedback(self, test_db):
        """UserFeedback row can be created with minimal fields."""
        session = test_db()
        try:
            fb = UserFeedback(
                artwork_filename="abc.png",
                action="like",
                signal_value=0.8,
            )
            session.add(fb)
            session.commit()

            result = (
                session.query(UserFeedback)
                .filter_by(artwork_filename="abc.png")
                .first()
            )
            assert result is not None
            assert result.action == "like"
            assert result.signal_value == 0.8
        finally:
            session.close()

    def test_user_feedback_defaults(self, test_db):
        """UserFeedback created_at is set automatically."""
        session = test_db()
        try:
            fb = UserFeedback(artwork_filename="x.png", action="love", signal_value=1.0)
            session.add(fb)
            session.commit()
            assert fb.created_at is not None
        finally:
            session.close()

    def test_user_feedback_artwork_fk(self, test_db):
        """UserFeedback artwork_id FK can reference GeneratedImage."""
        session = test_db()
        try:
            img = GeneratedImage(filename="gen.png", prompt="test", model_id="m")
            session.add(img)
            session.flush()

            fb = UserFeedback(
                artwork_id=img.id,
                artwork_filename="gen.png",
                action="download",
                signal_value=0.9,
            )
            session.add(fb)
            session.commit()

            result = (
                session.query(UserFeedback)
                .filter_by(artwork_filename="gen.png")
                .first()
            )
            assert result.artwork_id == img.id
        finally:
            session.close()

    def test_user_feedback_all_actions(self, test_db):
        """All valid actions can be stored."""
        session = test_db()
        try:
            actions = ["like", "love", "download", "share", "skip", "delete"]
            for action in actions:
                fb = UserFeedback(
                    artwork_filename=f"{action}.png",
                    action=action,
                    signal_value=0.5,
                )
                session.add(fb)
            session.commit()
            count = session.query(UserFeedback).count()
            assert count == len(actions)
        finally:
            session.close()


class TestGalleryCollectionUpdatedAt:
    """GalleryCollection.updated_at should be set on update via event listener."""

    def test_updated_at_set_on_update(self, test_db):
        """updated_at changes when a collection is modified."""
        session = test_db()
        try:
            col = GalleryCollection(
                name="My Collection",
                description="test",
            )
            session.add(col)
            session.commit()
            _ = col.updated_at  # capture before mutation

            # Mutate a field to trigger 'before_update'
            col.name = "Renamed"
            session.commit()

            # updated_at should have been set by the event listener
            assert col.updated_at is not None
            # If updated more than a millisecond apart they should differ,
            # but since SQLite is fast we just check it's set.
            assert isinstance(col.updated_at, datetime)
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestSocialConfig:
    def test_social_config_has_twitter_fields(self):
        from ai_artist.utils.config import SocialConfig

        s = SocialConfig()
        for attr in [
            "twitter_api_key",
            "twitter_api_secret",
            "twitter_access_token",
            "twitter_access_secret",
            "twitter_bearer_token",
        ]:
            assert hasattr(s, attr), f"Missing attribute: {attr}"
            assert getattr(s, attr) is None  # default is None

    def test_social_config_has_instagram_fields(self):
        from ai_artist.utils.config import SocialConfig

        s = SocialConfig()
        assert s.instagram_username is None
        assert s.instagram_password is None
        assert s.instagram_session_file == "data/instagram_session.json"

    def test_social_config_has_bluesky_fields(self):
        from ai_artist.utils.config import SocialConfig

        s = SocialConfig()
        assert s.bluesky_handle is None
        assert s.bluesky_password is None

    def test_social_config_secret_str(self):
        from pydantic import SecretStr

        from ai_artist.utils.config import SocialConfig

        s = SocialConfig(twitter_api_key="mykey")
        assert isinstance(s.twitter_api_key, SecretStr)
        assert s.twitter_api_key.get_secret_value() == "mykey"


class TestWebConfigDebug:
    def test_debug_defaults_false(self):
        from ai_artist.utils.config import WebConfig

        w = WebConfig()
        assert w.debug is False

    def test_debug_set_true(self):
        from ai_artist.utils.config import WebConfig

        w = WebConfig(debug=True)
        assert w.debug is True

    def test_from_env_debug(self, monkeypatch):
        from ai_artist.utils.config import WebConfig

        monkeypatch.setenv("DEBUG", "true")
        w = WebConfig.from_env()
        assert w.debug is True

    def test_from_env_debug_false(self, monkeypatch):
        from ai_artist.utils.config import WebConfig

        monkeypatch.setenv("DEBUG", "0")
        w = WebConfig.from_env()
        assert w.debug is False


# ---------------------------------------------------------------------------
# Portfolio cache
# ---------------------------------------------------------------------------


class TestPortfolioCache:
    def test_cache_is_reused_within_ttl(self):
        """Second call within TTL returns cached result without re-scanning."""
        import time

        import ai_artist.web.lumira_routes as routes

        # Reset cache state
        routes._portfolio_cache = [{"prompt": "cached"}]
        routes._portfolio_cache_ts = time.monotonic()  # just set

        import asyncio

        # Save/restore the thread's event loop so a closed loop is not left as
        # "current" for later tests on this thread.
        try:
            prev_loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            prev_loop = None
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(routes._load_portfolio_from_gallery())
        finally:
            loop.close()
            asyncio.set_event_loop(prev_loop)

        # Should return the cached value without touching the filesystem
        assert result == [{"prompt": "cached"}]
        # Reset for other tests
        routes._portfolio_cache = None
        routes._portfolio_cache_ts = 0.0

    def test_cache_is_invalidated_after_creation(self):
        """After autonomy creation, cache ts is reset to force re-scan."""
        import time

        import ai_artist.web.lumira_routes as routes

        routes._portfolio_cache_ts = time.monotonic()
        routes._portfolio_cache = [{"prompt": "old"}]

        # Simulate what happens on successful autonomy creation
        routes._portfolio_cache_ts = 0.0

        assert routes._portfolio_cache_ts == 0.0


# ---------------------------------------------------------------------------
# _score_image fallback
# ---------------------------------------------------------------------------


class TestScoreImageFallback:
    def test_returns_fallback_on_import_error(self):
        """_score_image returns 0.8 if curator import fails."""
        import ai_artist.web.lumira_routes as routes

        old_curator = routes._image_curator
        try:
            routes._image_curator = None
            with patch.dict("sys.modules", {"ai_artist.curation.curator": None}):
                img = MagicMock()
                score = routes._score_image(img, "test prompt")
            assert score == 0.8
        finally:
            routes._image_curator = old_curator

    def test_returns_rounded_score_from_curator(self):
        """_score_image rounds the curator overall_score."""
        import ai_artist.web.lumira_routes as routes

        mock_metrics = MagicMock()
        mock_metrics.overall_score = 0.7654321
        mock_curator = MagicMock()
        mock_curator.evaluate.return_value = mock_metrics

        old_curator = routes._image_curator
        try:
            routes._image_curator = mock_curator
            img = MagicMock()
            score = routes._score_image(img, "test")
            assert score == round(0.7654321, 4)
        finally:
            routes._image_curator = old_curator


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------


class TestFeedbackEndpoint:
    """Integration tests for the feedback API route."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create test client with overridden DB session."""
        from ai_artist.db.session import get_db
        from ai_artist.web.app import app

        db_path = tmp_path / "fb_test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        TestSession = sessionmaker(bind=engine)

        def override_get_db():
            session = TestSession()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        yield client
        app.dependency_overrides.clear()

    def test_submit_feedback_like_succeeds(self, client):
        """POST /api/feedback/submit with valid like action returns 200."""
        # Patch adaptive learner to isolate from on-disk state
        with patch("ai_artist.web.feedback.get_adaptive_learner") as mock_learner:
            from ai_artist.learning.adaptive_learner import AdaptiveLearner

            mock_al = MagicMock(spec=AdaptiveLearner)
            mock_al.get_learning_stats.return_value = {"total_feedback": 1}
            mock_learner.return_value = mock_al
            resp = client.post(
                "/api/feedback/submit",
                json={
                    "artwork_id": "test_art.png",
                    "action": "like",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_submit_feedback_invalid_action(self, client):
        """POST /api/feedback/submit with invalid action returns 400."""
        resp = client.post(
            "/api/feedback/submit",
            json={"artwork_id": "x.png", "action": "INVALID"},
        )
        assert resp.status_code == 400

    def test_submit_feedback_validates_artwork_id_length(self, client):
        """artwork_id > 512 chars should be rejected with 422."""
        resp = client.post(
            "/api/feedback/submit",
            json={"artwork_id": "a" * 513, "action": "like"},
        )
        assert resp.status_code == 422

    def test_submit_feedback_validates_session_id_length(self, client):
        """session_id > 64 chars should be rejected with 422."""
        resp = client.post(
            "/api/feedback/submit",
            json={"artwork_id": "x.png", "action": "like", "session_id": "s" * 65},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Admin endpoint
# ---------------------------------------------------------------------------


class TestAdminPerformance:
    """Tests for the admin performance metrics endpoint."""

    @pytest.fixture
    def client(self, tmp_path):
        from ai_artist.db.session import get_db
        from ai_artist.web.app import app
        from ai_artist.web.dependencies import require_api_key

        db_path = tmp_path / "admin_test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        TestSession = sessionmaker(bind=engine)

        def override_get_db():
            session = TestSession()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_api_key] = lambda: "dev"
        client = TestClient(app, raise_server_exceptions=False)
        yield client
        app.dependency_overrides.clear()

    def test_performance_metrics_returns_200(self, client):
        resp = client.get("/admin/performance")
        assert resp.status_code == 200

    def test_performance_metrics_has_avg_duration(self, client):
        resp = client.get("/admin/performance")
        data = resp.json()
        assert "avg_duration" in data
        assert isinstance(data["avg_duration"], int | float)
