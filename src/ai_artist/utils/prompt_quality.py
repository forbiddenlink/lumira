"""Prompt quality helpers shared by web routes and gallery listing."""

from __future__ import annotations

_TRIVIAL_PROMPTS = frozenset(
    {
        "test",
        "testing",
        "foo",
        "bar",
        "asdf",
        "hello",
        "hi",
        "sample",
        "demo",
        "placeholder",
    }
)


def normalize_prompt_key(prompt: str) -> str:
    """Normalize a prompt for duplicate comparison."""
    return " ".join((prompt or "").strip().lower().split())


def is_trivial_prompt(prompt: str | None) -> bool:
    """Return True for junk / harness prompts that must never enter the gallery."""
    key = normalize_prompt_key(prompt or "")
    if not key:
        return True
    if key in _TRIVIAL_PROMPTS:
        return True
    if key.startswith("test,") or key.startswith("test "):
        return True
    return len(key) < 3
