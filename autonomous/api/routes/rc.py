"""RC WebSocket endpoint — low-latency stick control.

Accepts JSON messages with short keys: {"t": 200, "y": 127, "p": 127, "r": 127}
Directly updates the flight controller state with zero HTTP overhead.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from autonomous.services.drone_service import drone_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def rc_ws(websocket: WebSocket):
    """Real-time RC stick control via WebSocket.

    Client sends JSON: {t: throttle, y: yaw, p: pitch, r: roll} (0-255, 127=center).
    No ACK — fire and forget for minimum latency.
    """
    await websocket.accept()
    logger.info("[rc-ws] Client connected")

    try:
        while True:
            data = await websocket.receive_json()
            fc = (
                getattr(drone_service.drone, 'flight_controller', None)
                if drone_service.drone else None
            )
            if fc and getattr(fc, 'is_active', False):
                fc.set_axes(
                    throttle=data.get("t"),
                    yaw=data.get("y"),
                    pitch=data.get("p"),
                    roll=data.get("r"),
                )
    except WebSocketDisconnect:
        logger.info("[rc-ws] Client disconnected")
    except Exception as e:
        logger.debug("[rc-ws] Closed: %s", e)
