"""Tests for WebSocket real-time events.

This module provides a test harness for testing WebSocket broadcast events,
including mood drifts, memory insights, inner dialogue, previews, and concept evolution.
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from ai_artist.web.websocket import (
    ConnectionManager,
    broadcast_concept_evolved,
    broadcast_inner_dialogue,
    broadcast_memory_insight,
    broadcast_mood_drift,
    broadcast_preview_ready,
)
from ai_artist.web.websocket import manager as global_manager


class WebSocketEventCapture:
    """Test harness for capturing WebSocket events.

    Provides a mock WebSocket that captures all received messages
    for verification in tests.
    """

    def __init__(self):
        self.received_messages: list[dict[str, Any]] = []
        self.websocket = MagicMock(spec=WebSocket)
        self.websocket.accept = AsyncMock()
        self.websocket.send_json = AsyncMock(side_effect=self._capture_message)
        self._connected = False

    async def _capture_message(self, message: dict) -> None:
        """Capture sent messages for later verification."""
        self.received_messages.append(message)

    async def connect(
        self, manager: ConnectionManager, client_id: str = "test"
    ) -> None:
        """Connect this capture client to a manager."""
        await manager.connect(self.websocket, client_id)
        self._connected = True

    async def disconnect(
        self, manager: ConnectionManager, client_id: str = "test"
    ) -> None:
        """Disconnect this capture client from a manager."""
        await manager.disconnect(self.websocket, client_id)
        self._connected = False

    def get_messages_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Filter captured messages by event type."""
        return [m for m in self.received_messages if m.get("type") == event_type]

    def clear(self) -> None:
        """Clear all captured messages."""
        self.received_messages.clear()

    @property
    def last_message(self) -> dict[str, Any] | None:
        """Get the most recently captured message."""
        return self.received_messages[-1] if self.received_messages else None

    @property
    def message_count(self) -> int:
        """Get total number of captured messages."""
        return len(self.received_messages)


class MultiClientCapture:
    """Test harness for multiple WebSocket clients.

    Manages multiple WebSocketEventCapture instances for testing
    broadcast scenarios with multiple connected clients.
    """

    def __init__(self, num_clients: int = 2):
        self.clients = [WebSocketEventCapture() for _ in range(num_clients)]

    async def connect_all(self, manager: ConnectionManager) -> None:
        """Connect all clients to the manager."""
        for i, client in enumerate(self.clients):
            await client.connect(manager, client_id=f"client-{i}")

    async def disconnect_all(self, manager: ConnectionManager) -> None:
        """Disconnect all clients from the manager."""
        for i, client in enumerate(self.clients):
            await client.disconnect(manager, client_id=f"client-{i}")

    def all_received(self, event_type: str) -> bool:
        """Check if all clients received a message of the given type."""
        return all(
            len(client.get_messages_by_type(event_type)) > 0 for client in self.clients
        )

    def get_all_messages(self) -> list[list[dict[str, Any]]]:
        """Get all messages from all clients."""
        return [client.received_messages for client in self.clients]

    def clear_all(self) -> None:
        """Clear all captured messages from all clients."""
        for client in self.clients:
            client.clear()


@pytest.fixture
def ws_manager() -> ConnectionManager:
    """Create a fresh WebSocket manager for testing."""
    return ConnectionManager()


@pytest.fixture
def event_capture() -> WebSocketEventCapture:
    """Create an event capture client."""
    return WebSocketEventCapture()


@pytest.fixture
def multi_capture() -> MultiClientCapture:
    """Create a multi-client capture harness."""
    return MultiClientCapture(num_clients=3)


class TestEventCapture:
    """Tests for the WebSocketEventCapture test harness."""

    @pytest.mark.asyncio
    async def test_capture_connects_to_manager(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test that event capture can connect to a manager."""
        await event_capture.connect(ws_manager)

        assert event_capture.websocket in ws_manager.active_connections
        event_capture.websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_receives_messages(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test that event capture receives broadcast messages."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast({"type": "test", "data": "hello"})

        assert event_capture.message_count == 1
        assert event_capture.last_message["type"] == "test"
        assert event_capture.last_message["data"] == "hello"

    @pytest.mark.asyncio
    async def test_capture_filters_by_type(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test filtering messages by type."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast({"type": "mood_drift", "mood": "contemplative"})
        await ws_manager.broadcast({"type": "memory_insight", "insight": "test"})
        await ws_manager.broadcast({"type": "mood_drift", "mood": "playful"})

        mood_messages = event_capture.get_messages_by_type("mood_drift")
        assert len(mood_messages) == 2
        assert mood_messages[0]["mood"] == "contemplative"
        assert mood_messages[1]["mood"] == "playful"


class TestMoodDriftBroadcast:
    """Tests for broadcast_mood_drift() events."""

    @pytest.mark.asyncio
    async def test_mood_drift_structure(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test mood drift event has correct structure."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_mood_drift(
            mood="contemplative", intensity=0.8, reason="natural_drift"
        )

        msg = event_capture.last_message
        assert msg is not None
        assert msg["type"] == "mood_drift"
        assert msg["mood"] == "contemplative"
        assert msg["intensity"] == 0.8
        assert msg["reason"] == "natural_drift"
        assert "timestamp" in msg
        # Verify timestamp is valid ISO format
        datetime.fromisoformat(msg["timestamp"])

    @pytest.mark.asyncio
    async def test_mood_drift_default_reason(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test mood drift with default reason."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_mood_drift(mood="playful", intensity=0.6)

        msg = event_capture.last_message
        assert msg["reason"] == "natural_drift"

    @pytest.mark.asyncio
    async def test_mood_drift_custom_reasons(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test mood drift with various trigger reasons."""
        await event_capture.connect(ws_manager)

        reasons = ["natural_drift", "creation", "interaction", "memory_recall"]

        for reason in reasons:
            event_capture.clear()
            await ws_manager.broadcast_mood_drift(
                mood="serene", intensity=0.5, reason=reason
            )
            assert event_capture.last_message["reason"] == reason

    @pytest.mark.asyncio
    async def test_mood_drift_intensity_range(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test mood drift handles various intensity values."""
        await event_capture.connect(ws_manager)

        intensities = [0.0, 0.5, 1.0, 0.33]

        for intensity in intensities:
            event_capture.clear()
            await ws_manager.broadcast_mood_drift(mood="curious", intensity=intensity)
            assert event_capture.last_message["intensity"] == intensity


class TestMemoryInsightBroadcast:
    """Tests for broadcast_memory_insight() events."""

    @pytest.mark.asyncio
    async def test_memory_insight_structure(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test memory insight event has correct structure."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_memory_insight(
            insight="I notice I create better art in the morning",
            insight_type="pattern",
        )

        msg = event_capture.last_message
        assert msg is not None
        assert msg["type"] == "memory_insight"
        assert msg["insight"] == "I notice I create better art in the morning"
        assert msg["insight_type"] == "pattern"
        assert "timestamp" in msg
        datetime.fromisoformat(msg["timestamp"])

    @pytest.mark.asyncio
    async def test_memory_insight_default_type(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test memory insight with default type."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_memory_insight(insight="Learning something new")

        msg = event_capture.last_message
        assert msg["insight_type"] == "learning"

    @pytest.mark.asyncio
    async def test_memory_insight_types(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test memory insight with various types."""
        await event_capture.connect(ws_manager)

        insight_types = ["learning", "preference", "pattern"]

        for insight_type in insight_types:
            event_capture.clear()
            await ws_manager.broadcast_memory_insight(
                insight=f"Testing {insight_type}", insight_type=insight_type
            )
            assert event_capture.last_message["insight_type"] == insight_type


class TestInnerDialogueBroadcast:
    """Tests for broadcast_inner_dialogue() events."""

    @pytest.mark.asyncio
    async def test_inner_dialogue_structure(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test inner dialogue event has correct structure."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_inner_dialogue(
            session_id="session-123",
            voice="dreamer",
            content="What if we tried something bolder?",
            iteration=1,
            metadata={"confidence": 0.9},
        )

        msg = event_capture.last_message
        assert msg is not None
        assert msg["type"] == "inner_dialogue"
        assert msg["session_id"] == "session-123"
        assert msg["voice"] == "dreamer"
        assert msg["content"] == "What if we tried something bolder?"
        assert msg["iteration"] == 1
        assert msg["metadata"] == {"confidence": 0.9}
        assert "timestamp" in msg
        datetime.fromisoformat(msg["timestamp"])

    @pytest.mark.asyncio
    async def test_inner_dialogue_default_values(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test inner dialogue with default values."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_inner_dialogue(
            session_id="session-456", voice="critic", content="This needs more contrast"
        )

        msg = event_capture.last_message
        assert msg["iteration"] == 1
        assert msg["metadata"] == {}

    @pytest.mark.asyncio
    async def test_inner_dialogue_voices(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test inner dialogue with all voice types."""
        await event_capture.connect(ws_manager)

        voices = ["dreamer", "critic", "curator", "rememberer"]

        for voice in voices:
            event_capture.clear()
            await ws_manager.broadcast_inner_dialogue(
                session_id="session-789", voice=voice, content=f"Speaking as {voice}"
            )
            assert event_capture.last_message["voice"] == voice

    @pytest.mark.asyncio
    async def test_inner_dialogue_iterations(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test inner dialogue across multiple iterations."""
        await event_capture.connect(ws_manager)

        for i in range(1, 4):
            await ws_manager.broadcast_inner_dialogue(
                session_id="session-iter",
                voice="critic",
                content=f"Iteration {i} feedback",
                iteration=i,
            )

        messages = event_capture.get_messages_by_type("inner_dialogue")
        assert len(messages) == 3
        assert [m["iteration"] for m in messages] == [1, 2, 3]


class TestPreviewReadyBroadcast:
    """Tests for broadcast_preview_ready() events."""

    @pytest.mark.asyncio
    async def test_preview_ready_structure(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test preview ready event has correct structure."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_preview_ready(
            session_id="session-preview",
            image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            score=0.85,
            approved=True,
            prompt="A serene landscape at dawn",
            generation_time=12.5,
        )

        msg = event_capture.last_message
        assert msg is not None
        assert msg["type"] == "preview_ready"
        assert msg["session_id"] == "session-preview"
        assert msg["image_base64"] is not None
        assert msg["score"] == 0.85
        assert msg["approved"] is True
        assert msg["prompt"] == "A serene landscape at dawn"
        assert msg["generation_time"] == 12.5
        assert "timestamp" in msg
        datetime.fromisoformat(msg["timestamp"])

    @pytest.mark.asyncio
    async def test_preview_ready_null_image(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test preview ready with null image (failed generation)."""
        await event_capture.connect(ws_manager)

        await ws_manager.broadcast_preview_ready(
            session_id="session-failed",
            image_base64=None,
            score=0.0,
            approved=False,
            prompt="Complex abstract concept",
            generation_time=5.0,
        )

        msg = event_capture.last_message
        assert msg["image_base64"] is None
        assert msg["approved"] is False

    @pytest.mark.asyncio
    async def test_preview_ready_approval_states(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test preview ready with approved and rejected states."""
        await event_capture.connect(ws_manager)

        # Approved preview
        await ws_manager.broadcast_preview_ready(
            session_id="session-1",
            image_base64="base64data",
            score=0.9,
            approved=True,
            prompt="Good concept",
            generation_time=10.0,
        )
        assert event_capture.last_message["approved"] is True

        # Rejected preview (low score)
        await ws_manager.broadcast_preview_ready(
            session_id="session-2",
            image_base64="base64data",
            score=0.3,
            approved=False,
            prompt="Weak concept",
            generation_time=10.0,
        )
        assert event_capture.last_message["approved"] is False


class TestConceptEvolvedBroadcast:
    """Tests for broadcast_concept_evolved() events."""

    @pytest.mark.asyncio
    async def test_concept_evolved_structure(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test concept evolved event has correct structure."""
        await event_capture.connect(ws_manager)

        concept = {
            "prompt": "A dreamlike forest",
            "style": "impressionist",
            "mood_influence": 0.7,
            "elements": ["trees", "mist", "soft_light"],
        }

        await ws_manager.broadcast_concept_evolved(
            session_id="session-evolve", concept=concept, iteration=2, reason="critique"
        )

        msg = event_capture.last_message
        assert msg is not None
        assert msg["type"] == "concept_evolved"
        assert msg["session_id"] == "session-evolve"
        assert msg["concept"] == concept
        assert msg["iteration"] == 2
        assert msg["reason"] == "critique"
        assert "timestamp" in msg
        datetime.fromisoformat(msg["timestamp"])

    @pytest.mark.asyncio
    async def test_concept_evolved_reasons(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test concept evolved with various reasons."""
        await event_capture.connect(ws_manager)

        reasons = ["critique", "insight", "memory", "mood_shift", "refinement"]

        for reason in reasons:
            event_capture.clear()
            await ws_manager.broadcast_concept_evolved(
                session_id="session-reasons",
                concept={"prompt": "test"},
                iteration=1,
                reason=reason,
            )
            assert event_capture.last_message["reason"] == reason

    @pytest.mark.asyncio
    async def test_concept_evolution_sequence(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test a sequence of concept evolutions."""
        await event_capture.connect(ws_manager)

        concepts = [
            {"prompt": "A forest", "iteration": 1},
            {"prompt": "A misty forest at dawn", "iteration": 2},
            {"prompt": "A misty forest at dawn with ethereal light", "iteration": 3},
        ]

        for i, concept in enumerate(concepts, 1):
            await ws_manager.broadcast_concept_evolved(
                session_id="session-evolution",
                concept=concept,
                iteration=i,
                reason="refinement",
            )

        messages = event_capture.get_messages_by_type("concept_evolved")
        assert len(messages) == 3
        # Verify evolution shows increasing complexity
        prompts = [m["concept"]["prompt"] for m in messages]
        assert len(prompts[0]) < len(prompts[1]) < len(prompts[2])


class TestMultipleClientsBroadcast:
    """Tests for broadcasting to multiple connected clients."""

    @pytest.mark.asyncio
    async def test_all_clients_receive_mood_drift(
        self, ws_manager: ConnectionManager, multi_capture: MultiClientCapture
    ):
        """Test all clients receive mood drift broadcast."""
        await multi_capture.connect_all(ws_manager)

        await ws_manager.broadcast_mood_drift(
            mood="euphoric", intensity=0.95, reason="creation"
        )

        assert multi_capture.all_received("mood_drift")

        # Verify all clients got the same message
        all_messages = multi_capture.get_all_messages()
        for messages in all_messages:
            assert len(messages) == 1
            assert messages[0]["mood"] == "euphoric"
            assert messages[0]["intensity"] == 0.95

    @pytest.mark.asyncio
    async def test_all_clients_receive_inner_dialogue(
        self, ws_manager: ConnectionManager, multi_capture: MultiClientCapture
    ):
        """Test all clients receive inner dialogue broadcast."""
        await multi_capture.connect_all(ws_manager)

        await ws_manager.broadcast_inner_dialogue(
            session_id="shared-session",
            voice="curator",
            content="This piece needs more balance",
            iteration=1,
        )

        assert multi_capture.all_received("inner_dialogue")

        # All clients should have identical messages
        for client in multi_capture.clients:
            msg = client.last_message
            assert msg["voice"] == "curator"
            assert msg["session_id"] == "shared-session"

    @pytest.mark.asyncio
    async def test_multiple_broadcasts_to_all_clients(
        self, ws_manager: ConnectionManager, multi_capture: MultiClientCapture
    ):
        """Test multiple broadcasts reach all clients."""
        await multi_capture.connect_all(ws_manager)

        # Send multiple different events
        await ws_manager.broadcast_mood_drift("serene", 0.8)
        await ws_manager.broadcast_memory_insight("Pattern detected", "pattern")
        await ws_manager.broadcast_inner_dialogue("s1", "dreamer", "Dreaming...")

        # Each client should have all 3 messages
        for client in multi_capture.clients:
            assert client.message_count == 3
            types = [m["type"] for m in client.received_messages]
            assert "mood_drift" in types
            assert "memory_insight" in types
            assert "inner_dialogue" in types

    @pytest.mark.asyncio
    async def test_broadcast_timestamp_consistency(
        self, ws_manager: ConnectionManager, multi_capture: MultiClientCapture
    ):
        """Test all clients receive same timestamp for a broadcast."""
        await multi_capture.connect_all(ws_manager)

        await ws_manager.broadcast_mood_drift("nostalgic", 0.6)

        # All timestamps should be identical (same broadcast)
        timestamps = [
            client.last_message["timestamp"] for client in multi_capture.clients
        ]
        assert len(set(timestamps)) == 1  # All same


class TestClientDisconnectHandling:
    """Tests for client disconnect handling during broadcasts."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_active(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test disconnected client is removed from active connections."""
        await event_capture.connect(ws_manager)
        assert event_capture.websocket in ws_manager.active_connections

        await event_capture.disconnect(ws_manager)
        assert event_capture.websocket not in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_continues_after_disconnect(
        self, ws_manager: ConnectionManager
    ):
        """Test broadcast continues working after client disconnect."""
        # Connect two clients
        client1 = WebSocketEventCapture()
        client2 = WebSocketEventCapture()

        await client1.connect(ws_manager, "client-1")
        await client2.connect(ws_manager, "client-2")

        # Disconnect first client
        await client1.disconnect(ws_manager, "client-1")

        # Broadcast should still reach second client
        await ws_manager.broadcast_mood_drift("anxious", 0.7)

        assert client2.message_count == 1
        assert client2.last_message["mood"] == "anxious"

    @pytest.mark.asyncio
    async def test_stale_connection_removed_on_broadcast(
        self, ws_manager: ConnectionManager
    ):
        """Test stale connections are cleaned up during broadcast."""
        # Create a "stale" connection that throws on send
        stale_ws = MagicMock(spec=WebSocket)
        stale_ws.accept = AsyncMock()
        stale_ws.send_json = AsyncMock(side_effect=RuntimeError("Connection closed"))

        # Create a good connection
        good_capture = WebSocketEventCapture()

        await ws_manager.connect(stale_ws, "stale")
        await good_capture.connect(ws_manager, "good")

        assert len(ws_manager.active_connections) == 2

        # Broadcast should clean up stale connection
        await ws_manager.broadcast_mood_drift("rebellious", 0.9)

        # Stale connection should be removed
        assert stale_ws not in ws_manager.active_connections
        # Good connection should still receive message
        assert good_capture.message_count == 1
        assert len(ws_manager.active_connections) == 1

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test client can reconnect after disconnect."""
        # Connect
        await event_capture.connect(ws_manager, "reconnector")
        await ws_manager.broadcast_mood_drift("serene", 0.5)
        assert event_capture.message_count == 1

        # Disconnect
        await event_capture.disconnect(ws_manager, "reconnector")

        # Clear and reconnect
        event_capture.clear()
        await event_capture.connect(ws_manager, "reconnector")

        # Should receive new messages
        await ws_manager.broadcast_mood_drift("playful", 0.8)
        assert event_capture.message_count == 1
        assert event_capture.last_message["mood"] == "playful"


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    async def setup_global_manager(self):
        """Set up and tear down global manager connections."""
        # Clear any existing connections
        async with global_manager._lock:
            global_manager.active_connections.clear()
        yield
        # Clean up
        async with global_manager._lock:
            global_manager.active_connections.clear()

    @pytest.mark.asyncio
    async def test_module_broadcast_mood_drift(self):
        """Test module-level broadcast_mood_drift function."""
        capture = WebSocketEventCapture()
        await capture.connect(global_manager, "module-test")

        await broadcast_mood_drift("transcendent", 1.0, "meditation")

        assert capture.message_count == 1
        assert capture.last_message["type"] == "mood_drift"
        assert capture.last_message["mood"] == "transcendent"

    @pytest.mark.asyncio
    async def test_module_broadcast_memory_insight(self):
        """Test module-level broadcast_memory_insight function."""
        capture = WebSocketEventCapture()
        await capture.connect(global_manager, "module-test")

        await broadcast_memory_insight("Discovered a new preference", "preference")

        assert capture.message_count == 1
        assert capture.last_message["type"] == "memory_insight"
        assert capture.last_message["insight_type"] == "preference"

    @pytest.mark.asyncio
    async def test_module_broadcast_inner_dialogue(self):
        """Test module-level broadcast_inner_dialogue function."""
        capture = WebSocketEventCapture()
        await capture.connect(global_manager, "module-test")

        await broadcast_inner_dialogue(
            session_id="module-session",
            voice="rememberer",
            content="I recall creating something similar",
            iteration=1,
            metadata={"memory_id": "mem-123"},
        )

        assert capture.message_count == 1
        assert capture.last_message["type"] == "inner_dialogue"
        assert capture.last_message["voice"] == "rememberer"

    @pytest.mark.asyncio
    async def test_module_broadcast_preview_ready(self):
        """Test module-level broadcast_preview_ready function."""
        capture = WebSocketEventCapture()
        await capture.connect(global_manager, "module-test")

        await broadcast_preview_ready(
            session_id="module-preview",
            image_base64="base64data",
            score=0.75,
            approved=True,
            prompt="Test prompt",
            generation_time=8.0,
        )

        assert capture.message_count == 1
        assert capture.last_message["type"] == "preview_ready"
        assert capture.last_message["approved"] is True

    @pytest.mark.asyncio
    async def test_module_broadcast_concept_evolved(self):
        """Test module-level broadcast_concept_evolved function."""
        capture = WebSocketEventCapture()
        await capture.connect(global_manager, "module-test")

        await broadcast_concept_evolved(
            session_id="module-evolve",
            concept={"prompt": "Evolved concept"},
            iteration=3,
            reason="insight",
        )

        assert capture.message_count == 1
        assert capture.last_message["type"] == "concept_evolved"
        assert capture.last_message["iteration"] == 3


class TestEventStructureValidation:
    """Tests to validate event structure and required fields."""

    @pytest.mark.asyncio
    async def test_all_events_have_type(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test all events include type field."""
        await event_capture.connect(ws_manager)

        # Trigger all broadcast types
        await ws_manager.broadcast_mood_drift("serene", 0.5)
        await ws_manager.broadcast_memory_insight("insight")
        await ws_manager.broadcast_inner_dialogue("s1", "critic", "content")
        await ws_manager.broadcast_preview_ready("s1", None, 0.5, False, "p", 1.0)
        await ws_manager.broadcast_concept_evolved("s1", {}, 1, "reason")

        for msg in event_capture.received_messages:
            assert "type" in msg
            assert isinstance(msg["type"], str)
            assert len(msg["type"]) > 0

    @pytest.mark.asyncio
    async def test_all_events_have_timestamp(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test all events include valid timestamp."""
        await event_capture.connect(ws_manager)

        # Trigger all broadcast types
        await ws_manager.broadcast_mood_drift("serene", 0.5)
        await ws_manager.broadcast_memory_insight("insight")
        await ws_manager.broadcast_inner_dialogue("s1", "critic", "content")
        await ws_manager.broadcast_preview_ready("s1", None, 0.5, False, "p", 1.0)
        await ws_manager.broadcast_concept_evolved("s1", {}, 1, "reason")

        for msg in event_capture.received_messages:
            assert "timestamp" in msg
            # Verify timestamp is valid ISO format
            try:
                datetime.fromisoformat(msg["timestamp"])
            except ValueError:
                pytest.fail(f"Invalid timestamp format: {msg['timestamp']}")

    @pytest.mark.asyncio
    async def test_session_events_have_session_id(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test session-scoped events include session_id."""
        await event_capture.connect(ws_manager)

        session_id = "test-session-id"

        # These events should have session_id
        await ws_manager.broadcast_inner_dialogue(session_id, "critic", "content")
        await ws_manager.broadcast_preview_ready(session_id, None, 0.5, False, "p", 1.0)
        await ws_manager.broadcast_concept_evolved(session_id, {}, 1, "reason")

        for msg in event_capture.received_messages:
            assert "session_id" in msg
            assert msg["session_id"] == session_id


class TestConcurrencyAndRaceConditions:
    """Tests for concurrent access and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(
        self, ws_manager: ConnectionManager, event_capture: WebSocketEventCapture
    ):
        """Test multiple concurrent broadcasts."""
        await event_capture.connect(ws_manager)

        # Send multiple broadcasts concurrently
        tasks = [ws_manager.broadcast_mood_drift(f"mood-{i}", 0.5) for i in range(10)]
        await asyncio.gather(*tasks)

        # All messages should be received
        assert event_capture.message_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_connect_disconnect(self, ws_manager: ConnectionManager):
        """Test concurrent connect and disconnect operations."""
        captures = [WebSocketEventCapture() for _ in range(5)]

        # Connect all concurrently
        await asyncio.gather(
            *[c.connect(ws_manager, f"client-{i}") for i, c in enumerate(captures)]
        )

        assert len(ws_manager.active_connections) == 5

        # Disconnect half concurrently
        await asyncio.gather(
            *[
                c.disconnect(ws_manager, f"client-{i}")
                for i, c in enumerate(captures[:3])
            ]
        )

        assert len(ws_manager.active_connections) == 2

    @pytest.mark.asyncio
    async def test_broadcast_during_connect_disconnect(
        self, ws_manager: ConnectionManager
    ):
        """Test broadcasts while clients connect and disconnect."""
        stable_capture = WebSocketEventCapture()
        await stable_capture.connect(ws_manager, "stable")

        async def connect_disconnect():
            c = WebSocketEventCapture()
            await c.connect(ws_manager, "transient")
            await asyncio.sleep(0.01)
            await c.disconnect(ws_manager, "transient")

        async def broadcast_loop():
            for i in range(5):
                await ws_manager.broadcast_mood_drift(f"mood-{i}", 0.5)
                await asyncio.sleep(0.005)

        # Run both concurrently
        await asyncio.gather(connect_disconnect(), broadcast_loop())

        # Stable client should receive at least some messages
        assert stable_capture.message_count > 0
