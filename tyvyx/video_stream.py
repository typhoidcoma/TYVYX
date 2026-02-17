"""Simple, minimal OpenCV video stream helper for TYVYX.

This stripped-down helper keeps a threaded VideoCapture reader and exposes
`start()`, `read()`, `stop()` and `is_opened()` with a minimal feature set
so the rest of the app and tests can rely on a stable interface.
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np


class OpenCVVideoStream:
    """Minimal threaded OpenCV capture.

    Args:
        source: camera index (int) or URL string.
    """

    def __init__(self, source: str | int = 0, **kwargs):
        # compatibility options
        self.source = source
        self._prefer_tcp = bool(kwargs.pop('prefer_tcp', False))
        self._buffer_size = kwargs.pop('buffer_size', None)
        # retry options
        self._max_retries = int(kwargs.pop('max_retries', 3))
        self._retry_delay = float(kwargs.pop('retry_delay', 1.0))
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stopped = True
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def start(self, timeout: float = 3.0) -> bool:
        # Build actual source string (apply TCP transport for RTSP if requested)
        src = self.source
        if isinstance(src, str) and self._prefer_tcp and src.startswith('rtsp://') and 'rtsp_transport' not in src:
            sep = '&' if '?' in src else '?'
            src = f"{src}{sep}rtsp_transport=tcp"

        attempt = 0
        while attempt < self._max_retries:
            try:
                # Prefer FFMPEG backend for RTSP sources when available — more robust
                if isinstance(src, str) and src.startswith('rtsp://'):
                    try:
                        self._cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                    except Exception:
                        self._cap = cv2.VideoCapture(src)
                else:
                    self._cap = cv2.VideoCapture(src)

                # attempt to set buffer size if provided
                if self._buffer_size is not None and self._cap is not None:
                    try:
                        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, int(self._buffer_size))
                    except Exception:
                        pass

                start = time.time()
                while time.time() - start < timeout:
                    try:
                        if self._cap is not None and self._cap.isOpened():
                            break
                    except Exception:
                        pass
                    time.sleep(0.05)

                if self._cap is not None and self._cap.isOpened():
                    self._stopped = False
                    self._thread = threading.Thread(target=self._update_loop, daemon=True)
                    self._thread.start()
                    return True

                try:
                    if self._cap:
                        self._cap.release()
                except Exception:
                    pass
            except Exception:
                # swallow and retry
                pass

            attempt += 1
            time.sleep(self._retry_delay)

        return False

    def _update_loop(self) -> None:
        if not self._cap:
            return
        while not self._stopped:
            try:
                ret, frame = self._cap.read()
                if not ret:
                    time.sleep(0.02)
                    continue
                with self._lock:
                    self._frame = frame
            except Exception:
                break
        try:
            if self._cap:
                self._cap.release()
        except Exception:
            pass

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def stop(self) -> None:
        self._stopped = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass

    def is_opened(self) -> bool:
        return bool(self._cap and self._cap.isOpened())


if __name__ == "__main__":
    # simple smoke run
    stream = OpenCVVideoStream(0)
    ok = stream.start()
    print('started:', ok)
    try:
        t = 0
        while t < 50:
            ok, f = stream.read()
            if ok:
                print('frame', f.shape)
                break
            time.sleep(0.1); t += 1
    finally:
        stream.stop()
