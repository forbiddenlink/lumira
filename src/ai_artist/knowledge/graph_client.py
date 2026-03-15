"""FalkorDB knowledge graph client for semantic art reasoning.

Provides graph-based queries for:
- Subject/style/mood associations
- Artwork similarity and influence chains
- Creative pattern discovery
- "What subjects pair well?" reasoning

Gracefully degrades to in-memory mode if FalkorDB is unavailable.
"""

import os
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Check for FalkorDB availability
try:
    from falkordb import FalkorDB

    FALKORDB_AVAILABLE = True
except ImportError:
    FALKORDB_AVAILABLE = False
    logger.debug("falkordb not installed, using in-memory fallback")


class ArtworkNode(BaseModel):
    """Artwork node in the knowledge graph."""

    id: str
    title: str
    prompt: str = ""
    model: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    aesthetic_score: float | None = None
    file_path: str | None = None


class SubjectNode(BaseModel):
    """Subject node (what the artwork depicts)."""

    name: str
    category: str = "general"  # nature, abstract, portrait, architecture, etc.
    usage_count: int = 0


class StyleNode(BaseModel):
    """Style node (artistic style/movement)."""

    name: str
    era: str | None = None
    usage_count: int = 0


class MoodNode(BaseModel):
    """Mood node (emotional quality)."""

    name: str
    valence: float = 0.5  # -1 (negative) to 1 (positive)
    arousal: float = 0.5  # 0 (calm) to 1 (energetic)
    usage_count: int = 0


class KnowledgeGraph:
    """FalkorDB-backed knowledge graph for Lumira's creative reasoning.

    Falls back to in-memory storage if FalkorDB is unavailable.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        graph_name: str = "lumira_knowledge",
    ):
        """Initialize knowledge graph connection.

        Args:
            host: FalkorDB host
            port: FalkorDB port
            password: Optional password
            graph_name: Name of the graph
        """
        self.graph_name = graph_name
        self._graph: Any = None
        self._db: Any = None
        self._connected = False

        # In-memory fallback storage
        self._memory_artworks: dict[str, ArtworkNode] = {}
        self._memory_subjects: dict[str, SubjectNode] = {}
        self._memory_styles: dict[str, StyleNode] = {}
        self._memory_moods: dict[str, MoodNode] = {}
        self._memory_relationships: list[dict[str, Any]] = []

        if FALKORDB_AVAILABLE:
            try:
                self._db = FalkorDB(
                    host=host,
                    port=port,
                    password=password or os.getenv("FALKORDB_PASSWORD"),
                )
                self._graph = self._db.select_graph(graph_name)
                self._connected = True
                self._create_indexes()
                logger.info(
                    "knowledge_graph_connected",
                    host=host,
                    port=port,
                    graph=graph_name,
                )
            except Exception as e:
                logger.warning(
                    "knowledge_graph_connection_failed",
                    error=str(e),
                    message="Using in-memory fallback",
                )
                self._connected = False
        else:
            logger.info("knowledge_graph_using_memory_fallback")

    @property
    def is_connected(self) -> bool:
        """Check if connected to FalkorDB."""
        return self._connected and self._graph is not None

    def _create_indexes(self) -> None:
        """Create indexes for common queries."""
        if not self.is_connected:
            return

        try:
            # Index on node IDs/names for fast lookups
            self._graph.query("CREATE INDEX FOR (a:Artwork) ON (a.id)")
            self._graph.query("CREATE INDEX FOR (s:Subject) ON (s.name)")
            self._graph.query("CREATE INDEX FOR (st:Style) ON (st.name)")
            self._graph.query("CREATE INDEX FOR (m:Mood) ON (m.name)")
        except Exception:
            # Indexes may already exist
            pass

    # ==========================================================================
    # Node Creation (MERGE = create if not exists)
    # ==========================================================================

    def add_artwork(
        self,
        artwork_id: str,
        title: str,
        prompt: str = "",
        model: str = "",
        aesthetic_score: float | None = None,
        file_path: str | None = None,
    ) -> ArtworkNode:
        """Add or update an artwork node."""
        node = ArtworkNode(
            id=artwork_id,
            title=title,
            prompt=prompt,
            model=model,
            aesthetic_score=aesthetic_score,
            file_path=file_path,
        )

        if self.is_connected:
            self._graph.query(
                """
                MERGE (a:Artwork {id: $id})
                SET a.title = $title,
                    a.prompt = $prompt,
                    a.model = $model,
                    a.aesthetic_score = $aesthetic_score,
                    a.file_path = $file_path,
                    a.created_at = $created_at
                """,
                {
                    "id": artwork_id,
                    "title": title,
                    "prompt": prompt,
                    "model": model,
                    "aesthetic_score": aesthetic_score,
                    "file_path": file_path,
                    "created_at": node.created_at,
                },
            )
        else:
            self._memory_artworks[artwork_id] = node

        logger.debug("artwork_added_to_graph", artwork_id=artwork_id)
        return node

    def add_subject(self, name: str, category: str = "general") -> SubjectNode:
        """Add or update a subject node."""
        if self.is_connected:
            self._graph.query(
                """
                MERGE (s:Subject {name: $name})
                ON CREATE SET s.category = $category, s.usage_count = 1
                ON MATCH SET s.usage_count = s.usage_count + 1
                """,
                {"name": name, "category": category},
            )
            return SubjectNode(name=name, category=category)
        else:
            if name in self._memory_subjects:
                self._memory_subjects[name].usage_count += 1
            else:
                self._memory_subjects[name] = SubjectNode(name=name, category=category)
            return self._memory_subjects[name]

    def add_style(self, name: str, era: str | None = None) -> StyleNode:
        """Add or update a style node."""
        if self.is_connected:
            self._graph.query(
                """
                MERGE (s:Style {name: $name})
                ON CREATE SET s.era = $era, s.usage_count = 1
                ON MATCH SET s.usage_count = s.usage_count + 1
                """,
                {"name": name, "era": era},
            )
            return StyleNode(name=name, era=era)
        else:
            if name in self._memory_styles:
                self._memory_styles[name].usage_count += 1
            else:
                self._memory_styles[name] = StyleNode(name=name, era=era)
            return self._memory_styles[name]

    def add_mood(
        self, name: str, valence: float = 0.5, arousal: float = 0.5
    ) -> MoodNode:
        """Add or update a mood node."""
        if self.is_connected:
            self._graph.query(
                """
                MERGE (m:Mood {name: $name})
                ON CREATE SET m.valence = $valence, m.arousal = $arousal, m.usage_count = 1
                ON MATCH SET m.usage_count = m.usage_count + 1
                """,
                {"name": name, "valence": valence, "arousal": arousal},
            )
            return MoodNode(name=name, valence=valence, arousal=arousal)
        else:
            if name in self._memory_moods:
                self._memory_moods[name].usage_count += 1
            else:
                self._memory_moods[name] = MoodNode(
                    name=name, valence=valence, arousal=arousal
                )
            return self._memory_moods[name]

    # ==========================================================================
    # Relationship Creation
    # ==========================================================================

    def link_artwork_depicts(
        self, artwork_id: str, subject_name: str, confidence: float = 1.0
    ) -> None:
        """Create DEPICTS relationship between artwork and subject."""
        if self.is_connected:
            self._graph.query(
                """
                MATCH (a:Artwork {id: $artwork_id}), (s:Subject {name: $subject_name})
                MERGE (a)-[r:DEPICTS]->(s)
                SET r.confidence = $confidence
                """,
                {
                    "artwork_id": artwork_id,
                    "subject_name": subject_name,
                    "confidence": confidence,
                },
            )
        else:
            self._memory_relationships.append(
                {
                    "type": "DEPICTS",
                    "from": artwork_id,
                    "to": subject_name,
                    "confidence": confidence,
                }
            )

    def link_artwork_style(
        self, artwork_id: str, style_name: str, strength: float = 1.0
    ) -> None:
        """Create HAS_STYLE relationship between artwork and style."""
        if self.is_connected:
            self._graph.query(
                """
                MATCH (a:Artwork {id: $artwork_id}), (s:Style {name: $style_name})
                MERGE (a)-[r:HAS_STYLE]->(s)
                SET r.strength = $strength
                """,
                {
                    "artwork_id": artwork_id,
                    "style_name": style_name,
                    "strength": strength,
                },
            )
        else:
            self._memory_relationships.append(
                {
                    "type": "HAS_STYLE",
                    "from": artwork_id,
                    "to": style_name,
                    "strength": strength,
                }
            )

    def link_artwork_mood(
        self, artwork_id: str, mood_name: str, intensity: float = 1.0
    ) -> None:
        """Create EVOKES relationship between artwork and mood."""
        if self.is_connected:
            self._graph.query(
                """
                MATCH (a:Artwork {id: $artwork_id}), (m:Mood {name: $mood_name})
                MERGE (a)-[r:EVOKES]->(m)
                SET r.intensity = $intensity
                """,
                {
                    "artwork_id": artwork_id,
                    "mood_name": mood_name,
                    "intensity": intensity,
                },
            )
        else:
            self._memory_relationships.append(
                {
                    "type": "EVOKES",
                    "from": artwork_id,
                    "to": mood_name,
                    "intensity": intensity,
                }
            )

    def link_similar_artworks(
        self, artwork_id1: str, artwork_id2: str, similarity: float
    ) -> None:
        """Create SIMILAR_TO relationship between artworks."""
        if self.is_connected:
            self._graph.query(
                """
                MATCH (a1:Artwork {id: $id1}), (a2:Artwork {id: $id2})
                MERGE (a1)-[r:SIMILAR_TO]->(a2)
                SET r.score = $similarity
                """,
                {"id1": artwork_id1, "id2": artwork_id2, "similarity": similarity},
            )
        else:
            self._memory_relationships.append(
                {
                    "type": "SIMILAR_TO",
                    "from": artwork_id1,
                    "to": artwork_id2,
                    "score": similarity,
                }
            )

    def link_subject_mood_association(
        self, subject_name: str, mood_name: str, weight: float = 1.0
    ) -> None:
        """Create ASSOCIATED_WITH relationship between subject and mood."""
        if self.is_connected:
            self._graph.query(
                """
                MATCH (s:Subject {name: $subject_name}), (m:Mood {name: $mood_name})
                MERGE (s)-[r:ASSOCIATED_WITH]->(m)
                SET r.weight = $weight
                """,
                {
                    "subject_name": subject_name,
                    "mood_name": mood_name,
                    "weight": weight,
                },
            )
        else:
            self._memory_relationships.append(
                {
                    "type": "ASSOCIATED_WITH",
                    "from": subject_name,
                    "to": mood_name,
                    "weight": weight,
                }
            )

    # ==========================================================================
    # Query Operations
    # ==========================================================================

    def find_artworks_by_subject(
        self, subject_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Find artworks depicting a subject."""
        if self.is_connected:
            result = self._graph.ro_query(
                """
                MATCH (a:Artwork)-[d:DEPICTS]->(s:Subject {name: $name})
                RETURN a.id, a.title, a.aesthetic_score, d.confidence
                ORDER BY d.confidence DESC
                LIMIT $limit
                """,
                {"name": subject_name, "limit": limit},
            )
            return [
                {
                    "id": r[0],
                    "title": r[1],
                    "aesthetic_score": r[2],
                    "confidence": r[3],
                }
                for r in result.result_set
            ]
        else:
            # In-memory fallback
            matching = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "DEPICTS" and rel["to"] == subject_name
            ]
            results = []
            for rel in matching[:limit]:
                artwork = self._memory_artworks.get(rel["from"])
                title = artwork.title if artwork else ""
                results.append(
                    {
                        "id": rel["from"],
                        "title": title,
                        "confidence": rel.get("confidence", 1.0),
                    }
                )
            return results

    def find_artworks_by_mood(
        self, mood_name: str, min_intensity: float = 0.5, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Find artworks evoking a mood."""
        if self.is_connected:
            result = self._graph.ro_query(
                """
                MATCH (a:Artwork)-[e:EVOKES]->(m:Mood {name: $name})
                WHERE e.intensity >= $min_intensity
                RETURN a.id, a.title, e.intensity
                ORDER BY e.intensity DESC
                LIMIT $limit
                """,
                {"name": mood_name, "min_intensity": min_intensity, "limit": limit},
            )
            return [
                {"id": r[0], "title": r[1], "intensity": r[2]}
                for r in result.result_set
            ]
        else:
            matching = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "EVOKES"
                and rel["to"] == mood_name
                and rel.get("intensity", 1.0) >= min_intensity
            ]
            return [
                {"id": rel["from"], "intensity": rel.get("intensity", 1.0)}
                for rel in matching[:limit]
            ]

    def find_similar_artworks(
        self, artwork_id: str, depth: int = 2, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Find artworks similar to given artwork (up to N hops)."""
        if self.is_connected:
            result = self._graph.ro_query(
                f"""
                MATCH (a:Artwork {{id: $id}})-[:SIMILAR_TO*1..{depth}]->(similar:Artwork)
                RETURN DISTINCT similar.id, similar.title, similar.aesthetic_score
                LIMIT $limit
                """,
                {"id": artwork_id, "limit": limit},
            )
            return [
                {"id": r[0], "title": r[1], "aesthetic_score": r[2]}
                for r in result.result_set
            ]
        else:
            # Simple in-memory: direct connections only
            matching = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "SIMILAR_TO" and rel["from"] == artwork_id
            ]
            return [
                {"id": rel["to"], "score": rel.get("score", 0.5)}
                for rel in matching[:limit]
            ]

    def get_subjects_for_mood(
        self, mood_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get subjects commonly associated with a mood.

        This is the key creative reasoning query:
        "What subjects work well for a serene mood?"
        """
        if self.is_connected:
            result = self._graph.ro_query(
                """
                MATCH (s:Subject)-[a:ASSOCIATED_WITH]->(m:Mood {name: $mood_name})
                RETURN s.name, s.category, a.weight
                ORDER BY a.weight DESC
                LIMIT $limit
                """,
                {"mood_name": mood_name, "limit": limit},
            )
            return [
                {"name": r[0], "category": r[1], "weight": r[2]}
                for r in result.result_set
            ]
        else:
            matching = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "ASSOCIATED_WITH" and rel["to"] == mood_name
            ]
            return [
                {"name": rel["from"], "weight": rel.get("weight", 1.0)}
                for rel in matching[:limit]
            ]

    def get_styles_for_subject(
        self, subject_name: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get styles commonly used for a subject.

        "What styles work well for ocean scenes?"
        """
        if self.is_connected:
            result = self._graph.ro_query(
                """
                MATCH (a:Artwork)-[:DEPICTS]->(s:Subject {name: $subject_name})
                MATCH (a)-[h:HAS_STYLE]->(style:Style)
                RETURN style.name, COUNT(a) as count, AVG(a.aesthetic_score) as avg_score
                ORDER BY avg_score DESC, count DESC
                LIMIT $limit
                """,
                {"subject_name": subject_name, "limit": limit},
            )
            return [
                {"name": r[0], "count": r[1], "avg_score": r[2]}
                for r in result.result_set
            ]
        else:
            # Simplified in-memory
            return []

    def get_artwork_context(self, artwork_id: str) -> dict[str, Any] | None:
        """Get full context for an artwork (subjects, styles, moods)."""
        if self.is_connected:
            result = self._graph.ro_query(
                """
                MATCH (a:Artwork {id: $id})
                OPTIONAL MATCH (a)-[d:DEPICTS]->(subject:Subject)
                OPTIONAL MATCH (a)-[h:HAS_STYLE]->(style:Style)
                OPTIONAL MATCH (a)-[e:EVOKES]->(mood:Mood)
                RETURN a.title, a.prompt, a.aesthetic_score,
                       collect(DISTINCT {name: subject.name, confidence: d.confidence}),
                       collect(DISTINCT {name: style.name, strength: h.strength}),
                       collect(DISTINCT {name: mood.name, intensity: e.intensity})
                """,
                {"id": artwork_id},
            )
            if result.result_set:
                r = result.result_set[0]
                return {
                    "id": artwork_id,
                    "title": r[0],
                    "prompt": r[1],
                    "aesthetic_score": r[2],
                    "subjects": [s for s in r[3] if s.get("name")],
                    "styles": [s for s in r[4] if s.get("name")],
                    "moods": [m for m in r[5] if m.get("name")],
                }
            return None
        else:
            artwork = self._memory_artworks.get(artwork_id)
            if not artwork:
                return None
            # Get relationships
            subjects = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "DEPICTS" and rel["from"] == artwork_id
            ]
            styles = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "HAS_STYLE" and rel["from"] == artwork_id
            ]
            moods = [
                rel
                for rel in self._memory_relationships
                if rel["type"] == "EVOKES" and rel["from"] == artwork_id
            ]
            return {
                "id": artwork_id,
                "title": artwork.title,
                "prompt": artwork.prompt,
                "aesthetic_score": artwork.aesthetic_score,
                "subjects": [
                    {"name": s["to"], "confidence": s.get("confidence", 1.0)}
                    for s in subjects
                ],
                "styles": [
                    {"name": s["to"], "strength": s.get("strength", 1.0)}
                    for s in styles
                ],
                "moods": [
                    {"name": m["to"], "intensity": m.get("intensity", 1.0)}
                    for m in moods
                ],
            }

    def get_creative_suggestions(self, mood_name: str) -> dict[str, Any]:
        """Get creative suggestions based on mood - the key reasoning query.

        Returns subjects and styles that have worked well for this mood.
        """
        subjects = self.get_subjects_for_mood(mood_name, limit=5)

        # Get top styles that work with these subjects
        style_suggestions = []
        if self.is_connected:
            result = self._graph.ro_query(
                """
                MATCH (a:Artwork)-[e:EVOKES]->(m:Mood {name: $mood_name})
                MATCH (a)-[:HAS_STYLE]->(style:Style)
                WHERE a.aesthetic_score IS NOT NULL
                RETURN style.name, COUNT(a) as count, AVG(a.aesthetic_score) as avg_score
                ORDER BY avg_score DESC
                LIMIT 5
                """,
                {"mood_name": mood_name},
            )
            style_suggestions = [
                {"name": r[0], "count": r[1], "avg_score": r[2]}
                for r in result.result_set
            ]

        return {
            "mood": mood_name,
            "suggested_subjects": subjects,
            "suggested_styles": style_suggestions,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        if self.is_connected:
            result = self._graph.ro_query("""
                MATCH (a:Artwork) WITH COUNT(a) as artworks
                MATCH (s:Subject) WITH artworks, COUNT(s) as subjects
                MATCH (st:Style) WITH artworks, subjects, COUNT(st) as styles
                MATCH (m:Mood) WITH artworks, subjects, styles, COUNT(m) as moods
                RETURN artworks, subjects, styles, moods
                """)
            if result.result_set:
                r = result.result_set[0]
                return {
                    "artworks": r[0],
                    "subjects": r[1],
                    "styles": r[2],
                    "moods": r[3],
                    "connected": True,
                }
        return {
            "artworks": len(self._memory_artworks),
            "subjects": len(self._memory_subjects),
            "styles": len(self._memory_styles),
            "moods": len(self._memory_moods),
            "relationships": len(self._memory_relationships),
            "connected": False,
        }


# Singleton instance
_knowledge_graph: KnowledgeGraph | None = None


def get_knowledge_graph(
    host: str = "localhost",
    port: int = 6379,
    password: str | None = None,
    graph_name: str = "lumira_knowledge",
) -> KnowledgeGraph:
    """Get or create knowledge graph instance."""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph(
            host=host,
            port=port,
            password=password,
            graph_name=graph_name,
        )
    return _knowledge_graph
