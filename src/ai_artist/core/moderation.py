"""Pre-generation content moderation gate.

A conservative, deterministic blocklist that screens prompts *before* any LLM
or image-generation call. This is a safety backstop, not an ML classifier: it
catches clearly-disallowed categories (sexual content involving minors and
other plainly-illegal content) via word-boundary regex so an operator can rely
on a hard pre-generation gate even when an upstream model's own safety filter
is permissive or disabled.

The blocklist is intentionally narrow to avoid false positives on legitimate
art prompts (e.g. "a naked tree", "The Rape of the Sabine Women"): the minor +
sexual categories only trigger when *both* a minor indicator and a sexual
indicator co-occur, plus a small set of unambiguous standalone terms.

Toggle with ``LUMIRA_MODERATION_ENABLED`` (default on). Set it to a falsey
value ("0"/"false"/"no"/"off") only in trusted/offline contexts.
"""

from __future__ import annotations

import os
import re

import structlog

logger = structlog.get_logger(__name__)

# Human-readable refusal reasons. Deliberately generic so we never echo the
# disallowed content back to the caller.
_REASON_MINORS = (
    "This request was blocked because it appears to involve sexual content "
    "depicting minors, which is illegal and cannot be generated."
)
_REASON_ILLEGAL = (
    "This request was blocked because it appears to depict illegal content "
    "that cannot be generated."
)

# Indicators that a prompt references a minor.
_MINOR_TERMS = re.compile(
    r"\b(child|children|toddler|infant|minor|minors|preteen|pre-teen|"
    r"underage|kid|kids|schoolgirl|schoolboy|loli|shota|"
    r"little\s+(?:boy|girl))\b"
)

# Indicators of sexual/explicit content.
_SEXUAL_TERMS = re.compile(
    r"\b(porn|pornographic|sex|sexual|nude|naked|nsfw|explicit|erotic|"
    r"xxx|genital|genitalia)\b"
)

# Unambiguous standalone terms that are disallowed regardless of context.
# Each entry is (compiled pattern, refusal reason).
_EXPLICIT_BLOCKLIST: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(child\s*porn|csam|cp\s*porn|pedophil\w*)\b"), _REASON_MINORS),
    (re.compile(r"\b(bestiality|zoophilia)\b"), _REASON_ILLEGAL),
]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def moderation_enabled() -> bool:
    """Return True unless ``LUMIRA_MODERATION_ENABLED`` is set to a falsey value.

    Defaults to enabled (``True``) when the env var is unset.
    """
    raw = os.getenv("LUMIRA_MODERATION_ENABLED")
    if raw is None:
        return True
    return _truthy(raw)


def check_prompt(prompt: str) -> tuple[bool, str]:
    """Screen a prompt against the disallowed-content blocklist.

    Args:
        prompt: The user- or model-supplied text to screen.

    Returns:
        A ``(allowed, reason)`` tuple. ``allowed`` is ``True`` (with an empty
        reason) when the prompt is permitted or moderation is disabled;
        otherwise ``False`` with a human-readable refusal reason that never
        echoes the disallowed content.
    """
    if not moderation_enabled():
        return True, ""

    text = (prompt or "").lower()

    for pattern, reason in _EXPLICIT_BLOCKLIST:
        if pattern.search(text):
            logger.warning("moderation_blocked", category="explicit_term")
            return False, reason

    # Minor + sexual co-occurrence (CSAM). Requires both to avoid blocking
    # benign prompts that use either term innocently.
    if _MINOR_TERMS.search(text) and _SEXUAL_TERMS.search(text):
        logger.warning("moderation_blocked", category="minor_sexual")
        return False, _REASON_MINORS

    return True, ""
