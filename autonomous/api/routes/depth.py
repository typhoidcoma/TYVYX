"""
Depth Estimation API Routes

REST endpoints for controlling depth estimation and retrieving depth data.

Endpoints:
    GET  /status    - Get depth service status
    GET  /data      - Get current depth data (altitude, avg depth, timing)
    GET  /map       - Get colorized depth map as JPEG image
    POST /start     - Start depth estimation
    POST /stop      - Stop depth estimation
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
import logging

from autonomous.services.depth_service import depth_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models

class DepthDataResponse(BaseModel):
    """Current depth estimation data"""
    enabled: bool
    avg_depth: float
    altitude: float
    timestamp: float
    process_time_ms: float
    total_inferences: int
    total_frames: int
    model_loaded: bool
    model_name: str
    process_every_n: int
    sensitivity: int = 0
    max_depth: float = 20.0
    depth_scale: float = 0.1
    depth_range: list = [0.0, 0.0]


class SensitivityRequest(BaseModel):
    """Sensitivity value 0-100"""
    value: int


class MaxDepthRequest(BaseModel):
    """Max depth clamp in meters"""
    value: float


class DepthScaleRequest(BaseModel):
    """Depth scale multiplier for MiDaS"""
    value: float


class StatusResponse(BaseModel):
    """Generic status response"""
    success: bool
    message: str


# Endpoints

@router.get(
    "/status",
    response_model=DepthDataResponse,
    summary="Get depth service status"
)
async def get_status() -> DepthDataResponse:
    try:
        data = depth_service.get_data()
        return DepthDataResponse(**data)
    except Exception as e:
        logger.error("Error getting depth status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/data",
    response_model=DepthDataResponse,
    summary="Get current depth data"
)
async def get_data() -> DepthDataResponse:
    try:
        data = depth_service.get_data()
        return DepthDataResponse(**data)
    except Exception as e:
        logger.error("Error getting depth data: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/map",
    summary="Get colorized depth map as JPEG",
    responses={
        200: {"content": {"image/jpeg": {}}},
        204: {"description": "No depth map available yet"}
    }
)
async def get_depth_map():
    """Returns the latest colorized depth map as a JPEG image."""
    jpeg = depth_service.get_depth_jpeg()
    if jpeg is None:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")


@router.post(
    "/start",
    response_model=StatusResponse,
    summary="Start depth estimation"
)
async def start_depth() -> StatusResponse:
    try:
        if depth_service.is_enabled():
            return StatusResponse(success=True, message="Depth estimation already running")
        depth_service.start()
        return StatusResponse(success=True, message="Depth estimation started")
    except Exception as e:
        logger.error("Error starting depth: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/stop",
    response_model=StatusResponse,
    summary="Stop depth estimation"
)
async def stop_depth() -> StatusResponse:
    try:
        if not depth_service.is_enabled():
            return StatusResponse(success=True, message="Depth estimation already stopped")
        depth_service.stop()
        return StatusResponse(success=True, message="Depth estimation stopped")
    except Exception as e:
        logger.error("Error stopping depth: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/sensitivity",
    response_model=StatusResponse,
    summary="Set depth map visualization sensitivity"
)
async def set_sensitivity(request: SensitivityRequest) -> StatusResponse:
    depth_service.set_sensitivity(request.value)
    return StatusResponse(success=True, message=f"Sensitivity set to {request.value}")


@router.post(
    "/max_depth",
    response_model=StatusResponse,
    summary="Set max depth clamp (meters)"
)
async def set_max_depth(request: MaxDepthRequest) -> StatusResponse:
    depth_service.set_max_depth(request.value)
    return StatusResponse(success=True, message=f"Max depth set to {request.value}m")


@router.post(
    "/depth_scale",
    response_model=StatusResponse,
    summary="Set depth scale multiplier (MiDaS)"
)
async def set_depth_scale(request: DepthScaleRequest) -> StatusResponse:
    depth_service.set_depth_scale(request.value)
    return StatusResponse(success=True, message=f"Depth scale set to {request.value}")
