"""
Autopilot API Routes — Position hold control.

Endpoints for enabling/disabling position hold, setting target,
and tuning PID gains at runtime.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from autonomous.services.autopilot_service import autopilot_service

logger = logging.getLogger(__name__)

router = APIRouter()


class EnableRequest(BaseModel):
    x: Optional[float] = Field(default=None, description="Target X (None = current)")
    y: Optional[float] = Field(default=None, description="Target Y (None = current)")


class TargetRequest(BaseModel):
    x: float
    y: float


class GainsRequest(BaseModel):
    axis: str = Field(..., description="'x' or 'y'")
    kp: Optional[float] = None
    ki: Optional[float] = None
    kd: Optional[float] = None


@router.get("/state")
async def get_state():
    """Get current autopilot state."""
    return autopilot_service.get_state()


@router.post("/enable")
async def enable(request: EnableRequest = EnableRequest()):
    """Enable position hold at current (or specified) position."""
    try:
        autopilot_service.enable(target_x=request.x, target_y=request.y)
        return {"success": True, "message": "Position hold enabled"}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[autopilot] Enable error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disable")
async def disable():
    """Disable position hold."""
    autopilot_service.disable()
    return {"success": True, "message": "Position hold disabled"}


@router.post("/target")
async def set_target(request: TargetRequest):
    """Update target position while hold is active."""
    if not autopilot_service.is_enabled():
        raise HTTPException(status_code=400, detail="Autopilot not enabled")
    autopilot_service.set_target(request.x, request.y)
    return {"success": True, "message": "Target updated"}


@router.post("/gains")
async def set_gains(request: GainsRequest):
    """Tune PID gains for an axis."""
    if request.axis not in ('x', 'y'):
        raise HTTPException(status_code=400, detail="axis must be 'x' or 'y'")
    autopilot_service.set_gains(
        request.axis, kp=request.kp, ki=request.ki, kd=request.kd,
    )
    return {"success": True, "message": f"Gains updated for {request.axis}"}
