"""OpenCV video stream helper packaged under `teky`."""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np


class OpenCVVideoStream:
    """Threaded OpenCV RTSP stream helper.

    Args:
        source: RTSP URL or integer camera index.
        buffer_size: value for `CAP_PROP_BUFFERSIZE` (1 is low-latency).
        name: optional name used for debug prints.
    """

    def __init__(self, source: str | int, buffer_size: int = 1, name: str = "stream"):
        self.source = source
        self.buffer_size = buffer_size
        self.name = name

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stopped = True
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def start(self, timeout: float = 5.0) -> bool:
        """Open the capture and start reader thread.

        Returns True if capture opened successfully within `timeout` seconds.
        """
        try:
            self._cap = cv2.VideoCapture(self.source)
            # Attempt to set low buffer for lower latency
            try:
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
            except Exception:
                pass

            start = time.time()
            while time.time() - start < timeout:
                if self._cap.isOpened():
                    break
                time.sleep(0.1)

            if not self._cap.isOpened():
                return False

            self._stopped = False
            self._thread = threading.Thread(target=self._update_loop, daemon=True)
            self._thread.start()
            return True

        except Exception:
            return False

    def _update_loop(self) -> None:
        """Continuously read frames in background thread."""
        if not self._cap:
            return

        while not self._stopped:
            try:
                ret, frame = self._cap.read()
                if not ret:
                    # small sleep to avoid busy-loop on failure
                    time.sleep(0.05)
                    continue

                with self._lock:
                    self._frame = frame
            except Exception:
                break

        # ensure capture is released when loop ends
        try:
            if self._cap:
                self._cap.release()
        except Exception:
            pass

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Return the latest frame (copy semantics applied by caller).

        Returns (ok, frame) where `ok` is False when no frame is available.
        """
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def stop(self) -> None:
        """Stop reader thread and release resources."""
        self._stopped = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass

    def is_opened(self) -> bool:
        """Return True if underlying capture is opened."""
        return bool(self._cap and self._cap.isOpened())


def example_main():
    """Small CLI example that displays the stream using OpenCV GUI."""
    stream = OpenCVVideoStream("rtsp://192.168.1.1:7070/webcam")
    if not stream.start():
        print("Failed to open stream")
        return

    try:
        while True:
            ok, frame = stream.read()
            if ok and frame is not None:
                cv2.imshow("TEKY OpenCV Stream", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                break
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    example_main()
