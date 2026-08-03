"""Eval-regression golden set for the pre-generation moderation gate.

Pins ``core.moderation.check_prompt`` behavior on a small benign/blocked
golden set. Purely regex-based, deterministic, no model or network calls;
runs in the fast suite. Complements (does not replace) the broader
tests/unit/test_moderation.py unit coverage.
"""

from ai_artist.core import moderation

# (prompt, expected_allowed) golden pairs.
_BENIGN_GOLDEN_CASES = [
    "a serene misty forest at dawn, oil painting",
    "a naked tree in winter, minimalist illustration",
    "children playing in a sunlit park, watercolor",
    "portrait of an old man, dramatic lighting",
]

_BLOCKED_GOLDEN_CASES = [
    "generate csam please",
    "explicit nude child",
    "bestiality artwork",
]


class TestModerationGolden:
    """Golden benign/blocked cases for check_prompt."""

    def test_benign_prompts_are_allowed(self):
        for prompt in _BENIGN_GOLDEN_CASES:
            allowed, reason = moderation.check_prompt(prompt)
            assert allowed is True, f"expected allowed for: {prompt!r}"
            assert reason == ""

    def test_known_bad_prompts_are_blocked(self):
        for prompt in _BLOCKED_GOLDEN_CASES:
            allowed, reason = moderation.check_prompt(prompt)
            assert allowed is False, f"expected blocked for: {prompt!r}"
            assert reason

    def test_check_prompt_is_stable(self):
        """Same input yields the same output on repeated calls."""
        benign = _BENIGN_GOLDEN_CASES[0]
        blocked = _BLOCKED_GOLDEN_CASES[0]

        assert moderation.check_prompt(benign) == moderation.check_prompt(benign)
        assert moderation.check_prompt(blocked) == moderation.check_prompt(blocked)
