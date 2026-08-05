"""Helpers to index creations into the knowledge graph for curator voice."""

from __future__ import annotations

from typing import Any

from .graph_client import get_knowledge_graph


def index_artwork_in_knowledge_graph(
    artwork_id: str,
    *,
    prompt: str = "",
    title: str | None = None,
    mood: str | None = None,
    subject: str | None = None,
    style: str | None = None,
    model: str = "",
    aesthetic_score: float | None = None,
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    """Index an artwork and return soft-linked archive neighbors."""
    graph = get_knowledge_graph()
    return graph.index_creation(
        artwork_id,
        prompt=prompt,
        title=title,
        mood=mood,
        subject=subject,
        style=style,
        model=model,
        aesthetic_score=aesthetic_score,
        file_path=file_path,
    )
