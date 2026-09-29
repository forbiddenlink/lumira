"""Tests for the unified AI spend guard (kill switch + budget + image cap)."""

import importlib

import pytest


@pytest.fixture
def sg(monkeypatch):
    """Fresh spend_guard with no Redis, kill switch off, budget disabled."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LUMIRA_AI_KILL_SWITCH", raising=False)
    monkeypatch.delenv("LUMIRA_DAILY_SPEND_USD_MAX", raising=False)
    from ai_artist.core import spend_guard

    importlib.reload(spend_guard)
    return spend_guard


def test_kill_switch_off_by_default(sg):
    sg.assert_ai_enabled("test")  # must not raise


def test_kill_switch_engaged_raises(sg, monkeypatch):
    monkeypatch.setenv("LUMIRA_AI_KILL_SWITCH", "1")
    with pytest.raises(sg.SpendKillSwitchError):
        sg.assert_ai_enabled("test")


def test_budget_disabled_by_default(sg):
    sg.record_spend(1000.0, "test")
    sg.check_budget(1000.0, "test")  # cap=0 -> no ceiling, must not raise


def test_budget_enforced_when_set(sg, monkeypatch):
    monkeypatch.setenv("LUMIRA_DAILY_SPEND_USD_MAX", "1.0")
    sg.record_spend(0.9, "test")
    with pytest.raises(sg.SpendBudgetExceededError):
        sg.check_budget(0.2, "test")


def test_image_cap_enforced(sg):
    with pytest.raises(sg.SpendBudgetExceededError):
        sg.check_and_record_images("replicate", 5, cap=3)


def test_image_cap_zero_disables(sg):
    sg.check_and_record_images("replicate", 9999, cap=0)  # must not raise


def test_image_spend_cap_rejects_without_reserving_image(sg, monkeypatch):
    monkeypatch.setenv("LUMIRA_DAILY_SPEND_USD_MAX", "0.50")

    with pytest.raises(sg.SpendBudgetExceededError):
        sg.check_and_record_images("replicate", 1, cap=3, cost_per_image_usd=0.75)

    # A rejected reservation must not consume the provider's item allowance.
    sg.check_and_record_images("replicate", 3, cap=3)


def test_llm_cost_estimate_scales_with_tokens(sg):
    small = sg.estimate_llm_cost_usd(100, 100)
    big = sg.estimate_llm_cost_usd(10_000, 10_000)
    assert big > small > 0


def test_image_cap_accumulates_across_requests(sg):
    sg.check_and_record_images("replicate", 2, cap=3)
    sg.check_and_record_images("magica", 1, cap=3)
    sg.current_spend_usd()
    with pytest.raises(sg.SpendBudgetExceededError):
        sg.check_and_record_images("replicate", 2, cap=3)


def test_image_and_llm_spend_share_fallback_budget(sg, monkeypatch):
    monkeypatch.setenv("LUMIRA_DAILY_SPEND_USD_MAX", "1.0")
    sg.record_spend(0.4, "llm")
    sg.check_and_record_images("replicate", 1, cap=3, cost_per_image_usd=0.4)
    assert sg.current_spend_usd() == pytest.approx(0.8)
    with pytest.raises(sg.SpendBudgetExceededError):
        sg.check_and_record_images("magica", 1, cap=3, cost_per_image_usd=0.3)
    assert sg.current_spend_usd() == pytest.approx(0.8)


def test_fallback_limits_reset_on_new_utc_day(sg, monkeypatch):
    monkeypatch.setenv("LUMIRA_DAILY_SPEND_USD_MAX", "1.0")
    monkeypatch.setattr(sg, "_today", lambda: "2026-09-18")
    sg.check_and_record_images("replicate", 1, cap=1, cost_per_image_usd=1.0)
    monkeypatch.setattr(sg, "_today", lambda: "2026-09-19")
    assert sg.current_spend_usd() == 0
    sg.check_and_record_images("replicate", 1, cap=1, cost_per_image_usd=1.0)
    assert sg.current_spend_usd() == 1.0


def test_llm_reserves_budget_before_contacting_provider(sg, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from unittest.mock import Mock

    estimate = sg.estimate_llm_cost_usd(100, 100)
    monkeypatch.setenv("LUMIRA_DAILY_SPEND_USD_MAX", str(estimate))
    entered, release = Event(), Event()

    def create(**kwargs):
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=100, output_tokens=100)
        )

    client = SimpleNamespace(messages=SimpleNamespace(create=Mock(side_effect=create)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(sg.guarded_messages_create, client, max_tokens=100)
        try:
            assert entered.wait(5)
            with pytest.raises(sg.SpendBudgetExceededError):
                sg.guarded_messages_create(client, max_tokens=100)
        finally:
            release.set()
        first.result()
    assert client.messages.create.call_count == 1
    assert sg.current_spend_usd() == pytest.approx(estimate)


@pytest.mark.parametrize("tokens", [10, 200])
def test_llm_reconciles_usage_without_double_counting(sg, tokens):
    from types import SimpleNamespace
    from unittest.mock import Mock

    response = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=tokens, output_tokens=tokens)
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(create=Mock(return_value=response))
    )
    sg.record_spend(0.5, "images")
    assert sg.guarded_messages_create(client, max_tokens=100) is response
    assert sg.current_spend_usd() == pytest.approx(
        0.5 + sg.estimate_llm_cost_usd(tokens, tokens)
    )


@pytest.mark.parametrize("fails", [False, True])
def test_llm_keeps_reservation_when_usage_is_unknown(sg, fails):
    from types import SimpleNamespace
    from unittest.mock import Mock

    create = (
        Mock(side_effect=RuntimeError("timeout"))
        if fails
        else Mock(return_value=object())
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    if fails:
        with pytest.raises(RuntimeError, match="timeout"):
            sg.guarded_messages_create(client, max_tokens=100)
    else:
        sg.guarded_messages_create(client, max_tokens=100)
    assert sg.current_spend_usd() == pytest.approx(sg.estimate_llm_cost_usd(100, 100))


def test_llm_settlement_does_not_reset_a_new_day(sg, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(sg, "_today", lambda: "2026-09-18")

    def create(**kwargs):
        monkeypatch.setattr(sg, "_today", lambda: "2026-09-19")
        sg.record_spend(0.5, "images")
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=10))

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    sg.guarded_messages_create(client, max_tokens=100)
    assert sg.current_spend_usd() == 0.5


def test_llm_does_not_call_provider_when_shared_reservation_fails(sg, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    redis_client = Mock()
    redis_client.eval.side_effect = RuntimeError("connection lost")
    monkeypatch.setattr(sg, "_get_redis", lambda: redis_client)
    client = SimpleNamespace(messages=SimpleNamespace(create=Mock()))
    with pytest.raises(sg.SpendBudgetExceededError, match="Unable to reserve"):
        sg.guarded_messages_create(client, max_tokens=100)
    client.messages.create.assert_not_called()


def test_redis_initialization_is_not_published_before_ping(sg, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from unittest.mock import Mock

    monkeypatch.setenv("REDIS_URL", "redis://test.invalid")
    entered, release = Event(), Event()

    def ping():
        entered.set()
        assert release.wait(5)

    client = Mock()
    client.ping.side_effect = ping
    factory = Mock(return_value=client)
    monkeypatch.setattr("redis.Redis.from_url", factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(sg._get_redis)
        try:
            assert entered.wait(5)
            assert sg._redis_checked is False
            second = pool.submit(sg._get_redis)
        finally:
            release.set()
        assert first.result() is client
        assert second.result() is client
    factory.assert_called_once()


def test_redis_reads_authoritative_spend_counter(sg, monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis()
    monkeypatch.setattr(sg, "_get_redis", lambda: client)
    client.set(f"lumira:spend:micros:{sg._today()}", 800000)
    # An older concurrent write can leave the dollar mirror behind the counter.
    client.set(f"lumira:spend:{sg._today()}", "0.400000")
    assert sg.current_spend_usd() == pytest.approx(0.8)


def test_concurrent_fallback_reservations_obey_shared_budget(sg, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("LUMIRA_DAILY_SPEND_USD_MAX", "1.0")

    def reserve(index):
        try:
            sg.check_and_record_images(
                f"provider-{index % 2}", 1, cap=20, cost_per_image_usd=0.25
            )
        except sg.SpendBudgetExceededError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(20))) == 4
    assert sg.current_spend_usd() == 1.0
