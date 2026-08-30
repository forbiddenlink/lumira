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


class TestStatusVocabulary:
    """``GeneratedImage.status`` is the pipeline state and nothing else.

    Three of the five write paths in lumira_routes.py used to set
    ``status=mood.value``, which put mood names ("melancholic", "serene", ...)
    in the same column as "curated". Status filters silently missed those rows
    and the collection breakdown mixed two vocabularies. Migration
    d7f2c9a41b83 corrected the existing data; this keeps it corrected.
    """

    PIPELINE_STATUSES = {"pending", "curated", "rejected", "active"}

    def test_no_write_path_assigns_a_mood_to_status(self):
        from pathlib import Path

        from ai_artist.personality.moods import Mood

        source_root = Path(__file__).resolve().parents[2] / "src" / "ai_artist"
        offenders = []
        for path in source_root.rglob("*.py"):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if not stripped.startswith("status="):
                    continue
                value = stripped[len("status=") :].rstrip(",")
                if "mood" in value.lower():
                    offenders.append(f"{path.name}:{lineno}: {stripped}")

        assert not offenders, (
            "status is the pipeline state; record mood in generation_params "
            "and tags instead:\n  " + "\n  ".join(offenders)
        )

        # Sanity: the moods these sites used really are a different vocabulary.
        assert not {m.value for m in Mood} & self.PIPELINE_STATUSES
