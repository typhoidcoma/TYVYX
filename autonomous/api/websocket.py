"""
WebSocket Support for Real-Time Telemetry

Provides WebSocket endpoints for streaming drone telemetry data to frontend.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging
import json
from typing import List

from autonomous.services.drone_service import drone_service

logger = logging.getLogger(__name__)

websocket_router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store websocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove websocket connection"""
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        message_json = json.dumps(message)

        # Send to all connections, removing any that fail
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending to websocket: {e}")
                disconnected.append(connection)

        # Remove failed connections
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


manager = ConnectionManager()


@websocket_router.websocket("/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for streaming telemetry data

    Streams drone status and telemetry at ~10 Hz
    """
    await manager.connect(websocket)

    try:
        # Start telemetry broadcast loop
        while True:
            # Get telemetry data
            telemetry = drone_service.get_telemetry()

            # Send to this client
            await websocket.send_json({
                "type": "telemetry",
                "data": telemetry
            })

            # Wait for next update (10 Hz = 100ms)
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected normally")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def broadcast_telemetry():
    """
    Background task to broadcast telemetry to all connected clients

    This would be started as a background task if needed for global broadcast.
    For now, each websocket connection streams its own data.
    """
    while True:
        try:
            telemetry = drone_service.get_telemetry()

            await manager.broadcast({
                "type": "telemetry",
                "data": telemetry
            })

            await asyncio.sleep(0.1)  # 10 Hz

        except Exception as e:
            logger.error(f"Error in telemetry broadcast: {e}")
            await asyncio.sleep(1.0)
