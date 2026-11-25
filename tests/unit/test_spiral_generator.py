"""Tests for SpiralGenerator (Spiral REST API image backend).

All HTTP is mocked: no network, no API key required. Verifies (provider, model)
resolution, the missing-key guard, the daily budget backstop, aspect/resolution
mapping, per-family input builders, and the start-run -> poll -> download path.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from ai_artist.core import spiral_generator as mg
from ai_artist.core.spiral_client import SpiralError
from ai_artist.core.spiral_generator import SpiralGenerator

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
    # fakeredis without its Lua extra falls back to the in-process ledger.
    monkeypatch.setattr(spend_guard, "_memory_ledger", spend_guard._InMemoryLedger())
    monkeypatch.delenv("LUMIRA_AI_KILL_SWITCH", raising=False)
    monkeypatch.delenv("LUMIRA_DAILY_SPEND_USD_MAX", raising=False)
    yield


def _mock_ok_run(run_id: str = "run-1"):
    """Mocked responses for one run: POST ok, poll completed, one PNG download."""
    post_resp = MagicMock()
    post_resp.json.return_value = {"id": run_id}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {
        "status": "completed",
        "output": {
            "items": [
                {
                    "type": "image",
                    "url": "https://cdn.example/out.png",
                    "mime_type": "image/png",
                }
            ]
        },
    }
    poll_resp.raise_for_status.return_value = None

    dl_resp = MagicMock()
    dl_resp.content = _png_bytes()
    dl_resp.raise_for_status.return_value = None
    return post_resp, poll_resp, dl_resp


def _run(gen, *args, **kwargs):
    """Generate with mocked HTTP; return (images, post_mock)."""
    post_resp, poll_resp, dl_resp = _mock_ok_run()
    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        images = gen.generate(*args, **kwargs)
    return images, post


def test_model_id_resolves_friendly_name(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="flux2-max")
    assert gen.model_key == "flux_2_max"
    assert gen.model == ("fal", "fal-ai/flux-2-max")


def test_model_id_passthrough_catalog_key(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    assert gen.model_key == "nano_banana_pro"
    assert gen.model == ("fal", "fal-ai/nano-banana-pro")


def test_catalog_pairs():
    assert mg.SPIRAL_MODELS["gpt_image_2"] == ("fal", "openai/gpt-image-2")
    assert mg.SPIRAL_MODELS["grok_imagine_image"] == ("fal", "xai/grok-imagine-image")
    assert mg.SPIRAL_MODELS["nano_banana_2"] == ("fal", "fal-ai/nano-banana-2")


def test_raw_provider_model_ref_resolves(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="fal/fal-ai/some-model")
    assert gen.model == ("fal", "fal-ai/some-model")


def test_invalid_model_ref_rejected():
    with pytest.raises(ValueError):
        SpiralGenerator(model_id="no_slash_here")
    with pytest.raises(ValueError):
        SpiralGenerator(model_id="fal/../admin")


def test_generate_without_key_raises(monkeypatch):
    monkeypatch.delenv("SPIRAL_API_KEY", raising=False)
    gen = SpiralGenerator(model_id="nano_banana_pro")
    with pytest.raises(ValueError, match="SPIRAL_API_KEY"):
        gen.generate("a prompt")


def test_budget_guard_blocks_over_cap(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_SPIRAL_DAILY_MAX_IMAGES", "1")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    with pytest.raises(RuntimeError, match="budget exceeded"):
        gen.generate("a prompt", num_images=2)


def test_aspect_and_resolution_mapping():
    assert mg._aspect_ratio(1024, 1024) == "1:1"
    assert mg._aspect_ratio(1920, 1080) == "16:9"
    assert mg._resolution_tier(1024, 1024) == "1K"
    assert mg._resolution_tier(2400, 1792) == "2K"
    assert mg._resolution_tier(4096, 3000) == "4K"


def test_generate_happy_path(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    monkeypatch.delenv("LUMIRA_SPIRAL_DAILY_MAX_IMAGES", raising=False)
    gen = SpiralGenerator(model_id="nano_banana_pro")

    post_resp, poll_resp, dl_resp = _mock_ok_run("run-123")
    with (
        patch.object(mg.httpx, "post", return_value=post_resp) as post,
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]) as get,
    ):
        images = gen.generate("misty forest", width=2400, height=1792, seed=7)

    assert len(images) == 1
    assert isinstance(images[0], Image.Image)
    # POST /v1/runs with the (provider, model) pair and an idempotency key.
    (url,), kwargs = post.call_args
    assert url.endswith("/v1/runs")
    assert kwargs["json"]["provider"] == "fal"
    assert kwargs["json"]["model"] == "fal-ai/nano-banana-pro"
    assert kwargs["headers"]["Idempotency-Key"]
    assert kwargs["headers"]["Authorization"] == "Bearer k"
    body = kwargs["json"]["input"]
    assert body["prompt"] == "misty forest"
    assert body["seed"] == 7
    assert body["aspect_ratio"] == "4:3"
    assert body["resolution"] == "2K"
    assert body["output_format"] == "png"
    # poll hit the run endpoint with a long-poll wait.
    poll_url = get.call_args_list[0].args[0]
    assert poll_url.endswith("/v1/runs/run-123")
    assert "wait_seconds" in get.call_args_list[0].kwargs["params"]


def test_idempotency_key_unique_per_run(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    keys = []
    for _ in range(2):
        _, post = _run(gen, "x")
        keys.append(post.call_args.kwargs["headers"]["Idempotency-Key"])
    assert keys[0] != keys[1]


def test_flux_input_uses_image_size(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="flux2-max")
    _, post = _run(gen, "bold abstract", width=1600, height=896)
    body = post.call_args.kwargs["json"]["input"]
    assert body["image_size"] == {"width": 1600, "height": 896}
    assert "resolution" not in body and "aspect_ratio" not in body
    assert "num_images" not in body  # FLUX takes no num_images


def test_flux_runs_once_per_image(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="flux2-max")
    r1, r2 = _mock_ok_run("a"), _mock_ok_run("b")
    with (
        patch.object(mg.httpx, "post", side_effect=[r1[0], r2[0]]) as post,
        patch.object(mg.httpx, "get", side_effect=[r1[1], r1[2], r2[1], r2[2]]),
    ):
        images = gen.generate("x", num_images=2)
    assert len(images) == 2
    assert post.call_count == 2


def test_grok_has_no_seed(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="grok_imagine_image")
    _, post = _run(gen, "chaos", width=1024, height=1024, seed=5)
    body = post.call_args.kwargs["json"]["input"]
    assert "seed" not in body
    assert body["resolution"] == "1k"
    assert body["aspect_ratio"] == "1:1"


def test_gpt_image_size_multiple_of_16(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="gpt_image_2")
    _, post = _run(gen, "x", width=1000, height=700)
    size = post.call_args.kwargs["json"]["input"]["image_size"]
    assert size["width"] % 16 == 0 and size["height"] % 16 == 0


def test_unknown_model_minimal_input(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="fal/fal-ai/some-other-model")
    _, post = _run(gen, "anything", seed=3)
    body = post.call_args.kwargs["json"]["input"]
    assert body == {"prompt": "anything", "seed": 3}


def test_use_refiner_not_leaked_to_payload(monkeypatch):
    # worker passes use_refiner to every backend; it must NOT reach the REST input.
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    _, post = _run(gen, "x", use_refiner=True, num_inference_steps=99)
    body = post.call_args.kwargs["json"]["input"]
    assert "use_refiner" not in body
    assert "num_inference_steps" not in body


def test_budget_routed_through_spend_guard(monkeypatch):
    # generate() must call check_and_record_images with provider, count, cap and
    # the per-model image cost.
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_SPIRAL_DAILY_MAX_IMAGES", "5")
    monkeypatch.delenv("LUMIRA_SPIRAL_COST_PER_IMAGE_USD", raising=False)
    gen = SpiralGenerator(model_id="nano_banana_pro")
    post_resp, poll_resp, dl_resp = _mock_ok_run()
    with (
        patch.object(mg, "check_and_record_images") as guard,
        patch.object(mg.httpx, "post", return_value=post_resp),
        patch.object(mg.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate("x", num_images=1)
    guard.assert_called_once_with(
        "spiral", 1, 5, mg._COST_PER_IMAGE_USD["nano_banana_pro"]
    )


def test_cost_override_env(monkeypatch):
    monkeypatch.setenv("LUMIRA_SPIRAL_COST_PER_IMAGE_USD", "0.5")
    assert mg._cost_per_image("grok_imagine_image") == 0.5


def test_budget_recorded_on_attempt(monkeypatch):
    # The guard records on attempt (mirrors ReplicateGenerator), so a second
    # call over the cap is blocked.
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_SPIRAL_DAILY_MAX_IMAGES", "1")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    _run(gen, "x", num_images=1)  # consumes the only slot
    with pytest.raises(RuntimeError, match="budget exceeded"):
        gen.generate("y", num_images=1)


def test_clamp_dims_preserves_aspect_and_limits():
    d = mg._clamp_dims(3000, 1000)
    assert d["width"] == 2560  # FLUX max edge
    assert d["width"] % 16 == 0 and d["height"] % 16 == 0
    assert d["width"] * d["height"] <= 4_194_304
    assert abs(d["width"] / d["height"] - 3.0) < 0.1
    # small dims scale up to the 256 floor, multiples of 16.
    up = mg._clamp_dims(128, 64)
    assert up["width"] >= 256 and up["height"] >= 256
    assert up["width"] % 16 == 0 and up["height"] % 16 == 0


def test_download_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    post_resp, poll_resp, _ = _mock_ok_run()
    good = MagicMock()
    good.content = _png_bytes()
    good.raise_for_status.return_value = None
    # poll, then download fails once and succeeds on retry.
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
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="nano_banana_pro")

    post_resp = MagicMock()
    post_resp.json.return_value = {"id": "run-x"}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {"status": "failed", "error": "boom"}
    poll_resp.raise_for_status.return_value = None

    with (
        patch.object(mg.httpx, "post", return_value=post_resp),
        patch.object(mg.httpx, "get", return_value=poll_resp),
        pytest.raises(RuntimeError, match="failed"),
    ):
        gen.generate("a prompt")


def test_insufficient_balance_402_raises_spiral_error(monkeypatch):
    monkeypatch.setenv("SPIRAL_API_KEY", "k")
    gen = SpiralGenerator(model_id="nano_banana_pro")
    resp = httpx.Response(
        402,
        json={
            "code": "INSUFFICIENT_BALANCE",
            "title": "Insufficient balance",
            "retryable": False,
        },
        request=httpx.Request("POST", "https://api.spiral.ai/v1/runs"),
    )
    with (
        patch.object(mg.httpx, "post", return_value=resp),
        pytest.raises(SpiralError) as exc,
    ):
        gen.generate("x")
    assert exc.value.status == 402
    assert exc.value.code == "INSUFFICIENT_BALANCE"
    assert exc.value.retryable is False
