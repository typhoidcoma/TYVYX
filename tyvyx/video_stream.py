"""Simple, minimal OpenCV video stream helper for TYVYX.

This stripped-down helper keeps a threaded VideoCapture reader and exposes
`start()`, `read()`, `stop()` and `is_opened()` with a minimal feature set
so the rest of the app and tests can rely on a stable interface.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np

# Tell OpenCV's FFMPEG backend to use a 5-second timeout for RTSP connections.
# This is more reliable than URL query params which may not be forwarded.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "stimeout;5000000|rtsp_transport;tcp",
)


def _rtsp_port_reachable(url: str, timeout: float = 2.0) -> bool:
    """Quick TCP connect check to the RTSP port. Returns True if reachable."""
    try:
        parsed = urlparse(url.split("?")[0])  # strip query params
        host = parsed.hostname or "192.168.1.1"
        port = parsed.port or 7070
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


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
        self._max_retries = int(kwargs.pop('max_retries', 2))
        self._retry_delay = float(kwargs.pop('retry_delay', 1.0))
        # RTSP timeout in seconds (passed as stimeout in microseconds)
        self._rtsp_timeout = float(kwargs.pop('rtsp_timeout', 5.0))
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stopped = True
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def _build_source_url(self) -> str | int:
        """Build the actual source string with transport and timeout params."""
        src = self.source
        if not isinstance(src, str) or not src.startswith('rtsp://'):
            return src

        params = []
        if self._prefer_tcp and 'rtsp_transport' not in src:
            params.append('rtsp_transport=tcp')
        # stimeout = microseconds for FFMPEG RTSP timeout
        if 'stimeout' not in src:
            params.append(f'stimeout={int(self._rtsp_timeout * 1_000_000)}')

        if params:
            sep = '&' if '?' in src else '?'
            src = f"{src}{sep}{'&'.join(params)}"
        return src

    def start(self, timeout: float = 5.0) -> bool:
        src = self._build_source_url()

        # Quick check: is the RTSP port reachable at all?
        if isinstance(src, str) and src.startswith('rtsp://'):
            if not _rtsp_port_reachable(str(src), timeout=2.0):
                print(f"RTSP port not reachable at {self.source}")
                return False

        attempt = 0
        while attempt < self._max_retries:
            try:
                # Prefer FFMPEG backend for RTSP sources when available — more robust
                if isinstance(src, str) and src.startswith('rtsp://'):
                    try:
                        self._cap = cv2.VideoCapture(str(src), cv2.CAP_FFMPEG)
                    except Exception:
                        self._cap = cv2.VideoCapture(str(src))
                else:
                    self._cap = cv2.VideoCapture(src)

                # attempt to set buffer size if provided
                if self._buffer_size is not None and self._cap is not None:
                    try:
                        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, int(self._buffer_size))
                    except Exception:
                        pass

                start_t = time.time()
                while time.time() - start_t < timeout:
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
            if attempt < self._max_retries:
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
