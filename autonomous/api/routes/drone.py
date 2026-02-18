"""
Drone Control REST API Routes

Endpoints for drone connection, control commands, and status.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from autonomous.services.drone_service import drone_service
from autonomous.services.network_service import find_drone_interface

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class ConnectRequest(BaseModel):
    drone_ip: Optional[str] = ""  # auto-detect from WiFi adapter
    bind_ip: Optional[str] = ""
    protocol: Optional[str] = ""  # "e88pro" | "wifi_uav" | "" (auto-detect)


class CommandRequest(BaseModel):
    action: str
    params: Optional[dict] = None


class StatusResponse(BaseModel):
    connected: bool
    video_streaming: bool
    flight_armed: Optional[bool] = None
    is_running: Optional[bool] = None
    device_type: Optional[int] = None
    timestamp: float
    bind_ip: Optional[str] = None
    drone_protocol: Optional[str] = None


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
        bind_ip = request.bind_ip or ""
        drone_ip = request.drone_ip or ""

        # Auto-detect adapter, bind IP, and drone IP (gateway) from WiFi
        drone_iface = find_drone_interface()
        ssid = ""

        if not drone_ip and drone_iface and drone_iface.gateway_ip:
            drone_ip = drone_iface.gateway_ip  # gateway = drone IP
            logger.info(f"Auto-detected drone IP from gateway: {drone_ip}")

        if not bind_ip and drone_iface and drone_iface.local_ip:
            bind_ip = drone_iface.local_ip
            logger.info(f"Auto-detected bind IP: {drone_iface.name} -> {bind_ip}")

        if drone_iface and drone_iface.ssid:
            ssid = drone_iface.ssid

        probe_port = 0
        if drone_iface and drone_iface.probe_port:
            probe_port = drone_iface.probe_port

        if not drone_ip:
            raise HTTPException(
                status_code=400,
                detail="No drone detected. Connect to a drone WiFi hotspot "
                       "or provide drone_ip explicitly."
            )

        success = await drone_service.connect(
            drone_ip, bind_ip=bind_ip, protocol=request.protocol or "",
            ssid=ssid, probe_port=probe_port,
        )

        if success:
            return {
                "success": True,
                "message": f"Connected to drone at {drone_ip}",
                "bind_ip": bind_ip or None,
                "status": drone_service.get_status()
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to connect to drone"
            )

    except HTTPException:
        raise
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
            protocol = params.get("protocol", "")  # empty = auto-detect
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

        elif action == "arm":
            success = await drone_service.arm_flight()
            return {"success": success, "message": "Armed" if success else "Failed to arm"}

        elif action == "disarm":
            success = await drone_service.disarm_flight()
            return {"success": success, "message": "Disarmed" if success else "Failed to disarm"}

        elif action == "takeoff":
            success = await drone_service.flight_takeoff()
            return {"success": success, "message": "Takeoff" if success else "Not armed"}

        elif action == "land":
            success = await drone_service.flight_land()
            return {"success": success, "message": "Landing" if success else "Not armed"}

        elif action == "calibrate":
            success = await drone_service.flight_calibrate()
            return {"success": success, "message": "Calibrating" if success else "Not armed"}

        elif action == "headless":
            success = await drone_service.flight_headless()
            return {"success": success, "message": "Headless toggled" if success else "Not armed"}

        elif action == "axes":
            success = await drone_service.flight_set_axes(
                throttle=params.get("throttle"),
                yaw=params.get("yaw"),
                pitch=params.get("pitch"),
                roll=params.get("roll"),
            )
            return {"success": success, "message": "Axes set" if success else "Not armed"}

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
