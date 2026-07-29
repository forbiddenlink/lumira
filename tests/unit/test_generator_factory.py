"""Tests for the image-generator backend factory.

The factory routes ``config.model.backend`` to a concrete generator class while
preserving the prior hardwired-local behavior. These tests patch the concrete
classes so no torch/diffusers or Replicate network access is required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_artist.core.generator_factory import (
    BACKEND_LOCAL,
    BACKEND_REPLICATE,
    get_image_generator,
)

pytestmark = pytest.mark.unit


def test_default_backend_is_local():
    with patch("ai_artist.core.generator.ImageGenerator") as Local:
        gen = get_image_generator(model_id="stabilityai/sdxl")
    Local.assert_called_once()
    assert gen is Local.return_value


def test_replicate_backend_routes_to_replicate():
    with patch("ai_artist.core.replicate_generator.ReplicateGenerator") as Rep:
        gen = get_image_generator(
            BACKEND_REPLICATE, model_id="flux-schnell", device="cpu", dtype=None
        )
    Rep.assert_called_once_with(model_id="flux-schnell", device="cpu", dtype=None)
    assert gen is Rep.return_value


def test_magica_backend_routes_to_magica():
    with patch("ai_artist.core.magica_generator.MagicaGenerator") as Mag:
        gen = get_image_generator("magica", model_id="nano_banana_pro")
    Mag.assert_called_once_with(model_id="nano_banana_pro", device="cuda", dtype=None)
    assert gen is Mag.return_value


def test_resolve_web_prefers_magica_when_local_and_keyed(monkeypatch):
    from ai_artist.core.generator_factory import resolve_web_image_backend

    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.delenv("LUMIRA_FORCE_LOCAL_WEB", raising=False)
    assert resolve_web_image_backend("local") == "magica"


def test_resolve_web_respects_explicit_replicate(monkeypatch):
    from ai_artist.core.generator_factory import resolve_web_image_backend

    monkeypatch.setenv("MAGICA_API_KEY", "k")
    assert resolve_web_image_backend("replicate") == "replicate"


def test_resolve_web_force_local(monkeypatch):
    from ai_artist.core.generator_factory import resolve_web_image_backend

    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_FORCE_LOCAL_WEB", "1")
    assert resolve_web_image_backend("local") == "local"


def test_build_web_image_generator_magica_mood(monkeypatch):
    from types import SimpleNamespace

    from ai_artist.core.generator_factory import build_web_image_generator

    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.delenv("LUMIRA_FORCE_LOCAL_WEB", raising=False)
    config = SimpleNamespace(
        model=SimpleNamespace(backend="magica", base_model="x", device="cpu")
    )
    with patch("ai_artist.core.magica_generator.MagicaGenerator") as Mag:
        backend, gen = build_web_image_generator(config, mood="playful")
    assert backend == "magica"
    Mag.assert_called_once()
    assert Mag.call_args.kwargs["model_id"] == "gpt_image_2"
    assert gen is Mag.return_value


def test_build_web_img2img_falls_back_from_magica(monkeypatch):
    from types import SimpleNamespace

    from ai_artist.core.generator_factory import build_web_image_generator

    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r")
    config = SimpleNamespace(
        model=SimpleNamespace(backend="magica", base_model="flux2-pro", device="cpu")
    )
    with patch("ai_artist.core.replicate_generator.ReplicateGenerator") as Rep:
        backend, gen = build_web_image_generator(config, require_img2img=True)
    assert backend == "replicate"
    assert gen is Rep.return_value


def test_unknown_backend_falls_back_to_local():
    with patch("ai_artist.core.generator.ImageGenerator") as Local:
        gen = get_image_generator("nonsense", model_id="m")
    Local.assert_called_once()
    assert gen is Local.return_value


def test_backend_is_case_insensitive():
    with patch("ai_artist.core.replicate_generator.ReplicateGenerator") as Rep:
        get_image_generator("REPLICATE", model_id="m")
    Rep.assert_called_once()


def test_local_omits_dtype_when_none():
    with patch("ai_artist.core.generator.ImageGenerator") as Local:
        get_image_generator(BACKEND_LOCAL, model_id="m", device="cuda", dtype=None)
    _, kwargs = Local.call_args
    assert "dtype" not in kwargs
    assert kwargs["model_id"] == "m"
    assert kwargs["device"] == "cuda"


def test_local_forwards_dtype_when_given():
    sentinel = object()
    with patch("ai_artist.core.generator.ImageGenerator") as Local:
        get_image_generator(BACKEND_LOCAL, model_id="m", dtype=sentinel)
    _, kwargs = Local.call_args
    assert kwargs["dtype"] is sentinel
