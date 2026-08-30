"""Vector-based semantic memory for Lumira.

Enables semantic search over past creations and memories using embeddings.
Uses ChromaDB for local, persistent vector storage.

Security note -- this must stay embedded. ChromaDB 1.5.9 (the latest release)
carries three unpatched advisories, and all three are reachable only through
its HTTP server: CVE-2026-45833 needs the /api/v2/.../collections endpoint
with UPDATE_COLLECTION permission, and CVE-2026-45830 / CVE-2026-45831 are
flaws in the tenant scoping of its RBAC authorization provider. A
``PersistentClient`` runs in-process against a local directory with no server,
no auth and no tenants, so none of them apply.

Switching this to ``chromadb.HttpClient`` -- or running a Chroma server beside
the app -- makes all three live, with no upstream fix available. Do not do it
without re-checking those advisories first.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from ..utils.logging import get_logger

logger = get_logger(__name__)


class VectorMemory:
    """Semantic memory using vector embeddings.

    Stores and retrieves memories based on meaning, not just keywords.
    Complements the existing episodic/semantic memory system.
    """

    def __init__(
        self,
        persist_dir: str | Path = "data/vector_memory",
        collection_name: str = "lumira_creations",
    ):
        """Initialize vector memory.

        Args:
            persist_dir: Directory for persistent storage
            collection_name: Name of the ChromaDB collection
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create collection for creations
        self.creations = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Lumira's artwork memories"},
        )

        # Get or create collection for reflections
        self.reflections = self.client.get_or_create_collection(
            name="lumira_reflections",
            metadata={"description": "Lumira's artistic reflections"},
        )

        logger.info(
            "vector_memory_initialized",
            persist_dir=str(self.persist_dir),
            creations_count=self.creations.count(),
            reflections_count=self.reflections.count(),
        )

    def add_creation(
        self,
        creation_id: str,
        prompt: str,
        subject: str,
        style: str,
        mood: str,
        reasoning: str = "",
        quality_score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a creation to vector memory.

        Args:
            creation_id: Unique identifier (e.g., filename)
            prompt: The generation prompt
            subject: Main subject of the artwork
            style: Artistic style used
            mood: Mood during creation
            reasoning: Why this was created
            quality_score: Quality assessment score
            metadata: Additional metadata
        """
        # Combine text for embedding
        document = (
            f"{prompt}. Subject: {subject}. Style: {style}. Mood: {mood}. {reasoning}"
        )

        # Prepare metadata
        meta: dict[str, str | int | float | bool] = {
            "subject": subject,
            "style": style,
            "mood": mood,
            "quality_score": quality_score,
            "created_at": datetime.now().isoformat(),
        }
        if metadata:
            # Filter to string values only (ChromaDB requirement)
            for k, v in metadata.items():
                if isinstance(v, str | int | float | bool):
                    meta[k] = v

        self.creations.upsert(
            ids=[creation_id],
            documents=[document],
            metadatas=[meta],
        )

        logger.debug(
            "creation_added_to_vector_memory",
            id=creation_id,
            subject=subject,
        )

    def add_reflection(
        self,
        reflection_id: str,
        content: str,
        reflection_type: str = "daily",
        themes: list[str] | None = None,
    ) -> None:
        """Add a reflection to vector memory.

        Args:
            reflection_id: Unique identifier
            content: The reflection text
            reflection_type: Type (session, daily, weekly, monthly)
            themes: Key themes in the reflection
        """
        meta = {
            "type": reflection_type,
            "themes": ",".join(themes) if themes else "",
            "created_at": datetime.now().isoformat(),
        }

        self.reflections.upsert(
            ids=[reflection_id],
            documents=[content],
            metadatas=[meta],
        )

        logger.debug(
            "reflection_added_to_vector_memory",
            id=reflection_id,
            type=reflection_type,
        )

    def search_creations(
        self,
        query: str,
        n_results: int = 5,
        mood_filter: str | None = None,
        style_filter: str | None = None,
        min_quality: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar creations by semantic meaning.

        Args:
            query: Natural language search query
            n_results: Maximum results to return
            mood_filter: Filter by specific mood
            style_filter: Filter by specific style
            min_quality: Minimum quality score

        Returns:
            List of matching creations with similarity scores
        """
        # Build where clause for filters
        where: dict[str, Any] | None = None
        where_conditions: list[dict[str, Any]] = []

        if mood_filter:
            where_conditions.append({"mood": mood_filter})
        if style_filter:
            where_conditions.append({"style": {"$contains": style_filter}})
        if min_quality is not None:
            where_conditions.append({"quality_score": {"$gte": min_quality}})

        if len(where_conditions) == 1:
            where = where_conditions[0]
        elif len(where_conditions) > 1:
            where = {"$and": where_conditions}

        results = self.creations.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        # Format results
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, id_ in enumerate(results["ids"][0]):
                formatted.append(
                    {
                        "id": id_,
                        "document": (
                            results["documents"][0][i] if results["documents"] else ""
                        ),
                        "metadata": (
                            results["metadatas"][0][i] if results["metadatas"] else {}
                        ),
                        "distance": (
                            results["distances"][0][i] if results["distances"] else 0
                        ),
                    }
                )

        return formatted

    def search_reflections(
        self,
        query: str,
        n_results: int = 3,
        reflection_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar reflections.

        Args:
            query: Natural language search query
            n_results: Maximum results to return
            reflection_type: Filter by reflection type

        Returns:
            List of matching reflections
        """
        where: Any = {"type": reflection_type} if reflection_type else None

        results = self.reflections.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, id_ in enumerate(results["ids"][0]):
                formatted.append(
                    {
                        "id": id_,
                        "content": (
                            results["documents"][0][i] if results["documents"] else ""
                        ),
                        "metadata": (
                            results["metadatas"][0][i] if results["metadatas"] else {}
                        ),
                        "distance": (
                            results["distances"][0][i] if results["distances"] else 0
                        ),
                    }
                )

        return formatted

    def find_similar_to_creation(
        self,
        creation_id: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Find creations similar to an existing one.

        Args:
            creation_id: ID of the reference creation
            n_results: Maximum results to return

        Returns:
            List of similar creations (excluding the reference)
        """
        # Get the original creation
        result = self.creations.get(ids=[creation_id])
        if not result["documents"]:
            return []

        # Search using its document
        document = result["documents"][0]
        results = self.search_creations(document, n_results=n_results + 1)

        # Filter out the original
        return [r for r in results if r["id"] != creation_id][:n_results]

    def get_mood_themes(self, mood: str, n_results: int = 10) -> list[str]:
        """Get common themes/subjects for a specific mood.

        Args:
            mood: The mood to analyze
            n_results: Number of creations to sample

        Returns:
            List of common subjects for this mood
        """
        results = self.creations.query(
            query_texts=[f"artwork created in {mood} mood"],
            n_results=n_results,
            where={"mood": mood},
        )

        subjects: list[str] = []
        if results["metadatas"] and results["metadatas"][0]:
            for entry in results["metadatas"][0]:
                subject = entry.get("subject")
                if subject:
                    subjects.append(str(subject))

        return subjects

    def get_stats(self) -> dict[str, Any]:
        """Get vector memory statistics.

        Returns:
            Dict with memory statistics
        """
        return {
            "creations_count": self.creations.count(),
            "reflections_count": self.reflections.count(),
            "persist_dir": str(self.persist_dir),
        }

    def index_existing_creations(self, db_session: Any) -> int:
        """Index existing creations from database into vector memory.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            Number of creations indexed
        """
        from ..db.models import GeneratedImage

        images = db_session.query(GeneratedImage).all()
        count = 0

        for img in images:
            try:
                params = img.generation_params or {}
                self.add_creation(
                    creation_id=str(img.id),
                    prompt=img.prompt or "",
                    subject=params.get("subject", ""),
                    style=params.get("style", ""),
                    mood=img.status or "",
                    reasoning=params.get("reasoning", ""),
                    quality_score=img.final_score or 0.0,
                )
                count += 1
            except Exception as e:
                logger.warning(
                    "failed_to_index_creation",
                    id=img.id,
                    error=str(e),
                )

        logger.info("indexed_existing_creations", count=count)
        return count


# Singleton instance
_vector_memory: VectorMemory | None = None


def get_vector_memory() -> VectorMemory:
    """Get the singleton VectorMemory instance."""
    global _vector_memory
    if _vector_memory is None:
        _vector_memory = VectorMemory()
    return _vector_memory
