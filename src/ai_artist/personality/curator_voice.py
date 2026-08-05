"""Compose a short curator voice line for why a piece fits Lumira's body of work.

Uses the knowledge graph when available, with graceful fallbacks to thematic
series and adaptive taste — so the gallery always has something honest to say
even without FalkorDB.
"""

from __future__ import annotations

from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


def compose_curator_voice(
    *,
    mood: str | None = None,
    prompt: str | None = None,
    artwork_id: str | None = None,
    subject: str | None = None,
    style: str | None = None,
) -> str:
    """Return a 1–2 sentence curator note for UI / sidecar metadata."""
    parts: list[str] = []
    mood_l = (mood or "").strip().lower() or None
    subject_l = (subject or "").strip() or None
    style_l = (style or "").strip() or None
    prompt_l = (prompt or "").strip()

    # Knowledge graph: artwork context + mood suggestions
    try:
        from ..knowledge import get_knowledge_graph

        graph = get_knowledge_graph()
        if artwork_id:
            neighbors = graph.find_similar_artworks(str(artwork_id), depth=1, limit=3)
            titles: list[str] = []
            for n in neighbors:
                label = n.get("title") or n.get("id")
                if label:
                    titles.append(str(label)[:48])
            if titles:
                if len(titles) == 1:
                    parts.append(f"Neighbors in the archive: «{titles[0]}».")
                else:
                    parts.append(
                        "Neighbors in the archive: "
                        + ", ".join(f"«{t}»" for t in titles[:3])
                        + "."
                    )
            ctx = graph.get_artwork_context(str(artwork_id))
            if ctx:
                styles: list[str] = [
                    str(s.get("name"))
                    for s in (ctx.get("styles") or [])
                    if isinstance(s, dict) and s.get("name")
                ]
                subjects: list[str] = [
                    str(s.get("name"))
                    for s in (ctx.get("subjects") or [])
                    if isinstance(s, dict) and s.get("name")
                ]
                if styles or subjects:
                    bits: list[str] = []
                    if subjects:
                        bits.append(", ".join(subjects[:2]))
                    if styles:
                        bits.append("in " + ", ".join(styles[:2]))
                    parts.append(
                        "In the graph of her work, this sits with "
                        + " ".join(bits)
                        + "."
                    )
        if mood_l and not parts:
            sug = graph.get_creative_suggestions(mood_l)
            sug_subjects: list[str] = [
                str(s.get("name") if isinstance(s, dict) else s)
                for s in (sug.get("suggested_subjects") or [])[:2]
                if (s.get("name") if isinstance(s, dict) else s)
            ]
            sug_styles: list[str] = [
                str(s.get("name") if isinstance(s, dict) else s)
                for s in (sug.get("suggested_styles") or [])[:2]
                if (s.get("name") if isinstance(s, dict) else s)
            ]
            if sug_subjects or sug_styles:
                line = f"For {mood_l}, she often returns to"
                if sug_subjects:
                    line += " " + " and ".join(sug_subjects)
                if sug_styles:
                    line += (" via " if sug_subjects else " ") + " and ".join(
                        sug_styles
                    )
                parts.append(line + ".")
    except Exception as e:
        logger.debug("curator_voice_knowledge_failed", error=str(e))

    # Active thematic series match
    try:
        from ..intelligence.narrative_engine import get_narrative_engine
        from ..personality.moods import MoodSystem

        narrative = get_narrative_engine(mood_system=MoodSystem())
        status = narrative.get_series_status()
        hay = " ".join(
            filter(
                None,
                [
                    subject_l,
                    style_l,
                    prompt_l[:120],
                    mood_l,
                ],
            )
        ).lower()
        for series in status.get("active") or []:
            theme = str(series.get("theme") or "").lower()
            title = str(series.get("title") or "Untitled")
            if theme and theme in hay:
                progress = series.get("progress") or ""
                parts.append(
                    f"Continues the arc of «{title}»"
                    + (f" ({progress})" if progress else "")
                    + "."
                )
                break
    except Exception as e:
        logger.debug("curator_voice_series_failed", error=str(e))

    # Adaptive taste motif echo
    try:
        from ..learning import get_adaptive_learner

        taste = get_adaptive_learner().get_taste_summary()
        motifs: list[str] = [
            str(m.get("motif"))
            for m in (taste.get("top_motifs") or [])
            if isinstance(m, dict) and m.get("motif")
        ][:3]
        if motifs and prompt_l:
            hit = [m for m in motifs if m.lower() in prompt_l.lower()]
            if hit:
                parts.append(
                    "Echoes motifs she's been learning to love: "
                    + ", ".join(hit[:2])
                    + "."
                )
            elif taste.get("narrative") and not parts:
                parts.append(str(taste["narrative"]).rstrip(".") + ".")
    except Exception as e:
        logger.debug("curator_voice_taste_failed", error=str(e))

    if parts:
        return " ".join(parts[:3])

    # Honest minimal fallback
    if mood_l and style_l:
        return (
            f"A {mood_l} note in her portfolio — {style_l} holding the thread "
            "across the body of work."
        )
    if mood_l:
        return (
            f"Filed under {mood_l}: another step in the conversation she's "
            "having with her own archive."
        )
    if subject_l:
        return (
            f"She keeps returning to {subject_l} — this piece belongs to that inquiry."
        )
    return (
        "A new mark in the archive — neighbors will emerge as the body of "
        "work thickens."
    )


def curator_voice_payload(
    *,
    mood: str | None = None,
    prompt: str | None = None,
    artwork_id: str | None = None,
    subject: str | None = None,
    style: str | None = None,
) -> dict[str, Any]:
    """Structured payload for API responses."""
    note = compose_curator_voice(
        mood=mood,
        prompt=prompt,
        artwork_id=artwork_id,
        subject=subject,
        style=style,
    )
    return {
        "curator_note": note,
        "mood": mood,
        "artwork_id": artwork_id,
        "subject": subject,
        "style": style,
    }
