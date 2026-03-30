"""
Visual Odometry data types.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import time


@dataclass
class VOResult:
    """Result of processing a single frame through the VO pipeline."""

    success: bool
    R: Optional[np.ndarray] = None          # 3x3 rotation matrix
    t: Optional[np.ndarray] = None          # 3x1 translation (unit scale)
    num_matches: int = 0
    num_inliers: int = 0
    is_keyframe: bool = False
    pose_4x4: Optional[np.ndarray] = None   # Cumulative world pose
    map_points_count: int = 0
    process_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
