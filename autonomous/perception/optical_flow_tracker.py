"""
Optical Flow Tracker for Drone Position Estimation

This module implements sparse Lucas-Kanade optical flow tracking
for estimating drone velocity from video frames.

The tracker detects and tracks visual features (corners) across frames
and calculates the median pixel velocity, which can be used to estimate
the drone's movement in world coordinates.

Typical usage:
    tracker = OpticalFlowTracker(max_corners=100)
    for frame in video_stream:
        success, velocity, features = tracker.update(frame)
        if success:
            print(f"Velocity: {velocity} px/frame")
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class OpticalFlowTracker:
    """
    Sparse Lucas-Kanade optical flow tracker

    Tracks visual features (corners) across frames to estimate camera motion.
    Uses Shi-Tomasi corner detection and Lucas-Kanade optical flow.

    Attributes:
        max_corners: Maximum number of features to track
        quality_level: Quality level for corner detection (0.0-1.0)
        min_distance: Minimum distance between detected corners (pixels)
        block_size: Size of averaging block for corner detection
        min_features: Minimum features before re-detection
        max_level: Number of pyramid levels for Lucas-Kanade
        win_size: Window size for Lucas-Kanade

        frame_prev: Previous frame (grayscale)
        features_prev: Previous feature points
    """

    def __init__(
        self,
        max_corners: int = 100,
        quality_level: float = 0.01,
        min_distance: int = 10,
        block_size: int = 7,
        min_features: int = 20,
        max_level: int = 3,
        win_size: int = 21,
        max_pixel_velocity: float = 50.0
    ):
        """
        Initialize optical flow tracker

        Args:
            max_corners: Maximum number of corners to detect
            quality_level: Quality threshold for corner detection (0.0-1.0)
            min_distance: Minimum distance between corners (pixels)
            block_size: Size of averaging block for corner detection
            min_features: Minimum features before triggering re-detection
            max_level: Number of pyramid levels for Lucas-Kanade
            win_size: Window size for Lucas-Kanade optical flow
            max_pixel_velocity: Maximum allowed pixel velocity (outlier rejection)
        """
        # Feature detection parameters
        self.max_corners = max_corners
        self.quality_level = quality_level
        self.min_distance = min_distance
        self.block_size = block_size
        self.min_features = min_features
        self.max_pixel_velocity = max_pixel_velocity

        # Lucas-Kanade parameters
        self.lk_params = dict(
            winSize=(win_size, win_size),
            maxLevel=max_level,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
        )

        # Shi-Tomasi corner detection parameters
        self.feature_params = dict(
            maxCorners=max_corners,
            qualityLevel=quality_level,
            minDistance=min_distance,
            blockSize=block_size
        )

        # State
        self.frame_prev = None
        self.features_prev = None
        self.frame_count = 0

    def detect_features(self, frame: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Detect good features to track using Shi-Tomasi corner detector

        Args:
            frame: Grayscale frame
            mask: Optional mask to specify regions for detection

        Returns:
            Feature points as (N, 1, 2) array or empty array if none found
        """
        features = cv2.goodFeaturesToTrack(
            frame,
            mask=mask,
            **self.feature_params
        )

        if features is None:
            logger.warning("No features detected in frame")
            return np.array([])

        logger.debug(f"Detected {len(features)} features")
        return features

    def filter_outliers(
        self,
        features_prev: np.ndarray,
        features_next: np.ndarray,
        status: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Filter outlier feature tracks based on flow magnitude

        Args:
            features_prev: Previous feature positions
            features_next: Next feature positions
            status: Tracking status from optical flow

        Returns:
            Tuple of (filtered_prev, filtered_next, filtered_status)
        """
        # Start with features marked as successfully tracked
        mask = status.flatten() == 1

        if not np.any(mask):
            return np.array([]), np.array([]), np.array([])

        # Calculate flow magnitude for each feature
        flow = features_next[mask] - features_prev[mask]
        flow_magnitude = np.linalg.norm(flow, axis=2).flatten()

        # Filter by maximum pixel velocity
        velocity_mask = flow_magnitude < self.max_pixel_velocity

        # Update mask
        indices = np.where(mask)[0]
        filtered_indices = indices[velocity_mask]
        final_mask = np.zeros_like(mask)
        final_mask[filtered_indices] = True

        # Apply filter
        features_prev_filtered = features_prev[final_mask]
        features_next_filtered = features_next[final_mask]
        status_filtered = status[final_mask]

        num_filtered = len(features_prev) - len(features_prev_filtered)
        if num_filtered > 0:
            logger.debug(f"Filtered {num_filtered} outlier features")

        return features_prev_filtered, features_next_filtered, status_filtered

    def calculate_velocity(
        self,
        features_prev: np.ndarray,
        features_next: np.ndarray
    ) -> np.ndarray:
        """
        Calculate median velocity from feature tracks

        Uses median to be robust against outliers

        Args:
            features_prev: Previous feature positions (N, 1, 2)
            features_next: Next feature positions (N, 1, 2)

        Returns:
            Median velocity as [vx, vy] in pixels/frame
        """
        if len(features_prev) == 0 or len(features_next) == 0:
            return np.array([0.0, 0.0])

        # Calculate flow for each feature
        flow = features_next - features_prev  # Shape: (N, 1, 2)
        flow = flow.reshape(-1, 2)  # Shape: (N, 2)

        # Use median for robustness
        median_flow = np.median(flow, axis=0)

        logger.debug(f"Median velocity: {median_flow} px/frame from {len(flow)} features")

        return median_flow

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Update tracker with new frame and calculate velocity

        Args:
            frame: Current frame (BGR or grayscale)

        Returns:
            Tuple of (success, velocity, features):
                - success: Whether tracking was successful
                - velocity: Median velocity as [vx, vy] in pixels/frame (None if failed)
                - features: Current feature points (None if failed)
        """
        # Convert to grayscale if needed
        if len(frame.shape) == 3:
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            frame_gray = frame.copy()

        self.frame_count += 1

        # First frame - just detect features
        if self.frame_prev is None:
            self.features_prev = self.detect_features(frame_gray)
            self.frame_prev = frame_gray
            logger.info(f"Initialized with {len(self.features_prev)} features")
            return False, None, None

        # Re-detect if features dropped below threshold
        if self.features_prev is None or len(self.features_prev) < self.min_features:
            logger.info(f"Re-detecting features (count={len(self.features_prev) if self.features_prev is not None else 0})")
            self.features_prev = self.detect_features(frame_gray)
            self.frame_prev = frame_gray
            return False, None, None

        # Calculate optical flow
        features_next, status, error = cv2.calcOpticalFlowPyrLK(
            self.frame_prev,
            frame_gray,
            self.features_prev,
            None,
            **self.lk_params
        )

        if features_next is None or len(features_next) == 0:
            logger.warning("Optical flow tracking failed")
            self.features_prev = None  # Trigger re-detection
            return False, None, None

        # Filter outliers
        features_prev_good, features_next_good, status_good = self.filter_outliers(
            self.features_prev,
            features_next,
            status
        )

        if len(features_prev_good) == 0:
            logger.warning("No good features after filtering")
            self.features_prev = None  # Trigger re-detection
            return False, None, None

        # Calculate velocity
        velocity = self.calculate_velocity(features_prev_good, features_next_good)

        # Update state
        self.frame_prev = frame_gray
        self.features_prev = features_next_good  # Keep only successfully tracked features

        logger.debug(f"Frame {self.frame_count}: {len(self.features_prev)} features, velocity={velocity}")

        return True, velocity, features_next_good

    def reset(self):
        """
        Reset tracker state

        Call this when video stream restarts or tracking should be reinitialized
        """
        self.frame_prev = None
        self.features_prev = None
        self.frame_count = 0
        logger.info("Optical flow tracker reset")

    def get_feature_count(self) -> int:
        """Get current number of tracked features"""
        if self.features_prev is None:
            return 0
        return len(self.features_prev)
