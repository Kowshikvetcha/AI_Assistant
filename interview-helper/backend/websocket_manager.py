"""
WebSocket connection manager.
Handles broadcasting messages to all connected frontend clients.
"""

import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from models import MessageType, ControlMessage

logger = logging.getLogger("interview_helper")


class ConnectionManager:
    """Manages active WebSocket connections and message broadcasting."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"🔗 Client connected. Active connections: "
            f"{len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"🔌 Client disconnected. Active connections: "
            f"{len(self.active_connections)}"
        )

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients.

        Silently removes any broken connections.
        """
        dead: list[WebSocket] = []
        payload = json.dumps(message)

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                dead.append(connection)

        for conn in dead:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a JSON message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")

    @property
    def client_count(self) -> int:
        return len(self.active_connections)


async def parse_control_message(data: str) -> ControlMessage | None:
    """Parse and validate a control message from the frontend.

    Args:
        data: Raw WebSocket message text.

    Returns:
        ControlMessage if valid, None otherwise.
    """
    try:
        payload = json.loads(data)
        if payload.get("type") == MessageType.CONTROL:
            return ControlMessage(**payload)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Invalid control message: {e}")
    return None
