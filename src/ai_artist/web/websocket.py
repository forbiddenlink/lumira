"""WebSocket manager for real-time updates."""

import asyncio
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts.

    Follows FastAPI WebSocket best practices for connection management.
    Thread-safe using asyncio.Lock for connection list modifications.
    """

    def __init__(self):
        # Use list instead of set for better iteration safety
        self.active_connections: list[WebSocket] = []
        self.generation_sessions: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str = ""):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(
            "websocket_connected",
            client_id=client_id,
            total_connections=len(self.active_connections),
        )

    async def disconnect(self, websocket: WebSocket, client_id: str = ""):
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(
            "websocket_disconnected",
            client_id=client_id,
            total_connections=len(self.active_connections),
        )

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning("websocket_send_failed", error=str(e))
            # Remove dead connection
            await self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients.

        Handles disconnections gracefully and removes stale connections.
        Thread-safe: creates copy of connections list before iterating.
        """
        # Create copy to avoid modification during iteration
        async with self._lock:
            connections_copy = self.active_connections.copy()

        disconnected = []
        for connection in connections_copy:
            try:
                await connection.send_json(message)
            except (WebSocketDisconnect, RuntimeError) as e:
                # Connection closed or stale
                logger.debug("broadcast_connection_closed", error=str(e))
                disconnected.append(connection)
            except Exception as e:
                logger.warning("broadcast_failed", error=str(e))
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)

    async def send_generation_start(self, session_id: str, prompt: str = ""):
        """Send generation start notification."""
        start = {
            "type": "generation_start",
            "session_id": session_id,
            "prompt": prompt,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(start)

    async def send_generation_progress(
        self, session_id: str, step: int, total_steps: int, message: str = ""
    ):
        """Send generation progress update."""
        progress = {
            "type": "generation_progress",
            "session_id": session_id,
            "step": step,
            "total_steps": total_steps,
            "progress_percent": int((step / total_steps) * 100),
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(progress)

    async def send_generation_complete(
        self, session_id: str, image_paths: list, metadata: dict
    ):
        """Send generation complete notification."""
        complete = {
            "type": "generation_complete",
            "session_id": session_id,
            "image_paths": image_paths,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(complete)

    async def send_generation_error(self, session_id: str, error: str):
        """Send generation error notification."""
        error_msg = {
            "type": "generation_error",
            "session_id": session_id,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(error_msg)

    async def send_curation_update(
        self, session_id: str, image_path: str, metrics: dict
    ):
        """Send curation metrics update."""
        update = {
            "type": "curation_update",
            "session_id": session_id,
            "image_path": image_path,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(update)

    async def send_gallery_update(self, action: str, image_data: dict):
        """Send gallery update notification."""
        update = {
            "type": "gallery_update",
            "action": action,  # "new_image", "deleted", "featured"
            "data": image_data,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(update)

    async def send_thinking_update(
        self,
        session_id: str,
        thought_type: str,
        content: str,
        context: dict | None = None,
    ):
        """Send Lumira's thinking process update for visible thinking.

        Args:
            session_id: The creation session ID
            thought_type: One of "observe", "reflect", "decide", "express", "create"
            content: The thought content
            context: Optional additional context
        """
        update = {
            "type": "thinking_update",
            "session_id": session_id,
            "thought_type": thought_type,
            "content": content,
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(update)

    async def send_lumira_state(
        self,
        mood: str,
        energy: float,
        feeling: str,
        session_id: str | None = None,
    ):
        """Send Lumira's current emotional state.

        Args:
            mood: Current mood name
            energy: Energy level (0-1)
            feeling: Lumira's description of how she feels
            session_id: Optional session ID
        """
        state = {
            "type": "lumira_state",
            "session_id": session_id,
            "mood": mood,
            "energy": energy,
            "feeling": feeling,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(state)

    async def send_critique_update(
        self,
        session_id: str,
        iteration: int,
        approved: bool,
        critique: str,
        confidence: float,
    ):
        """Send critique loop update.

        Args:
            session_id: The creation session ID
            iteration: Which critique iteration (1, 2, 3...)
            approved: Whether the concept was approved
            critique: The critique text
            confidence: Confidence score (0-1)
        """
        update = {
            "type": "critique_update",
            "session_id": session_id,
            "iteration": iteration,
            "approved": approved,
            "critique": critique,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(update)

    async def broadcast_mood_drift(
        self,
        mood: str,
        intensity: float,
        reason: str = "natural_drift",
    ):
        """Broadcast mood drift to all connected clients.

        Args:
            mood: The new mood name
            intensity: Mood intensity (0-1)
            reason: What triggered the drift (natural_drift, creation, interaction)
        """
        message = {
            "type": "mood_drift",
            "mood": mood,
            "intensity": intensity,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(message)

    async def broadcast_memory_insight(
        self,
        insight: str,
        insight_type: str = "learning",
    ):
        """Broadcast a memory insight to all connected clients.

        Args:
            insight: The insight content
            insight_type: Type of insight (learning, preference, pattern)
        """
        message = {
            "type": "memory_insight",
            "insight": insight,
            "insight_type": insight_type,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(message)


# Global instance
manager = ConnectionManager()


# Convenience functions for module-level access
async def broadcast_mood_drift(
    mood: str, intensity: float, reason: str = "natural_drift"
):
    """Broadcast mood drift to all connected clients."""
    await manager.broadcast_mood_drift(mood, intensity, reason)


async def broadcast_memory_insight(insight: str, insight_type: str = "learning"):
    """Broadcast a memory insight to all connected clients."""
    await manager.broadcast_memory_insight(insight, insight_type)
