"""
Extended Kalman Filter for 3D Position Estimation

Fuses multiple sensor sources at different rates:
  1. Optical flow velocity [vx, vy] at ~21 Hz (high-rate, relative)
  2. Depth-based altitude [z] at ~7 Hz (absolute Z)
  3. WiFi RSSI distance [d] at ~3 Hz (non-linear, absolute range constraint)

State vector: [x, y, z, vx, vy, vz]

The RSSI measurement is non-linear (d = sqrt(x^2 + y^2 + z^2)), which is
why we need an EKF rather than a plain linear Kalman filter.
"""

import numpy as np
import logging
import time
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


class EKFPositionEstimator:
    """
    6-state Extended Kalman Filter for 3D drone position estimation.

    Backward-compatible with the old 2D PositionEstimator interface
    (get_position returns 2D, get_velocity returns 2D) so the autopilot
    service continues working without changes.
    """

    def __init__(
        self,
        process_noise_xy: float = 0.03,
        process_noise_z: float = 0.05,
        measurement_noise_velocity: float = 0.1,
        measurement_noise_altitude: float = 0.3,
        measurement_noise_rssi: float = 2.0,
        initial_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ):
        """
        Args:
            process_noise_xy: Process noise for X/Y axes
            process_noise_z: Process noise for Z axis
            measurement_noise_velocity: Noise for optical flow velocity
            measurement_noise_altitude: Noise for depth-based altitude
            measurement_noise_rssi: Noise for RSSI distance (high — RSSI is noisy)
            initial_position: Starting (x, y, z) in meters
        """
        # State: [x, y, z, vx, vy, vz]
        self.x = np.array([
            initial_position[0], initial_position[1], initial_position[2],
            0.0, 0.0, 0.0
        ], dtype=np.float64)

        # Covariance (6x6)
        self.P = np.eye(6, dtype=np.float64)
        self.P[2, 2] = 0.5  # Lower initial Z uncertainty

        # Process noise parameters
        self.Q_xy = float(process_noise_xy)
        self.Q_z = float(process_noise_z)

        # Measurement noise for each source
        self.R_velocity = float(measurement_noise_velocity)
        self.R_altitude = float(measurement_noise_altitude)
        self.R_rssi = float(measurement_noise_rssi)

        # RSSI anchor position (laptop) — set via ground_zero calibration
        self.laptop_position = np.array([0.0, 0.0, 0.0], dtype=np.float64)

        # Timing
        self.last_update_time = None  # type: Optional[float]

        # Statistics
        self.num_predictions = 0
        self.num_velocity_updates = 0
        self.num_altitude_updates = 0
        self.num_rssi_updates = 0

        logger.info(
            "EKFPositionEstimator initialized at (%.2f, %.2f, %.2f)",
            initial_position[0], initial_position[1], initial_position[2]
        )

    def set_anchor_position(self, x: float, y: float, z: float) -> None:
        """Set the RSSI anchor (laptop) position in world coordinates.

        Called during ground-zero calibration to place the laptop at the
        estimated RSSI distance from the drone origin.
        """
        self.laptop_position = np.array([x, y, z], dtype=np.float64)
        logger.info(
            "RSSI anchor set to (%.2f, %.2f, %.2f)",
            x, y, z
        )

    def predict(self, dt: Optional[float] = None) -> np.ndarray:
        """
        Predict state forward using constant-velocity model.

        Args:
            dt: Time delta in seconds. If None, uses time since last update.

        Returns:
            Predicted state [x, y, z, vx, vy, vz]
        """
        if dt is None:
            now = time.time()
            if self.last_update_time is None:
                dt = 0.1
            else:
                dt = now - self.last_update_time
            self.last_update_time = now
        else:
            self.last_update_time = time.time()

        # Clamp dt to reasonable range
        dt = max(0.001, min(dt, 1.0))

        # State transition: constant velocity
        F = np.eye(6, dtype=np.float64)
        F[0, 3] = dt  # x += vx * dt
        F[1, 4] = dt  # y += vy * dt
        F[2, 5] = dt  # z += vz * dt

        self.x = F @ self.x

        # Process noise
        Q = np.zeros((6, 6), dtype=np.float64)
        Q[0, 0] = self.Q_xy * dt * dt
        Q[1, 1] = self.Q_xy * dt * dt
        Q[2, 2] = self.Q_z * dt * dt
        Q[3, 3] = self.Q_xy * dt
        Q[4, 4] = self.Q_xy * dt
        Q[5, 5] = self.Q_z * dt

        self.P = F @ self.P @ F.T + Q
        self.num_predictions += 1

        return self.x.copy()

    def update_velocity(self, vx: float, vy: float) -> np.ndarray:
        """
        Update with optical flow velocity measurement [vx, vy].

        Linear observation: H maps state to [vx, vy].

        Args:
            vx: Measured X velocity in m/s
            vy: Measured Y velocity in m/s

        Returns:
            Updated state [x, y, z, vx, vy, vz]
        """
        H = np.zeros((2, 6), dtype=np.float64)
        H[0, 3] = 1.0  # observe vx
        H[1, 4] = 1.0  # observe vy

        z = np.array([vx, vy], dtype=np.float64)
        R = np.eye(2, dtype=np.float64) * self.R_velocity

        self._kf_update(H, z, R)
        self.num_velocity_updates += 1
        self.last_update_time = time.time()
        return self.x.copy()

    def update_altitude(self, z_measured: float) -> np.ndarray:
        """
        Update with depth-based altitude measurement.

        Linear observation: H maps state to [z].

        Args:
            z_measured: Measured altitude in meters

        Returns:
            Updated state [x, y, z, vx, vy, vz]
        """
        H = np.zeros((1, 6), dtype=np.float64)
        H[0, 2] = 1.0  # observe z

        z_obs = np.array([z_measured], dtype=np.float64)
        R = np.array([[self.R_altitude]], dtype=np.float64)

        self._kf_update(H, z_obs, R)
        self.num_altitude_updates += 1

        logger.debug("Altitude update: measured=%.2f, state_z=%.2f", z_measured, self.x[2])
        return self.x.copy()

    def update_rssi_distance(self, distance_measured: float) -> np.ndarray:
        """
        Update with RSSI distance measurement.

        Non-linear: d = sqrt((x-lx)^2 + (y-ly)^2 + (z-lz)^2)
        Uses EKF linearization via Jacobian.

        Args:
            distance_measured: Estimated distance to laptop in meters

        Returns:
            Updated state [x, y, z, vx, vy, vz]
        """
        dx = self.x[0] - self.laptop_position[0]
        dy = self.x[1] - self.laptop_position[1]
        dz = self.x[2] - self.laptop_position[2]
        d_predicted = np.sqrt(dx * dx + dy * dy + dz * dz)

        if d_predicted < 0.01:
            # Too close to anchor — Jacobian undefined, skip
            return self.x.copy()

        # Jacobian of h(x) = sqrt((x-lx)^2 + (y-ly)^2 + (z-lz)^2)
        H = np.zeros((1, 6), dtype=np.float64)
        H[0, 0] = dx / d_predicted
        H[0, 1] = dy / d_predicted
        H[0, 2] = dz / d_predicted

        # Innovation (measurement - predicted)
        y = np.array([distance_measured - d_predicted], dtype=np.float64)
        R = np.array([[self.R_rssi]], dtype=np.float64)

        # EKF update with linearized H
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + (K @ y).flatten()
        self.P = (np.eye(6, dtype=np.float64) - K @ H) @ self.P

        self.num_rssi_updates += 1
        logger.debug(
            "RSSI update: measured=%.2f, predicted=%.2f, innovation=%.2f",
            distance_measured, d_predicted, y[0]
        )
        return self.x.copy()

    def predict_and_update_velocity(
        self,
        velocity: np.ndarray,
        dt: Optional[float] = None
    ) -> np.ndarray:
        """
        Predict + velocity update in one step (replaces old predict_and_update).

        Args:
            velocity: [vx, vy] in m/s
            dt: Time delta in seconds

        Returns:
            Updated state [x, y, z, vx, vy, vz]
        """
        self.predict(dt)
        return self.update_velocity(float(velocity[0]), float(velocity[1]))

    def _kf_update(self, H: np.ndarray, z: np.ndarray, R: np.ndarray) -> None:
        """Standard Kalman update (linear observation)."""
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + (K @ y).flatten()
        self.P = (np.eye(6, dtype=np.float64) - K @ H) @ self.P

    # ── Backward-compatible interface (2D for autopilot) ──

    def get_position(self) -> Tuple[float, float]:
        """Get current 2D position (x, y). Backward-compatible."""
        return (float(self.x[0]), float(self.x[1]))

    def get_position_3d(self) -> Tuple[float, float, float]:
        """Get current 3D position (x, y, z)."""
        return (float(self.x[0]), float(self.x[1]), float(self.x[2]))

    def get_velocity(self) -> Tuple[float, float]:
        """Get current 2D velocity (vx, vy). Backward-compatible."""
        return (float(self.x[3]), float(self.x[4]))

    def get_velocity_3d(self) -> Tuple[float, float, float]:
        """Get current 3D velocity (vx, vy, vz)."""
        return (float(self.x[3]), float(self.x[4]), float(self.x[5]))

    def get_altitude(self) -> float:
        """Get current altitude estimate from EKF state."""
        return float(self.x[2])

    def get_state(self) -> np.ndarray:
        """Get full state vector [x, y, z, vx, vy, vz]."""
        return self.x.copy()

    def get_covariance(self) -> np.ndarray:
        """Get 6x6 covariance matrix."""
        return self.P.copy()

    def get_position_uncertainty(self) -> Tuple[float, float]:
        """Get 2D position uncertainty (sigma_x, sigma_y). Backward-compatible."""
        return (float(np.sqrt(self.P[0, 0])), float(np.sqrt(self.P[1, 1])))

    def get_altitude_uncertainty(self) -> float:
        """Get altitude uncertainty (sigma_z)."""
        return float(np.sqrt(self.P[2, 2]))

    def reset(self, initial_position=None):
        """
        Reset filter state.

        Args:
            initial_position: (x, y) or (x, y, z). Accepts both for compat.
        """
        if initial_position is None:
            initial_position = (0.0, 0.0, 0.0)
        elif len(initial_position) == 2:
            initial_position = (initial_position[0], initial_position[1], self.x[2])

        self.x = np.array([
            initial_position[0], initial_position[1], initial_position[2],
            0.0, 0.0, 0.0
        ], dtype=np.float64)
        self.P = np.eye(6, dtype=np.float64)
        self.P[2, 2] = 0.5

        self.last_update_time = None
        self.num_predictions = 0
        self.num_velocity_updates = 0
        self.num_altitude_updates = 0
        self.num_rssi_updates = 0

        logger.info(
            "EKF reset to (%.2f, %.2f, %.2f)",
            initial_position[0], initial_position[1], initial_position[2]
        )

    def set_process_noise(self, process_noise: float) -> None:
        """Update XY process noise. Backward-compatible."""
        self.Q_xy = float(process_noise)

    def set_measurement_noise(self, measurement_noise: float) -> None:
        """Update velocity measurement noise. Backward-compatible."""
        self.R_velocity = float(measurement_noise)

    def get_statistics(self) -> Dict[str, Any]:
        """Get filter statistics."""
        pos = self.get_position_3d()
        vel = self.get_velocity_3d()
        unc = self.get_position_uncertainty()

        return {
            'position': {'x': pos[0], 'y': pos[1], 'z': pos[2]},
            'velocity': {'vx': vel[0], 'vy': vel[1], 'vz': vel[2]},
            'uncertainty': {
                'sigma_x': unc[0],
                'sigma_y': unc[1],
                'sigma_z': self.get_altitude_uncertainty()
            },
            'num_predictions': self.num_predictions,
            'num_velocity_updates': self.num_velocity_updates,
            'num_altitude_updates': self.num_altitude_updates,
            'num_rssi_updates': self.num_rssi_updates,
            'anchor_position': {
                'x': float(self.laptop_position[0]),
                'y': float(self.laptop_position[1]),
                'z': float(self.laptop_position[2])
            }
        }
