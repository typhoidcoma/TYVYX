"""
Position Estimator using Kalman Filter

Estimates 2D position and velocity from noisy optical flow measurements
using a Kalman filter with constant velocity motion model.
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import logging
import time

logger = logging.getLogger(__name__)


class PositionEstimator:
    """
    Kalman filter for 2D position estimation

    State vector: [x, y, vx, vy]
        - x, y: Position in meters
        - vx, vy: Velocity in meters/second

    Measurement: [vx_measured, vy_measured]
        - Velocity from optical flow

    Uses constant velocity motion model with process noise
    """

    def __init__(
        self,
        process_noise: float = 0.03,
        measurement_noise: float = 0.1,
        initial_position: Tuple[float, float] = (0.0, 0.0)
    ):
        """
        Initialize Kalman filter for position estimation

        Args:
            process_noise: Process noise covariance (state uncertainty)
            measurement_noise: Measurement noise covariance (sensor uncertainty)
            initial_position: Starting position as (x, y) in meters
        """
        # Create Kalman filter
        # State: [x, y, vx, vy] - 4 dimensions
        # Measurement: [vx, vy] - 2 dimensions
        self.kf = cv2.KalmanFilter(4, 2)

        # State transition matrix (constant velocity model)
        # Will be updated with dt in predict()
        self.kf.transitionMatrix = np.array([
            [1, 0, 0, 0],  # x_k = x_{k-1} + vx * dt
            [0, 1, 0, 0],  # y_k = y_{k-1} + vy * dt
            [0, 0, 1, 0],  # vx_k = vx_{k-1}
            [0, 0, 0, 1]   # vy_k = vy_{k-1}
        ], dtype=np.float32)

        # Measurement matrix (we measure velocity directly)
        self.kf.measurementMatrix = np.array([
            [0, 0, 1, 0],  # Measure vx
            [0, 0, 0, 1]   # Measure vy
        ], dtype=np.float32)

        # Process noise covariance
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise

        # Measurement noise covariance
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise

        # Error covariance (initial uncertainty)
        self.kf.errorCovPost = np.eye(4, dtype=np.float32)

        # Initialize state
        self.kf.statePost = np.array([
            [initial_position[0]],
            [initial_position[1]],
            [0.0],
            [0.0]
        ], dtype=np.float32)

        # Timing
        self.last_update_time = None

        # Statistics
        self.num_predictions = 0
        self.num_updates = 0

        logger.info(
            f"PositionEstimator initialized at ({initial_position[0]:.2f}, {initial_position[1]:.2f})"
        )

    def predict(self, dt: Optional[float] = None) -> np.ndarray:
        """
        Predict next state using motion model

        Args:
            dt: Time delta in seconds. If None, uses time since last update.

        Returns:
            Predicted state as [x, y, vx, vy]
        """
        if dt is None:
            if self.last_update_time is None:
                dt = 0.1  # Default 100ms
            else:
                dt = time.time() - self.last_update_time

        # Update transition matrix with current dt
        self.kf.transitionMatrix[0, 2] = dt  # x += vx * dt
        self.kf.transitionMatrix[1, 3] = dt  # y += vy * dt

        # Predict
        prediction = self.kf.predict()
        self.num_predictions += 1

        state = prediction.flatten()
        logger.debug(
            f"Predict (dt={dt:.3f}s): pos=({state[0]:.3f}, {state[1]:.3f}), "
            f"vel=({state[2]:.3f}, {state[3]:.3f})"
        )

        return state

    def update(self, velocity_measurement: np.ndarray) -> np.ndarray:
        """
        Update state with velocity measurement

        Args:
            velocity_measurement: Measured velocity as [vx, vy] in m/s

        Returns:
            Corrected state as [x, y, vx, vy]
        """
        # Convert to measurement format
        measurement = np.array([
            [velocity_measurement[0]],
            [velocity_measurement[1]]
        ], dtype=np.float32)

        # Correct with measurement
        corrected = self.kf.correct(measurement)
        self.num_updates += 1
        self.last_update_time = time.time()

        state = corrected.flatten()
        logger.debug(
            f"Update: measurement=({velocity_measurement[0]:.3f}, {velocity_measurement[1]:.3f}), "
            f"pos=({state[0]:.3f}, {state[1]:.3f}), vel=({state[2]:.3f}, {state[3]:.3f})"
        )

        return state

    def predict_and_update(self, velocity_measurement: np.ndarray, dt: Optional[float] = None) -> np.ndarray:
        """
        Predict next state and update with measurement in one step

        Args:
            velocity_measurement: Measured velocity as [vx, vy] in m/s
            dt: Optional time delta (seconds)

        Returns:
            Updated state as [x, y, vx, vy]
        """
        self.predict(dt)
        return self.update(velocity_measurement)

    def get_state(self) -> np.ndarray:
        """
        Get current state estimate

        Returns:
            State as [x, y, vx, vy]
        """
        return self.kf.statePost.flatten()

    def get_position(self) -> Tuple[float, float]:
        """
        Get current position estimate

        Returns:
            Position as (x, y) in meters
        """
        state = self.get_state()
        return float(state[0]), float(state[1])

    def get_velocity(self) -> Tuple[float, float]:
        """
        Get current velocity estimate

        Returns:
            Velocity as (vx, vy) in m/s
        """
        state = self.get_state()
        return float(state[2]), float(state[3])

    def get_covariance(self) -> np.ndarray:
        """
        Get state covariance matrix (uncertainty)

        Returns:
            4x4 covariance matrix
        """
        return self.kf.errorCovPost.copy()

    def get_position_uncertainty(self) -> Tuple[float, float]:
        """
        Get position uncertainty (standard deviation)

        Returns:
            Uncertainty as (sigma_x, sigma_y) in meters
        """
        cov = self.get_covariance()
        sigma_x = np.sqrt(cov[0, 0])
        sigma_y = np.sqrt(cov[1, 1])
        return float(sigma_x), float(sigma_y)

    def reset(self, initial_position: Tuple[float, float] = (0.0, 0.0)):
        """
        Reset filter to initial state

        Args:
            initial_position: Starting position as (x, y) in meters
        """
        self.kf.statePost = np.array([
            [initial_position[0]],
            [initial_position[1]],
            [0.0],
            [0.0]
        ], dtype=np.float32)

        self.kf.errorCovPost = np.eye(4, dtype=np.float32)
        self.last_update_time = None
        self.num_predictions = 0
        self.num_updates = 0

        logger.info(f"PositionEstimator reset to ({initial_position[0]:.2f}, {initial_position[1]:.2f})")

    def set_process_noise(self, process_noise: float):
        """
        Update process noise covariance

        Higher values = trust model less, adapt faster to changes
        Lower values = trust model more, smoother but slower adaptation

        Args:
            process_noise: Process noise covariance
        """
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise
        logger.debug(f"Process noise set to {process_noise}")

    def set_measurement_noise(self, measurement_noise: float):
        """
        Update measurement noise covariance

        Higher values = trust measurements less, smoother but slower
        Lower values = trust measurements more, noisier but more responsive

        Args:
            measurement_noise: Measurement noise covariance
        """
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise
        logger.debug(f"Measurement noise set to {measurement_noise}")

    def get_statistics(self) -> dict:
        """
        Get filter statistics

        Returns:
            Dictionary with statistics
        """
        pos = self.get_position()
        vel = self.get_velocity()
        uncertainty = self.get_position_uncertainty()

        return {
            'position': {'x': pos[0], 'y': pos[1]},
            'velocity': {'vx': vel[0], 'vy': vel[1]},
            'uncertainty': {'sigma_x': uncertainty[0], 'sigma_y': uncertainty[1]},
            'num_predictions': self.num_predictions,
            'num_updates': self.num_updates
        }


class SimpleDeadReckoning:
    """
    Simple dead reckoning without Kalman filter

    Integrates velocity measurements directly to estimate position.
    Useful for comparison or when Kalman filter is not needed.
    """

    def __init__(self, initial_position: Tuple[float, float] = (0.0, 0.0)):
        """
        Initialize dead reckoning

        Args:
            initial_position: Starting position as (x, y) in meters
        """
        self.position = np.array(initial_position, dtype=np.float32)
        self.velocity = np.array([0.0, 0.0], dtype=np.float32)
        self.last_update_time = None

        logger.info(f"SimpleDeadReckoning initialized at ({initial_position[0]:.2f}, {initial_position[1]:.2f})")

    def update(self, velocity_measurement: np.ndarray, dt: Optional[float] = None) -> np.ndarray:
        """
        Update position with velocity measurement

        Args:
            velocity_measurement: Measured velocity as [vx, vy] in m/s
            dt: Optional time delta (seconds)

        Returns:
            Updated state as [x, y, vx, vy]
        """
        if dt is None:
            if self.last_update_time is None:
                dt = 0.1  # Default 100ms
            else:
                dt = time.time() - self.last_update_time

        # Update velocity (simple averaging for smoothing)
        alpha = 0.7  # Smoothing factor
        self.velocity = alpha * velocity_measurement + (1 - alpha) * self.velocity

        # Integrate position
        self.position += self.velocity * dt

        self.last_update_time = time.time()

        return np.array([self.position[0], self.position[1], self.velocity[0], self.velocity[1]])

    def get_position(self) -> Tuple[float, float]:
        """Get current position"""
        return float(self.position[0]), float(self.position[1])

    def get_velocity(self) -> Tuple[float, float]:
        """Get current velocity"""
        return float(self.velocity[0]), float(self.velocity[1])

    def reset(self, initial_position: Tuple[float, float] = (0.0, 0.0)):
        """Reset to initial position"""
        self.position = np.array(initial_position, dtype=np.float32)
        self.velocity = np.array([0.0, 0.0], dtype=np.float32)
        self.last_update_time = None
        logger.info(f"SimpleDeadReckoning reset to ({initial_position[0]:.2f}, {initial_position[1]:.2f})")
