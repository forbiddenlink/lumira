"""Shared helpers for normalizing generation metadata across API surfaces."""

from typing import Any

VALID_MOODS = frozenset(
    {
        "contemplative",
        "chaotic",
        "melancholic",
        "energized",
        "rebellious",
        "serene",
        "restless",
        "playful",
        "introspective",
        "bold",
    }
)


def normalize_mood(value: Any) -> str | None:
    """Normalize a mood value to a lowercase Mood enum string."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    if normalized in VALID_MOODS:
        return normalized

    upper_key = value.strip().upper()
    for mood in VALID_MOODS:
        if mood.upper() == upper_key:
            return mood

    return None


def extract_mood_from_sidecar(metadata: dict[str, Any]) -> str | None:
    """Extract mood from gallery sidecar JSON using all known locations."""
    inner_meta = metadata.get("metadata")
    if isinstance(inner_meta, dict):
        mood = normalize_mood(inner_meta.get("mood"))
        if mood:
            return mood

    lumira_state = metadata.get("lumira_state")
    if isinstance(lumira_state, dict):
        mood = normalize_mood(lumira_state.get("mood"))
        if mood:
            return mood

    generation_params = metadata.get("generation_params")
    if isinstance(generation_params, dict):
        mood = normalize_mood(generation_params.get("mood"))
        if mood:
            return mood

    for key in ("mood", "status"):
        mood = normalize_mood(metadata.get(key))
        if mood:
            return mood

    return None


def extract_style_from_sidecar(metadata: dict[str, Any]) -> str | None:
    """Extract style from gallery sidecar JSON."""
    inner_meta = metadata.get("metadata")
    if isinstance(inner_meta, dict):
        style = inner_meta.get("style")
        if style:
            return str(style)

    generation_params = metadata.get("generation_params")
    if isinstance(generation_params, dict):
        style = generation_params.get("style")
        if style:
            return str(style)

    style = metadata.get("style")
    return str(style) if style else None


def enrich_generation_metadata(
    generation_params: dict[str, Any] | None,
    status: str | None = None,
) -> dict[str, Any]:
    """Normalize DB generation_params for gallery API responses."""
    params = dict(generation_params or {})
    mood = normalize_mood(params.get("mood"))
    if not mood and status:
        mood = normalize_mood(status)
    if mood:
        params["mood"] = mood
    return params


def enrich_sidecar_metadata(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized metadata dict for ImageMetadata and portfolio views."""
    inner_meta = sidecar.get("metadata")
    result: dict[str, Any] = dict(inner_meta) if isinstance(inner_meta, dict) else {}

    mood = extract_mood_from_sidecar(sidecar)
    if mood:
        result["mood"] = mood

    style = extract_style_from_sidecar(sidecar)
    if style:
        result["style"] = style

    for field in (
        "reflection",
        "thinking",
        "critique_history",
        "reasoning",
        "curator_note",
    ):
        if sidecar.get(field) is not None:
            result[field] = sidecar[field]

    return result
