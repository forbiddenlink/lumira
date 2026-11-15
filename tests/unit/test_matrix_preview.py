"""Pure matrix-preview regressions; synthetic text only, no generation calls."""

from ai_artist.utils.prompt_matrix import PromptMatrix


def test_preview_matches_prefix_of_full_expansion():
    matrix = PromptMatrix()
    prompt = "a {red|blue} {cat|dog}"
    rows, total = matrix.preview_prompt(prompt, 3)
    assert rows == matrix.parse_prompt(prompt)[:3]
    assert total == 4


def test_large_matrix_preview_never_expands_all_combinations():
    rows, total = PromptMatrix().preview_prompt("{a|b}" * 60, 2)
    assert len(rows) == 2
    assert total == 2**60
    assert rows[0] == "a" * 60


def test_plain_prompt_remains_single_item():
    assert PromptMatrix().preview_prompt("a quiet landscape") == (
        ["a quiet landscape"],
        1,
    )


def test_preview_rejects_invalid_limits():
    for limit in (0, -1, 51, 1.5, True, "3"):
        try:
            PromptMatrix().preview_prompt("{a|b}", limit)
        except ValueError as error:
            assert "limit" in str(error)
        else:
            raise AssertionError(f"Accepted invalid limit {limit}")


def test_preview_rejects_empty_and_malformed_options():
    for prompt in ("{}", "{a||b}", "{a|b", "{{a|b}}", "{only}"):
        try:
            PromptMatrix().preview_prompt(prompt)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted malformed prompt {prompt}")


def test_preview_prompt_length_is_bounded():
    try:
        PromptMatrix().preview_prompt("x" * 2001)
    except ValueError as error:
        assert "2000" in str(error)
    else:
        raise AssertionError("Accepted oversized prompt")
