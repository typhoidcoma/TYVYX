"""
Depth Estimation Service

Runs monocular depth inference on video frames from the drone camera.
Supports MiDaS (Intel) and Depth Anything V2 (HuggingFace) models on GPU.

Outputs:
  - Per-frame depth map (HxW float32, relative or metric)
  - Median altitude estimate (meters)
  - Colorized depth JPEG for frontend visualization

The altitude estimate auto-feeds into position_service to fix the
pixel-to-world scaling that optical flow depends on.
"""

import cv2
import logging
import threading
import time
from typing import Optional, List, Dict, Any

import numpy as np
import torch

logger = logging.getLogger(__name__)


class DepthService:
    """
    Singleton service for monocular depth estimation.

    Supports two model backends:
      - MiDaS (torch.hub): model_name = "MiDaS_DPT_Large" etc.
      - Depth Anything V2 (HuggingFace): model_name = "depth-anything/..."
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Model
        self._model = None
        self._transform = None   # MiDaS transform
        self._device = "cuda"
        self._model_name = ""
        self._backend = ""       # "midas" or "hf"

        # State
        self._enabled = False
        self._frame_counter = 0
        self.process_every_n = 1

        # Latest results (thread-safe)
        self._last_depth_map = None      # type: Optional[np.ndarray]
        self._last_depth_jpeg = None     # type: Optional[bytes]
        self._last_avg_depth = 0.0
        self._last_altitude = 1.0
        self._last_timestamp = 0.0
        self._process_time_ms = 0.0

        # Configuration
        self._colormap = cv2.COLORMAP_INFERNO
        self._max_depth = 20.0
        self._sensitivity = 0
        self._depth_scale = 200.0  # MiDaS inverse-depth→meters: depth = scale / raw
        self._auto_feed_altitude = True

        # Temporal smoothing (EMA)
        self._ema_depth = None  # type: Optional[np.ndarray]
        self._ema_alpha = 0.4

        # Callbacks
        self._on_depth_callbacks = []    # type: List[Any]
        self._callbacks_lock = threading.Lock()
        self._state_lock = threading.Lock()

        # Busy flag
        self._busy = False

        # Statistics
        self._total_frames = 0
        self._total_inferences = 0

        self._initialized = True
        logger.info("DepthService singleton created")

    def initialize(self, config):
        # type: (Dict[str, Any]) -> None
        depth_config = config.get('depth', {})
        self._model_name = depth_config.get('model_name', 'DPT_Large')
        self._device = depth_config.get('device', 'cuda')
        self.process_every_n = depth_config.get('process_every_n', 1)
        self._auto_feed_altitude = depth_config.get('auto_feed_altitude', True)
        self._max_depth = depth_config.get('max_depth', 20.0)
        self._depth_scale = depth_config.get('depth_scale', 200.0)
        self._ema_alpha = depth_config.get('ema_alpha', 0.4)

        colormap_name = depth_config.get('colormap', 'inferno').upper()
        self._colormap = getattr(cv2, 'COLORMAP_' + colormap_name, cv2.COLORMAP_INFERNO)

        # Detect backend from model name
        if '/' in self._model_name and 'depth-anything' in self._model_name.lower():
            self._backend = "hf"
        else:
            self._backend = "midas"

        logger.info(
            "DepthService initialized: model=%s, backend=%s, device=%s, every_n=%d",
            self._model_name, self._backend, self._device, self.process_every_n
        )

    def _load_model(self):
        # type: () -> bool
        if self._model is not None:
            return True

        try:
            logger.info("Loading depth model: %s (backend=%s)...", self._model_name, self._backend)
            t0 = time.time()

            if self._backend == "midas":
                self._model = torch.hub.load('intel-isl/MiDaS', self._model_name, trust_repo=True)
                self._model.to(self._device).eval()

                transforms = torch.hub.load('intel-isl/MiDaS', 'transforms', trust_repo=True)
                if 'DPT' in self._model_name:
                    self._transform = transforms.dpt_transform
                elif 'small' in self._model_name.lower():
                    self._transform = transforms.small_transform
                else:
                    self._transform = transforms.dpt_transform
            else:
                from transformers import pipeline
                self._model = pipeline(
                    "depth-estimation",
                    model=self._model_name,
                    device=0 if self._device == "cuda" else -1
                )

            elapsed = time.time() - t0
            logger.info("Depth model loaded in %.1fs on %s", elapsed, self._device)
            return True

        except Exception as e:
            logger.error("Failed to load depth model: %s", e, exc_info=True)
            self._model = None
            return False

    def start(self):
        # type: () -> None
        self._enabled = True
        self._frame_counter = 0
        self._ema_depth = None
        logger.info("Depth estimation enabled")

    def stop(self):
        # type: () -> None
        self._enabled = False
        logger.info("Depth estimation disabled")

    def is_enabled(self):
        # type: () -> bool
        return self._enabled

    def process_frame(self, frame):
        # type: (np.ndarray) -> bool
        if not self._enabled:
            return False

        self._total_frames += 1
        self._frame_counter += 1

        if self._frame_counter % self.process_every_n != 0:
            return False

        if self._busy:
            return False
        self._busy = True

        if self._model is None:
            if not self._load_model():
                self._busy = False
                return False

        try:
            t0 = time.time()

            if self._backend == "midas":
                depth_map = self._infer_midas(frame)
            else:
                depth_map = self._infer_hf(frame)

            # Resize to original frame size
            orig_h, orig_w = frame.shape[:2]
            if depth_map.shape != (orig_h, orig_w):
                depth_map = cv2.resize(depth_map, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

            # Clamp to max depth
            depth_map = np.clip(depth_map, 0, self._max_depth)

            # Temporal smoothing (EMA)
            if self._ema_depth is not None and self._ema_depth.shape == depth_map.shape:
                depth_map = self._ema_alpha * depth_map + (1.0 - self._ema_alpha) * self._ema_depth
            self._ema_depth = depth_map.copy()

            # Estimate altitude from center region
            h, w = depth_map.shape
            cy, cx = h // 4, w // 4
            center_crop = depth_map[cy:cy + h // 2, cx:cx + w // 2]
            median_depth = float(np.median(center_crop))
            avg_depth = float(np.mean(center_crop))

            depth_jpeg = self._colorize_depth(depth_map)
            elapsed_ms = (time.time() - t0) * 1000

            with self._state_lock:
                self._last_depth_map = depth_map
                self._last_depth_jpeg = depth_jpeg
                self._last_avg_depth = avg_depth
                self._last_altitude = max(0.1, median_depth)
                self._last_timestamp = time.time()
                self._process_time_ms = elapsed_ms
                self._total_inferences += 1

            logger.debug(
                "Depth: median=%.2fm, avg=%.2fm, range=%.2f-%.2fm, time=%.0fms",
                median_depth, avg_depth,
                float(depth_map.min()), float(depth_map.max()),
                elapsed_ms
            )

            self._busy = False

            with self._callbacks_lock:
                cbs = list(self._on_depth_callbacks)
            for cb in cbs:
                try:
                    cb()
                except Exception as e:
                    logger.debug("Depth callback error: %s", e)

            return True

        except Exception as e:
            self._busy = False
            logger.error("Depth estimation error: %s", e, exc_info=True)
            return False

    def _infer_midas(self, frame):
        # type: (np.ndarray) -> np.ndarray
        """Run MiDaS inference. Returns HxW float32 depth map."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_batch = self._transform(rgb).to(self._device)

        with torch.no_grad():
            prediction = self._model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=rgb.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth_map = prediction.cpu().numpy().astype(np.float32)

        # MiDaS outputs inverse relative depth (higher = closer).
        # Convert to metric depth: depth_meters = depth_scale / inverse_depth
        depth_map = np.maximum(depth_map, 1e-3)  # avoid division by zero
        depth_map = self._depth_scale / depth_map

        return depth_map

    def _infer_hf(self, frame):
        # type: (np.ndarray) -> np.ndarray
        """Run HuggingFace depth-estimation pipeline. Returns HxW float32."""
        from PIL import Image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        result = self._model(pil_image)
        return np.array(result['depth'], dtype=np.float32)

    def _colorize_depth(self, depth_map):
        # type: (np.ndarray) -> bytes
        s = max(0, min(100, self._sensitivity))
        lo = 1.0 + s * 0.47
        hi = 99.0 - s * 0.47
        d_min = float(np.percentile(depth_map, lo))
        d_max = float(np.percentile(depth_map, hi))
        d_max = max(d_max, d_min + 0.5)

        clipped = np.clip(depth_map, d_min, d_max)
        normalized = ((clipped - d_min) / (d_max - d_min) * 255).astype(np.uint8)
        normalized = 255 - normalized

        colored = cv2.applyColorMap(normalized, self._colormap)
        _, buf = cv2.imencode('.jpg', colored, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buf.tobytes()

    def get_data(self):
        # type: () -> Dict[str, Any]
        with self._state_lock:
            return {
                'enabled': self._enabled,
                'avg_depth': self._last_avg_depth,
                'altitude': self._last_altitude,
                'timestamp': self._last_timestamp,
                'process_time_ms': self._process_time_ms,
                'total_inferences': self._total_inferences,
                'total_frames': self._total_frames,
                'model_loaded': self._model is not None,
                'model_name': self._model_name,
                'process_every_n': self.process_every_n,
                'sensitivity': self._sensitivity,
                'max_depth': self._max_depth,
                'depth_scale': self._depth_scale,
                'depth_range': [
                    float(self._last_depth_map.min()) if self._last_depth_map is not None else 0.0,
                    float(self._last_depth_map.max()) if self._last_depth_map is not None else 0.0,
                ],
            }

    def get_depth_jpeg(self):
        # type: () -> Optional[bytes]
        with self._state_lock:
            return self._last_depth_jpeg

    def get_altitude(self):
        # type: () -> float
        with self._state_lock:
            return self._last_altitude

    def set_sensitivity(self, value):
        # type: (int) -> None
        self._sensitivity = max(0, min(100, value))

    def set_max_depth(self, value):
        # type: (float) -> None
        self._max_depth = max(0.5, min(20.0, value))

    def set_depth_scale(self, value):
        # type: (float) -> None
        """Set MiDaS depth scale: depth_meters = scale / raw_output (10 - 1000)."""
        self._depth_scale = max(10.0, min(1000.0, value))

    def on_depth_update(self, callback):
        with self._callbacks_lock:
            self._on_depth_callbacks.append(callback)

    def remove_on_depth_update(self, callback):
        with self._callbacks_lock:
            try:
                self._on_depth_callbacks.remove(callback)
            except ValueError:
                pass


# Global singleton instance
depth_service = DepthService()
