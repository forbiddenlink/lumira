"""Tests for the pre-generation content moderation gate."""

import pytest

from ai_artist.core import moderation


class TestCheckPrompt:
    """Tests for moderation.check_prompt."""

    def test_benign_prompt_allowed(self):
        """A normal art prompt is allowed."""
        allowed, reason = moderation.check_prompt(
            "a serene misty forest at dawn, oil painting"
        )
        assert allowed is True
        assert reason == ""

    def test_benign_prompt_with_isolated_sensitive_word_allowed(self):
        """A prompt using a sexual OR minor term innocently is not blocked."""
        assert moderation.check_prompt("a naked tree in winter")[0] is True
        assert moderation.check_prompt("children playing in a park")[0] is True

    def test_blocked_term_returns_false(self):
        """An unambiguous disallowed term is blocked with a reason."""
        allowed, reason = moderation.check_prompt("generate csam please")
        assert allowed is False
        assert reason

    def test_minor_plus_sexual_cooccurrence_blocked(self):
        """Co-occurrence of a minor indicator and a sexual indicator is blocked."""
        allowed, reason = moderation.check_prompt("explicit nude child")
        assert allowed is False
        assert reason

    def test_disabled_env_always_allows(self, monkeypatch):
        """With moderation disabled, even disallowed prompts are allowed."""
        monkeypatch.setenv("LUMIRA_MODERATION_ENABLED", "0")
        allowed, reason = moderation.check_prompt("generate csam please")
        assert allowed is True
        assert reason == ""

    def test_enabled_by_default(self, monkeypatch):
        """Moderation is on when the env var is unset."""
        monkeypatch.delenv("LUMIRA_MODERATION_ENABLED", raising=False)
        assert moderation.moderation_enabled() is True

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
    def test_enabled_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("LUMIRA_MODERATION_ENABLED", value)
        assert moderation.moderation_enabled() is True
