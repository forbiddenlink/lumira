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
    # Isolate the shared spend-guard ledger between tests. A fresh fakeredis
    # client per test gives real per-provider counters without a live Redis.
    import fakeredis

    from ai_artist.core import spend_guard

    monkeypatch.setattr(spend_guard, "_redis_checked", True)
    monkeypatch.setattr(spend_guard, "_redis_client", fakeredis.FakeStrictRedis())
    monkeypatch.delenv("LUMIRA_AI_KILL_SWITCH", raising=False)
    monkeypatch.delenv("LUMIRA_DAILY_SPEND_USD_MAX", raising=False)
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
        "status": "COMPLETED",
        "output": {"result": ["https://cdn.example/out.png"]},
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


def _mock_ok_run(monkeypatch):
    """Patch httpx so a run POSTs, polls to complete, and downloads one PNG.

    Returns (post_mock, get_mock) after the caller enters the context.
    """
    post_resp = MagicMock()
    post_resp.json.return_value = {"runId": "run-1"}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    # REST run-status shape: URLs live at output.result (verified live 2026-07-28).
    poll_resp.json.return_value = {
        "status": "COMPLETED",
        "output": {"result": ["https://cdn.example/out.png"]},
    }
    poll_resp.raise_for_status.return_value = None

    dl_resp = MagicMock()
    dl_resp.content = _png_bytes()
    dl_resp.raise_for_status.return_value = None
    return post_resp, poll_resp, dl_resp


def test_flux_input_uses_image_size(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="flux2-max")  # -> flux_2_max
    post_resp, poll_resp, dl_resp = _mock_ok_run(monkeypatch)
    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("bold abstract", width=1600, height=900)
    body = post.call_args.kwargs["json"]["input"]
    assert body["image_size"] == {"width": 1600, "height": 900}
    assert "resolution" not in body and "aspect_ratio" not in body


def test_unknown_model_minimal_input(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="some_other_node")
    post_resp, poll_resp, dl_resp = _mock_ok_run(monkeypatch)
    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("anything", seed=3)
    body = post.call_args.kwargs["json"]["input"]
    assert body == {"prompt": "anything", "num_images": 1, "seed": 3}


def test_sub_model_id_sent_top_level(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="flux2-max", sub_model_id="flux-2-max-text")
    post_resp, poll_resp, dl_resp = _mock_ok_run(monkeypatch)
    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("bold abstract")
    sent = post.call_args.kwargs["json"]
    assert sent["subModelId"] == "flux-2-max-text"
    assert "subModelId" not in sent["input"]


def test_extract_urls_rest_and_fallback_shapes():
    # REST shape: output.result (verified live 2026-07-28).
    rest = {"output": {"result": ["https://cdn.example/a.png"]}}
    assert MagicaGenerator._extract_urls(rest) == ["https://cdn.example/a.png"]
    # Fallback shape: top-level assets[].url.
    legacy = {"assets": [{"url": "https://cdn.example/b.png"}, {"nope": 1}]}
    assert MagicaGenerator._extract_urls(legacy) == ["https://cdn.example/b.png"]
    # Nothing usable -> empty.
    assert MagicaGenerator._extract_urls({"output": {}}) == []


def test_use_refiner_not_leaked_to_payload(monkeypatch):
    # worker passes use_refiner to every backend; it must NOT reach the REST input.
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="nano_banana_pro")
    post_resp, poll_resp, dl_resp = _mock_ok_run(monkeypatch)
    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("x", use_refiner=True, num_inference_steps=99)
    body = post.call_args.kwargs["json"]["input"]
    assert "use_refiner" not in body
    assert "num_inference_steps" not in body


def test_budget_routed_through_spend_guard(monkeypatch):
    # Spend is now tracked by the shared spend guard: generate() must call
    # check_and_record_images with the provider, count, cap, and per-image cost.
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_IMAGES", "5")
    gen = MagicaGenerator(model_id="nano_banana_pro")
    post_resp, poll_resp, dl_resp = _mock_ok_run(monkeypatch)
    with (
        patch.object(mg, "check_and_record_images") as guard,
        patch.object(mg.httpx, "post", return_value=post_resp),
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("x", num_images=1)
    guard.assert_called_once_with("magica", 1, 5, mg._MAGICA_COST_PER_IMAGE_USD)


def test_budget_recorded_on_attempt(monkeypatch):
    # The guard records on attempt (mirrors ReplicateGenerator), so a second
    # call over the cap is blocked.
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_IMAGES", "1")
    gen = MagicaGenerator(model_id="nano_banana_pro")
    post_resp, poll_resp, dl_resp = _mock_ok_run(monkeypatch)
    with (
        patch.object(mg.httpx, "post", return_value=post_resp),
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("x", num_images=1)  # consumes the only slot
    with pytest.raises(RuntimeError, match="budget exceeded"):
        gen.generate("y", num_images=1)


def test_clamp_dims_preserves_aspect():
    d = mg._clamp_dims(3000, 1000)
    assert d["width"] == 2048
    assert d["height"] == round(1000 * 2048 / 3000)  # ~683, ratio preserved
    assert 256 <= d["height"] <= 2048
    # small dims scale up preserving 2:1 ratio (128x64 -> 512x256)
    up = mg._clamp_dims(128, 64)
    assert up["width"] == 512 and up["height"] == 256


def test_download_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaGenerator(model_id="nano_banana_pro")
    post_resp, poll_resp, _ = _mock_ok_run(monkeypatch)
    good = MagicMock()
    good.content = _png_bytes()
    good.raise_for_status.return_value = None
    # poll -> then download fails once, succeeds on retry.
    seq = [poll_resp, mg.httpx.HTTPError("transient"), good]
    with (
        patch.object(mg.httpx, "post", return_value=post_resp),
        patch.object(mg.httpx, "get", side_effect=seq),
    ):
        images = gen.generate("x")
    assert len(images) == 1


def test_model_for_mood():
    assert mg.model_for_mood("melancholic") == "nano_banana_pro"
    assert mg.model_for_mood("BOLD") == "flux_2_max"
    assert mg.model_for_mood("chaotic") == "grok_imagine_image"
    assert mg.model_for_mood("no_such_mood") == mg.DEFAULT_MODEL


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
