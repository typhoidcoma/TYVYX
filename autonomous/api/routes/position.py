"""
Position API Routes

REST endpoints for position tracking control and data retrieval.

Endpoints:
    GET  /current         - Get current position state
    GET  /trajectory      - Get trajectory history
    GET  /statistics      - Get detailed statistics
    POST /start           - Start position tracking
    POST /stop            - Stop position tracking
    POST /reset           - Reset position to origin
    POST /altitude        - Set altitude
    POST /clear_trajectory - Clear trajectory history
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging

from autonomous.services.position_service import position_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Request models

class AltitudeRequest(BaseModel):
    """Request to set altitude"""
    altitude: float = Field(..., gt=0.0, le=100.0, description="Altitude in meters (0.1-100m)")


class ResetRequest(BaseModel):
    """Request to reset position"""
    x: float = Field(default=0.0, description="Initial X position in meters")
    y: float = Field(default=0.0, description="Initial Y position in meters")


class TrajectoryRequest(BaseModel):
    """Request for trajectory data"""
    max_points: Optional[int] = Field(default=None, gt=0, le=10000, description="Maximum trajectory points to return")


# Response models

class PositionData(BaseModel):
    """Position data response"""
    x: float
    y: float


class VelocityData(BaseModel):
    """Velocity data response"""
    vx: float
    vy: float


class PositionResponse(BaseModel):
    """Current position state response"""
    position: PositionData
    velocity: VelocityData
    altitude: float
    enabled: bool
    feature_count: int
    timestamp: float


class TrajectoryPoint(BaseModel):
    """Single trajectory point"""
    x: float
    y: float
    timestamp: float


class TrajectoryResponse(BaseModel):
    """Trajectory history response"""
    points: List[TrajectoryPoint]
    count: int


class UncertaintyData(BaseModel):
    """Position uncertainty data"""
    sigma_x: float
    sigma_y: float


class MeasurementData(BaseModel):
    """Last velocity measurement"""
    vx: float
    vy: float


class StatisticsResponse(BaseModel):
    """Detailed statistics response"""
    enabled: bool
    position: PositionData
    velocity: VelocityData
    altitude: float
    frame_count: int
    trajectory_points: int
    timestamp: float
    feature_count: Optional[int] = None
    uncertainty: Optional[UncertaintyData] = None
    last_measurement: Optional[MeasurementData] = None


class StatusResponse(BaseModel):
    """Generic status response"""
    success: bool
    message: str


# Endpoints

@router.get(
    "/current",
    response_model=PositionResponse,
    summary="Get current position",
    description="Get current position state including position, velocity, and tracking status"
)
async def get_current_position() -> PositionResponse:
    """
    Get current position state

    Returns current position, velocity, altitude, tracking status, and feature count.
    """
    try:
        data = position_service.get_position()

        return PositionResponse(
            position=PositionData(
                x=data['position']['x'],
                y=data['position']['y']
            ),
            velocity=VelocityData(
                vx=data['velocity']['vx'],
                vy=data['velocity']['vy']
            ),
            altitude=data['altitude'],
            enabled=data['enabled'],
            feature_count=data['feature_count'],
            timestamp=data['timestamp']
        )

    except Exception as e:
        logger.error(f"Error getting current position: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get position: {str(e)}"
        )


@router.get(
    "/trajectory",
    response_model=TrajectoryResponse,
    summary="Get trajectory history",
    description="Get recent trajectory points showing drone path over time"
)
async def get_trajectory(max_points: Optional[int] = None) -> TrajectoryResponse:
    """
    Get trajectory history

    Args:
        max_points: Optional limit on number of points (most recent)

    Returns trajectory points with x, y, timestamp.
    """
    try:
        points = position_service.get_trajectory(max_points)

        return TrajectoryResponse(
            points=[
                TrajectoryPoint(
                    x=p['x'],
                    y=p['y'],
                    timestamp=p['timestamp']
                )
                for p in points
            ],
            count=len(points)
        )

    except Exception as e:
        logger.error(f"Error getting trajectory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trajectory: {str(e)}"
        )


@router.get(
    "/statistics",
    response_model=StatisticsResponse,
    summary="Get detailed statistics",
    description="Get comprehensive position tracking statistics including uncertainty"
)
async def get_statistics() -> StatisticsResponse:
    """
    Get detailed position statistics

    Returns position, velocity, uncertainty, feature count, and other metrics.
    """
    try:
        stats = position_service.get_statistics()

        response_data = {
            'enabled': stats['enabled'],
            'position': PositionData(
                x=stats['position']['x'],
                y=stats['position']['y']
            ),
            'velocity': VelocityData(
                vx=stats['velocity']['vx'],
                vy=stats['velocity']['vy']
            ),
            'altitude': stats['altitude'],
            'frame_count': stats['frame_count'],
            'trajectory_points': stats['trajectory_points'],
            'timestamp': stats['timestamp']
        }

        # Add optional fields if present
        if 'feature_count' in stats:
            response_data['feature_count'] = stats['feature_count']

        if 'uncertainty' in stats:
            response_data['uncertainty'] = UncertaintyData(
                sigma_x=stats['uncertainty']['sigma_x'],
                sigma_y=stats['uncertainty']['sigma_y']
            )

        if 'last_measurement' in stats:
            response_data['last_measurement'] = MeasurementData(
                vx=stats['last_measurement']['vx'],
                vy=stats['last_measurement']['vy']
            )

        return StatisticsResponse(**response_data)

    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@router.post(
    "/start",
    response_model=StatusResponse,
    summary="Start position tracking",
    description="Enable position tracking from video frames"
)
async def start_tracking() -> StatusResponse:
    """
    Start position tracking

    Enables processing of video frames for position estimation.
    Requires service to be initialized.
    """
    try:
        if position_service.is_enabled():
            return StatusResponse(
                success=True,
                message="Position tracking already running"
            )

        position_service.start()

        return StatusResponse(
            success=True,
            message="Position tracking started"
        )

    except RuntimeError as e:
        logger.error(f"Failed to start tracking: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error starting tracking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start tracking: {str(e)}"
        )


@router.post(
    "/stop",
    response_model=StatusResponse,
    summary="Stop position tracking",
    description="Disable position tracking"
)
async def stop_tracking() -> StatusResponse:
    """
    Stop position tracking

    Disables processing of video frames. Position state is preserved.
    """
    try:
        if not position_service.is_enabled():
            return StatusResponse(
                success=True,
                message="Position tracking already stopped"
            )

        position_service.stop()

        return StatusResponse(
            success=True,
            message="Position tracking stopped"
        )

    except Exception as e:
        logger.error(f"Error stopping tracking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop tracking: {str(e)}"
        )


@router.post(
    "/reset",
    response_model=StatusResponse,
    summary="Reset position",
    description="Reset position to specified coordinates (default origin)"
)
async def reset_position(request: ResetRequest = ResetRequest()) -> StatusResponse:
    """
    Reset position to initial state

    Args:
        request: Reset coordinates (x, y), defaults to (0, 0)

    Clears trajectory and resets Kalman filter.
    """
    try:
        position_service.reset(initial_position=(request.x, request.y))

        return StatusResponse(
            success=True,
            message=f"Position reset to ({request.x}, {request.y})"
        )

    except Exception as e:
        logger.error(f"Error resetting position: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset position: {str(e)}"
        )


@router.post(
    "/altitude",
    response_model=StatusResponse,
    summary="Set altitude",
    description="Update altitude for velocity scaling"
)
async def set_altitude(request: AltitudeRequest) -> StatusResponse:
    """
    Set current altitude

    Args:
        request: Altitude in meters (0.1-100m)

    Affects pixel-to-world velocity conversion.
    """
    try:
        position_service.set_altitude(request.altitude)

        return StatusResponse(
            success=True,
            message=f"Altitude set to {request.altitude:.2f}m"
        )

    except Exception as e:
        logger.error(f"Error setting altitude: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set altitude: {str(e)}"
        )


@router.post(
    "/clear_trajectory",
    response_model=StatusResponse,
    summary="Clear trajectory",
    description="Clear trajectory history without resetting position"
)
async def clear_trajectory() -> StatusResponse:
    """
    Clear trajectory history

    Removes all trajectory points but preserves current position.
    """
    try:
        position_service.clear_trajectory()

        return StatusResponse(
            success=True,
            message="Trajectory cleared"
        )

    except Exception as e:
        logger.error(f"Error clearing trajectory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear trajectory: {str(e)}"
        )
