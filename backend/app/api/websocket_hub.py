"""WebSocket Event Hub for Real-Time UI Streaming."""
import asyncio
import json
from typing import Any, Dict, List
from fastapi import WebSocket, WebSocketDisconnect
from app.core.logger import logger


class WebSocketHub:
    """Manages active browser connections and broadcasts real-time trading updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WEBSOCKET] Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WEBSOCKET] Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcasts a JSON message to all connected dashboards."""
        if not self.active_connections:
            return

        payload = {
            "event": event_type,
            "data": data
        }
        message = json.dumps(payload, default=str)
        dead_connections = []

        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead_connections.append(conn)

        for dead in dead_connections:
            self.disconnect(dead)


ws_hub = WebSocketHub()
