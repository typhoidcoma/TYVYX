"""
Coordinate Transform Utilities

Transforms between pixel coordinates (image space) and world coordinates
(meters) for position estimation from optical flow.

Uses pinhole camera model for projections.
"""

import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class CoordinateTransformer:
    """
    Transform between pixel and world coordinates

    Uses pinhole camera model to convert pixel velocities from optical flow
    into world velocities (m/s) based on camera calibration and altitude.

    Attributes:
        camera_matrix: 3x3 camera intrinsic matrix
        altitude: Current altitude above ground (meters, positive up)
        fx, fy: Focal lengths in pixels
        cx, cy: Principal point (image center)
    """

    def __init__(self, camera_matrix: np.ndarray):
        """
        Initialize coordinate transformer

        Args:
            camera_matrix: 3x3 intrinsic camera matrix
                          [[fx,  0, cx],
                           [ 0, fy, cy],
                           [ 0,  0,  1]]
        """
        self.camera_matrix = camera_matrix.astype(np.float32)

        # Extract camera parameters
        self.fx = camera_matrix[0, 0]
        self.fy = camera_matrix[1, 1]
        self.cx = camera_matrix[0, 2]
        self.cy = camera_matrix[1, 2]

        # State
        self.altitude = 1.0  # Default altitude (meters)

        logger.info(
            f"CoordinateTransformer initialized: fx={self.fx:.1f}, "
            f"fy={self.fy:.1f}, cx={self.cx:.1f}, cy={self.cy:.1f}"
        )

    def set_altitude(self, altitude: float):
        """
        Set current altitude for velocity scaling

        Args:
            altitude: Height above ground (meters, positive up)
        """
        self.altitude = max(0.1, altitude)  # Minimum 0.1m to avoid division by zero
        logger.debug(f"Altitude set to {self.altitude:.2f}m")

    def pixel_to_world_point(
        self,
        pixel_point: np.ndarray,
        altitude: Optional[float] = None
    ) -> np.ndarray:
        """
        Convert pixel coordinate to world coordinate at current altitude

        Args:
            pixel_point: Pixel coordinates as [x, y]
            altitude: Optional altitude (uses stored altitude if None)

        Returns:
            World coordinates as [x, y] in meters
        """
        if altitude is None:
            altitude = self.altitude

        # Convert pixel to normalized image coordinates
        u, v = pixel_point
        x_norm = (u - self.cx) / self.fx
        y_norm = (v - self.cy) / self.fy

        # Scale by altitude (pinhole model)
        # Assuming drone is looking down at flat ground
        x_world = x_norm * altitude
        y_world = y_norm * altitude

        return np.array([x_world, y_world])

    def pixel_velocity_to_world(
        self,
        pixel_velocity: np.ndarray,
        altitude: Optional[float] = None,
        fps: float = 30.0
    ) -> np.ndarray:
        """
        Convert pixel velocity to world velocity

        Uses pinhole camera model:
            velocity_world = (pixel_velocity / fps) * (altitude / focal_length)

        Args:
            pixel_velocity: Velocity in pixels/frame as [vx_px, vy_px]
            altitude: Height above ground (meters). Uses stored if None.
            fps: Frame rate (frames per second)

        Returns:
            Velocity in meters/second as [vx_world, vy_world]

        Note:
            Assumes flat ground plane and camera pointing downward.
            Sign convention: positive X is forward, positive Y is right
        """
        if altitude is None:
            altitude = self.altitude

        # Convert pixels/frame to pixels/second
        vx_px_per_sec = pixel_velocity[0] / fps if fps > 0 else 0.0
        vy_px_per_sec = pixel_velocity[1] / fps if fps > 0 else 0.0

        # Scale by altitude / focal length (pinhole model)
        vx_world = vx_px_per_sec * (altitude / self.fx)
        vy_world = vy_px_per_sec * (altitude / self.fy)

        logger.debug(
            f"Pixel velocity {pixel_velocity} → World velocity [{vx_world:.3f}, {vy_world:.3f}] m/s "
            f"(alt={altitude:.2f}m, fps={fps})"
        )

        return np.array([vx_world, vy_world])

    def world_to_pixel_point(
        self,
        world_point: np.ndarray,
        altitude: Optional[float] = None
    ) -> np.ndarray:
        """
        Convert world coordinate to pixel coordinate

        Args:
            world_point: World coordinates as [x, y] in meters
            altitude: Optional altitude (uses stored altitude if None)

        Returns:
            Pixel coordinates as [u, v]
        """
        if altitude is None:
            altitude = self.altitude

        x_world, y_world = world_point

        # Scale by focal length / altitude
        x_norm = x_world / altitude
        y_norm = y_world / altitude

        # Convert to pixel coordinates
        u = x_norm * self.fx + self.cx
        v = y_norm * self.fy + self.cy

        return np.array([u, v])

    def get_ground_plane_scale(self, altitude: Optional[float] = None) -> float:
        """
        Get scale factor for ground plane (meters per pixel)

        Args:
            altitude: Optional altitude (uses stored altitude if None)

        Returns:
            Meters per pixel at current altitude
        """
        if altitude is None:
            altitude = self.altitude

        # Average focal length
        f_avg = (self.fx + self.fy) / 2.0

        # Meters per pixel
        scale = altitude / f_avg

        return scale

    def get_field_of_view(self, image_width: int, image_height: int) -> Tuple[float, float]:
        """
        Calculate horizontal and vertical field of view

        Args:
            image_width: Image width in pixels
            image_height: Image height in pixels

        Returns:
            Tuple of (horizontal_fov, vertical_fov) in radians
        """
        fov_x = 2.0 * np.arctan(image_width / (2.0 * self.fx))
        fov_y = 2.0 * np.arctan(image_height / (2.0 * self.fy))

        return fov_x, fov_y


# Utility functions

def create_camera_matrix(
    fx: float,
    fy: float,
    cx: float,
    cy: float
) -> np.ndarray:
    """
    Create camera intrinsic matrix

    Args:
        fx: Focal length in x direction (pixels)
        fy: Focal length in y direction (pixels)
        cx: Principal point x coordinate (pixels)
        cy: Principal point y coordinate (pixels)

    Returns:
        3x3 camera matrix
    """
    return np.array([
        [fx,  0, cx],
        [ 0, fy, cy],
        [ 0,  0,  1]
    ], dtype=np.float32)


def rotation_matrix_2d(angle_rad: float) -> np.ndarray:
    """
    Create 2D rotation matrix

    Args:
        angle_rad: Rotation angle in radians

    Returns:
        2x2 rotation matrix
    """
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    return np.array([
        [cos_a, -sin_a],
        [sin_a,  cos_a]
    ], dtype=np.float32)


def rotate_velocity(velocity: np.ndarray, heading: float) -> np.ndarray:
    """
    Rotate velocity vector by heading angle

    Converts velocity from camera frame to world frame

    Args:
        velocity: Velocity as [vx, vy] in camera frame
        heading: Heading angle in radians (0 = north, positive = clockwise)

    Returns:
        Velocity in world frame
    """
    R = rotation_matrix_2d(heading)
    return R @ velocity
