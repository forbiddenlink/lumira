"""Small, atomic JSON persistence primitives for Lumira runtime state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_json_value(path: Path) -> Any | None:
    """Load JSON, returning ``None`` for absent or invalid files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data


def load_json_object(path: Path) -> dict[str, Any] | None:
    """Load a JSON object, returning ``None`` for non-object values."""
    data = load_json_value(path)
    return data if isinstance(data, dict) else None


def write_json_value(path: Path, payload: Any) -> None:
    """Atomically replace ``path`` with UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            json.dump(payload, temporary_file, indent=2, default=str)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def write_json_object(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace ``path`` with a UTF-8 JSON object."""
    write_json_value(path, payload)
