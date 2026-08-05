"""Knowledge graph for semantic reasoning about art."""

from .graph_client import (
    KnowledgeGraph,
    get_knowledge_graph,
)
from .indexing import index_artwork_in_knowledge_graph

__all__ = [
    "KnowledgeGraph",
    "get_knowledge_graph",
    "index_artwork_in_knowledge_graph",
]
