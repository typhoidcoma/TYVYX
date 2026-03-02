"""
WiFi RSSI Distance API Routes

REST endpoints for WiFi RSSI distance estimation and calibration.

Endpoints:
    GET  /status      - Get RSSI service status
    GET  /data        - Get current RSSI + distance data
    GET  /calibration - Get calibration data
    POST /start       - Start RSSI polling
    POST /stop        - Stop RSSI polling
    POST /calibrate   - Record calibration point at known distance
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from autonomous.services.wifi_rssi_service import wifi_rssi_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models

class CalibrateRequest(BaseModel):
    """Request to record calibration point"""
    distance: float = Field(..., gt=0.0, le=100.0, description="Known distance to drone in meters")


class RssiModelData(BaseModel):
    """Path-loss model parameters"""
    rssi_ref: float
    d_ref: float
    n: float


class RssiDataResponse(BaseModel):
    """Current RSSI data"""
    enabled: bool
    signal_pct: int
    rssi_dbm: float
    distance: float
    ssid: str
    timestamp: float
    model: RssiModelData
    calibration_points: int


class CalibrationPoint(BaseModel):
    """Single calibration point"""
    distance: float
    rssi_dbm: float


class CalibrationResponse(BaseModel):
    """Calibration data"""
    points: List[CalibrationPoint]
    model: RssiModelData


class StatusResponse(BaseModel):
    """Generic status response"""
    success: bool
    message: str


# Endpoints

@router.get(
    "/status",
    response_model=RssiDataResponse,
    summary="Get RSSI service status"
)
async def get_status() -> RssiDataResponse:
    try:
        data = wifi_rssi_service.get_data()
        return RssiDataResponse(**data)
    except Exception as e:
        logger.error("Error getting RSSI status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/data",
    response_model=RssiDataResponse,
    summary="Get current RSSI + distance"
)
async def get_data() -> RssiDataResponse:
    try:
        data = wifi_rssi_service.get_data()
        return RssiDataResponse(**data)
    except Exception as e:
        logger.error("Error getting RSSI data: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/calibration",
    response_model=CalibrationResponse,
    summary="Get calibration data"
)
async def get_calibration() -> CalibrationResponse:
    try:
        data = wifi_rssi_service.get_calibration()
        return CalibrationResponse(
            points=[CalibrationPoint(**p) for p in data['points']],
            model=RssiModelData(**data['model'])
        )
    except Exception as e:
        logger.error("Error getting calibration: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/start",
    response_model=StatusResponse,
    summary="Start RSSI polling"
)
async def start_rssi() -> StatusResponse:
    try:
        if wifi_rssi_service.is_enabled():
            return StatusResponse(success=True, message="RSSI polling already running")
        wifi_rssi_service.start()
        return StatusResponse(success=True, message="RSSI polling started")
    except Exception as e:
        logger.error("Error starting RSSI: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/stop",
    response_model=StatusResponse,
    summary="Stop RSSI polling"
)
async def stop_rssi() -> StatusResponse:
    try:
        if not wifi_rssi_service.is_enabled():
            return StatusResponse(success=True, message="RSSI polling already stopped")
        wifi_rssi_service.stop()
        return StatusResponse(success=True, message="RSSI polling stopped")
    except Exception as e:
        logger.error("Error stopping RSSI: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/calibrate",
    summary="Record RSSI calibration point"
)
async def calibrate(request: CalibrateRequest):
    """
    Record current RSSI at a known distance.

    Place the drone at a measured distance from the laptop and call this
    endpoint to record a calibration point. With 2+ points, the path-loss
    model (rssi_ref, n) is automatically fitted.
    """
    try:
        if not wifi_rssi_service.is_enabled():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RSSI polling not running — start it first"
            )

        result = wifi_rssi_service.calibrate(request.distance)

        if 'error' in result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['error']
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error calibrating RSSI: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
