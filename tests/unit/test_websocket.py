"""Tests for WebSocket functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from ai_artist.web.app import app
from ai_artist.web.websocket import ConnectionManager


@pytest.fixture
def ws_manager():
    """Create a fresh WebSocket manager."""
    return ConnectionManager()


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestConnectionManager:
    """Test ConnectionManager functionality."""

    @pytest.mark.asyncio
    async def test_connect(self, ws_manager):
        """Test WebSocket connection."""
        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()

        await ws_manager.connect(mock_websocket, client_id="test-123")

        assert mock_websocket in ws_manager.active_connections
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_rejects_when_at_limit(self, ws_manager):
        """Test connection limit enforcement."""
        ws_manager.max_connections = 1
        first = MagicMock()
        first.accept = AsyncMock()
        second = MagicMock()
        second.accept = AsyncMock()

        assert await ws_manager.connect(first, client_id="first") is True
        assert await ws_manager.connect(second, client_id="second") is False
        second.accept.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect(self, ws_manager):
        """Test WebSocket disconnection."""
        mock_websocket = MagicMock()
        ws_manager.active_connections.append(mock_websocket)

        await ws_manager.disconnect(mock_websocket, client_id="test-123")

        assert mock_websocket not in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_send_personal_message(self, ws_manager):
        """Test sending personal message to specific connection."""
        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        await ws_manager.send_personal_message({"type": "test"}, mock_websocket)

        mock_websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast(self, ws_manager):
        """Test broadcasting to all connections."""
        mock_ws1 = MagicMock()
        mock_ws1.send_json = AsyncMock()
        mock_ws2 = MagicMock()
        mock_ws2.send_json = AsyncMock()

        ws_manager.active_connections = [mock_ws1, mock_ws2]

        await ws_manager.broadcast({"type": "test", "message": "hello"})

        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected(self, ws_manager):
        """Test broadcast handles disconnected clients gracefully."""
        mock_ws_good = MagicMock()
        mock_ws_good.send_json = AsyncMock()

        mock_ws_bad = MagicMock()
        mock_ws_bad.send_json = AsyncMock(side_effect=Exception("Disconnected"))

        ws_manager.active_connections = [mock_ws_good, mock_ws_bad]

        await ws_manager.broadcast({"type": "test"})

        # Good connection should still work
        mock_ws_good.send_json.assert_called_once()
        # Bad connection should be removed
        assert mock_ws_bad not in ws_manager.active_connections


class TestWebSocketMessages:
    """Test WebSocket message types."""

    @pytest.mark.asyncio
    async def test_generation_progress_message(self, ws_manager):
        """Test generation progress message format."""
        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        ws_manager.active_connections = [mock_websocket]

        await ws_manager.send_generation_progress(
            session_id="test-session",
            step=15,
            total_steps=30,
            message="Generating... 50%",
        )

        # Verify message was sent
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "generation_progress"
        assert call_args["session_id"] == "test-session"
        assert call_args["step"] == 15
        assert call_args["total_steps"] == 30

    @pytest.mark.asyncio
    async def test_generation_complete_message(self, ws_manager):
        """Test generation complete message format."""
        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        ws_manager.active_connections = [mock_websocket]

        await ws_manager.send_generation_complete(
            session_id="test-session",
            image_paths=["/path/to/image.png"],
            metadata={"prompt": "test"},
        )

        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "generation_complete"
        assert call_args["session_id"] == "test-session"
        assert len(call_args["image_paths"]) == 1

    @pytest.mark.asyncio
    async def test_generation_error_message(self, ws_manager):
        """Test generation error message format."""
        mock_websocket = MagicMock()
        mock_websocket.send_json = AsyncMock()

        ws_manager.active_connections = [mock_websocket]

        await ws_manager.send_generation_error(
            session_id="test-session", error="Out of memory"
        )

        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "generation_error"
        assert call_args["session_id"] == "test-session"
        assert call_args["error"] == "Out of memory"


class TestWebSocketEndpoint:
    """Test WebSocket endpoint integration."""

    def test_websocket_connect(self, client):
        """Test WebSocket connection endpoint."""
        with client.websocket_connect("/ws") as websocket:
            # Connection successful
            assert websocket is not None

    def test_websocket_receive_ping(self, client):
        """Test receiving ping message."""
        with client.websocket_connect("/ws") as websocket:
            # Send ping
            websocket.send_json({"type": "ping"})

            # Should receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"

    def test_websocket_subscribe_to_session(self, client):
        """Test subscribing to generation session."""
        with client.websocket_connect("/ws") as websocket:
            session_id = "test-session-123"

            # Send subscribe message
            websocket.send_json({"type": "subscribe", "session_id": session_id})

            # Should be subscribed (no error)
            # In real implementation, would verify subscription

    def test_websocket_rejects_unsupported_message_type(self, client):
        """Test unsupported inbound message types are rejected."""
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "admin_command", "payload": "evil"})
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "Unsupported" in data["error"]

    def test_websocket_multiple_connections(self, client):
        """Test multiple concurrent WebSocket connections."""
        with (
            client.websocket_connect("/ws") as ws1,
            client.websocket_connect("/ws") as ws2,
        ):
            ws1.send_json({"type": "ping"})
            ws2.send_json({"type": "ping"})

            assert ws1.receive_json()["type"] == "pong"
            assert ws2.receive_json()["type"] == "pong"


class TestWebSocketReconnection:
    """Test reconnection scenarios."""

    def test_disconnect_and_reconnect(self, client):
        """Test client can reconnect after disconnect."""
        # First connection
        with client.websocket_connect("/ws") as ws1:
            ws1.send_json({"type": "ping"})
            assert ws1.receive_json()["type"] == "pong"

        # Reconnect
        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "ping"})
            assert ws2.receive_json()["type"] == "pong"
