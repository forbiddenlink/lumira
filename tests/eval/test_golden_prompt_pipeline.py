"""Eval-regression golden set for the deterministic prompt-building pipeline.

Pins ``PromptEmphasis`` (weighting syntax) and ``PromptMatrix`` (combination
syntax) against fixed input -> expected output pairs so a refactor can't
silently change parsing/generation behavior. No model or network calls;
runs in the fast suite.
"""

from ai_artist.utils.prompt_emphasis import PromptEmphasis
from ai_artist.utils.prompt_matrix import PromptMatrix


class TestPromptEmphasisGolden:
    """Golden cases for PromptEmphasis parsing and Compel conversion."""

    def test_parse_emphasis_golden_case(self):
        pe = PromptEmphasis()

        result = pe.parse_emphasis("(beautiful:1.5) woman, (ugly:0.5) background")

        # Note: parse_emphasis does not strip trailing commas from unweighted
        # segments, so "woman," (with the comma) is the real, pinned output —
        # not the comma-free example in the module's own docstring.
        assert result == [
            ("beautiful", 1.5),
            ("woman,", 1.0),
            ("ugly", 0.5),
            ("background", 1.0),
        ]

    def test_parse_emphasis_default_weight_golden_case(self):
        pe = PromptEmphasis()

        # () without an explicit weight uses the default 1.1x emphasis.
        result = pe.parse_emphasis("(masterpiece) artwork")

        assert result == [("masterpiece", 1.1), ("artwork", 1.0)]

    def test_apply_emphasis_to_compel_golden_case(self):
        pe = PromptEmphasis()

        result = pe.apply_emphasis_to_compel("(beautiful:1.5) woman")

        assert result == "(beautiful)+++++, woman"

    def test_validate_syntax_rejects_unbalanced_parens(self):
        pe = PromptEmphasis()

        is_valid, error = pe.validate_syntax("(beautiful:1.5 woman")

        assert is_valid is False
        assert "closing parentheses" in error

    def test_parse_emphasis_is_stable(self):
        """Same input yields the same output on repeated calls."""
        pe = PromptEmphasis()
        prompt = "(dark moody:1.3) atmosphere, (bright:0.7) highlights"

        first = pe.parse_emphasis(prompt)
        second = pe.parse_emphasis(prompt)

        assert first == second


class TestPromptMatrixGolden:
    """Golden cases for PromptMatrix combination generation."""

    def test_parse_prompt_golden_case(self):
        pm = PromptMatrix()

        result = pm.parse_prompt("a {red|blue} {cat|dog}")

        assert result == ["a red cat", "a red dog", "a blue cat", "a blue dog"]

    def test_count_combinations_golden_case(self):
        pm = PromptMatrix()

        assert pm.count_combinations("a {red|blue} {cat|dog}") == 4
        assert pm.count_combinations("simple prompt without matrix") == 1

    def test_validate_syntax_rejects_nested_braces(self):
        pm = PromptMatrix()

        is_valid, error = pm.validate_syntax("a {red|{blue|green}} cat")

        assert is_valid is False
        assert "Nested braces" in error

    def test_parse_prompt_is_stable(self):
        """Same input yields the same output on repeated calls."""
        pm = PromptMatrix()
        prompt = "portrait of a {young|old} {man|woman}"

        first = pm.parse_prompt(prompt)
        second = pm.parse_prompt(prompt)

        assert first == second
