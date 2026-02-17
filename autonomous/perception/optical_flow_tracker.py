"""
Optical Flow Tracker for Drone Position Estimation

This module implements sparse Lucas-Kanade optical flow tracking
for estimating drone velocity from video frames.

The tracker detects and tracks visual features (corners) across frames
and calculates the median pixel velocity, which can be used to estimate
the drone's movement in world coordinates.

GPU acceleration via OpenCV CUDA is used automatically when available
(requires OpenCV built with CUDA support). Falls back to CPU otherwise.

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


def _cuda_available() -> bool:
    """Return True if OpenCV was built with CUDA and a device is present."""
    try:
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except (cv2.error, AttributeError):
        return False


class OpticalFlowTracker:
    """
    Sparse Lucas-Kanade optical flow tracker with optional CUDA acceleration.

    Uses cv2.cuda.SparsePyrLKOpticalFlow and
    cv2.cuda.createGoodFeaturesToTrackDetector when OpenCV CUDA is available,
    otherwise falls back to the standard CPU implementation.

    Attributes:
        max_corners: Maximum number of features to track
        quality_level: Quality level for corner detection (0.0-1.0)
        min_distance: Minimum distance between detected corners (pixels)
        block_size: Size of averaging block for corner detection
        min_features: Minimum features before re-detection
        max_level: Number of pyramid levels for Lucas-Kanade
        win_size: Window size for Lucas-Kanade
        use_cuda: Whether GPU path is active
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
        # Feature detection parameters
        self.max_corners = max_corners
        self.quality_level = quality_level
        self.min_distance = min_distance
        self.block_size = block_size
        self.min_features = min_features
        self.max_pixel_velocity = max_pixel_velocity
        self.win_size = win_size
        self.max_level = max_level

        # State
        self.frame_prev: Optional[np.ndarray] = None
        self.features_prev: Optional[np.ndarray] = None
        self.frame_count = 0

        # GPU / CPU init
        self.use_cuda = _cuda_available()
        if self.use_cuda:
            self._init_cuda(win_size, max_level)
            logger.info(
                f"OpticalFlowTracker: CUDA GPU path active "
                f"({cv2.cuda.getDevice()} — {cv2.cuda.DeviceInfo(cv2.cuda.getDevice()).name()})"
            )
        else:
            self._init_cpu(win_size, max_level)
            logger.info("OpticalFlowTracker: CPU path active (OpenCV CUDA not available)")

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_cuda(self, win_size: int, max_level: int) -> None:
        """Set up GPU-accelerated detectors / trackers."""
        self._cuda_detector = cv2.cuda.createGoodFeaturesToTrackDetector(
            cv2.CV_8UC1,
            maxCorners=self.max_corners,
            qualityLevel=self.quality_level,
            minDistance=self.min_distance,
            blockSize=self.block_size,
        )
        self._cuda_lk = cv2.cuda.SparsePyrLKOpticalFlow.create(
            winSize=(win_size, win_size),
            maxLevel=max_level,
            iters=30,
        )

    def _init_cpu(self, win_size: int, max_level: int) -> None:
        """Set up CPU-based parameter dicts."""
        self.lk_params = dict(
            winSize=(win_size, win_size),
            maxLevel=max_level,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        self.feature_params = dict(
            maxCorners=self.max_corners,
            qualityLevel=self.quality_level,
            minDistance=self.min_distance,
            blockSize=self.block_size,
        )

    # ------------------------------------------------------------------
    # Feature detection
    # ------------------------------------------------------------------

    def detect_features(self, frame: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Detect good features to track (GPU or CPU path).

        Args:
            frame: Grayscale uint8 frame
            mask: Optional mask (CPU path only — CUDA detector ignores it)

        Returns:
            Feature points as (N, 1, 2) float32 array, or empty array
        """
        if self.use_cuda:
            return self._detect_features_cuda(frame)
        return self._detect_features_cpu(frame, mask)

    def _detect_features_cuda(self, frame: np.ndarray) -> np.ndarray:
        gpu_frame = cv2.cuda_GpuMat()
        gpu_frame.upload(frame)
        gpu_pts = self._cuda_detector.detect(gpu_frame, None)
        if gpu_pts is None or gpu_pts.size().width == 0:
            logger.warning("CUDA: no features detected")
            return np.array([])
        pts = gpu_pts.download()          # shape: (1, N, 2) or (N, 2)
        pts = pts.reshape(-1, 1, 2).astype(np.float32)
        logger.debug(f"CUDA detected {len(pts)} features")
        return pts

    def _detect_features_cpu(self, frame: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray:
        features = cv2.goodFeaturesToTrack(frame, mask=mask, **self.feature_params)
        if features is None:
            logger.warning("CPU: no features detected")
            return np.array([])
        logger.debug(f"CPU detected {len(features)} features")
        return features

    # ------------------------------------------------------------------
    # Optical flow
    # ------------------------------------------------------------------

    def _calc_flow_cuda(
        self,
        frame_prev: np.ndarray,
        frame_next: np.ndarray,
        features_prev: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Run LK optical flow on GPU. Returns (features_next, status) as CPU arrays."""
        gpu_prev = cv2.cuda_GpuMat()
        gpu_next = cv2.cuda_GpuMat()
        gpu_prev.upload(frame_prev)
        gpu_next.upload(frame_next)

        # SparsePyrLKOpticalFlow expects CV_32FC2 point matrix
        pts = features_prev.reshape(1, -1, 2).astype(np.float32)
        gpu_pts = cv2.cuda_GpuMat()
        gpu_pts.upload(pts)

        gpu_next_pts, gpu_status, _ = self._cuda_lk.calc(gpu_prev, gpu_next, gpu_pts, None)

        if gpu_next_pts is None:
            return None, None

        next_pts = gpu_next_pts.download().reshape(-1, 1, 2).astype(np.float32)
        status = gpu_status.download().reshape(-1, 1).astype(np.uint8)
        return next_pts, status

    def _calc_flow_cpu(
        self,
        frame_prev: np.ndarray,
        frame_next: np.ndarray,
        features_prev: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Run LK optical flow on CPU."""
        features_next, status, _ = cv2.calcOpticalFlowPyrLK(
            frame_prev, frame_next, features_prev, None, **self.lk_params
        )
        return features_next, status

    # ------------------------------------------------------------------
    # Outlier rejection + velocity
    # ------------------------------------------------------------------

    def filter_outliers(
        self,
        features_prev: np.ndarray,
        features_next: np.ndarray,
        status: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Filter outlier feature tracks by tracking status and flow magnitude."""
        mask = status.flatten() == 1
        if not np.any(mask):
            return np.array([]), np.array([]), np.array([])

        flow = features_next[mask] - features_prev[mask]
        flow_magnitude = np.linalg.norm(flow, axis=2).flatten()
        velocity_mask = flow_magnitude < self.max_pixel_velocity

        indices = np.where(mask)[0]
        filtered_indices = indices[velocity_mask]
        final_mask = np.zeros_like(mask)
        final_mask[filtered_indices] = True

        num_filtered = int(mask.sum()) - int(velocity_mask.sum())
        if num_filtered > 0:
            logger.debug(f"Filtered {num_filtered} outlier features")

        return features_prev[final_mask], features_next[final_mask], status[final_mask]

    def calculate_velocity(
        self,
        features_prev: np.ndarray,
        features_next: np.ndarray,
    ) -> np.ndarray:
        """Calculate median velocity from feature tracks (pixels/frame)."""
        if len(features_prev) == 0 or len(features_next) == 0:
            return np.array([0.0, 0.0])
        flow = (features_next - features_prev).reshape(-1, 2)
        median_flow = np.median(flow, axis=0)
        logger.debug(f"Median velocity: {median_flow} px/frame from {len(flow)} features")
        return median_flow

    # ------------------------------------------------------------------
    # Main update loop
    # ------------------------------------------------------------------

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Update tracker with new frame and calculate velocity.

        Args:
            frame: Current frame (BGR or grayscale)

        Returns:
            Tuple of (success, velocity, features):
                - success: Whether tracking was successful
                - velocity: Median velocity [vx, vy] in pixels/frame (None if failed)
                - features: Current feature points (None if failed)
        """
        if len(frame.shape) == 3:
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            frame_gray = frame.copy()

        self.frame_count += 1

        # First frame — just detect and store
        if self.frame_prev is None:
            self.features_prev = self.detect_features(frame_gray)
            self.frame_prev = frame_gray
            logger.info(f"Initialized with {len(self.features_prev)} features")
            return False, None, None

        # Re-detect if features dropped below threshold
        feature_count = len(self.features_prev) if self.features_prev is not None else 0
        if self.features_prev is None or feature_count < self.min_features:
            logger.info(f"Re-detecting features (count={feature_count})")
            self.features_prev = self.detect_features(frame_gray)
            self.frame_prev = frame_gray
            return False, None, None

        # Optical flow (GPU or CPU)
        if self.use_cuda:
            features_next, status = self._calc_flow_cuda(self.frame_prev, frame_gray, self.features_prev)
        else:
            features_next, status = self._calc_flow_cpu(self.frame_prev, frame_gray, self.features_prev)

        if features_next is None or len(features_next) == 0:
            logger.warning("Optical flow tracking failed")
            self.features_prev = None
            return False, None, None

        # Filter outliers
        features_prev_good, features_next_good, _ = self.filter_outliers(
            self.features_prev, features_next, status
        )

        if len(features_prev_good) == 0:
            logger.warning("No good features after filtering")
            self.features_prev = None
            return False, None, None

        # Calculate velocity
        velocity = self.calculate_velocity(features_prev_good, features_next_good)

        # Update state
        self.frame_prev = frame_gray
        self.features_prev = features_next_good

        logger.debug(
            f"Frame {self.frame_count}: {len(self.features_prev)} features, "
            f"velocity={velocity} ({'CUDA' if self.use_cuda else 'CPU'})"
        )

        return True, velocity, features_next_good

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset tracker state (call when stream restarts)."""
        self.frame_prev = None
        self.features_prev = None
        self.frame_count = 0
        logger.info("Optical flow tracker reset")

    def get_feature_count(self) -> int:
        """Return current number of tracked features."""
        if self.features_prev is None:
            return 0
        return len(self.features_prev)
