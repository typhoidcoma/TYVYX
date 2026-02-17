"""
Position Service for Drone Position Estimation

Singleton service that integrates optical flow tracking, coordinate transforms,
and Kalman filtering to estimate drone position from video frames.

Typical usage:
    position_service.initialize(config)
    position_service.start()
    position_service.process_frame(frame)
    position = position_service.get_position()
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Tuple, List, Dict, Any
import numpy as np

from autonomous.perception.optical_flow_tracker import OpticalFlowTracker
from autonomous.localization.coordinate_transforms import (
    CoordinateTransformer,
    create_camera_matrix
)
from autonomous.localization.position_estimator import PositionEstimator

logger = logging.getLogger(__name__)


class PositionService:
    """
    Singleton service for position estimation from optical flow

    Processes video frames at a controlled rate (default 10 Hz) to estimate
    drone position using:
    1. Optical flow tracking (pixel velocity)
    2. Coordinate transformation (world velocity)
    3. Kalman filtering (position estimation)

    Attributes:
        optical_flow: OpticalFlowTracker instance
        transformer: CoordinateTransformer instance
        estimator: PositionEstimator instance

        enabled: Whether position tracking is active
        position: Current position as (x, y) in meters
        velocity: Current velocity as (vx, vy) in m/s
        trajectory: List of position history points

        frame_count: Total frames processed
        last_update_time: Timestamp of last position update
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern - only one instance allowed"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize position service (called once)"""
        if self._initialized:
            return

        # Components
        self.optical_flow: Optional[OpticalFlowTracker] = None
        self.transformer: Optional[CoordinateTransformer] = None
        self.estimator: Optional[PositionEstimator] = None

        # State
        self.enabled = False
        self.position: Tuple[float, float] = (0.0, 0.0)
        self.velocity: Tuple[float, float] = (0.0, 0.0)
        self.trajectory: List[Dict[str, Any]] = []

        # Configuration
        self.altitude = 1.0  # Default altitude in meters
        self.fps = 30.0  # Video frame rate
        self.max_trajectory_points = 1000
        self.update_rate = 10  # Hz (process every 3rd frame at 30 fps)

        # Statistics
        self.frame_count = 0
        self.last_update_time: Optional[float] = None
        self.last_velocity_measurement: Optional[np.ndarray] = None

        # Thread safety
        self.state_lock = threading.Lock()

        self._initialized = True
        logger.info("PositionService singleton created")

    def initialize(self, config: Dict[str, Any]) -> None:
        """
        Initialize position service with configuration

        Args:
            config: Configuration dictionary with keys:
                - camera: Camera calibration (fx, fy, cx, cy)
                - slam.optical_flow: Optical flow parameters
                - position_estimation: Position estimation parameters
        """
        try:
            # Extract camera calibration
            camera_config = config.get('camera', {})
            fx = camera_config.get('fx', 500.0)
            fy = camera_config.get('fy', 500.0)
            cx = camera_config.get('cx', 320.0)
            cy = camera_config.get('cy', 240.0)

            camera_matrix = create_camera_matrix(fx, fy, cx, cy)

            # Extract optical flow parameters
            flow_config = config.get('slam', {}).get('optical_flow', {})
            max_corners = flow_config.get('max_corners', 100)
            quality_level = flow_config.get('quality_level', 0.01)
            min_distance = flow_config.get('min_distance', 10)
            block_size = flow_config.get('block_size', 7)
            min_features = flow_config.get('min_features', 20)
            max_level = flow_config.get('max_level', 3)
            max_pixel_velocity = flow_config.get('max_pixel_velocity', 50.0)

            # Extract position estimation parameters
            pos_config = config.get('position_estimation', {})
            self.altitude = pos_config.get('default_altitude', 1.0)
            process_noise = pos_config.get('process_noise', 0.03)
            measurement_noise = pos_config.get('measurement_noise', 0.1)
            self.max_trajectory_points = pos_config.get('max_trajectory_points', 1000)
            self.update_rate = pos_config.get('update_rate', 10)

            # Create components
            self.optical_flow = OpticalFlowTracker(
                max_corners=max_corners,
                quality_level=quality_level,
                min_distance=min_distance,
                block_size=block_size,
                min_features=min_features,
                max_level=max_level,
                max_pixel_velocity=max_pixel_velocity
            )

            self.transformer = CoordinateTransformer(camera_matrix)
            self.transformer.set_altitude(self.altitude)

            self.estimator = PositionEstimator(
                process_noise=process_noise,
                measurement_noise=measurement_noise,
                initial_position=(0.0, 0.0)
            )

            logger.info(
                f"PositionService initialized: "
                f"camera=({fx:.1f}, {fy:.1f}, {cx:.1f}, {cy:.1f}), "
                f"altitude={self.altitude:.2f}m, update_rate={self.update_rate}Hz"
            )

        except Exception as e:
            logger.error(f"Failed to initialize PositionService: {e}", exc_info=True)
            raise

    def start(self) -> None:
        """Start position tracking"""
        with self.state_lock:
            if not self.optical_flow or not self.transformer or not self.estimator:
                raise RuntimeError("PositionService not initialized - call initialize() first")

            self.enabled = True
            self.frame_count = 0
            self.last_update_time = time.time()

            logger.info("Position tracking started")

    def stop(self) -> None:
        """Stop position tracking"""
        with self.state_lock:
            self.enabled = False
            logger.info("Position tracking stopped")

    def reset(self, initial_position: Tuple[float, float] = (0.0, 0.0)) -> None:
        """
        Reset position to initial state

        Args:
            initial_position: Starting position as (x, y) in meters
        """
        with self.state_lock:
            if self.optical_flow:
                self.optical_flow.reset()
            if self.estimator:
                self.estimator.reset(initial_position)

            self.position = initial_position
            self.velocity = (0.0, 0.0)
            self.trajectory.clear()
            self.frame_count = 0
            self.last_update_time = time.time()
            self.last_velocity_measurement = None

            logger.info(f"Position reset to {initial_position}")

    def set_altitude(self, altitude: float) -> None:
        """
        Update altitude for velocity scaling

        Args:
            altitude: Height above ground in meters
        """
        with self.state_lock:
            self.altitude = max(0.1, altitude)
            if self.transformer:
                self.transformer.set_altitude(self.altitude)

            logger.info(f"Altitude updated to {self.altitude:.2f}m")

    def process_frame(self, frame: np.ndarray) -> bool:
        """
        Process video frame for position estimation

        Args:
            frame: Video frame (BGR or grayscale)

        Returns:
            True if position was updated, False otherwise
        """
        if not self.enabled:
            return False

        if not self.optical_flow or not self.transformer or not self.estimator:
            logger.warning("Cannot process frame - service not initialized")
            return False

        try:
            # Rate limiting - process at update_rate Hz
            self.frame_count += 1
            frame_skip = int(self.fps / self.update_rate)
            if self.frame_count % frame_skip != 0:
                return False

            # Calculate optical flow
            success, pixel_velocity, features = self.optical_flow.update(frame)

            if not success or pixel_velocity is None:
                # No valid flow - just predict without update
                dt = time.time() - self.last_update_time if self.last_update_time else 0.1
                with self.state_lock:
                    self.estimator.predict(dt)
                    self.position = self.estimator.get_position()
                    self.velocity = self.estimator.get_velocity()
                    self.last_update_time = time.time()
                return False

            # Convert pixel velocity to world velocity
            world_velocity = self.transformer.pixel_velocity_to_world(
                pixel_velocity,
                altitude=self.altitude,
                fps=self.fps
            )

            # Update Kalman filter
            dt = time.time() - self.last_update_time if self.last_update_time else 0.1

            with self.state_lock:
                # Predict and update
                state = self.estimator.predict_and_update(world_velocity, dt)

                # Update state
                self.position = self.estimator.get_position()
                self.velocity = self.estimator.get_velocity()
                self.last_update_time = time.time()
                self.last_velocity_measurement = world_velocity

                # Add to trajectory
                self._add_trajectory_point(
                    self.position[0],
                    self.position[1],
                    self.last_update_time
                )

            logger.debug(
                f"Position updated: pos=({self.position[0]:.3f}, {self.position[1]:.3f}), "
                f"vel=({self.velocity[0]:.3f}, {self.velocity[1]:.3f}), "
                f"features={self.optical_flow.get_feature_count()}"
            )

            return True

        except Exception as e:
            logger.error(f"Error processing frame for position: {e}", exc_info=True)
            return False

    def _add_trajectory_point(self, x: float, y: float, timestamp: float) -> None:
        """
        Add point to trajectory history (internal use, assumes lock held)

        Args:
            x: X position in meters
            y: Y position in meters
            timestamp: Unix timestamp
        """
        self.trajectory.append({
            'x': x,
            'y': y,
            'timestamp': timestamp
        })

        # Limit trajectory length
        if len(self.trajectory) > self.max_trajectory_points:
            self.trajectory.pop(0)

    def get_position(self) -> Dict[str, Any]:
        """
        Get current position state

        Returns:
            Dictionary with position data:
                - position: {x, y} in meters
                - velocity: {vx, vy} in m/s
                - altitude: Current altitude in meters
                - enabled: Whether tracking is active
                - feature_count: Number of tracked features
                - timestamp: Unix timestamp of last update
        """
        with self.state_lock:
            feature_count = self.optical_flow.get_feature_count() if self.optical_flow else 0

            return {
                'position': {
                    'x': self.position[0],
                    'y': self.position[1]
                },
                'velocity': {
                    'vx': self.velocity[0],
                    'vy': self.velocity[1]
                },
                'altitude': self.altitude,
                'enabled': self.enabled,
                'feature_count': feature_count,
                'timestamp': self.last_update_time or time.time()
            }

    def get_trajectory(self, max_points: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get trajectory history

        Args:
            max_points: Maximum number of points to return (most recent)

        Returns:
            List of trajectory points with {x, y, timestamp}
        """
        with self.state_lock:
            if max_points is None or max_points >= len(self.trajectory):
                return self.trajectory.copy()
            else:
                return self.trajectory[-max_points:]

    def clear_trajectory(self) -> None:
        """Clear trajectory history"""
        with self.state_lock:
            self.trajectory.clear()
            logger.info("Trajectory cleared")

    def is_enabled(self) -> bool:
        """Check if position tracking is enabled"""
        return self.enabled

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics

        Returns:
            Dictionary with statistics including position, velocity, uncertainty,
            feature count, frame count, etc.
        """
        with self.state_lock:
            stats = {
                'enabled': self.enabled,
                'position': {
                    'x': self.position[0],
                    'y': self.position[1]
                },
                'velocity': {
                    'vx': self.velocity[0],
                    'vy': self.velocity[1]
                },
                'altitude': self.altitude,
                'frame_count': self.frame_count,
                'trajectory_points': len(self.trajectory),
                'timestamp': self.last_update_time or time.time()
            }

            # Add optical flow stats
            if self.optical_flow:
                stats['feature_count'] = self.optical_flow.get_feature_count()

            # Add estimator uncertainty
            if self.estimator:
                uncertainty = self.estimator.get_position_uncertainty()
                stats['uncertainty'] = {
                    'sigma_x': uncertainty[0],
                    'sigma_y': uncertainty[1]
                }

            # Add last measurement
            if self.last_velocity_measurement is not None:
                stats['last_measurement'] = {
                    'vx': float(self.last_velocity_measurement[0]),
                    'vy': float(self.last_velocity_measurement[1])
                }

            return stats


# Global singleton instance
position_service = PositionService()
