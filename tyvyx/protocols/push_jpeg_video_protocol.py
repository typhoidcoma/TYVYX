"""Push-based JPEG video protocol adapter (0x93 protocol).

Used by BL608 / BL-UAVSDK WiFi UAV drones (K417 / Drone-XXXXXX).
Reverse-engineered from YN Fly APK (libuav_lib.so) + live packet capture.

Protocol summary:
  - Send START_STREAM (ef 00 04 00) to drone port 8800
  - Drone pushes JPEG fragments continuously from its source port 1234
  - Packets: 0x93 0x01 magic, 56-byte header, payload at byte 56+
  - Header fields (confirmed via live capture):
      bytes 2-3:   LE uint16 packet_length (total packet size)
      bytes 32-33: LE uint16 fragment_id (0-based index within frame)
      bytes 36-37: LE uint16 fragment_total (total fragments in frame)
      bytes 44-45: LE uint16 width (640)
      bytes 46-47: LE uint16 height (360)
  - Frame complete when all fragment_total fragments received
  - Payload: raw JPEG scan data (no SOI/DQT/DHT/SOF/SOS)
  - Client must prepend full JPEG headers (including Huffman tables) + append EOI
"""

import ctypes
import queue
import socket
import struct
import sys
import threading
import time
from typing import Dict, List, Optional

from tyvyx.models.video_frame import VideoFrame
from tyvyx.utils.wifi_uav_packets import START_STREAM
from tyvyx.utils.wifi_uav_jpeg import generate_jpeg_headers_full, EOI


# Protocol constants
MAGIC = b"\x93\x01"
HEADER_SIZE = 56          # Bytes 0-55 are header, 56+ is payload
MAX_PACKET_SIZE = 1080
KEEPALIVE_INTERVAL = 0.1  # Re-send START_STREAM (100ms / 10 Hz — sweet spot for half-duplex WiFi)

# Header field offsets (confirmed via live packet capture + BL-UAVSDK RE)
OFF_PKT_LEN = 2           # LE uint16: total packet size
OFF_FRAG_ID = 32          # LE uint16: fragment index (0-based)
OFF_FRAG_TOTAL = 36       # LE uint16: total fragments in frame
OFF_WIDTH = 44            # LE uint16: frame width (e.g. 640)
OFF_HEIGHT = 46           # LE uint16: frame height (e.g. 360)


class PushJpegVideoProtocolAdapter:
    """Transport + JPEG reassembly for push-based WiFi UAV drones.

    Unlike the pull-based WifiUavVideoProtocolAdapter, this adapter:
      - Does NOT send REQUEST_A / REQUEST_B per frame
      - Receives a continuous push stream after sending START_STREAM
      - Uses a different packet header format (0x93 magic, 56-byte header)
      - Still outputs JPEG frames (same downstream pipeline)
    """

    DEFAULT_DRONE_IP = "192.168.169.1"
    DEFAULT_PORT = 8800

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        control_port: int = DEFAULT_PORT,
        video_port: int = DEFAULT_PORT,
        jpeg_width: int = 640,
        jpeg_height: int = 360,
        components: int = 3,
        bind_ip: str = "",
        debug: bool = False,
        **kwargs,
    ):
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.bind_ip = bind_ip

        self._debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)

        # Pre-built JPEG header (SOI + DQT + DHT + SOF0 + SOS)
        self._jpeg_header = generate_jpeg_headers_full(jpeg_width, jpeg_height, components)
        self._dbg(f"[push-jpeg] JPEG header: {len(self._jpeg_header)} bytes")

        # Socket
        self._sock = self._create_socket()

        # Frame assembly — fragment-based with immediate completion
        self._fragments: Dict[int, bytes] = {}  # frag_id -> payload
        self._frag_total = 0                     # expected fragment count
        self._frame_count = 0

        # Threading
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._keepalive_thread: Optional[threading.Thread] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=4)

        # Stats
        self.frames_ok = 0
        self.frames_dropped = 0
        self.packets_rx = 0
        self.packets_rejected = 0
        self._last_frame_time = 0.0
        self._last_rx_time = 0.0    # Last packet received (any type)
        self._stall_timeout = 30.0  # Stop adapter after 30s with no frames
        self._stats_time = time.time()
        self._stats_pkts = 0
        self._stats_frames = 0

        self._dbg(f"[push-jpeg] Adapter created  drone={drone_ip}:{control_port}  "
                  f"bind={bind_ip or '*'}  sock={self._sock.getsockname()}")

    # ── lifecycle (called by VideoReceiverService) ──

    def start(self) -> None:
        if self._running:
            return

        self._running = True

        # Send initial START_STREAM
        self._send_start()

        # RX thread — receive and assemble frames
        self._rx_thread = threading.Thread(
            target=self._rx_loop, daemon=True, name="PushJpegRx",
        )
        self._rx_thread.start()

        # Keepalive thread — re-send START_STREAM periodically
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, daemon=True, name="PushJpegKeepalive",
        )
        self._keepalive_thread.start()

        self._dbg("[push-jpeg] Started")

    def stop(self) -> None:
        self._dbg("[push-jpeg] Stopping...")
        self._running = False

        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=1.5)

        try:
            self._sock.close()
        except Exception:
            pass

        self._dbg(f"[push-jpeg] Stopped  ok={self.frames_ok}  dropped={self.frames_dropped}  "
                  f"rx={self.packets_rx}  rejected={self.packets_rejected}")

    def is_running(self) -> bool:
        if not self._running or self._rx_thread is None or not self._rx_thread.is_alive():
            return False
        # Stop if no frames received for stall_timeout seconds
        if self._last_frame_time > 0 and (time.time() - self._last_frame_time) > self._stall_timeout:
            self._dbg(f"[push-jpeg] Stall detected ({self._stall_timeout}s), stopping for reconnect")
            self._running = False
            return False
        return True

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        return []

    # ── shared socket (for RC adapter to multiplex on the same socket) ──

    def get_shared_socket(self) -> socket.socket:
        return self._sock

    # ── keepalive (not needed by VideoReceiverService but harmless) ──

    def start_keepalive(self, interval: float = 1.0) -> None:
        pass

    def stop_keepalive(self) -> None:
        pass

    # ── internal ──

    def _create_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if sys.platform == "win32":
            SIO_UDP_CONNRESET = 0x9800000C
            ret = ctypes.c_ulong(0)
            false = b"\x00\x00\x00\x00"
            ctypes.windll.ws2_32.WSAIoctl(
                sock.fileno(), SIO_UDP_CONNRESET,
                false, len(false), None, 0,
                ctypes.byref(ret), None, None,
            )

        sock.bind((self.bind_ip or "", 0))
        sock.settimeout(1.0)
        return sock

    def _send_start(self) -> None:
        try:
            self._sock.sendto(START_STREAM, (self.drone_ip, self.control_port))
            self._dbg("[push-jpeg] START_STREAM sent")
        except OSError as e:
            self._dbg(f"[push-jpeg] Send error: {e}")

    def _send_start_fast(self) -> None:
        """Send START_STREAM without logging (called per-frame in RX hot path)."""
        try:
            self._sock.sendto(START_STREAM, (self.drone_ip, self.control_port))
        except OSError:
            pass

    def _keepalive_loop(self) -> None:
        """Continuously pump START_STREAM to drive the video stream.

        The drone outputs video data proportionally to how frequently
        it receives START_STREAM — more pumping = faster video.
        """
        while self._running:
            time.sleep(KEEPALIVE_INTERVAL)
            if self._running:
                self._send_start_fast()

    def _rx_loop(self) -> None:
        """Receive packets, filter by magic, assemble JPEG frames.

        Uses fragment_id (bytes 32-33) and fragment_total (bytes 36-37)
        for proper reassembly with immediate completion detection.
        """
        sock = self._sock
        self._dbg(f"[push-jpeg] RX thread started, socket={sock.getsockname()}")

        while self._running:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
            except OSError:
                if self._running:
                    self._dbg("[push-jpeg] Socket error in RX loop")
                break

            self.packets_rx += 1
            self._stats_pkts += 1
            self._last_rx_time = time.time()

            # Periodic stats every 5 seconds
            now = time.time()
            if now - self._stats_time >= 5.0:
                elapsed = now - self._stats_time
                pps = self._stats_pkts / elapsed
                fps = self._stats_frames / elapsed
                nfrags = len(self._fragments)
                print(f"[push-jpeg] STATS: {pps:.1f} pkt/s | {fps:.1f} fps | "
                      f"frags={nfrags}/{self._frag_total} | rejected={self.packets_rejected}")
                self._stats_pkts = 0
                self._stats_frames = 0
                self._stats_time = now

            # Log first few packets
            if self.packets_rx <= 5:
                head = data[:40].hex(" ") if data else "(empty)"
                self._dbg(f"[push-jpeg] RX #{self.packets_rx}: {len(data)} bytes from {addr}  head={head}")

            # Filter: must start with 0x93 0x01 and be at least header-sized
            if len(data) < HEADER_SIZE or data[0:2] != MAGIC:
                self.packets_rejected += 1
                if self.packets_rejected <= 3:
                    head = data[:16].hex(" ") if data else "(empty)"
                    self._dbg(f"[push-jpeg] Rejected: {len(data)} bytes  head={head}")
                continue

            # Parse header fields
            frag_id = struct.unpack_from("<H", data, OFF_FRAG_ID)[0]
            frag_total = struct.unpack_from("<H", data, OFF_FRAG_TOTAL)[0]

            # New frame detected: fragment_id == 0 resets assembly
            if frag_id == 0:
                if self._fragments:
                    # Previous frame incomplete — drop it
                    self.frames_dropped += 1
                self._fragments.clear()
                self._frag_total = frag_total

            # Store fragment payload
            payload = data[HEADER_SIZE:]
            if payload:
                self._fragments[frag_id] = payload

            # Frame complete? Emit immediately (don't wait for next frame's frag 0)
            if self._frag_total > 0 and len(self._fragments) == self._frag_total:
                self._emit_frame()
                self._send_start_fast()

        self._dbg(f"[push-jpeg] RX thread stopped, total rx={self.packets_rx}")

    def _emit_frame(self) -> None:
        """Assemble fragments into a JPEG frame and queue it."""
        if not self._fragments:
            return

        self._last_frame_time = time.time()
        self._frame_count += 1
        self._stats_frames += 1

        # Reassemble in fragment_id order
        ordered = [self._fragments[i] for i in sorted(self._fragments)]
        jpeg = self._jpeg_header + b"".join(ordered) + EOI

        frame = VideoFrame(frame_id=self._frame_count, data=jpeg)
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
            self._dbg(f"[push-jpeg] Frame {self._frame_count}: {len(jpeg)} bytes  "
                      f"({len(self._fragments)}/{self._frag_total} frags)  ok={self.frames_ok}")

        self._fragments.clear()
