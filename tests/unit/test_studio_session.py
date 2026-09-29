"""Studio session: hypothesis mode + after-image critique."""

from __future__ import annotations

from ai_artist.intelligence.studio_session import (
    choose_session_mode,
    hypothesis_seed,
    judge_finished_work,
    looks_like_slop,
    pick_archive_seed,
    refine_prompt,
    retries_allowed,
)


class TestChooseSessionMode:
    def test_continuation_when_series_drive_is_loud(self) -> None:
        mode = choose_session_mode(
            {
                "novelty": {"intensity": 0.4},
                "series_continuation": {"intensity": 0.8},
            }
        )
        assert mode == "continuation"

    def test_novelty_when_it_is_the_strongest_drive(self) -> None:
        mode = choose_session_mode(
            {
                "novelty": {"intensity": 0.7},
                "emotional_expression": {"intensity": 0.2},
            }
        )
        assert mode == "novelty"

    def test_introspective_from_emotional_drive(self) -> None:
        mode = choose_session_mode({"emotional_expression": {"intensity": 0.9}})
        assert mode == "introspective"

    def test_mashup_from_exploration(self) -> None:
        mode = choose_session_mode({"exploration": {"intensity": 0.6}})
        assert mode == "mashup"

    def test_quiet_drives_fall_back_to_surprise(self) -> None:
        assert choose_session_mode({"novelty": {"intensity": 0.1}}) == "surprise"
        assert choose_session_mode(None) == "surprise"


class TestHypothesisSeed:
    def test_introspective_seed_names_the_mood(self) -> None:
        seed = hypothesis_seed("introspective", mood="melancholic")
        assert "melancholic" in seed
        assert "uncertainty" in seed

    def test_outer_steer_is_appended(self) -> None:
        seed = hypothesis_seed(
            "continuation",
            mood="serene",
            outer_steer="Stay with water and withheld light.",
        )
        assert "Outer loop:" in seed
        assert "withheld light" in seed


class TestPickArchiveSeed:
    def test_none_unless_continuation(self) -> None:
        recent = [{"subject": "harbor", "prompt": "mist over a harbor", "score": 0.9}]
        assert pick_archive_seed(recent, "novelty") is None
        assert pick_archive_seed([], "continuation") is None

    def test_picks_the_highest_scored_recent_work(self) -> None:
        recent = [
            {
                "details": {
                    "subject": "kitchen",
                    "prompt": "a dim kitchen",
                    "style": "oil",
                    "score": 0.4,
                }
            },
            {
                "id": "harbor-1",
                "details": {
                    "subject": "harbor",
                    "prompt": "mist over a harbor",
                    "style": "ink",
                    "score": 0.91,
                },
            },
        ]
        seed = pick_archive_seed(recent, "continuation")
        assert seed is not None
        assert seed["subject"] == "harbor"
        assert seed["style"] == "ink"
        assert seed["source_id"] == "harbor-1"


class TestSlop:
    def test_stacked_marketing_tokens_are_slop(self) -> None:
        assert looks_like_slop(
            "a forest, masterpiece, 8k, trending on artstation, ultra detailed"
        )

    def test_overlapping_artstation_tokens_are_not_enough(self) -> None:
        """'artstation' used to double-count inside 'trending on artstation'."""
        assert not looks_like_slop("a forest, masterpiece, trending on artstation")

    def test_honest_prompt_is_not_slop(self) -> None:
        assert not looks_like_slop(
            "a dim kitchen at 4am, one window, steam from a kettle"
        )


class TestJudgeFinishedWork:
    def test_keeps_a_strong_score(self) -> None:
        verdict = judge_finished_work(
            score=0.88,
            prompt="a dim kitchen at 4am, one window, steam from a kettle",
            subject="kitchen",
        )
        assert verdict.keep is True
        assert verdict.should_retry is False
        assert verdict.reason == "ok"

    def test_retries_a_weak_score(self) -> None:
        verdict = judge_finished_work(
            score=0.41,
            prompt="a dim kitchen at 4am",
            subject="kitchen",
            similar_titles=["Last night's kitchen"],
        )
        assert verdict.should_retry is True
        assert verdict.reason == "score"
        assert "0.41" in verdict.critic_note
        assert "Last night's kitchen" in verdict.critic_note

    def test_retries_slop_even_without_a_score(self) -> None:
        verdict = judge_finished_work(
            score=None,
            prompt="masterpiece, 8k, trending on artstation, ultra detailed forest",
        )
        assert verdict.should_retry is True
        assert verdict.reason == "slop"

    def test_retries_a_repeated_subject(self) -> None:
        verdict = judge_finished_work(
            score=0.81,
            prompt="another mountain at dusk",
            subject="mountain",
            recent_subjects=["ocean", "mountain", "forest"],
        )
        assert verdict.should_retry is True
        assert verdict.reason == "repetition"

    def test_allow_repeat_keeps_a_deliberate_remix(self) -> None:
        verdict = judge_finished_work(
            score=0.81,
            prompt="another mountain at dusk",
            subject="mountain",
            recent_subjects=["ocean", "mountain", "forest"],
            allow_repeat=True,
        )
        assert verdict.keep is True
        assert verdict.reason == "ok"

    def test_budget_keeps_after_one_retry(self) -> None:
        verdict = judge_finished_work(
            score=0.3,
            prompt="masterpiece, 8k, trending on artstation, ultra detailed",
            already_retried=True,
        )
        assert verdict.keep is True
        assert verdict.reason == "budget"


class TestRefinePrompt:
    def test_strips_slop_and_adds_mood_craft(self) -> None:
        refined = refine_prompt(
            prompt="a forest, masterpiece, 8k, trending on artstation",
            subject="forest",
            mood="serene",
            reason="slop",
        )
        lowered = refined.lower()
        assert "masterpiece" not in lowered
        assert "8k" not in lowered
        assert "artstation" not in lowered
        assert "forest" in lowered
        assert "uncluttered" in lowered or "gradients" in lowered

    def test_names_the_archive_neighbor(self) -> None:
        refined = refine_prompt(
            prompt="mist over a harbor",
            similar_titles=["Harbor at dusk"],
            reason="score",
        )
        assert "Harbor at dusk" in refined


class TestRetriesAllowed:
    def test_default_allows_retry(self, monkeypatch) -> None:
        monkeypatch.delenv("LUMIRA_SESSION_RETRY", raising=False)
        assert retries_allowed() is True

    def test_env_can_disable_retry(self, monkeypatch) -> None:
        monkeypatch.setenv("LUMIRA_SESSION_RETRY", "0")
        assert retries_allowed() is False
