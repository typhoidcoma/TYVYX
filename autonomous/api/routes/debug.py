"""
Debug API Routes — Individual Sensor Fusion Testing

Endpoints for testing each sensor fusion component in isolation:
- Optical flow: pixel velocity, feature count, coordinate transform
- Depth: raw values, altitude feed status
- RSSI: history, model params, reset calibration
- EKF: full state vector, covariance, inject synthetic measurements
- Pipeline: enable/disable individual measurement streams
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
import numpy as np

from autonomous.services.position_service import position_service
from autonomous.services.depth_service import depth_service
from autonomous.services.wifi_rssi_service import wifi_rssi_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Optical Flow ──────────────────────────────────────────────

@router.get("/optical_flow", summary="Optical flow state")
async def get_optical_flow_state():
    """Raw optical flow diagnostics: pixel velocity, feature count, GPU status."""
    of = position_service.optical_flow
    if not of:
        return {"initialized": False}

    return {
        "initialized": True,
        "feature_count": of.get_feature_count(),
        "using_gpu": getattr(of, 'use_gpu', False),
        "max_corners": getattr(of, 'max_corners', None),
        "min_features": getattr(of, 'min_features', None),
        "max_pixel_velocity": getattr(of, 'max_pixel_velocity', None),
        "last_pixel_velocity": _ndarray_to_list(
            position_service.last_velocity_measurement
        ) if position_service.last_velocity_measurement is not None else None,
    }


# ── Coordinate Transform ─────────────────────────────────────

class TransformTestRequest(BaseModel):
    """Test pixel velocity → world velocity conversion."""
    vx_px: float = Field(..., description="Pixel velocity X (px/frame)")
    vy_px: float = Field(..., description="Pixel velocity Y (px/frame)")
    altitude: Optional[float] = Field(None, description="Override altitude (m)")
    fps: Optional[float] = Field(None, description="Override FPS")


@router.post("/transform/pixel_to_world", summary="Test pixel→world transform")
async def test_pixel_to_world(req: TransformTestRequest):
    """Convert pixel velocity to world velocity with current or custom params."""
    t = position_service.transformer
    if not t:
        raise HTTPException(400, "CoordinateTransformer not initialized")

    alt = req.altitude if req.altitude is not None else position_service.altitude
    fps = req.fps if req.fps is not None else position_service.fps

    pixel_vel = np.array([req.vx_px, req.vy_px])
    world_vel = t.pixel_velocity_to_world(pixel_vel, altitude=alt, fps=fps)

    return {
        "input": {"vx_px": req.vx_px, "vy_px": req.vy_px},
        "params": {
            "altitude": alt,
            "fps": fps,
            "fx": float(t.fx),
            "fy": float(t.fy),
        },
        "output": {
            "vx_world": float(world_vel[0]),
            "vy_world": float(world_vel[1]),
        },
        "scale_m_per_px": float(t.get_ground_plane_scale(alt)),
    }


@router.get("/transform/camera", summary="Camera intrinsics")
async def get_camera_intrinsics():
    """Current camera matrix parameters."""
    t = position_service.transformer
    if not t:
        return {"initialized": False}

    fov_x, fov_y = t.get_field_of_view(640, 360)
    return {
        "fx": float(t.fx),
        "fy": float(t.fy),
        "cx": float(t.cx),
        "cy": float(t.cy),
        "fov_x_deg": float(np.degrees(fov_x)),
        "fov_y_deg": float(np.degrees(fov_y)),
        "altitude": float(t.altitude),
        "scale_m_per_px": float(t.get_ground_plane_scale()),
    }


# ── EKF ───────────────────────────────────────────────────────

@router.get("/ekf/state", summary="Full EKF state")
async def get_ekf_state():
    """Full 6-state vector, covariance diagonal, and update counts."""
    ekf = position_service.estimator
    if not ekf:
        return {"initialized": False}

    state = ekf.get_state()
    P = ekf.get_covariance()
    stats = ekf.get_statistics()

    return {
        "state": {
            "x": float(state[0]),
            "y": float(state[1]),
            "z": float(state[2]),
            "vx": float(state[3]),
            "vy": float(state[4]),
            "vz": float(state[5]),
        },
        "covariance_diag": [float(P[i, i]) for i in range(6)],
        "uncertainty": stats["uncertainty"],
        "anchor": stats["anchor_position"],
        "updates": {
            "predictions": stats["num_predictions"],
            "velocity": stats["num_velocity_updates"],
            "altitude": stats["num_altitude_updates"],
            "rssi": stats["num_rssi_updates"],
        },
    }


class InjectVelocityRequest(BaseModel):
    vx: float = Field(..., description="World velocity X (m/s)")
    vy: float = Field(..., description="World velocity Y (m/s)")


@router.post("/ekf/inject_velocity", summary="Inject synthetic velocity")
async def inject_velocity(req: InjectVelocityRequest):
    """Test EKF by injecting a synthetic velocity measurement."""
    ekf = position_service.estimator
    if not ekf:
        raise HTTPException(400, "EKF not initialized")

    before = ekf.get_state().copy()
    world_vel = np.array([req.vx, req.vy])
    ekf.predict_and_update_velocity(world_vel, dt=0.05)
    after = ekf.get_state()

    return {
        "before": {"x": float(before[0]), "y": float(before[1]), "z": float(before[2])},
        "injected": {"vx": req.vx, "vy": req.vy},
        "after": {"x": float(after[0]), "y": float(after[1]), "z": float(after[2])},
        "delta": {
            "dx": float(after[0] - before[0]),
            "dy": float(after[1] - before[1]),
            "dz": float(after[2] - before[2]),
        },
    }


class InjectAltitudeRequest(BaseModel):
    altitude: float = Field(..., description="Altitude (m)")


@router.post("/ekf/inject_altitude", summary="Inject synthetic altitude")
async def inject_altitude(req: InjectAltitudeRequest):
    """Test EKF by injecting a synthetic altitude measurement."""
    ekf = position_service.estimator
    if not ekf:
        raise HTTPException(400, "EKF not initialized")

    before_z = float(ekf.get_state()[2])
    ekf.update_altitude(req.altitude)
    after_z = float(ekf.get_state()[2])

    return {
        "before_z": before_z,
        "injected": req.altitude,
        "after_z": after_z,
        "delta_z": after_z - before_z,
    }


class InjectRssiRequest(BaseModel):
    distance: float = Field(..., description="Distance (m)")


@router.post("/ekf/inject_rssi", summary="Inject synthetic RSSI distance")
async def inject_rssi(req: InjectRssiRequest):
    """Test EKF by injecting a synthetic RSSI distance measurement."""
    ekf = position_service.estimator
    if not ekf:
        raise HTTPException(400, "EKF not initialized")

    before = ekf.get_state().copy()
    ekf.update_rssi_distance(req.distance)
    after = ekf.get_state()

    return {
        "before": {"x": float(before[0]), "y": float(before[1]), "z": float(before[2])},
        "injected_distance": req.distance,
        "after": {"x": float(after[0]), "y": float(after[1]), "z": float(after[2])},
        "anchor": _ndarray_to_list(ekf.laptop_position),
    }


# ── Depth ─────────────────────────────────────────────────────

@router.get("/depth", summary="Depth service diagnostics")
async def get_depth_diagnostics():
    """Depth service internals: model info, altitude, feed status."""
    if not depth_service._initialized:
        return {"initialized": False}

    data = depth_service.get_data()
    return {
        "enabled": data.get("enabled", False),
        "altitude": data.get("altitude", 0),
        "avg_depth": data.get("avg_depth", 0),
        "model_name": data.get("model_name", "unknown"),
        "model_loaded": data.get("model_loaded", False),
        "process_time_ms": data.get("process_time_ms", 0),
        "total_inferences": data.get("total_inferences", 0),
        "feeds_ekf_altitude": position_service.using_bottom_camera,
        "depth_scale": getattr(depth_service, 'depth_scale', None),
    }


# ── RSSI ──────────────────────────────────────────────────────

@router.get("/rssi", summary="RSSI service diagnostics")
async def get_rssi_diagnostics():
    """RSSI service internals: model params, raw readings, calibration."""
    if not wifi_rssi_service._initialized:
        return {"initialized": False}

    data = wifi_rssi_service.get_data()
    cal = wifi_rssi_service.get_calibration()

    return {
        "enabled": data.get("enabled", False),
        "signal_pct": data.get("signal_pct", 0),
        "rssi_dbm": data.get("rssi_dbm", 0),
        "distance": data.get("distance", 0),
        "ssid": data.get("ssid", ""),
        "model": data.get("model", {}),
        "calibration_points": cal.get("points", []),
        "smoothing_window": getattr(wifi_rssi_service, 'smoothing_window', None),
        "poll_hz": getattr(wifi_rssi_service, 'poll_hz', None),
    }


class RssiModelRequest(BaseModel):
    rssi_ref: Optional[float] = Field(None, description="Reference RSSI (dBm) at d_ref")
    n: Optional[float] = Field(None, description="Path-loss exponent")
    d_ref: Optional[float] = Field(None, description="Reference distance (m)")


@router.post("/rssi/set_model", summary="Set RSSI path-loss model")
async def set_rssi_model(req: RssiModelRequest):
    """Manually set RSSI path-loss parameters for testing."""
    if not wifi_rssi_service._initialized:
        raise HTTPException(400, "RSSI service not initialized")

    if req.rssi_ref is not None:
        wifi_rssi_service.rssi_ref = req.rssi_ref
    if req.n is not None:
        wifi_rssi_service.path_loss_exponent = req.n
    if req.d_ref is not None:
        wifi_rssi_service.d_ref = req.d_ref

    return {
        "rssi_ref": wifi_rssi_service.rssi_ref,
        "n": wifi_rssi_service.path_loss_exponent,
        "d_ref": wifi_rssi_service.d_ref,
    }


@router.post("/rssi/reset_calibration", summary="Reset RSSI calibration")
async def reset_rssi_calibration():
    """Clear all calibration points and reset to default model."""
    if not wifi_rssi_service._initialized:
        raise HTTPException(400, "RSSI service not initialized")

    wifi_rssi_service.calibration_points = []
    return {"message": "Calibration points cleared", "calibration_points": 0}


# ── Pipeline Control ──────────────────────────────────────────

@router.get("/pipeline", summary="Full pipeline status")
async def get_pipeline_status():
    """Overview of the entire sensor fusion pipeline."""
    ekf = position_service.estimator
    ekf_stats = ekf.get_statistics() if ekf else {}

    return {
        "position_enabled": position_service.enabled,
        "camera_mode": "bottom" if position_service.using_bottom_camera else "front",
        "altitude": position_service.altitude,
        "fps": position_service.fps,
        "frame_count": position_service.frame_count,
        "depth_enabled": depth_service.is_enabled(),
        "depth_feeds_altitude": position_service.using_bottom_camera,
        "rssi_enabled": wifi_rssi_service.is_enabled(),
        "optical_flow_features": (
            position_service.optical_flow.get_feature_count()
            if position_service.optical_flow else 0
        ),
        "ekf": {
            "updates": {
                "velocity": ekf_stats.get("num_velocity_updates", 0),
                "altitude": ekf_stats.get("num_altitude_updates", 0),
                "rssi": ekf_stats.get("num_rssi_updates", 0),
                "predictions": ekf_stats.get("num_predictions", 0),
            },
            "anchor": ekf_stats.get("anchor_position", {}),
        } if ekf_stats else None,
    }


# ── Helpers ───────────────────────────────────────────────────

def _ndarray_to_list(arr):
    """Convert numpy array to JSON-safe list."""
    if arr is None:
        return None
    if hasattr(arr, 'tolist'):
        return arr.tolist()
    return list(arr)
