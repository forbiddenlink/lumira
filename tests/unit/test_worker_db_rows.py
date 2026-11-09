"""Worker-generated images must get a GeneratedImage row, or the gallery
(which lists DB rows) never shows them."""

from pathlib import Path

import pytest

from ai_artist.db import session as db_session_module
from ai_artist.db.models import Base, GeneratedImage
from ai_artist.db.session import create_session_factory, set_session_factory
from ai_artist.queue.worker import _record_image

METADATA = {
    "prompt": "a lighthouse in fog",
    "negative_prompt": "blurry",
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 30,
    "guidance_scale": 7.5,
    "seed": 42,
    "model_id": "test-model",
    "created_at": "2026-11-09T12:00:00",
    "job_id": "job-1",
}


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(db_session_module, "_session_factory", None)
    f = create_session_factory(tmp_path / "test.db")
    Base.metadata.create_all(f.kw["bind"])
    set_session_factory(f)
    yield f
    monkeypatch.setattr(db_session_module, "_session_factory", None)


def test_record_image_inserts_row(factory):
    _record_image(Path("gallery/2026/11/09/job-1_0.png"), METADATA)

    with factory() as s:
        rows = s.query(GeneratedImage).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.filename == "gallery/2026/11/09/job-1_0.png"
    assert row.prompt == "a lighthouse in fog"
    assert row.model_id == "test-model"
    assert row.seed == 42
    assert row.status == "pending"
    assert row.generation_params["job_id"] == "job-1"
    assert row.generation_params["source"] == "worker"


def test_record_image_failure_does_not_raise(factory):
    path = Path("gallery/dup.png")
    _record_image(path, METADATA)
    # Duplicate filename violates the unique constraint; must log, not raise.
    _record_image(path, METADATA)

    with factory() as s:
        assert s.query(GeneratedImage).count() == 1
