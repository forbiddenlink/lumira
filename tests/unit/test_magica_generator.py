"""Tests for MagicaGenerator (Magica REST API image backend).

All HTTP is mocked — no network, no API key required. Verifies node-type
resolution, the missing-key guard, the daily budget backstop, aspect/resolution
mapping, and the start-run -> poll -> download happy path.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from ai_artist.core import magica_generator as mg
from ai_artist.core.magica_generator import MagicaGenerator

pytestmark = pytest.mark.unit


def _png_bytes(color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_budget(monkeypatch):
    # Isolate the module-level daily counter between tests.
    monkeypatch.setattr(mg, "_spend_day", None)
    monkeypatch.setattr(mg, "_spend_count", 0)
    yield


def test_model_id_resolves_friendly_name(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="flux2-max")
    assert gen.node_type == "flux_2_max"


def test_model_id_passthrough_nodetype(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="nano_banana_pro")
    assert gen.node_type == "nano_banana_pro"


def test_generate_without_key_raises(monkeypatch):
    monkeypatch.delenv("MAGICA_API_KEY", raising=False)
    gen = MagicaGenerator(model_id="nano_banana_pro")
    with pytest.raises(ValueError, match="MAGICA_API_KEY"):
        gen.generate("a prompt")


def test_budget_guard_blocks_over_cap(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_IMAGES", "1")
    gen = MagicaGenerator(model_id="nano_banana_pro")
    with pytest.raises(RuntimeError, match="budget exceeded"):
        gen.generate("a prompt", num_images=2)


def test_aspect_and_resolution_mapping():
    assert mg._aspect_ratio(1024, 1024) == "1:1"
    assert mg._aspect_ratio(1920, 1080) == "16:9"
    assert mg._resolution_tier(1024, 1024) == "1K"
    assert mg._resolution_tier(2400, 1792) == "2K"
    assert mg._resolution_tier(4096, 3000) == "4K"


def test_generate_happy_path(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.delenv("LUMIRA_MAGICA_DAILY_MAX_IMAGES", raising=False)
    gen = MagicaGenerator(model_id="nano_banana_pro")

    post_resp = MagicMock()
    post_resp.json.return_value = {"runId": "run-123"}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {
        "status": "complete",
        "assets": [{"url": "https://cdn.example/out.png"}],
    }
    poll_resp.raise_for_status.return_value = None

    dl_resp = MagicMock()
    dl_resp.content = _png_bytes()
    dl_resp.raise_for_status.return_value = None

    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]) as get,
    ):
        images = gen.generate("misty forest", width=2400, height=1792, seed=7)

    assert len(images) == 1
    assert isinstance(images[0], Image.Image)
    # start-run POSTed to the resolved nodeType with prompt + seed in input.
    (url,), kwargs = post.call_args
    assert url.endswith("/v1/nodes/nano_banana_pro/run")
    body = kwargs["json"]["input"]
    assert body["prompt"] == "misty forest"
    assert body["seed"] == 7
    assert body["aspect_ratio"] == "4:3"
    assert body["resolution"] == "2K"
    # poll hit the runs endpoint.
    poll_url = get.call_args_list[0].args[0]
    assert poll_url.endswith("/v1/nodes/runs/run-123")


def test_generate_failed_run_raises(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="nano_banana_pro")

    post_resp = MagicMock()
    post_resp.json.return_value = {"runId": "run-x"}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {"status": "FAILED", "error": "boom"}
    poll_resp.raise_for_status.return_value = None

    with (
        patch.object(mg.httpx, "post", return_value=post_resp),
        patch.object(mg.httpx, "get", return_value=poll_resp),
        pytest.raises(RuntimeError, match="failed"),
    ):
        gen.generate("a prompt")
