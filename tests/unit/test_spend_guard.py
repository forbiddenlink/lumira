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


def test_llm_cost_estimate_scales_with_tokens(sg):
    small = sg.estimate_llm_cost_usd(100, 100)
    big = sg.estimate_llm_cost_usd(10_000, 10_000)
    assert big > small > 0
