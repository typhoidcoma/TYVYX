"""
Monocular Visual Odometry using ORB features + Essential matrix.

Pipeline per frame:
  1. Detect ORB keypoints + descriptors
  2. Match against previous frame (BFMatcher + Hamming + ratio test)
  3. Recover relative pose via Essential matrix (5-point RANSAC)
  4. Accumulate pose in world frame
  5. Keyframe selection — only insert when sufficient parallax exists
  6. Triangulate 3D map points from keyframe pairs
  7. Use PnP (2D-3D) for more robust pose when map points are available

Designed for low-res JPEG drone feeds (640x360 @ 21fps).
Zero dependencies beyond OpenCV + NumPy.
"""

import cv2
import logging
import time
from typing import Optional, Dict, Any, Tuple, List

import numpy as np

from autonomous.perception.vo_types import VOResult

logger = logging.getLogger(__name__)


class MonocularVO:
    """
    Real-time monocular visual odometry.

    Extracts 6DOF camera pose from sequential frames using ORB features,
    Essential matrix decomposition, and optional PnP refinement from
    triangulated 3D map points.
    """

    def __init__(
        self,
        camera_matrix: np.ndarray,
        dist_coeffs: Optional[np.ndarray] = None,
        n_features: int = 500,
        match_ratio: float = 0.75,
        min_matches: int = 15,
        keyframe_threshold: float = 20.0,
        use_pnp: bool = True,
    ):
        """
        Args:
            camera_matrix: 3x3 intrinsic matrix K
            dist_coeffs: Distortion coefficients (None = no distortion)
            n_features: ORB features to detect per frame
            match_ratio: Lowe's ratio test threshold for BFMatcher
            min_matches: Minimum good matches required for pose recovery
            keyframe_threshold: Minimum median feature displacement (px) for keyframe
            use_pnp: Enable PnP refinement when 3D map points exist
        """
        self.K = camera_matrix.astype(np.float64)
        self.dist_coeffs = dist_coeffs if dist_coeffs is not None else np.zeros(5)
        self.n_features = n_features
        self.match_ratio = match_ratio
        self.min_matches = min_matches
        self.keyframe_threshold = keyframe_threshold
        self.use_pnp = use_pnp

        # ORB detector
        self._orb = cv2.ORB_create(nfeatures=n_features)

        # BFMatcher with Hamming distance for ORB binary descriptors
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

        # Previous frame state
        self._prev_gray: Optional[np.ndarray] = None
        self._prev_kp: Optional[List[cv2.KeyPoint]] = None
        self._prev_desc: Optional[np.ndarray] = None

        # Keyframe state (for triangulation)
        self._kf_gray: Optional[np.ndarray] = None
        self._kf_kp: Optional[List[cv2.KeyPoint]] = None
        self._kf_desc: Optional[np.ndarray] = None
        self._kf_pose: Optional[np.ndarray] = None  # 4x4

        # Cumulative world pose (4x4, identity = start)
        self._pose = np.eye(4, dtype=np.float64)

        # Sparse 3D map: list of (point_3d, descriptor) tuples
        self._map_points: List[np.ndarray] = []
        self._map_descriptors: Optional[np.ndarray] = None

        # Statistics
        self._frame_count = 0
        self._keyframe_count = 0
        self._total_matches = 0
        self._total_inliers = 0
        self._lost_count = 0

        logger.info(
            "MonocularVO initialized: %d features, ratio=%.2f, "
            "min_matches=%d, kf_threshold=%.1fpx, pnp=%s",
            n_features, match_ratio, min_matches, keyframe_threshold, use_pnp,
        )

    def process_frame(self, frame: np.ndarray) -> VOResult:
        """
        Process a new frame and estimate camera motion.

        Args:
            frame: BGR or grayscale image

        Returns:
            VOResult with pose information and metrics
        """
        t0 = time.time()
        self._frame_count += 1

        # Convert to grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # Detect ORB features
        kp, desc = self._orb.detectAndCompute(gray, None)

        if desc is None or len(kp) < self.min_matches:
            # Not enough features — store frame and skip
            self._prev_gray = gray
            self._prev_kp = kp
            self._prev_desc = desc
            elapsed = (time.time() - t0) * 1000
            return VOResult(
                success=False,
                process_time_ms=elapsed,
                num_matches=0,
                num_inliers=0,
            )

        # First frame — initialize
        if self._prev_desc is None:
            self._prev_gray = gray
            self._prev_kp = kp
            self._prev_desc = desc
            self._kf_gray = gray
            self._kf_kp = kp
            self._kf_desc = desc
            self._kf_pose = self._pose.copy()
            self._keyframe_count = 1
            elapsed = (time.time() - t0) * 1000
            return VOResult(
                success=True,
                R=np.eye(3),
                t=np.zeros((3, 1)),
                is_keyframe=True,
                pose_4x4=self._pose.copy(),
                process_time_ms=elapsed,
            )

        # Try PnP first if we have map points
        pnp_result = None
        if self.use_pnp and len(self._map_points) >= self.min_matches:
            pnp_result = self._try_pnp(kp, desc)

        if pnp_result is not None:
            R, t, num_inliers = pnp_result
            self._update_pose(R, t)
            is_kf = self._check_keyframe(kp, desc, gray)
            elapsed = (time.time() - t0) * 1000
            return VOResult(
                success=True,
                R=R,
                t=t,
                num_matches=len(self._map_points),
                num_inliers=num_inliers,
                is_keyframe=is_kf,
                pose_4x4=self._pose.copy(),
                map_points_count=len(self._map_points),
                process_time_ms=elapsed,
            )

        # Essential matrix path (frame-to-frame)
        result = self._estimate_essential(
            self._prev_kp, self._prev_desc, kp, desc
        )

        if result is None:
            # Tracking lost — keep features for recovery
            self._lost_count += 1
            self._prev_gray = gray
            self._prev_kp = kp
            self._prev_desc = desc
            elapsed = (time.time() - t0) * 1000
            return VOResult(
                success=False,
                process_time_ms=elapsed,
                map_points_count=len(self._map_points),
            )

        R, t, num_matches, num_inliers = result
        self._total_matches += num_matches
        self._total_inliers += num_inliers

        # Update cumulative pose
        self._update_pose(R, t)

        # Check if this should be a keyframe
        is_kf = self._check_keyframe(kp, desc, gray)

        self._prev_gray = gray
        self._prev_kp = kp
        self._prev_desc = desc

        elapsed = (time.time() - t0) * 1000
        return VOResult(
            success=True,
            R=R,
            t=t,
            num_matches=num_matches,
            num_inliers=num_inliers,
            is_keyframe=is_kf,
            pose_4x4=self._pose.copy(),
            map_points_count=len(self._map_points),
            process_time_ms=elapsed,
        )

    def _match_features(
        self,
        desc1: np.ndarray,
        desc2: np.ndarray,
    ) -> List[cv2.DMatch]:
        """Match ORB descriptors with ratio test."""
        raw_matches = self._matcher.knnMatch(desc1, desc2, k=2)

        good = []
        for pair in raw_matches:
            if len(pair) == 2:
                m, n = pair
                if m.distance < self.match_ratio * n.distance:
                    good.append(m)

        return good

    def _estimate_essential(
        self,
        kp1: List[cv2.KeyPoint],
        desc1: np.ndarray,
        kp2: List[cv2.KeyPoint],
        desc2: np.ndarray,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, int, int]]:
        """
        Estimate relative pose via Essential matrix.

        Returns:
            (R, t, num_matches, num_inliers) or None if failed
        """
        good_matches = self._match_features(desc1, desc2)

        if len(good_matches) < self.min_matches:
            logger.debug(
                "Too few matches: %d < %d", len(good_matches), self.min_matches
            )
            return None

        # Extract matched point coordinates
        pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
        pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])

        # Find Essential matrix with RANSAC
        E, mask = cv2.findEssentialMat(
            pts1, pts2, self.K,
            method=cv2.RANSAC,
            prob=0.999,
            threshold=1.0,
        )

        if E is None or mask is None:
            return None

        num_inliers = int(mask.sum())
        if num_inliers < self.min_matches:
            return None

        # Recover rotation and translation from Essential matrix
        retval, R, t, pose_mask = cv2.recoverPose(E, pts1, pts2, self.K, mask=mask)

        if retval < self.min_matches:
            return None

        return R, t, len(good_matches), num_inliers

    def _try_pnp(
        self,
        kp: List[cv2.KeyPoint],
        desc: np.ndarray,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, int]]:
        """
        Try to recover pose from 2D-3D correspondences (PnP).

        Matches current frame descriptors against map point descriptors,
        then solves PnP with RANSAC.

        Returns:
            (R, t, num_inliers) or None if failed
        """
        if self._map_descriptors is None or len(self._map_points) < self.min_matches:
            return None

        good_matches = self._match_features(self._map_descriptors, desc)

        if len(good_matches) < self.min_matches:
            return None

        # Build 3D-2D correspondences
        pts_3d = np.float32([self._map_points[m.queryIdx] for m in good_matches])
        pts_2d = np.float32([kp[m.trainIdx].pt for m in good_matches])

        success, rvec, tvec, inliers = cv2.solvePnPRansac(
            pts_3d, pts_2d, self.K, self.dist_coeffs,
            iterationsCount=100,
            reprojectionError=3.0,
            confidence=0.99,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success or inliers is None or len(inliers) < self.min_matches:
            return None

        R, _ = cv2.Rodrigues(rvec)
        return R, tvec, len(inliers)

    def _update_pose(self, R: np.ndarray, t: np.ndarray) -> None:
        """Accumulate relative pose into world frame."""
        T_rel = np.eye(4, dtype=np.float64)
        T_rel[:3, :3] = R
        T_rel[:3, 3] = t.flatten()

        self._pose = self._pose @ T_rel

    def _check_keyframe(
        self,
        kp: List[cv2.KeyPoint],
        desc: np.ndarray,
        gray: np.ndarray,
    ) -> bool:
        """
        Check if current frame should be a keyframe.
        If so, triangulate new map points from keyframe pair.
        """
        if self._kf_desc is None:
            return False

        good_matches = self._match_features(self._kf_desc, desc)

        if len(good_matches) < self.min_matches:
            return False

        # Compute median feature displacement from keyframe
        pts_kf = np.float32([self._kf_kp[m.queryIdx].pt for m in good_matches])
        pts_cur = np.float32([kp[m.trainIdx].pt for m in good_matches])
        displacements = np.linalg.norm(pts_cur - pts_kf, axis=1)
        median_disp = float(np.median(displacements))

        if median_disp < self.keyframe_threshold:
            return False

        # This is a keyframe — triangulate 3D points
        self._triangulate_points(
            self._kf_kp, self._kf_desc, self._kf_pose,
            kp, desc, self._pose,
            good_matches,
        )

        # Update keyframe
        self._kf_gray = gray
        self._kf_kp = kp
        self._kf_desc = desc
        self._kf_pose = self._pose.copy()
        self._keyframe_count += 1

        logger.debug(
            "Keyframe %d: disp=%.1fpx, matches=%d, map_pts=%d",
            self._keyframe_count, median_disp,
            len(good_matches), len(self._map_points),
        )

        return True

    def _triangulate_points(
        self,
        kp1: List[cv2.KeyPoint],
        desc1: np.ndarray,
        pose1: np.ndarray,
        kp2: List[cv2.KeyPoint],
        desc2: np.ndarray,
        pose2: np.ndarray,
        matches: List[cv2.DMatch],
    ) -> None:
        """
        Triangulate 3D points from a keyframe pair.
        Adds valid points to the map.
        """
        pts1 = np.float32([kp1[m.queryIdx].pt for m in matches])
        pts2 = np.float32([kp2[m.trainIdx].pt for m in matches])

        # Projection matrices: P = K @ [R | t]
        P1 = self.K @ pose1[:3, :]
        P2 = self.K @ pose2[:3, :]

        # Triangulate
        pts_4d = cv2.triangulatePoints(P1, P2, pts1.T, pts2.T)
        pts_3d = (pts_4d[:3] / pts_4d[3]).T  # Nx3

        # Filter: remove points behind camera or too far away
        valid = []
        valid_desc = []
        for i, pt in enumerate(pts_3d):
            # Check point is in front of both cameras
            pt_cam1 = pose1[:3, :3] @ pt + pose1[:3, 3]
            pt_cam2 = pose2[:3, :3] @ pt + pose2[:3, 3]

            if pt_cam1[2] > 0 and pt_cam2[2] > 0:
                # Reject points too far away (likely noise)
                dist = np.linalg.norm(pt - pose2[:3, 3])
                if dist < 50.0:
                    valid.append(pt)
                    valid_desc.append(desc2[matches[i].trainIdx])

        if valid:
            self._map_points = valid
            self._map_descriptors = np.array(valid_desc, dtype=np.uint8)
            logger.debug("Triangulated %d valid map points", len(valid))

    def get_cumulative_pose(self) -> np.ndarray:
        """Get current 4x4 world-to-camera transform."""
        return self._pose.copy()

    def get_position(self) -> Tuple[float, float, float]:
        """Extract (x, y, z) position from cumulative pose."""
        return (
            float(self._pose[0, 3]),
            float(self._pose[1, 3]),
            float(self._pose[2, 3]),
        )

    def get_map_points(self) -> np.ndarray:
        """Get Nx3 array of triangulated 3D map points."""
        if not self._map_points:
            return np.empty((0, 3), dtype=np.float64)
        return np.array(self._map_points, dtype=np.float64)

    def reset(self) -> None:
        """Clear all state — start fresh."""
        self._prev_gray = None
        self._prev_kp = None
        self._prev_desc = None
        self._kf_gray = None
        self._kf_kp = None
        self._kf_desc = None
        self._kf_pose = None
        self._pose = np.eye(4, dtype=np.float64)
        self._map_points = []
        self._map_descriptors = None
        self._frame_count = 0
        self._keyframe_count = 0
        self._total_matches = 0
        self._total_inliers = 0
        self._lost_count = 0
        logger.info("MonocularVO reset")

    def get_statistics(self) -> Dict[str, Any]:
        """Get VO diagnostics."""
        pos = self.get_position()
        avg_matches = (
            self._total_matches / max(1, self._frame_count - 1)
        )
        avg_inliers = (
            self._total_inliers / max(1, self._frame_count - 1)
        )
        inlier_ratio = (
            self._total_inliers / max(1, self._total_matches)
        )

        return {
            "frame_count": self._frame_count,
            "keyframe_count": self._keyframe_count,
            "map_points_count": len(self._map_points),
            "lost_count": self._lost_count,
            "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
            "avg_matches": avg_matches,
            "avg_inliers": avg_inliers,
            "inlier_ratio": inlier_ratio,
            "n_features": self.n_features,
            "match_ratio": self.match_ratio,
            "min_matches": self.min_matches,
            "keyframe_threshold": self.keyframe_threshold,
            "use_pnp": self.use_pnp,
        }
