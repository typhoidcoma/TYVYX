"""TCP video protocol adapter for E88Pro/lxPro drones (TCP 7070).

Some E88Pro-family drones (e.g. Mten/FLOW-UFO) serve video over TCP
instead of UDP.  This adapter connects to TCP 7070, reads JPEG frames
delimited by SOI (FF D8) / EOI (FF D9), and queues them for the
standard video pipeline.

Duck-typed adapter — same interface as PushJpegVideoProtocolAdapter:
  start() / stop() / is_running() / get_frame(timeout) / get_packets()
  start_keepalive() / stop_keepalive()  (no-ops)

Used by VideoReceiverService which creates the adapter via
  adapter_cls(**adapter_args) and calls .start(), .get_frame(), etc.
"""

import queue
import socket
import sys
import threading
import time
from typing import List, Optional

from tyvyx.models.video_frame import VideoFrame


# JPEG markers
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


class TcpVideoProtocolAdapter:
    """TCP MJPEG video adapter for E88Pro/lxPro drones.

    Connects to TCP video_port (default 7070), reads the stream,
    extracts JPEG frames (SOI/EOI delimited), and queues VideoFrames.
    Auto-reconnects on connection loss.
    """

    def __init__(
        self,
        drone_ip,           # type: str
        video_port=7070,    # type: int
        control_port=7099,  # type: int
        bind_ip="",         # type: str
        debug=False,        # type: bool
        **kwargs
    ):
        self.drone_ip = drone_ip
        self.video_port = video_port
        self.control_port = control_port
        self.bind_ip = bind_ip

        self._debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)

        # Threading
        self._running = False
        self._rx_thread = None          # type: Optional[threading.Thread]
        self._frame_q = queue.Queue(maxsize=4)  # type: queue.Queue

        # Stats
        self._frame_count = 0
        self.frames_ok = 0
        self.frames_dropped = 0
        self.bytes_rx = 0
        self._last_frame_time = 0.0
        self._stall_timeout = 30.0     # Stop adapter after 30s without frames
        self._stats_time = time.time()
        self._stats_frames = 0
        self._stats_bytes = 0

        self._dbg("[tcp-video] Adapter created  drone=%s:%d  bind=%s",
                  drone_ip, video_port, bind_ip or "*")

    # ── lifecycle (called by VideoReceiverService) ──

    def start(self):
        # type: () -> None
        if self._running:
            return
        self._running = True
        self._rx_thread = threading.Thread(
            target=self._rx_loop, daemon=True, name="TcpVideoRx",
        )
        self._rx_thread.start()
        print("[tcp-video] Started (drone=%s:%d)" % (self.drone_ip, self.video_port))

    def stop(self):
        # type: () -> None
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=3.0)
        print("[tcp-video] Stopped  ok=%d  dropped=%d  bytes=%d" %
              (self.frames_ok, self.frames_dropped, self.bytes_rx))

    def is_running(self):
        # type: () -> bool
        if not self._running or self._rx_thread is None or not self._rx_thread.is_alive():
            return False
        # Stall detection
        if self._last_frame_time > 0 and (time.time() - self._last_frame_time) > self._stall_timeout:
            print("[tcp-video] Stall detected (%.0fs), stopping for reconnect" % self._stall_timeout)
            self._running = False
            return False
        return True

    def get_frame(self, timeout=1.0):
        # type: (float) -> Optional[VideoFrame]
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self):
        # type: () -> List[bytes]
        return []

    # ── keepalive stubs (not needed for TCP) ──

    def start_keepalive(self, interval=1.0):
        # type: (float) -> None
        pass

    def stop_keepalive(self):
        # type: () -> None
        pass

    # ── internal ──

    def _send_video_init(self):
        # type: () -> None
        """Send E88Pro init commands on UDP to wake up video streaming."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            if self.bind_ip:
                sock.bind((self.bind_ip, 0))

            # E88Pro init sequence
            commands = [
                bytes([0x08, 0x01]),  # CMD_START_VIDEO / init
                bytes([0x06, 0x01]),  # CMD_CAMERA_1 (front)
            ]
            for cmd in commands:
                sock.sendto(cmd, (self.drone_ip, self.control_port))
                time.sleep(0.1)

            sock.close()
            self._dbg("[tcp-video] Sent E88Pro init commands to %s:%d",
                      self.drone_ip, self.control_port)
        except OSError as e:
            print("[tcp-video] Init send error: %s" % e)

    def _connect_tcp(self):
        # type: () -> Optional[socket.socket]
        """Connect to the TCP video port. Returns socket or None."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        if self.bind_ip:
            sock.bind((self.bind_ip, 0))
        try:
            sock.connect((self.drone_ip, self.video_port))
            sock.settimeout(3.0)
            print("[tcp-video] Connected to %s:%d (local=%s)" %
                  (self.drone_ip, self.video_port, sock.getsockname()))
            return sock
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print("[tcp-video] TCP connect failed: %s" % e)
            try:
                sock.close()
            except Exception:
                pass
            return None

    def _rx_loop(self):
        # type: () -> None
        """Main receive loop: connect, read stream, extract frames, reconnect."""
        while self._running:
            # Send init commands before each connection attempt
            self._send_video_init()
            time.sleep(0.3)

            sock = self._connect_tcp()
            if sock is None:
                if self._running:
                    print("[tcp-video] Retrying in 2s...")
                    time.sleep(2.0)
                continue

            try:
                self._read_stream(sock)
            except Exception as e:
                if self._running:
                    print("[tcp-video] Stream error: %s" % e)
            finally:
                try:
                    sock.close()
                except Exception:
                    pass

            if self._running:
                print("[tcp-video] Connection lost, reconnecting in 1s...")
                time.sleep(1.0)

        self._dbg("[tcp-video] RX thread stopped")

    def _read_stream(self, sock):
        # type: (socket.socket) -> None
        """Read TCP stream, buffer data, extract JPEG frames by SOI/EOI."""
        buf = bytearray()
        in_frame = False
        frame_start = 0

        while self._running:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                # Periodic stats during timeout
                self._log_stats()
                continue
            except (ConnectionResetError, OSError):
                break

            if not data:
                break  # Connection closed

            self.bytes_rx += len(data)
            self._stats_bytes += len(data)
            buf.extend(data)

            # Scan buffer for JPEG frames
            while len(buf) >= 4:
                if not in_frame:
                    # Look for SOI (FF D8)
                    soi_idx = buf.find(JPEG_SOI)
                    if soi_idx < 0:
                        # Keep last byte (could be start of FF D8)
                        if len(buf) > 1:
                            buf = buf[-1:]
                        break
                    # Discard bytes before SOI
                    if soi_idx > 0:
                        buf = buf[soi_idx:]
                    in_frame = True
                    frame_start = 0

                # In frame — look for EOI (FF D9)
                # Start searching after SOI (at least 2 bytes in)
                search_start = max(frame_start + 2, 2)
                eoi_idx = buf.find(JPEG_EOI, search_start)

                if eoi_idx < 0:
                    # No EOI yet, need more data
                    # Safety: if buffer grows too large without EOI, discard
                    if len(buf) > 2 * 1024 * 1024:  # 2 MB
                        print("[tcp-video] Frame too large (>2MB), discarding")
                        buf.clear()
                        in_frame = False
                        self.frames_dropped += 1
                    break

                # Found complete frame: SOI...EOI
                frame_end = eoi_idx + 2  # include EOI marker
                jpeg_data = bytes(buf[:frame_end])
                buf = buf[frame_end:]
                in_frame = False

                self._emit_frame(jpeg_data)

            self._log_stats()

    def _emit_frame(self, jpeg_data):
        # type: (bytes) -> None
        """Queue a complete JPEG frame."""
        self._last_frame_time = time.time()
        self._frame_count += 1
        self._stats_frames += 1

        frame = VideoFrame(frame_id=self._frame_count, data=jpeg_data)
        self.frames_ok += 1

        try:
            self._frame_q.put(frame, timeout=0.1)
        except queue.Full:
            # Drop oldest, put new
            try:
                self._frame_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_q.put_nowait(frame)
            except queue.Full:
                self.frames_dropped += 1

        if self.frames_ok <= 3 or self.frames_ok % 100 == 0:
            print("[tcp-video] Frame %d: %d bytes  ok=%d" %
                  (self._frame_count, len(jpeg_data), self.frames_ok))

    def _log_stats(self):
        # type: () -> None
        """Print stats every 5 seconds."""
        now = time.time()
        if now - self._stats_time >= 5.0:
            elapsed = now - self._stats_time
            fps = self._stats_frames / elapsed if elapsed > 0 else 0
            kbps = self._stats_bytes / elapsed / 1024 if elapsed > 0 else 0
            print("[tcp-video] STATS: %.1f fps | %.1f KB/s | ok=%d dropped=%d" %
                  (fps, kbps, self.frames_ok, self.frames_dropped))
            self._stats_frames = 0
            self._stats_bytes = 0
            self._stats_time = now
