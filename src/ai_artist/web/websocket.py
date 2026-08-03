"""WebSocket manager for real-time updates."""

import asyncio
import os
import time
from collections import deque
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from ..utils.logging import get_logger

logger = get_logger(__name__)

ALLOWED_CLIENT_MESSAGE_TYPES = frozenset({"ping", "subscribe"})
DEFAULT_WS_MAX_CONNECTIONS = 100
DEFAULT_WS_MAX_MESSAGES_PER_MINUTE = 60


class ConnectionManager:
    """Manages WebSocket connections and broadcasts.

    Follows FastAPI WebSocket best practices for connection management.
    Thread-safe using asyncio.Lock for connection list modifications.
    """

    def __init__(self):
        # Use list instead of set for better iteration safety
        self.active_connections: list[WebSocket] = []
        self.generation_sessions: dict[str, dict] = {}
        # Lock is bound lazily to the running event loop (see _lock). Creating it
        # here would bind it to whichever loop was current at import time, and
        # asyncio.Lock raises if later acquired from a different loop — which is
        # exactly what happens with function-scoped test loops against this
        # module-level singleton.
        self._lock_obj: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self.max_connections = int(
            os.getenv("WS_MAX_CONNECTIONS", str(DEFAULT_WS_MAX_CONNECTIONS))
        )
        self.max_messages_per_minute = int(
            os.getenv(
                "WS_MAX_MESSAGES_PER_MINUTE",
                str(DEFAULT_WS_MAX_MESSAGES_PER_MINUTE),
            )
        )
        self._message_times: dict[int, deque[float]] = {}

    @property
    def _lock(self) -> asyncio.Lock:
        """Return a lock bound to the current running loop, recreating it if the
        loop changed. In production there is a single loop, so the lock is made
        once; under test isolation each async test gets a fresh loop and a
        matching fresh lock, avoiding 'bound to a different event loop' errors.
        """
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock_obj is None or self._lock_loop is not loop:
            self._lock_obj = asyncio.Lock()
            self._lock_loop = loop
        return self._lock_obj

    async def connect(self, websocket: WebSocket, client_id: str = "") -> bool:
        """Accept and register a WebSocket connection."""
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                logger.warning(
                    "websocket_connection_limit_reached",
                    client_id=client_id,
                    max_connections=self.max_connections,
                )
                return False

        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        self._message_times[id(websocket)] = deque()
        logger.info(
            "websocket_connected",
            client_id=client_id,
            total_connections=len(self.active_connections),
        )
        return True

    async def disconnect(self, websocket: WebSocket, client_id: str = ""):
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        self._message_times.pop(id(websocket), None)
        logger.info(
            "websocket_disconnected",
            client_id=client_id,
            total_connections=len(self.active_connections),
        )

    def allow_client_message(self, websocket: WebSocket) -> bool:
        """Rate-limit inbound client messages."""
        now = time.monotonic()
        window_start = now - 60.0
        key = id(websocket)
        times = self._message_times.setdefault(key, deque())

        while times and times[0] < window_start:
            times.popleft()

        if len(times) >= self.max_messages_per_minute:
            return False

        times.append(now)
        return True

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
                # Bound each send so one stalled/slow client cannot block
                # delivery to every other connected client.
                await asyncio.wait_for(connection.send_json(message), timeout=5.0)
            except TimeoutError:
                logger.warning("broadcast_send_timeout")
                disconnected.append(connection)
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

    async def broadcast_inner_dialogue(
        self,
        session_id: str,
        voice: str,
        content: str,
        iteration: int = 1,
        metadata: dict | None = None,
    ):
        """Broadcast an inner dialogue turn.

        Args:
            session_id: The creation session ID
            voice: The inner voice speaking (dreamer, critic, curator, rememberer)
            content: What the voice said
            iteration: Current iteration number
            metadata: Optional additional context
        """
        message = {
            "type": "inner_dialogue",
            "session_id": session_id,
            "voice": voice,
            "content": content,
            "iteration": iteration,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(message)

    async def broadcast_preview_ready(
        self,
        session_id: str,
        image_base64: str | None,
        score: float,
        approved: bool,
        prompt: str,
        generation_time: float,
    ):
        """Broadcast when a preview is ready for review.

        Args:
            session_id: The creation session ID
            image_base64: Base64-encoded preview image
            score: Quality score (0-1)
            approved: Whether auto-approved
            prompt: The generation prompt
            generation_time: How long generation took
        """
        message = {
            "type": "preview_ready",
            "session_id": session_id,
            "image_base64": image_base64,
            "score": score,
            "approved": approved,
            "prompt": prompt,
            "generation_time": generation_time,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast(message)

    async def broadcast_concept_evolved(
        self,
        session_id: str,
        concept: dict,
        iteration: int,
        reason: str,
    ):
        """Broadcast when a concept evolves during deliberation.

        Args:
            session_id: The creation session ID
            concept: The evolved concept details
            iteration: Which iteration this is
            reason: Why the concept evolved (critique, insight, etc)
        """
        message = {
            "type": "concept_evolved",
            "session_id": session_id,
            "concept": concept,
            "iteration": iteration,
            "reason": reason,
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


async def broadcast_inner_dialogue(
    session_id: str,
    voice: str,
    content: str,
    iteration: int = 1,
    metadata: dict | None = None,
):
    """Broadcast an inner dialogue turn."""
    await manager.broadcast_inner_dialogue(
        session_id, voice, content, iteration, metadata
    )


async def broadcast_preview_ready(
    session_id: str,
    image_base64: str | None,
    score: float,
    approved: bool,
    prompt: str,
    generation_time: float,
):
    """Broadcast when a preview is ready."""
    await manager.broadcast_preview_ready(
        session_id, image_base64, score, approved, prompt, generation_time
    )


async def broadcast_concept_evolved(
    session_id: str,
    concept: dict,
    iteration: int,
    reason: str,
):
    """Broadcast when a concept evolves."""
    await manager.broadcast_concept_evolved(session_id, concept, iteration, reason)
