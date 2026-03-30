"""
SLAM / Visual Odometry API Routes

Endpoints for monitoring and controlling the monocular VO pipeline.

Endpoints:
    GET  /status      - VO state, keyframe count, map points, match quality
    GET  /statistics   - Detailed VO metrics
    POST /reset        - Reset VO and map
    GET  /map_points   - Sparse 3D map (JSON array)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import logging

from autonomous.services.position_service import position_service

logger = logging.getLogger(__name__)

router = APIRouter()


class SlamStatusResponse(BaseModel):
    enabled: bool
    slam_type: str
    keyframe_count: int = 0
    map_points_count: int = 0
    avg_matches: float = 0.0
    inlier_ratio: float = 0.0
    lost_count: int = 0
    frame_count: int = 0


class StatusResponse(BaseModel):
    success: bool
    message: str


@router.get(
    "/status",
    response_model=SlamStatusResponse,
    summary="Get SLAM/VO status",
)
async def get_status() -> SlamStatusResponse:
    """Get current visual odometry state and metrics."""
    vo = position_service.visual_odometry
    if vo is None:
        return SlamStatusResponse(
            enabled=position_service.enabled,
            slam_type=position_service.slam_type,
        )

    stats = vo.get_statistics()
    return SlamStatusResponse(
        enabled=position_service.enabled,
        slam_type=position_service.slam_type,
        keyframe_count=stats['keyframe_count'],
        map_points_count=stats['map_points_count'],
        avg_matches=stats['avg_matches'],
        inlier_ratio=stats['inlier_ratio'],
        lost_count=stats['lost_count'],
        frame_count=stats['frame_count'],
    )


@router.get("/statistics", summary="Detailed VO statistics")
async def get_statistics():
    """Full VO diagnostics including config and cumulative stats."""
    vo = position_service.visual_odometry
    if vo is None:
        return {
            "slam_type": position_service.slam_type,
            "vo_available": False,
        }

    stats = vo.get_statistics()
    stats["slam_type"] = position_service.slam_type
    stats["vo_available"] = True
    return stats


@router.post(
    "/reset",
    response_model=StatusResponse,
    summary="Reset VO and map",
)
async def reset_slam() -> StatusResponse:
    """Reset visual odometry state — clears map points and pose."""
    vo = position_service.visual_odometry
    if vo is None:
        return StatusResponse(
            success=False,
            message=f"VO not available (slam_type={position_service.slam_type})",
        )

    vo.reset()
    return StatusResponse(success=True, message="Visual odometry reset")


@router.get("/map_points", summary="Get sparse 3D map points")
async def get_map_points():
    """Get triangulated 3D map points as JSON array."""
    vo = position_service.visual_odometry
    if vo is None:
        return {"points": [], "count": 0}

    pts = vo.get_map_points()
    return {
        "points": pts.tolist(),
        "count": len(pts),
    }
