import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.api.app.core.logging import logger

router = APIRouter(tags=["WebSockets"])

class ConnectionManager:
    """Manages active browser WebSocket connections for live telemetry & quotes."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "server_time": datetime.now(timezone.utc).isoformat(),
            "feed_status": "ONLINE",
            "active_mode": "PAPER",
        })
        while True:
            # Keep connection alive & receive client pings/subscriptions
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "PING":
                    await websocket.send_json({"type": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket exception: {e}")
        manager.disconnect(websocket)
