"""
Feature Detection Utilities

Helper functions for detecting and filtering visual features
for optical flow tracking and SLAM.
"""

import cv2
import numpy as np
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def detect_good_features(
    frame: np.ndarray,
    max_corners: int = 100,
    quality_level: float = 0.01,
    min_distance: int = 10,
    block_size: int = 7,
    mask: Optional[np.ndarray] = None,
    use_harris: bool = False,
    k: float = 0.04
) -> np.ndarray:
    """
    Detect good features to track using Shi-Tomasi or Harris corner detector

    Args:
        frame: Grayscale image
        max_corners: Maximum number of corners to detect
        quality_level: Quality threshold (0.0-1.0)
        min_distance: Minimum distance between corners (pixels)
        block_size: Size of averaging block
        mask: Optional mask to specify detection regions
        use_harris: Use Harris detector instead of Shi-Tomasi
        k: Harris detector parameter

    Returns:
        Feature points as (N, 1, 2) array or empty array if none found
    """
    if len(frame.shape) == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    features = cv2.goodFeaturesToTrack(
        frame,
        maxCorners=max_corners,
        qualityLevel=quality_level,
        minDistance=min_distance,
        mask=mask,
        blockSize=block_size,
        useHarrisDetector=use_harris,
        k=k
    )

    if features is None:
        return np.array([])

    return features


def filter_features_by_flow(
    features: np.ndarray,
    flow: np.ndarray,
    max_flow: float = 50.0
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Filter features with unrealistic flow magnitude

    Args:
        features: Feature points (N, 1, 2)
        flow: Flow vectors (N, 1, 2)
        max_flow: Maximum allowed flow magnitude (pixels)

    Returns:
        Tuple of (filtered_features, filtered_flow)
    """
    if len(features) == 0 or len(flow) == 0:
        return features, flow

    # Calculate flow magnitude
    flow_flat = flow.reshape(-1, 2)
    flow_magnitude = np.linalg.norm(flow_flat, axis=1)

    # Filter by max flow
    mask = flow_magnitude < max_flow

    filtered_features = features[mask]
    filtered_flow = flow[mask]

    num_filtered = len(features) - len(filtered_features)
    if num_filtered > 0:
        logger.debug(f"Filtered {num_filtered} features with excessive flow")

    return filtered_features, filtered_flow


def filter_features_by_roi(
    features: np.ndarray,
    roi: Tuple[int, int, int, int]
) -> np.ndarray:
    """
    Filter features to keep only those within a region of interest

    Args:
        features: Feature points (N, 1, 2)
        roi: Region of interest as (x, y, width, height)

    Returns:
        Filtered features
    """
    if len(features) == 0:
        return features

    x, y, w, h = roi

    # Reshape for easier access
    features_flat = features.reshape(-1, 2)

    # Create mask for features within ROI
    mask = (
        (features_flat[:, 0] >= x) &
        (features_flat[:, 0] < x + w) &
        (features_flat[:, 1] >= y) &
        (features_flat[:, 1] < y + h)
    )

    filtered_features = features[mask]

    return filtered_features


def create_grid_mask(
    image_shape: Tuple[int, int],
    cell_size: int = 50,
    features_per_cell: int = 2
) -> np.ndarray:
    """
    Create a mask for grid-based feature distribution

    Divides image into grid cells and allows a maximum number of
    features per cell to ensure spatially distributed features.

    Args:
        image_shape: Image shape as (height, width)
        cell_size: Size of grid cells (pixels)
        features_per_cell: Maximum features per cell

    Returns:
        Mask array (same size as image)
    """
    height, width = image_shape
    mask = np.ones((height, width), dtype=np.uint8) * 255

    # This would be used in conjunction with feature detection
    # to ensure features are distributed across the image

    return mask


def visualize_features(
    frame: np.ndarray,
    features: np.ndarray,
    flow: Optional[np.ndarray] = None,
    circle_radius: int = 3,
    circle_color: Tuple[int, int, int] = (0, 255, 0),
    line_color: Tuple[int, int, int] = (0, 0, 255)
) -> np.ndarray:
    """
    Visualize features and optical flow on frame

    Args:
        frame: Input frame (BGR)
        features: Feature points (N, 1, 2)
        flow: Optional flow vectors (N, 1, 2)
        circle_radius: Radius for feature circles
        circle_color: Color for feature circles (B, G, R)
        line_color: Color for flow lines (B, G, R)

    Returns:
        Frame with visualizations
    """
    vis_frame = frame.copy()

    if len(features) == 0:
        return vis_frame

    # Draw features
    for feature in features:
        x, y = feature.ravel()
        cv2.circle(vis_frame, (int(x), int(y)), circle_radius, circle_color, -1)

    # Draw flow vectors if provided
    if flow is not None and len(flow) > 0:
        for i, (feature, flow_vec) in enumerate(zip(features, flow)):
            x1, y1 = feature.ravel()
            dx, dy = flow_vec.ravel()
            x2, y2 = x1 + dx, y1 + dy
            cv2.arrowedLine(
                vis_frame,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                line_color,
                1,
                tipLength=0.3
            )

    return vis_frame


def compute_feature_quality(
    frame: np.ndarray,
    features: np.ndarray,
    window_size: int = 7
) -> np.ndarray:
    """
    Compute quality metric for each feature

    Uses corner response or similar metric to assess feature quality

    Args:
        frame: Grayscale frame
        features: Feature points (N, 1, 2)
        window_size: Window size for quality computation

    Returns:
        Quality scores for each feature (N,)
    """
    if len(features) == 0:
        return np.array([])

    if len(frame.shape) == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    quality_scores = []

    for feature in features:
        x, y = feature.ravel()
        x, y = int(x), int(y)

        # Extract window around feature
        half_size = window_size // 2
        y1 = max(0, y - half_size)
        y2 = min(frame.shape[0], y + half_size + 1)
        x1 = max(0, x - half_size)
        x2 = min(frame.shape[1], x + half_size + 1)

        window = frame[y1:y2, x1:x2]

        if window.size == 0:
            quality_scores.append(0.0)
            continue

        # Use variance as quality metric (higher variance = better feature)
        quality = np.var(window.astype(float))
        quality_scores.append(quality)

    return np.array(quality_scores)
