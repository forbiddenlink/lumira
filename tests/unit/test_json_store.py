from __future__ import annotations

from ai_artist.utils.json_store import (
    load_json_object,
    load_json_value,
    write_json_object,
    write_json_value,
)


def test_write_json_object_is_readable(tmp_path):
    path = tmp_path / "state.json"
    write_json_object(path, {"mood": "serene"})
    assert load_json_object(path) == {"mood": "serene"}
    assert not list(tmp_path.glob("*.tmp"))


def test_load_json_object_rejects_non_object_or_invalid_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[]")
    assert load_json_object(path) is None
    write_json_value(path, ["archive"])
    assert load_json_value(path) == ["archive"]
    path.write_text("not json")
    assert load_json_object(path) is None
