"""Studio session: hypothesis before paint, critique after the picture exists.

Concept critique already happens in ``ArtistCritic``. This module is the
missing inner loop — Lumira looks at the finished work (score, slop, repetition)
and either keeps it or takes one more pass. Inspired by Botto's 2025/26
creative-reasoning engine, kept small and spend-aware (max one retry).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..utils.logging import get_logger

logger = get_logger(__name__)

SessionMode = Literal[
    "introspective",
    "novelty",
    "continuation",
    "mashup",
    "surprise",
]

KEEP_THRESHOLD = 0.72
MAX_RETRIES = 1

# Stacked marketing tokens that make a prompt look like generic "AI slop"
_SLOP_MARKERS = (
    "trending on artstation",
    "ultra detailed",
    "ultra-detailed",
    "highly detailed",
    "award-winning",
    "award winning",
    "best quality",
    "cinematic lighting",
    "unreal engine",
    "octane render",
    "masterpiece",
    "8k",
    "4k",
    "uhd",
)

_MOOD_CRAFT: dict[str, str] = {
    "contemplative": "quiet negative space, one decisive focal point",
    "chaotic": "fractured rhythm, colliding marks, controlled accident",
    "melancholic": "muted temperature, long shadow, withheld light",
    "energized": "kinetic composition, saturated contrast, forward motion",
    "rebellious": "off-axis crop, raw surface, refusal of polish",
    "serene": "slow gradients, even breath, uncluttered plane",
    "restless": "overlapping layers, unresolved edge, visual itch",
    "playful": "unexpected scale, a sly color joke, lightness",
    "introspective": "inward symbol, private geometry, dim interior",
    "bold": "one large gesture, high contrast, no apology",
}


@dataclass(frozen=True)
class StudioVerdict:
    """Whether the finished picture is good enough to keep."""

    keep: bool
    score: float | None
    critic_note: str
    reason: str
    compared_to: tuple[str, ...] = ()

    @property
    def should_retry(self) -> bool:
        """True when she should generate one more time."""
        return not self.keep


def choose_session_mode(drive_status: dict[str, Any] | None) -> SessionMode:
    """Pick a hypothesis mode from the loudest creative drive.

    Mapping (Botto-style, through Lumira's existing drives):
    - series / thematic continuation → continuation
    - novelty → novelty
    - exploration → mashup
    - emotional_expression → introspective
    - otherwise → surprise
    """
    drives = drive_status or {}
    intensities: dict[str, float] = {}
    for name, payload in drives.items():
        if isinstance(payload, dict):
            try:
                intensities[name] = float(payload.get("intensity") or 0)
            except (TypeError, ValueError):
                intensities[name] = 0.0
        else:
            try:
                intensities[name] = float(payload)
            except (TypeError, ValueError):
                intensities[name] = 0.0

    series = max(
        intensities.get("series_continuation", 0.0),
        intensities.get("thematic_continuation", 0.0),
    )
    if series >= 0.65:
        return "continuation"

    ranked = sorted(intensities.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < 0.35:
        return "surprise"

    top = ranked[0][0]
    if top in {"series_continuation", "thematic_continuation"}:
        return "continuation"
    if top == "novelty":
        return "novelty"
    if top == "exploration":
        return "mashup"
    if top == "emotional_expression":
        return "introspective"
    return "surprise"


def hypothesis_seed(
    mode: SessionMode,
    *,
    mood: str,
    outer_steer: str | None = None,
) -> str:
    """A short creative intent that seeds ``CreativeMind`` context."""
    mood_l = (mood or "contemplative").strip().lower() or "contemplative"
    seeds: dict[SessionMode, str] = {
        "introspective": (
            f"What does my {mood_l} uncertainty look like if I paint it honestly, "
            "without illustrating the word?"
        ),
        "novelty": (
            "A subject I have not returned to recently — unfamiliar, specific, "
            "and a little dangerous."
        ),
        "continuation": (
            "Continue a visual thread from recent work: same family of forms, "
            "a new sentence."
        ),
        "mashup": (
            "Two things that should not share a canvas, forced into one atmosphere."
        ),
        "surprise": (f"Whatever the {mood_l} mood actually wants, not a safe default."),
    }
    text = seeds[mode]
    steer = (outer_steer or "").strip()
    if steer:
        text = f"{text} Outer loop: {steer[:280]}"
    return text


def pick_archive_seed(
    recent: list[dict[str, Any]] | None,
    mode: SessionMode,
) -> dict[str, str] | None:
    """Pick a recent work to continue — prompt-level remix, not img2img.

    Magica's generate path cannot take a reference image, so continuation is
    honest at the prompt: same subject family, a new sentence. Returns None
    unless the session is continuation and something paintable exists.
    """
    if mode != "continuation" or not recent:
        return None
    ranked: list[tuple[float, dict[str, str]]] = []
    for item in recent:
        raw_details = item.get("details")
        details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
        subject = str(details.get("subject") or item.get("subject") or "").strip()
        prompt = str(details.get("prompt") or item.get("prompt") or "").strip()
        style = str(details.get("style") or item.get("style") or "").strip()
        if not subject and not prompt:
            continue
        raw_score = details.get("score", item.get("score", item.get("final_score", 0)))
        try:
            score = float(raw_score or 0)
        except (TypeError, ValueError):
            score = 0.0
        ranked.append(
            (
                score,
                {
                    "subject": subject or prompt.split(",")[0][:80],
                    "style": style,
                    "prompt": prompt or subject,
                    "source_id": str(item.get("id") or details.get("id") or ""),
                },
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1]


def looks_like_slop(prompt: str | None) -> bool:
    """True when a prompt is stuffed with generic image-model marketing tokens."""
    text = (prompt or "").strip().lower()
    if not text:
        return False
    hits = sum(1 for marker in _SLOP_MARKERS if marker in text)
    return hits >= 3


def judge_finished_work(
    *,
    score: float | None,
    prompt: str,
    subject: str | None = None,
    recent_subjects: list[str] | None = None,
    similar_titles: list[str] | None = None,
    already_retried: bool = False,
    keep_threshold: float = KEEP_THRESHOLD,
    allow_repeat: bool = False,
) -> StudioVerdict:
    """Look at the finished picture (and its prompt) and decide keep vs retry.

    Signals, in order:
    1. Already retried once — keep whatever we have (spend cap).
    2. Real CLIP/aesthetic score below threshold — retry.
    3. Prompt is slop — retry.
    4. Subject repeats the last few works — retry (unless ``allow_repeat``,
       used when continuation is deliberately remixing a recent piece).
    Otherwise keep.
    """
    compared = tuple(t for t in (similar_titles or []) if t)[:3]
    subject_l = (subject or "").strip().lower()
    recent = {(s or "").strip().lower() for s in (recent_subjects or []) if s}

    if already_retried:
        return StudioVerdict(
            keep=True,
            score=score,
            critic_note="One more pass is enough. I will live with this one.",
            reason="budget",
            compared_to=compared,
        )

    if score is not None and score < keep_threshold:
        note = (
            f"The picture scores {score:.2f} — below the bar I set for myself. "
            "I want another attempt with a clearer intent."
        )
        if compared:
            note += f" It sits too close to {compared[0]}."
        return StudioVerdict(
            keep=False,
            score=score,
            critic_note=note,
            reason="score",
            compared_to=compared,
        )

    if looks_like_slop(prompt):
        return StudioVerdict(
            keep=False,
            score=score,
            critic_note=(
                "The prompt is dressed in generic 'AI art' language. "
                "I will strip the costume and paint from the idea itself."
            ),
            reason="slop",
            compared_to=compared,
        )

    if subject_l and subject_l in recent and not allow_repeat:
        return StudioVerdict(
            keep=False,
            score=score,
            critic_note=(
                f"I just painted '{subject}'. Repeating it would be habit, not desire. "
                "One more pass, from a different angle."
            ),
            reason="repetition",
            compared_to=compared,
        )

    if score is None:
        note = "I cannot score this yet, but the intent is mine. Keeping it."
    else:
        note = f"This holds. Score {score:.2f} — I will keep it."
    if compared:
        note += f" Neighbors in the archive: {', '.join(compared)}."
    return StudioVerdict(
        keep=True,
        score=score,
        critic_note=note,
        reason="ok",
        compared_to=compared,
    )


def refine_prompt(
    *,
    prompt: str,
    subject: str | None = None,
    style: str | None = None,
    mood: str | None = None,
    similar_titles: list[str] | None = None,
    reason: str = "score",
) -> str:
    """Rewrite the prompt for a single retry — strip slop, add specific craft."""
    text = (prompt or "").strip()
    lowered = text.lower()
    for marker in sorted(_SLOP_MARKERS, key=len, reverse=True):
        idx = lowered.find(marker)
        while idx != -1:
            text = (text[:idx] + text[idx + len(marker) :]).strip(" ,;")
            lowered = text.lower()
            idx = lowered.find(marker)

    text = " ".join(text.split())
    if not text:
        bits = [b for b in (subject, style) if b]
        text = ", ".join(bits) if bits else "an original composition"

    mood_l = (mood or "").strip().lower()
    craft = _MOOD_CRAFT.get(mood_l)
    if craft and craft.lower() not in text.lower():
        text = f"{text}, {craft}"

    if reason == "repetition" and subject:
        text = f"{text}, a new vantage, not another {subject}"
    elif similar_titles:
        title = similar_titles[0]
        if title.lower() not in text.lower():
            text = f"{text}, distinct from «{title}»"

    return text[:600]


def retries_allowed() -> bool:
    """False when ``LUMIRA_SESSION_RETRY=0`` — skip the extra generation."""
    import os

    flag = os.getenv("LUMIRA_SESSION_RETRY", "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}
