"""The social preview image is fetched by unfurlers on every share; keep it light."""

import struct
from pathlib import Path

OG = Path(__file__).resolve().parents[2] / "static" / "images" / "og-preview.png"


def test_og_preview_under_200kb() -> None:
    assert OG.stat().st_size < 200_000


def test_og_preview_keeps_1280x720_size() -> None:
    """Dimensions stay at the 1280x720 social-card size the templates assume."""
    header = OG.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", header[16:24])
    assert (width, height) == (1280, 720)
