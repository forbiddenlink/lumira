"""Test database operations."""

import pytest

from ai_artist.db.models import Base, GeneratedImage
from ai_artist.db.session import create_db_engine, create_session_factory


@pytest.fixture
def test_db(tmp_path):
    """Create test database."""
    db_path = tmp_path / "test.db"
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    return create_session_factory(db_path)


def test_create_image_record(test_db):
    """Test creating an image record."""
    session = test_db()
    try:
        image = GeneratedImage(
            filename="test.png",
            prompt="a test image",
            model_id="test-model",
        )
        session.add(image)
        session.commit()

        # Verify
        result = session.query(GeneratedImage).filter_by(filename="test.png").first()
        assert result is not None
        assert result.prompt == "a test image"
        assert result.model_id == "test-model"
    finally:
        session.close()


def test_image_defaults(test_db):
    """Test that default values are set correctly."""
    session = test_db()
    try:
        image = GeneratedImage(
            filename="test_defaults.png",
            prompt="test",
            model_id="test-model",
        )
        session.add(image)
        session.commit()

        result = (
            session.query(GeneratedImage)
            .filter_by(filename="test_defaults.png")
            .first()
        )
        assert result.status == "pending"
        assert result.is_featured is False
        assert result.negative_prompt == ""
    finally:
        session.close()
