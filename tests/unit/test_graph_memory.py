"""Tests for FalkorDB graph memory."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_artist.memory.graph_memory import GraphMemory, MemoryContext, StyleEffectiveness
from ai_artist.memory.graph_schema import DEFAULT_MOODS, MoodNode


class TestGraphMemoryInit:
    """Tests for GraphMemory initialization."""

    def test_init_defaults(self):
        """Test default initialization values."""
        gm = GraphMemory()
        assert gm.host == "localhost"
        assert gm.port == 6380
        assert gm.graph_name == "lumira"
        assert gm._db is None
        assert gm._graph is None

    def test_init_custom_values(self):
        """Test custom initialization values."""
        gm = GraphMemory(host="custom", port=7000, graph_name="test")
        assert gm.host == "custom"
        assert gm.port == 7000
        assert gm.graph_name == "test"


class TestMoodNode:
    """Tests for MoodNode schema."""

    def test_to_cypher_props(self):
        """Test converting mood node to Cypher properties."""
        mood = MoodNode(
            name="test_mood",
            energy_min=0.3,
            energy_max=0.7,
            typical_styles=["style1", "style2"],
            typical_colors=["red", "blue"],
        )
        props = mood.to_cypher_props()

        assert props["name"] == "test_mood"
        assert props["energy_min"] == 0.3
        assert props["energy_max"] == 0.7
        assert props["typical_styles"] == ["style1", "style2"]
        assert props["typical_colors"] == ["red", "blue"]


class TestDefaultMoods:
    """Tests for default mood definitions."""

    def test_all_10_moods_defined(self):
        """Ensure all 10 Lumira moods are defined."""
        expected_moods = {
            "contemplative",
            "playful",
            "melancholic",
            "euphoric",
            "serene",
            "anxious",
            "nostalgic",
            "curious",
            "rebellious",
            "transcendent",
        }
        actual_moods = {m.name for m in DEFAULT_MOODS}
        assert actual_moods == expected_moods

    def test_moods_have_valid_energy_ranges(self):
        """Ensure all moods have valid energy ranges."""
        for mood in DEFAULT_MOODS:
            assert 0.0 <= mood.energy_min <= 1.0
            assert 0.0 <= mood.energy_max <= 1.0
            assert mood.energy_min <= mood.energy_max

    def test_moods_have_styles_and_colors(self):
        """Ensure all moods have typical styles and colors."""
        for mood in DEFAULT_MOODS:
            assert len(mood.typical_styles) > 0, f"{mood.name} has no styles"
            assert len(mood.typical_colors) > 0, f"{mood.name} has no colors"


class TestStyleEffectiveness:
    """Tests for StyleEffectiveness dataclass."""

    def test_style_effectiveness_creation(self):
        """Test creating StyleEffectiveness."""
        se = StyleEffectiveness(
            name="impressionist",
            avg_score=0.85,
            uses=10,
            best_score=0.95,
        )
        assert se.name == "impressionist"
        assert se.avg_score == 0.85
        assert se.uses == 10
        assert se.best_score == 0.95


class TestMemoryContext:
    """Tests for MemoryContext dataclass."""

    def test_memory_context_creation(self):
        """Test creating MemoryContext."""
        ctx = MemoryContext(
            top_styles=[{"name": "style1", "avg_score": 0.8}],
            mood_pairs=[{"mood": "serene", "styles": ["zen"]}],
            similar_works=[],
            recent_work=[{"id": "1", "prompt": "test"}],
            recent_subjects=["test subject"],
            style_blends=[{"style_a": "a", "style_b": "b", "avg_score": 0.9}],
        )
        assert len(ctx.top_styles) == 1
        assert len(ctx.mood_pairs) == 1
        assert len(ctx.recent_subjects) == 1


@pytest.mark.asyncio
class TestGraphMemoryOperations:
    """Tests for GraphMemory operations (mocked)."""

    async def test_connect_without_falkordb(self):
        """Test connect fails gracefully without FalkorDB installed."""
        gm = GraphMemory()

        with (
            patch.dict("sys.modules", {"falkordb": None}),
            patch(
                "ai_artist.memory.graph_memory.GraphMemory.connect",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            # Simulate ImportError - should return False when FalkorDB not installed
            result = await gm.connect()
            assert result is False

    async def test_record_decision_without_connection(self):
        """Test record_decision returns empty string without connection."""
        gm = GraphMemory()
        # Don't connect

        result = await gm.record_decision(
            mood="contemplative",
            prompt="test prompt",
            styles=["impressionist"],
            style_weights=[1.0],
            outcome_score=0.8,
            artwork_path="/path/to/art.png",
        )
        assert result == ""

    async def test_get_successful_styles_without_connection(self):
        """Test get_successful_styles returns empty list without connection."""
        gm = GraphMemory()

        result = await gm.get_successful_styles_for_mood("contemplative")
        assert result == []

    async def test_get_context_for_creation_structure(self):
        """Test get_context_for_creation returns proper structure."""
        gm = GraphMemory()

        # Mock the individual methods
        gm.get_successful_styles_for_mood = AsyncMock(return_value=[])
        gm.get_mood_pairs = AsyncMock(return_value=[])
        gm.get_recent_decisions = AsyncMock(return_value=[])
        gm.get_best_style_blends = AsyncMock(return_value=[])

        ctx = await gm.get_context_for_creation("contemplative")

        assert isinstance(ctx, MemoryContext)
        assert isinstance(ctx.top_styles, list)
        assert isinstance(ctx.mood_pairs, list)
        assert isinstance(ctx.recent_subjects, list)
        assert isinstance(ctx.style_blends, list)

    async def test_get_stats_without_connection(self):
        """Test get_stats returns not connected status."""
        gm = GraphMemory()

        stats = await gm.get_stats()
        assert stats == {"connected": False}


@pytest.mark.asyncio
class TestGraphMemoryWithMockedFalkorDB:
    """Tests for GraphMemory with mocked FalkorDB client."""

    @pytest.fixture
    def mock_graph(self):
        """Create a mock graph object."""
        graph = MagicMock()
        graph.query = MagicMock()
        return graph

    @pytest.fixture
    def mock_db(self, mock_graph):
        """Create a mock FalkorDB object."""
        db = MagicMock()
        db.select_graph = MagicMock(return_value=mock_graph)
        db.close = MagicMock()
        return db

    async def test_connect_success(self, mock_db):
        """Test successful connection to FalkorDB."""
        gm = GraphMemory()

        with patch("ai_artist.memory.graph_memory.FalkorDB", create=True):
            # Need to patch it at import time
            import sys

            mock_module = MagicMock()
            mock_module.FalkorDB = MagicMock(return_value=mock_db)
            sys.modules["falkordb"] = mock_module

            try:
                result = await gm.connect()
                assert result is True
                assert gm._db is not None
                assert gm._graph is not None
            finally:
                # Clean up the module
                del sys.modules["falkordb"]

    async def test_connect_import_error(self):
        """Test connect handles missing FalkorDB package."""
        gm = GraphMemory()

        import sys

        # Remove falkordb if it exists
        if "falkordb" in sys.modules:
            original = sys.modules["falkordb"]
            del sys.modules["falkordb"]
        else:
            original = None

        try:
            # Make import fail
            import builtins

            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "falkordb":
                    raise ImportError("No module named 'falkordb'")
                return original_import(name, *args, **kwargs)

            builtins.__import__ = mock_import
            result = await gm.connect()
            assert result is False
        finally:
            builtins.__import__ = original_import
            if original:
                sys.modules["falkordb"] = original

    async def test_connect_connection_error(self):
        """Test connect handles connection errors."""
        gm = GraphMemory()

        import sys

        mock_module = MagicMock()
        mock_module.FalkorDB = MagicMock(
            side_effect=ConnectionError("Connection refused")
        )
        sys.modules["falkordb"] = mock_module

        try:
            result = await gm.connect()
            assert result is False
        finally:
            del sys.modules["falkordb"]

    async def test_initialize_schema_success(self, mock_db, mock_graph):
        """Test successful schema initialization."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        result = await gm.initialize_schema()

        assert result is True
        assert gm._initialized is True
        # Should have called query for schema creation
        assert mock_graph.query.called

    async def test_initialize_schema_without_connection(self, mock_db, mock_graph):
        """Test initialize_schema connects if not connected."""
        gm = GraphMemory()

        # Mock connect to set up the graph
        async def mock_connect():
            gm._db = mock_db
            gm._graph = mock_graph
            return True

        gm.connect = mock_connect

        result = await gm.initialize_schema()
        assert result is True

    async def test_initialize_schema_connection_fails(self):
        """Test initialize_schema fails if connection fails."""
        gm = GraphMemory()

        async def mock_connect():
            return False

        gm.connect = mock_connect

        result = await gm.initialize_schema()
        assert result is False

    async def test_initialize_schema_query_error(self, mock_db, mock_graph):
        """Test initialize_schema handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        # Make query raise an exception
        mock_graph.query.side_effect = Exception("Query failed")

        result = await gm.initialize_schema()
        assert result is False

    async def test_record_decision_success(self, mock_db, mock_graph):
        """Test successful decision recording."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        result = await gm.record_decision(
            mood="contemplative",
            prompt="test prompt",
            styles=["impressionist", "minimalist"],
            style_weights=[0.7, 0.3],
            outcome_score=0.85,
            artwork_path="/path/to/art.png",
            artwork_id="test-artwork-id",
        )

        assert result != ""
        # Should have queried for decision creation and style links
        assert mock_graph.query.call_count >= 1

    async def test_record_decision_single_style(self, mock_db, mock_graph):
        """Test decision recording with single style (no blend)."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        result = await gm.record_decision(
            mood="serene",
            prompt="peaceful scene",
            styles=["zen"],
            style_weights=[1.0],
            outcome_score=0.9,
            artwork_path="/path/to/art.png",
        )

        assert result != ""

    async def test_record_decision_query_error(self, mock_db, mock_graph):
        """Test record_decision handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Database error")

        result = await gm.record_decision(
            mood="contemplative",
            prompt="test",
            styles=["style1"],
            style_weights=[1.0],
            outcome_score=0.8,
            artwork_path="/path.png",
        )

        assert result == ""

    async def test_get_successful_styles_with_results(self, mock_db, mock_graph):
        """Test get_successful_styles returns parsed results."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        # Mock query result
        mock_result = MagicMock()
        mock_result.result_set = [
            ["impressionist", 0.85, 10, 0.95],
            ["minimalist", 0.80, 5, 0.88],
        ]
        mock_graph.query.return_value = mock_result

        result = await gm.get_successful_styles_for_mood("contemplative")

        assert len(result) == 2
        assert isinstance(result[0], StyleEffectiveness)
        assert result[0].name == "impressionist"
        assert result[0].avg_score == 0.85
        assert result[0].uses == 10
        assert result[0].best_score == 0.95

    async def test_get_successful_styles_query_error(self, mock_db, mock_graph):
        """Test get_successful_styles handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Query failed")

        result = await gm.get_successful_styles_for_mood("contemplative")

        assert result == []

    async def test_get_best_style_blends_with_results(self, mock_db, mock_graph):
        """Test get_best_style_blends returns parsed results."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_result = MagicMock()
        mock_result.result_set = [
            ["zen", "minimalist", 0.88, 5],
            ["impressionist", "atmospheric", 0.85, 3],
        ]
        mock_graph.query.return_value = mock_result

        result = await gm.get_best_style_blends(min_score=0.8)

        assert len(result) == 2
        assert result[0]["style_a"] == "zen"
        assert result[0]["style_b"] == "minimalist"
        assert result[0]["avg_score"] == 0.88
        assert result[0]["count"] == 5

    async def test_get_best_style_blends_without_connection(self):
        """Test get_best_style_blends returns empty without connection."""
        gm = GraphMemory()

        result = await gm.get_best_style_blends()
        assert result == []

    async def test_get_best_style_blends_query_error(self, mock_db, mock_graph):
        """Test get_best_style_blends handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Query failed")

        result = await gm.get_best_style_blends()
        assert result == []

    async def test_get_mood_pairs_with_results(self, mock_db, mock_graph):
        """Test get_mood_pairs returns parsed results."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_result = MagicMock()
        mock_result.result_set = [
            ["serene", ["zen", "naturalist"], ["sage", "cream"]],
            ["nostalgic", ["vintage"], ["amber", "brown"]],
        ]
        mock_graph.query.return_value = mock_result

        result = await gm.get_mood_pairs("contemplative")

        assert len(result) == 2
        assert result[0]["mood"] == "serene"
        assert result[0]["styles"] == ["zen", "naturalist"]
        assert result[0]["colors"] == ["sage", "cream"]

    async def test_get_mood_pairs_without_connection(self):
        """Test get_mood_pairs returns empty without connection."""
        gm = GraphMemory()

        result = await gm.get_mood_pairs("contemplative")
        assert result == []

    async def test_get_mood_pairs_query_error(self, mock_db, mock_graph):
        """Test get_mood_pairs handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Query failed")

        result = await gm.get_mood_pairs("contemplative")
        assert result == []

    async def test_get_recent_decisions_with_results(self, mock_db, mock_graph):
        """Test get_recent_decisions returns parsed results."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_result = MagicMock()
        mock_result.result_set = [
            [
                "id1",
                "mountain landscape",
                ["impressionist"],
                0.85,
                "2024-01-01T12:00:00",
            ],
            ["id2", "ocean sunset", ["romantic"], 0.90, "2024-01-01T11:00:00"],
        ]
        mock_graph.query.return_value = mock_result

        result = await gm.get_recent_decisions(limit=10)

        assert len(result) == 2
        assert result[0]["id"] == "id1"
        assert result[0]["prompt"] == "mountain landscape"
        assert result[0]["styles"] == ["impressionist"]
        assert result[0]["score"] == 0.85

    async def test_get_recent_decisions_without_connection(self):
        """Test get_recent_decisions returns empty without connection."""
        gm = GraphMemory()

        result = await gm.get_recent_decisions()
        assert result == []

    async def test_get_recent_decisions_query_error(self, mock_db, mock_graph):
        """Test get_recent_decisions handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Query failed")

        result = await gm.get_recent_decisions()
        assert result == []

    async def test_get_context_for_creation_with_real_data(self, mock_db, mock_graph):
        """Test get_context_for_creation processes work prompts."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        # Mock different query results for each call
        call_count = 0

        def mock_query_results(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if "s.name as style" in args[0]:  # get_successful_styles query
                result.result_set = [["impressionist", 0.85, 10, 0.95]]
            elif "m2.name as paired_mood" in args[0]:  # get_mood_pairs query
                result.result_set = [["serene", ["zen"], ["green"]]]
            elif "d.id, d.prompt" in args[0]:  # get_recent_decisions query
                result.result_set = [
                    ["id1", "peaceful mountain sunset view", ["zen"], 0.9, "2024-01-01"]
                ]
            elif "BLENDS_WITH" in args[0]:  # get_best_style_blends query
                result.result_set = []
            else:
                result.result_set = []
            return result

        mock_graph.query.side_effect = mock_query_results

        ctx = await gm.get_context_for_creation("contemplative")

        assert isinstance(ctx, MemoryContext)
        assert len(ctx.top_styles) == 1
        assert ctx.top_styles[0]["name"] == "impressionist"
        assert len(ctx.recent_subjects) == 1
        assert ctx.recent_subjects[0] == "peaceful mountain sunset"

    async def test_record_mood_pair_success(self, mock_db, mock_graph):
        """Test recording mood pair success."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        await gm.record_mood_pair_success("contemplative", "serene", 0.9)

        assert mock_graph.query.called
        # Verify the query was called with correct params
        call_args = mock_graph.query.call_args
        assert "PAIRS_WELL_WITH" in call_args[0][0]

    async def test_record_mood_pair_success_without_connection(self):
        """Test record_mood_pair_success does nothing without connection."""
        gm = GraphMemory()

        # Should not raise
        await gm.record_mood_pair_success("contemplative", "serene", 0.9)

    async def test_record_mood_pair_success_query_error(self, mock_db, mock_graph):
        """Test record_mood_pair_success handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Query failed")

        # Should not raise
        await gm.record_mood_pair_success("contemplative", "serene", 0.9)

    async def test_get_stats_with_data(self, mock_db, mock_graph):
        """Test get_stats returns node and relationship counts."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        # Mock different counts for each label

        def mock_query_results(query, *args, **kwargs):
            result = MagicMock()
            if "Mood" in query:
                result.result_set = [[10]]
            elif "Style" in query:
                result.result_set = [[25]]
            elif "Decision" in query or "Artwork" in query:
                result.result_set = [[100]]
            elif "()-[r]->()" in query:
                result.result_set = [[300]]
            else:
                result.result_set = [[0]]
            return result

        mock_graph.query.side_effect = mock_query_results

        stats = await gm.get_stats()

        assert stats["connected"] is True
        assert stats["nodes"]["mood"] == 10
        assert stats["nodes"]["style"] == 25
        assert stats["relationships"] == 300

    async def test_get_stats_query_error(self, mock_db, mock_graph):
        """Test get_stats handles query errors."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_graph.query.side_effect = Exception("Query failed")

        stats = await gm.get_stats()

        assert stats["connected"] is True
        assert "error" in stats

    async def test_close_connection(self, mock_db, mock_graph):
        """Test closing the database connection."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph
        gm._initialized = True

        await gm.close()

        assert gm._db is None
        assert gm._graph is None
        assert gm._initialized is False
        mock_db.close.assert_called_once()

    async def test_close_handles_errors(self, mock_db, mock_graph):
        """Test close handles errors gracefully."""
        gm = GraphMemory()
        gm._db = mock_db
        gm._graph = mock_graph

        mock_db.close.side_effect = Exception("Close failed")

        # Should not raise
        await gm.close()

        assert gm._db is None
        assert gm._graph is None

    async def test_close_without_connection(self):
        """Test close does nothing without connection."""
        gm = GraphMemory()

        # Should not raise
        await gm.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestGraphMemoryIntegration:
    """Integration tests requiring FalkorDB."""

    @pytest.fixture
    async def graph_memory(self):
        """Create and initialize graph memory."""
        gm = GraphMemory(host="localhost", port=6380)
        connected = await gm.connect()
        if not connected:
            pytest.skip("FalkorDB not available")
        await gm.initialize_schema()
        yield gm
        await gm.close()

    async def test_record_and_retrieve_decision(self, graph_memory):
        """Test full cycle of recording and retrieving a decision."""
        # Record a decision
        decision_id = await graph_memory.record_decision(
            mood="contemplative",
            prompt="serene mountain landscape",
            styles=["impressionist", "atmospheric"],
            style_weights=[0.7, 0.3],
            outcome_score=0.85,
            artwork_path="/gallery/test.png",
        )

        assert decision_id != ""

        # Retrieve successful styles
        styles = await graph_memory.get_successful_styles_for_mood(
            "contemplative", min_score=0.8
        )

        # Should find at least one style
        assert any(s.name in ["impressionist", "atmospheric"] for s in styles)

    async def test_style_blend_tracking(self, graph_memory):
        """Test that style blends are tracked."""
        # Record multiple decisions with same blend
        for score in [0.8, 0.85, 0.9]:
            await graph_memory.record_decision(
                mood="serene",
                prompt=f"test {score}",
                styles=["zen", "minimalist"],
                style_weights=[0.5, 0.5],
                outcome_score=score,
                artwork_path=f"/test/{score}.png",
            )

        blends = await graph_memory.get_best_style_blends(min_score=0.8)

        # Should have recorded the blend
        assert any(
            b["style_a"] == "zen" and b["style_b"] == "minimalist" for b in blends
        ) or any(b["style_a"] == "minimalist" and b["style_b"] == "zen" for b in blends)
