"""Tests for prompt quality / anti-spam helpers."""

from ai_artist.utils.prompt_quality import is_trivial_prompt, normalize_prompt_key


def test_trivial_prompts_rejected():
    assert is_trivial_prompt("test")
    assert is_trivial_prompt("TEST")
    assert is_trivial_prompt("  foo  ")
    assert is_trivial_prompt("test, something")
    assert is_trivial_prompt("ab")  # too short
    assert is_trivial_prompt("")
    assert is_trivial_prompt(None)
    assert is_trivial_prompt("E2E test artwork")
    assert is_trivial_prompt("playwright smoke check")


def test_real_prompts_accepted():
    assert not is_trivial_prompt("a lonely pier at dusk")
    assert not is_trivial_prompt("phoenix, atmospheric, rainbow hues")
    assert not is_trivial_prompt("silence made visible")


def test_normalize_collapses_whitespace():
    assert normalize_prompt_key("  Hello   World  ") == "hello world"
