"""OpenCV video stream helper packaged under `teky`."""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np
import subprocess
import shutil
from pathlib import Path


class OpenCVVideoStream:
    """Threaded OpenCV RTSP stream helper.

    Args:
        source: RTSP URL or integer camera index.
        buffer_size: value for `CAP_PROP_BUFFERSIZE` (1 is low-latency).
        name: optional name used for debug prints.
    """

    def __init__(self, source: str | int, buffer_size: int = 1, name: str = "stream", prefer_tcp: bool = False):
        self.source = source
        self.buffer_size = buffer_size
        self.name = name
        self.prefer_tcp = prefer_tcp

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stopped = True
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        # FFmpeg fallback process handle
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._using_ffmpeg = False
        self._ffmpeg_width = 0
        self._ffmpeg_height = 0

    def start(self, timeout: float = 5.0) -> bool:
        """Open the capture and start reader thread.

        Returns True if capture opened successfully within `timeout` seconds.
        """
        try:
            # Try to open with FFMPEG backend first (better RTSP support)
            try:
                self._cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            except Exception:
                # Fallback to default/open with no explicit backend
                self._cap = cv2.VideoCapture(self.source)

            # If user requested TCP transport and GStreamer is available, try a TCP pipeline
            if (self.prefer_tcp and (isinstance(self.source, str) and hasattr(cv2, 'CAP_GSTREAMER')) and not self._cap.isOpened()):
                try:
                    # GStreamer pipeline attempts to force RTSP over TCP and use appsink
                    pipeline = (
                        f"rtspsrc location={self.source} protocols=tcp ! rtph264depay ! avdec_h264 ! videoconvert ! appsink sync=false"
                    )
                    self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                except Exception:
                    pass
            # Attempt to set low buffer for lower latency
            try:
                # Set a slightly larger buffer by default to help with jitter/packet loss.
                # Keep user-specified buffer_size if provided, but ensure minimum of 1.
                buf = max(1, int(self.buffer_size))
                # Try setting the property; some backends ignore this.
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, buf)
            except Exception:
                pass

            start = time.time()
            while time.time() - start < timeout:
                if self._cap.isOpened():
                    break
                time.sleep(0.1)

            if not self._cap.isOpened():
                # Attempt FFmpeg subprocess fallback when OpenCV capture fails
                try:
                    ff_ok = self._start_ffmpeg_fallback(timeout=timeout)
                    if not ff_ok:
                        return False
                    # ffmpeg started successfully
                    return True
                except Exception:
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
            # If using ffmpeg fallback, read from process stdout
            if self._using_ffmpeg and self._ffmpeg_proc:
                self._ffmpeg_read_loop()
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

        # Release OpenCV capture if present
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass

        # Terminate ffmpeg fallback if running
        if self._using_ffmpeg and self._ffmpeg_proc:
            try:
                self._ffmpeg_proc.kill()
            except Exception:
                pass
            finally:
                self._ffmpeg_proc = None
                self._using_ffmpeg = False

    def is_opened(self) -> bool:
        """Return True if underlying capture is opened."""
        if self._cap and self._cap.isOpened():
            return True
        if self._using_ffmpeg and self._ffmpeg_proc:
            return True
        return False

    def _probe_stream_size(self, url: str, timeout: float = 3.0) -> tuple[int, int] | None:
        """Use ffprobe to get width and height of the video stream."""
        if not shutil.which('ffprobe'):
            return None
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', url]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = (p.stdout or '').strip()
            if not out:
                return None
            parts = out.split(',')
            if len(parts) >= 2:
                w = int(parts[0]); h = int(parts[1])
                return (w, h)
        except Exception:
            return None
        return None

    def _start_ffmpeg_fallback(self, timeout: float = 5.0) -> bool:
        """Start ffmpeg subprocess to read raw BGR frames over RTSP/TCP.

        Returns True on success.
        """
        if not isinstance(self.source, str):
            return False
        if not shutil.which('ffmpeg'):
            return False

        # Probe for width/height
        wh = self._probe_stream_size(self.source, timeout=3.0)
        if not wh:
            return False
        w, h = wh
        self._ffmpeg_width = w
        self._ffmpeg_height = h

        cmd = [
            'ffmpeg', '-rtsp_transport', 'tcp', '-i', self.source,
            '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'
        ]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            return False

        self._ffmpeg_proc = proc
        self._using_ffmpeg = True

        # start a dedicated thread to read frames
        t = threading.Thread(target=self._ffmpeg_read_loop, daemon=True)
        t.start()
        # give a short time to ensure frames arrive
        start = time.time()
        while time.time() - start < timeout:
            if self._frame is not None:
                return True
            time.sleep(0.1)
        # timeout
        return False

    def _ffmpeg_read_loop(self):
        """Read raw frames from ffmpeg stdout and populate self._frame."""
        proc = self._ffmpeg_proc
        if not proc or not proc.stdout:
            return
        w = int(self._ffmpeg_width); h = int(self._ffmpeg_height)
        frame_size = w * h * 3
        try:
            while not self._stopped and proc.poll() is None:
                data = proc.stdout.read(frame_size)
                if not data or len(data) < frame_size:
                    time.sleep(0.02)
                    continue
                arr = np.frombuffer(data, dtype=np.uint8)
                try:
                    frame = arr.reshape((h, w, 3))
                except Exception:
                    continue
                with self._lock:
                    self._frame = frame
        except Exception:
            pass
        finally:
            try:
                if proc:
                    proc.stdout.close()
            except Exception:
                pass


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
