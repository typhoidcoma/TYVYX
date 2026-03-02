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
from autonomous.localization.ekf_position_estimator import EKFPositionEstimator

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
        estimator: EKFPositionEstimator instance (6-state 3D EKF)

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
        self.estimator: Optional[EKFPositionEstimator] = None

        # State
        self.enabled = False
        self.using_bottom_camera = False  # True when bottom cam active for optical flow
        self.position: Tuple[float, float] = (0.0, 0.0)
        self.velocity: Tuple[float, float] = (0.0, 0.0)
        self.trajectory: List[Dict[str, Any]] = []

        # Configuration
        self.altitude = 1.0  # Default altitude in meters
        self.fps = 21.0  # Actual K417 video frame rate
        self.max_trajectory_points = 1000

        # Statistics
        self.frame_count = 0
        self.last_update_time: Optional[float] = None
        self.last_velocity_measurement: Optional[np.ndarray] = None

        # Callbacks fired after each successful position update
        self._on_update_callbacks = []  # type: List[Any]
        self._callbacks_lock = threading.Lock()

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

            self.estimator = EKFPositionEstimator(
                process_noise_xy=process_noise,
                measurement_noise_velocity=measurement_noise,
                initial_position=(0.0, 0.0, self.altitude)
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
        """Start position tracking.

        Auto-switches to bottom camera (cam 2) for downward-facing optical flow.
        The CoordinateTransformer assumes a downward camera — the front camera
        produces meaningless velocity data.
        """
        with self.state_lock:
            if not self.optical_flow or not self.transformer or not self.estimator:
                raise RuntimeError("PositionService not initialized - call initialize() first")

            self.enabled = True
            self.frame_count = 0
            self.last_update_time = time.time()

        # Switch to bottom camera for proper optical flow
        self._switch_camera_mode('bottom')

        logger.info("Position tracking started (bottom camera)")

    def stop(self) -> None:
        """Stop position tracking and restore front camera."""
        with self.state_lock:
            self.enabled = False

        # Restore front camera
        self._switch_camera_mode('front')

        logger.info("Position tracking stopped (front camera restored)")

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

    def ground_zero(self) -> Dict[str, Any]:
        """
        Calibrate ground zero — call when drone is on the ground before takeoff.

        Sets position origin at current drone location (ground level),
        places the RSSI laptop anchor at the current estimated RSSI distance,
        and resets all tracking state.

        Returns:
            Dict with calibration results (rssi_distance, anchor_position, position)
        """
        from autonomous.services.wifi_rssi_service import wifi_rssi_service

        with self.state_lock:
            # Get current RSSI distance for anchor placement
            rssi_distance = 0.0
            if wifi_rssi_service.is_enabled():
                rssi_distance = wifi_rssi_service.get_distance()

            # Reset EKF to ground level (0, 0, 0)
            if self.estimator:
                self.estimator.reset((0.0, 0.0, 0.0))
                # Place laptop anchor at RSSI distance along X axis
                if rssi_distance > 0.1:
                    self.estimator.set_anchor_position(rssi_distance, 0.0, 0.0)

            # Reset tracking state
            self.position = (0.0, 0.0)
            self.velocity = (0.0, 0.0)
            self.altitude = 0.0
            self.trajectory.clear()
            if self.optical_flow:
                self.optical_flow.reset()
            if self.transformer:
                self.transformer.set_altitude(0.0)

            self.frame_count = 0
            self.last_update_time = time.time()
            self.last_velocity_measurement = None

        anchor = [rssi_distance, 0.0, 0.0] if rssi_distance > 0.1 else [0.0, 0.0, 0.0]
        logger.info(
            "Ground zero calibrated: rssi_distance=%.2fm, anchor=%s",
            rssi_distance, anchor
        )

        return {
            'rssi_distance': rssi_distance,
            'anchor_position': anchor,
            'position': [0.0, 0.0, 0.0],
        }

    def set_camera_mode(self, mode: str) -> Dict[str, Any]:
        """Set camera mode for position tracking.

        Args:
            mode: 'bottom' for downward-facing optical flow (correct for tracking),
                  'front' for forward-facing camera (disables meaningful tracking).

        Returns:
            Dict with camera_mode and status info.
        """
        if mode not in ('bottom', 'front'):
            raise ValueError("mode must be 'bottom' or 'front'")

        self._switch_camera_mode(mode)

        return {
            'camera_mode': mode,
            'using_bottom_camera': self.using_bottom_camera,
        }

    def _switch_camera_mode(self, mode: str) -> None:
        """Internal: switch camera and update state.

        Args:
            mode: 'bottom' or 'front'
        """
        from autonomous.services.drone_service import drone_service

        cam_num = 2 if mode == 'bottom' else 1
        self.using_bottom_camera = (mode == 'bottom')

        # Reset optical flow — scene change invalidates tracked features
        if self.optical_flow:
            self.optical_flow.reset()

        # Switch camera on the drone (fire-and-forget, non-blocking)
        if drone_service.is_connected() and drone_service.drone:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.create_task(drone_service.switch_camera(cam_num))
            except RuntimeError:
                # No running event loop — use sync fallback
                if hasattr(drone_service.drone, 'switch_camera'):
                    drone_service.drone.switch_camera(cam_num)

        logger.info("Camera mode set to %s (cam %d)", mode, cam_num)

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

    def update_altitude_from_depth(self, altitude: float) -> None:
        """
        Update altitude from depth estimation service.

        Feeds the EKF with a direct Z measurement and also updates
        the coordinate transformer's altitude for proper velocity scaling.

        Args:
            altitude: Estimated altitude in meters (from depth service)
        """
        with self.state_lock:
            if self.estimator:
                self.estimator.update_altitude(altitude)
                self.altitude = self.estimator.get_altitude()
                if self.transformer:
                    self.transformer.set_altitude(self.altitude)

    def update_rssi_distance(self, distance: float) -> None:
        """
        Update with WiFi RSSI distance measurement.

        Feeds the EKF with a non-linear distance constraint from the laptop.

        Args:
            distance: Estimated distance to laptop in meters
        """
        with self.state_lock:
            if self.estimator:
                self.estimator.update_rssi_distance(distance)
                # Update position from EKF after RSSI correction
                self.position = self.estimator.get_position()

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
            self.frame_count += 1

            # Calculate optical flow
            success, pixel_velocity, features = self.optical_flow.update(frame)

            if not success or pixel_velocity is None:
                # No valid flow - just predict without update
                dt = time.time() - self.last_update_time if self.last_update_time else 0.1
                with self.state_lock:
                    self.estimator.predict(dt)
                    self.position = self.estimator.get_position()
                    self.velocity = self.estimator.get_velocity()
                    self.altitude = self.estimator.get_altitude()
                    self.last_update_time = time.time()
                return False

            # Convert pixel velocity to world velocity
            world_velocity = self.transformer.pixel_velocity_to_world(
                pixel_velocity,
                altitude=self.altitude,
                fps=self.fps
            )

            # Update EKF with velocity measurement
            dt = time.time() - self.last_update_time if self.last_update_time else 0.1

            with self.state_lock:
                # Predict and update
                state = self.estimator.predict_and_update_velocity(world_velocity, dt)

                # Update state
                self.position = self.estimator.get_position()
                self.velocity = self.estimator.get_velocity()
                self.altitude = self.estimator.get_altitude()
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

            # Fire update callbacks (autopilot PID, etc.)
            with self._callbacks_lock:
                cbs = list(self._on_update_callbacks)
            for cb in cbs:
                try:
                    cb()
                except Exception as e:
                    logger.debug("Position update callback error: %s", e)

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

            pos_3d = self.estimator.get_position_3d() if self.estimator else (self.position[0], self.position[1], self.altitude)
            vel_3d = self.estimator.get_velocity_3d() if self.estimator else (self.velocity[0], self.velocity[1], 0.0)

            return {
                'position': {
                    'x': pos_3d[0],
                    'y': pos_3d[1],
                    'z': pos_3d[2]
                },
                'velocity': {
                    'vx': vel_3d[0],
                    'vy': vel_3d[1],
                    'vz': vel_3d[2]
                },
                'altitude': self.altitude,
                'enabled': self.enabled,
                'feature_count': feature_count,
                'camera_mode': 'bottom' if self.using_bottom_camera else 'front',
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

    def on_update(self, callback):
        """Register a callback fired after each successful position update.
        Callback is called from the position processing thread — keep it fast."""
        with self._callbacks_lock:
            self._on_update_callbacks.append(callback)

    def remove_on_update(self, callback):
        """Unregister a position update callback."""
        with self._callbacks_lock:
            try:
                self._on_update_callbacks.remove(callback)
            except ValueError:
                pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics

        Returns:
            Dictionary with statistics including position, velocity, uncertainty,
            feature count, frame count, etc.
        """
        with self.state_lock:
            pos_3d = self.estimator.get_position_3d() if self.estimator else (self.position[0], self.position[1], self.altitude)
            vel_3d = self.estimator.get_velocity_3d() if self.estimator else (self.velocity[0], self.velocity[1], 0.0)

            stats = {
                'enabled': self.enabled,
                'position': {
                    'x': pos_3d[0],
                    'y': pos_3d[1],
                    'z': pos_3d[2]
                },
                'velocity': {
                    'vx': vel_3d[0],
                    'vy': vel_3d[1],
                    'vz': vel_3d[2]
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
                    'sigma_y': uncertainty[1],
                    'sigma_z': self.estimator.get_altitude_uncertainty()
                }

                # Add EKF-specific stats
                ekf_stats = self.estimator.get_statistics()
                stats['ekf'] = {
                    'velocity_updates': ekf_stats['num_velocity_updates'],
                    'altitude_updates': ekf_stats['num_altitude_updates'],
                    'rssi_updates': ekf_stats['num_rssi_updates'],
                    'predictions': ekf_stats['num_predictions']
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
