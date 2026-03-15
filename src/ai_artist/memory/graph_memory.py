"""FalkorDB graph memory for Lumira's institutional knowledge.

This module provides relationship-aware memory that tracks:
- Which styles work well for which moods
- Successful style combinations (blends)
- Decision history with outcomes
- Mood pair effectiveness
"""

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from ai_artist.memory.graph_schema import DEFAULT_MOODS, SCHEMA_QUERIES, MoodNode

logger = structlog.get_logger(__name__)


@dataclass
class MemoryContext:
    """Context retrieved from graph memory for decision-making."""

    top_styles: list[dict[str, Any]]
    mood_pairs: list[dict[str, Any]]
    similar_works: list[dict[str, Any]]
    recent_work: list[dict[str, Any]]
    recent_subjects: list[str]
    style_blends: list[dict[str, Any]]


@dataclass
class StyleEffectiveness:
    """Style effectiveness statistics."""

    name: str
    avg_score: float
    uses: int
    best_score: float


class GraphMemory:
    """FalkorDB-backed graph memory for Lumira.

    Provides institutional knowledge about:
    - Style effectiveness per mood
    - Successful style combinations
    - Decision patterns and outcomes
    - Mood pairing insights
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6380,  # Different from Redis (6379)
        graph_name: str = "lumira",
    ):
        """Initialize graph memory connection.

        Args:
            host: FalkorDB host
            port: FalkorDB port (default 6380 to avoid Redis conflict)
            graph_name: Name of the graph to use
        """
        self.host = host
        self.port = port
        self.graph_name = graph_name
        self._db = None
        self._graph = None
        self._initialized = False

    async def connect(self) -> bool:
        """Establish connection to FalkorDB."""
        try:
            from falkordb import FalkorDB

            self._db = FalkorDB(host=self.host, port=self.port)
            self._graph = self._db.select_graph(self.graph_name)
            logger.info(
                "graph_memory_connected",
                host=self.host,
                port=self.port,
                graph=self.graph_name,
            )
            return True
        except ImportError:
            logger.warning(
                "falkordb_not_installed",
                message="FalkorDB not installed. Install with: pip install falkordb",
            )
            return False
        except Exception as e:
            logger.error("graph_memory_connection_failed", error=str(e))
            return False

    async def initialize_schema(self) -> bool:
        """Initialize graph schema and default data."""
        if self._graph is None and not await self.connect():
            return False

        try:
            # Create indexes (suppress errors for existing indexes)
            for query in SCHEMA_QUERIES:
                with contextlib.suppress(Exception):
                    self._graph.query(query)

            # Create default mood nodes
            for mood in DEFAULT_MOODS:
                await self._ensure_mood_exists(mood)

            self._initialized = True
            logger.info("graph_schema_initialized")
            return True
        except Exception as e:
            logger.error("graph_schema_init_failed", error=str(e))
            return False

    async def _ensure_mood_exists(self, mood: MoodNode) -> None:
        """Create mood node if it doesn't exist."""
        query = """
        MERGE (m:Mood {name: $name})
        ON CREATE SET
            m.energy_min = $energy_min,
            m.energy_max = $energy_max,
            m.typical_styles = $typical_styles,
            m.typical_colors = $typical_colors
        """
        self._graph.query(query, params=mood.to_cypher_props())

    async def record_decision(
        self,
        mood: str,
        prompt: str,
        styles: list[str],
        style_weights: list[float],
        outcome_score: float,
        artwork_path: str,
        artwork_id: str | None = None,
    ) -> str:
        """Record a creative decision and its outcome.

        Args:
            mood: The mood state when decision was made
            prompt: The generation prompt used
            styles: List of style names used
            style_weights: Corresponding weights for each style
            outcome_score: Quality score of the result (0-1)
            artwork_path: Path to the generated artwork
            artwork_id: Optional artwork ID (generated if not provided)

        Returns:
            The decision ID
        """
        if self._graph is None:
            logger.warning("graph_not_connected", action="record_decision")
            return ""

        decision_id = str(uuid4())
        artwork_id = artwork_id or str(uuid4())
        timestamp = datetime.now().isoformat()

        # Create decision and artwork nodes, link to mood
        query = """
        MERGE (m:Mood {name: $mood})
        CREATE (d:Decision {
            id: $decision_id,
            prompt: $prompt,
            styles: $styles,
            style_weights: $style_weights,
            score: $score,
            timestamp: $timestamp
        })
        CREATE (a:Artwork {
            id: $artwork_id,
            path: $artwork_path,
            score: $score,
            created_at: $timestamp
        })
        CREATE (m)-[:INFLUENCES {strength: 1.0}]->(d)
        CREATE (d)-[:PRODUCED]->(a)
        RETURN d.id
        """

        try:
            self._graph.query(
                query,
                params={
                    "mood": mood,
                    "decision_id": decision_id,
                    "prompt": prompt,
                    "styles": styles,
                    "style_weights": style_weights,
                    "score": outcome_score,
                    "timestamp": timestamp,
                    "artwork_id": artwork_id,
                    "artwork_path": artwork_path,
                },
            )

            # Link to style nodes
            for style, weight in zip(styles, style_weights, strict=False):
                await self._link_decision_to_style(decision_id, style, weight)

            # Record style blend effectiveness if multiple styles
            if len(styles) > 1:
                await self._record_style_blend(styles, style_weights, outcome_score)

            logger.info(
                "decision_recorded",
                decision_id=decision_id,
                mood=mood,
                score=outcome_score,
                styles=styles,
            )
            return decision_id

        except Exception as e:
            logger.error("record_decision_failed", error=str(e))
            return ""

    async def _link_decision_to_style(
        self, decision_id: str, style: str, weight: float
    ) -> None:
        """Link a decision to a style node."""
        query = """
        MATCH (d:Decision {id: $decision_id})
        MERGE (s:Style {name: $style})
        CREATE (d)-[:USED {weight: $weight}]->(s)
        """
        self._graph.query(
            query,
            params={"decision_id": decision_id, "style": style, "weight": weight},
        )

    async def _record_style_blend(
        self, styles: list[str], weights: list[float], score: float
    ) -> None:
        """Record effectiveness of a style blend."""
        # Record pairwise blend relationships
        for i, style_a in enumerate(styles):
            for j, style_b in enumerate(styles):
                if i < j:  # Avoid duplicates
                    query = """
                    MERGE (a:Style {name: $style_a})
                    MERGE (b:Style {name: $style_b})
                    MERGE (a)-[r:BLENDS_WITH]->(b)
                    ON CREATE SET r.score = $score, r.count = 1
                    ON MATCH SET
                        r.score = (r.score * r.count + $score) / (r.count + 1),
                        r.count = r.count + 1
                    """
                    self._graph.query(
                        query,
                        params={
                            "style_a": style_a,
                            "style_b": style_b,
                            "score": score,
                        },
                    )

    async def get_successful_styles_for_mood(
        self, mood: str, min_score: float = 0.7, limit: int = 10
    ) -> list[StyleEffectiveness]:
        """Get styles that worked well for a given mood.

        Args:
            mood: Mood name to query
            min_score: Minimum score threshold
            limit: Maximum results to return

        Returns:
            List of StyleEffectiveness objects
        """
        if self._graph is None:
            return []

        query = """
        MATCH (m:Mood {name: $mood})-[:INFLUENCES]->(d:Decision)-[:USED]->(s:Style)
        WHERE d.score >= $min_score
        RETURN s.name as style,
               AVG(d.score) as avg_score,
               COUNT(*) as uses,
               MAX(d.score) as best_score
        ORDER BY avg_score DESC
        LIMIT $limit
        """

        try:
            result = self._graph.query(
                query, params={"mood": mood, "min_score": min_score, "limit": limit}
            )

            return [
                StyleEffectiveness(
                    name=row[0],
                    avg_score=row[1],
                    uses=row[2],
                    best_score=row[3],
                )
                for row in result.result_set
            ]
        except Exception as e:
            logger.error("query_styles_failed", error=str(e), mood=mood)
            return []

    async def get_best_style_blends(
        self, min_score: float = 0.75, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get style combinations that produced high-quality results.

        Returns:
            List of dicts with style_a, style_b, avg_score, count
        """
        if self._graph is None:
            return []

        query = """
        MATCH (a:Style)-[r:BLENDS_WITH]->(b:Style)
        WHERE r.score >= $min_score
        RETURN a.name as style_a, b.name as style_b,
               r.score as avg_score, r.count as count
        ORDER BY r.score DESC
        LIMIT $limit
        """

        try:
            result = self._graph.query(
                query, params={"min_score": min_score, "limit": limit}
            )

            return [
                {
                    "style_a": row[0],
                    "style_b": row[1],
                    "avg_score": row[2],
                    "count": row[3],
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.error("query_blends_failed", error=str(e))
            return []

    async def get_mood_pairs(self, mood: str, limit: int = 5) -> list[dict[str, Any]]:
        """Get moods that pair well with the given mood.

        Based on decisions where multiple moods influenced the outcome.
        """
        if self._graph is None:
            return []

        # For now, return typical pairings based on energy compatibility
        query = """
        MATCH (m1:Mood {name: $mood}), (m2:Mood)
        WHERE m1 <> m2
        AND ABS(m1.energy_min - m2.energy_min) < 0.3
        RETURN m2.name as paired_mood,
               m2.typical_styles as styles,
               m2.typical_colors as colors
        LIMIT $limit
        """

        try:
            result = self._graph.query(query, params={"mood": mood, "limit": limit})

            return [
                {
                    "mood": row[0],
                    "styles": row[1],
                    "colors": row[2],
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.error("query_mood_pairs_failed", error=str(e), mood=mood)
            return []

    async def get_recent_decisions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent creative decisions for variety checking."""
        if self._graph is None:
            return []

        query = """
        MATCH (d:Decision)
        RETURN d.id, d.prompt, d.styles, d.score, d.timestamp
        ORDER BY d.timestamp DESC
        LIMIT $limit
        """

        try:
            result = self._graph.query(query, params={"limit": limit})

            return [
                {
                    "id": row[0],
                    "prompt": row[1],
                    "styles": row[2],
                    "score": row[3],
                    "timestamp": row[4],
                }
                for row in result.result_set
            ]
        except Exception as e:
            logger.error("query_recent_decisions_failed", error=str(e))
            return []

    async def get_context_for_creation(
        self, mood: str, theme: str | None = None
    ) -> MemoryContext:
        """Get full context for a creation decision.

        Combines style effectiveness, mood pairs, recent work, and blend data.
        """
        top_styles = await self.get_successful_styles_for_mood(mood)
        mood_pairs = await self.get_mood_pairs(mood)
        recent_work = await self.get_recent_decisions(limit=10)
        style_blends = await self.get_best_style_blends()

        # Extract recent subjects from prompts
        recent_subjects = []
        for work in recent_work:
            prompt = work.get("prompt", "")
            # Simple extraction: first few words
            words = prompt.split()[:3]
            if words:
                recent_subjects.append(" ".join(words))

        return MemoryContext(
            top_styles=[
                {"name": s.name, "avg_score": s.avg_score, "uses": s.uses}
                for s in top_styles
            ],
            mood_pairs=mood_pairs,
            similar_works=[],  # Will be filled by vector search
            recent_work=recent_work,
            recent_subjects=recent_subjects,
            style_blends=style_blends,
        )

    async def record_mood_pair_success(
        self, mood_a: str, mood_b: str, score: float
    ) -> None:
        """Record that two moods worked well together."""
        if self._graph is None:
            return

        query = """
        MERGE (a:Mood {name: $mood_a})
        MERGE (b:Mood {name: $mood_b})
        MERGE (a)-[r:PAIRS_WELL_WITH]->(b)
        ON CREATE SET r.score = $score, r.count = 1
        ON MATCH SET
            r.score = (r.score * r.count + $score) / (r.count + 1),
            r.count = r.count + 1
        """

        try:
            self._graph.query(
                query, params={"mood_a": mood_a, "mood_b": mood_b, "score": score}
            )
        except Exception as e:
            logger.error("record_mood_pair_failed", error=str(e))

    async def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        if self._graph is None:
            return {"connected": False}

        try:
            node_counts = {}
            for label in ["Mood", "Style", "Decision", "Artwork"]:
                result = self._graph.query(f"MATCH (n:{label}) RETURN COUNT(n)")
                node_counts[label.lower()] = (
                    result.result_set[0][0] if result.result_set else 0
                )

            rel_count = self._graph.query(
                "MATCH ()-[r]->() RETURN COUNT(r)"
            ).result_set[0][0]

            return {
                "connected": True,
                "nodes": node_counts,
                "relationships": rel_count,
            }
        except Exception as e:
            logger.error("get_stats_failed", error=str(e))
            return {"connected": True, "error": str(e)}

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            with contextlib.suppress(Exception):
                self._db.close()
            self._db = None
            self._graph = None
            self._initialized = False
