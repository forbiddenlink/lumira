"""Regression tests for the CodeQL path-injection, SSRF and ReDoS fixes."""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_artist.core.spiral_client import SpiralClient, SpiralModel
from ai_artist.gallery.manager import GalleryManager
from ai_artist.utils.config import WebConfig
from ai_artist.utils.prompt_emphasis import PromptEmphasis
from ai_artist.web.app import app
from ai_artist.web.dependencies import set_gallery_manager, set_web_config

API_KEY = "test-secret-key"


@pytest.fixture
def client(tmp_path):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    set_gallery_manager(GalleryManager(gallery), str(gallery))
    set_web_config(WebConfig(api_keys=[SecretStr(API_KEY)]))
    limiter = getattr(app.state, "limiter", None)
    if limiter is not None and hasattr(limiter, "_storage"):
        limiter._storage.storage.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    set_web_config(WebConfig())


def test_video_rejects_artwork_path_outside_gallery(client, monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "dummy")
    with patch("ai_artist.core.spiral_media.SpiralVideoGenerator") as gen:
        response = client.post(
            "/api/lumira/video",
            json={"prompt": "drift", "artwork_path": "../../etc/settings.json"},
            headers={"X-API-Key": API_KEY},
        )
    assert response.status_code == 400
    gen.assert_not_called()  # rejected before the paid generation call


def test_image_file_outside_gallery_is_403_whether_or_not_it_exists(client, tmp_path):
    (tmp_path / "outside.png").write_bytes(b"x")
    existing = client.get("/api/images/file/%2E%2E/outside.png")
    missing = client.get("/api/images/file/%2E%2E/nope.png")
    assert existing.status_code == 403
    assert missing.status_code == 403


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("fal", "../admin"),
        ("fal", "a//b"),
        ("fal", "x?y=1"),
        ("fal", ""),
        ("fal", "a#b"),
        ("", "model"),
        ("a/b", "model"),
    ],
)
def test_spiral_rejects_malformed_provider_or_model(provider, model):
    with pytest.raises(ValueError):
        SpiralClient(api_key="dummy").start_run(SpiralModel(provider, model), {})


def test_emphasis_parses_weights_and_stays_linear_on_hostile_input():
    pe = PromptEmphasis()
    assert pe.parse_emphasis("(a:1.5) b, (c:.5) (d)") == [
        ("a", 1.5),
        ("b,", 1.0),
        ("c", 0.5),
        ("d", 1.1),
    ]
    hostile = "(" + "a" * 10 + ":" + "1" * 5000 + "!"
    start = time.perf_counter()
    pe.parse_emphasis(hostile * 20)
    assert time.perf_counter() - start < 1.0
