"""
Drone Control REST API Routes

Endpoints for drone connection, control commands, and status.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from autonomous.services.drone_service import drone_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class ConnectRequest(BaseModel):
    drone_ip: Optional[str] = "192.168.1.1"


class CommandRequest(BaseModel):
    action: str
    params: Optional[dict] = None


class StatusResponse(BaseModel):
    connected: bool
    video_streaming: bool
    is_running: Optional[bool] = None
    device_type: Optional[int] = None
    timestamp: float


# Endpoints
@router.post("/connect")
async def connect(request: ConnectRequest):
    """
    Connect to drone

    Args:
        request: Connection request with drone IP

    Returns:
        Connection status
    """
    try:
        success = await drone_service.connect(request.drone_ip)

        if success:
            return {
                "success": True,
                "message": f"Connected to drone at {request.drone_ip}",
                "status": drone_service.get_status()
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to connect to drone"
            )

    except Exception as e:
        logger.error(f"Error in connect endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect():
    """
    Disconnect from drone

    Returns:
        Disconnection status
    """
    try:
        await drone_service.disconnect()
        return {
            "success": True,
            "message": "Disconnected from drone"
        }

    except Exception as e:
        logger.error(f"Error in disconnect endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status() -> StatusResponse:
    """
    Get drone status

    Returns:
        Current drone status
    """
    try:
        status = drone_service.get_status()
        return StatusResponse(**status)

    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/command")
async def send_command(request: CommandRequest):
    """
    Send command to drone

    Args:
        request: Command request with action and params

    Supported actions:
    - start_video: Start video stream
    - stop_video: Stop video stream
    - switch_camera: Switch camera (params: {"camera": 1|2})
    - switch_screen: Switch screen mode (params: {"mode": 1|2})
    - raw: Send raw bytes (params: {"bytes": "010203..."})

    Returns:
        Command result
    """
    try:
        action = request.action
        params = request.params or {}

        if action == "start_video":
            protocol = params.get("protocol", "s2x")
            result = await drone_service.start_video(protocol=protocol)
            return {"success": result["success"], "message": result["message"]}

        elif action == "stop_video":
            await drone_service.stop_video()
            return {"success": True, "message": "Video stopped"}

        elif action == "switch_camera":
            camera = params.get("camera", 1)
            success = await drone_service.switch_camera(camera)
            return {"success": success, "message": f"Switched to camera {camera}" if success else "Failed to switch camera"}

        elif action == "switch_screen":
            mode = params.get("mode", 1)
            success = await drone_service.switch_screen_mode(mode)
            return {"success": success, "message": f"Switched to screen mode {mode}" if success else "Failed to switch screen mode"}

        elif action == "raw":
            # Send raw bytes (hex string like "010203")
            hex_str = params.get("bytes", "")
            try:
                cmd_bytes = bytes.fromhex(hex_str)
                success = await drone_service.send_command(cmd_bytes)
                return {"success": success, "message": f"Sent {len(cmd_bytes)} bytes"}
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid hex string")

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in command endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
async def get_telemetry():
    """
    Get drone telemetry

    Returns:
        Telemetry data
    """
    try:
        telemetry = drone_service.get_telemetry()
        return telemetry

    except Exception as e:
        logger.error(f"Error in telemetry endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
