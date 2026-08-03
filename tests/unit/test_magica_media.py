"""Tests for MagicaAudioGenerator / MagicaVideoGenerator (Magica REST media backends).

All HTTP is mocked -- no network, no API key required. Verifies the missing-key
guard, per-kind daily budget backstops, node-type resolution (explicit vs
mood-based), and the start-run -> poll -> download -> save happy paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_artist.core import magica_media as mm
from ai_artist.core.magica_media import MagicaAudioGenerator, MagicaVideoGenerator

pytestmark = pytest.mark.unit


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


def _mock_ok_run(run_id: str, urls: list[str], content: bytes):
    post_resp = MagicMock()
    post_resp.json.return_value = {"runId": run_id}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {"status": "COMPLETED", "output": {"result": urls}}
    poll_resp.raise_for_status.return_value = None

    dl_resp = MagicMock()
    dl_resp.content = content
    dl_resp.raise_for_status.return_value = None
    return post_resp, poll_resp, dl_resp


# --------------------------------------------------------------------------
# Missing-key guard
# --------------------------------------------------------------------------


def test_audio_generate_without_key_raises(monkeypatch):
    monkeypatch.delenv("MAGICA_API_KEY", raising=False)
    gen = MagicaAudioGenerator()
    with pytest.raises(ValueError, match="MAGICA_API_KEY"):
        gen.generate_audio("a prompt")


def test_video_generate_without_key_raises(monkeypatch):
    monkeypatch.delenv("MAGICA_API_KEY", raising=False)
    gen = MagicaVideoGenerator()
    with pytest.raises(ValueError, match="MAGICA_API_KEY"):
        gen.generate_video("a prompt")


# --------------------------------------------------------------------------
# Node-type resolution
# --------------------------------------------------------------------------


def test_audio_default_model():
    gen = MagicaAudioGenerator()
    assert gen.node_type == mm.DEFAULT_AUDIO_MODEL == "elevenlabs_music"


def test_video_default_model():
    gen = MagicaVideoGenerator()
    assert gen.node_type == mm.DEFAULT_VIDEO_MODEL == "kling_v3_pro"


def test_audio_friendly_name_resolves():
    gen = MagicaAudioGenerator(model_id="lyria-pro")
    assert gen.node_type == "lyria3_pro"


def test_video_friendly_name_resolves():
    gen = MagicaVideoGenerator(model_id="veo")
    assert gen.node_type == "veo_3_1"


def test_audio_mood_resolves_when_no_explicit_model():
    gen = MagicaAudioGenerator()
    assert gen._resolve_node_type("bold") == mm.audio_model_for_mood("bold")


def test_video_mood_resolves_when_no_explicit_model():
    gen = MagicaVideoGenerator()
    assert gen._resolve_node_type("energized") == "veo_3_1"
    assert gen._resolve_node_type("serene") == "kling_v3_pro"


def test_explicit_model_ignores_mood():
    gen = MagicaVideoGenerator(model_id="sora")
    assert gen._resolve_node_type("serene") == "sora_2"


def test_mood_for_unknown_mood_falls_back_to_default():
    assert mm.audio_model_for_mood("no_such_mood") == mm.DEFAULT_AUDIO_MODEL
    assert mm.video_model_for_mood("no_such_mood") == mm.DEFAULT_VIDEO_MODEL


# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------


def test_generate_audio_happy_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaAudioGenerator()

    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-audio-1", ["https://cdn.example/out.mp3"], b"fake-mp3-bytes"
    )

    with (
        patch.object(mm.httpx, "post", return_value=post_resp) as post,
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]) as get,
    ):
        path = gen.generate_audio(
            "melancholic piano instrumental",
            duration_seconds=30,
            seed=7,
            gallery_root=tmp_path,
        )

    assert path.exists()
    assert path.read_bytes() == b"fake-mp3-bytes"
    assert path.suffix == ".mp3"
    # Saved under gallery_root/YYYY/MM/DD/archive/.
    assert path.parent.name == "archive"

    (url,), kwargs = post.call_args
    assert url.endswith("/v1/nodes/elevenlabs_music/run")
    body = kwargs["json"]["input"]
    assert body["prompt"] == "melancholic piano instrumental"
    assert body["duration_seconds"] == 30
    assert body["seed"] == 7

    poll_url = get.call_args_list[0].args[0]
    assert poll_url.endswith("/v1/nodes/runs/run-audio-1")

    # Sidecar metadata written alongside the audio file.
    sidecar = path.with_suffix(".json")
    assert sidecar.exists()


def test_generate_video_happy_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaVideoGenerator()

    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-video-1", ["https://cdn.example/out.mp4"], b"fake-mp4-bytes"
    )

    with (
        patch.object(mm.httpx, "post", return_value=post_resp) as post,
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]) as get,
    ):
        path = gen.generate_video(
            "a serene misty forest at dawn",
            duration_seconds=5,
            aspect_ratio="16:9",
            gallery_root=tmp_path,
        )

    assert path.exists()
    assert path.read_bytes() == b"fake-mp4-bytes"
    assert path.suffix == ".mp4"
    assert path.parent.name == "archive"

    (url,), kwargs = post.call_args
    assert url.endswith("/v1/nodes/kling_v3_pro/run")
    body = kwargs["json"]["input"]
    assert body["prompt"] == "a serene misty forest at dawn"
    assert body["duration"] == 5
    assert body["aspect_ratio"] == "16:9"

    poll_url = get.call_args_list[0].args[0]
    assert poll_url.endswith("/v1/nodes/runs/run-video-1")


def test_generate_audio_kwargs_override_input(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaAudioGenerator()
    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-2", ["https://cdn.example/out.wav"], b"bytes"
    )
    with (
        patch.object(mm.httpx, "post", return_value=post_resp) as post,
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        path = gen.generate_audio("x", music_length_ms=45000, gallery_root=tmp_path)
    body = post.call_args.kwargs["json"]["input"]
    assert body["music_length_ms"] == 45000
    assert path.suffix == ".wav"


def test_generate_video_infers_extension_default_when_url_has_none(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaVideoGenerator()
    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-3", ["https://cdn.example/asset-without-extension"], b"bytes"
    )
    with (
        patch.object(mm.httpx, "post", return_value=post_resp),
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        path = gen.generate_video("x", gallery_root=tmp_path)
    assert path.suffix == ".mp4"


# --------------------------------------------------------------------------
# Budget guards
# --------------------------------------------------------------------------


def test_audio_budget_guard_blocks_over_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_AUDIO", "0")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_AUDIO", "1")
    gen = MagicaAudioGenerator()
    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-4", ["https://cdn.example/out.mp3"], b"bytes"
    )
    with (
        patch.object(mm.httpx, "post", return_value=post_resp),
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate_audio("x", gallery_root=tmp_path)  # consumes the only slot

    with pytest.raises(RuntimeError, match="budget exceeded"):
        gen.generate_audio("y", gallery_root=tmp_path)


def test_video_budget_guard_blocks_over_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_VIDEO", "1")
    gen = MagicaVideoGenerator()
    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-5", ["https://cdn.example/out.mp4"], b"bytes"
    )
    with (
        patch.object(mm.httpx, "post", return_value=post_resp),
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate_video("x", gallery_root=tmp_path)  # consumes the only slot

    with pytest.raises(RuntimeError, match="budget exceeded"):
        gen.generate_video("y", gallery_root=tmp_path)


def test_budget_routed_through_spend_guard(monkeypatch, tmp_path):
    # Spend is now tracked by the shared spend guard: generate_audio() must call
    # check_and_record_images with the kind-scoped provider, count, and cap.
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_AUDIO", "5")
    gen = MagicaAudioGenerator()
    post_resp, poll_resp, dl_resp = _mock_ok_run(
        "run-g", ["https://cdn.example/a.mp3"], b"a"
    )
    with (
        patch.object(mm, "check_and_record_images") as guard,
        patch.object(mm.httpx, "post", return_value=post_resp),
        patch.object(mm.httpx, "get", side_effect=[poll_resp, dl_resp]),
    ):
        gen.generate_audio("x", gallery_root=tmp_path)
    assert guard.call_args.args[0] == "magica_audio"
    assert guard.call_args.args[1] == 1
    assert guard.call_args.args[2] == 5


def test_audio_and_video_budgets_are_independent(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_AUDIO", "1")
    monkeypatch.setenv("LUMIRA_MAGICA_DAILY_MAX_VIDEO", "1")
    audio_gen = MagicaAudioGenerator()
    video_gen = MagicaVideoGenerator()

    a_post, a_poll, a_dl = _mock_ok_run("run-a", ["https://cdn.example/a.mp3"], b"a")
    with (
        patch.object(mm.httpx, "post", return_value=a_post),
        patch.object(mm.httpx, "get", side_effect=[a_poll, a_dl]),
    ):
        audio_gen.generate_audio("x", gallery_root=tmp_path)

    # Video budget is untouched by the audio spend above: it succeeds even
    # though the audio cap (1) is already consumed.
    v_post, v_poll, v_dl = _mock_ok_run("run-v", ["https://cdn.example/v.mp4"], b"v")
    with (
        patch.object(mm.httpx, "post", return_value=v_post),
        patch.object(mm.httpx, "get", side_effect=[v_poll, v_dl]),
    ):
        video_path = video_gen.generate_video("y", gallery_root=tmp_path)

    assert video_path.exists()


def test_generate_failed_run_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGICA_API_KEY", "k")
    gen = MagicaAudioGenerator()

    post_resp = MagicMock()
    post_resp.json.return_value = {"runId": "run-x"}
    post_resp.raise_for_status.return_value = None

    poll_resp = MagicMock()
    poll_resp.json.return_value = {"status": "FAILED", "error": "boom"}
    poll_resp.raise_for_status.return_value = None

    with (
        patch.object(mm.httpx, "post", return_value=post_resp),
        patch.object(mm.httpx, "get", return_value=poll_resp),
        pytest.raises(RuntimeError, match="failed"),
    ):
        gen.generate_audio("a prompt", gallery_root=tmp_path)
