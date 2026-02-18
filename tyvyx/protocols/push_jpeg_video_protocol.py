"""Push-based JPEG video protocol adapter (0x93 protocol).

Used by many cheap Chinese WiFi UAV drones (including K417 / Drone-XXXXXX).
Reverse-engineered via https://github.com/FahrulRPutra/reversing-wifi-uav
and https://github.com/JadanPoll/DroneUAVHack.

Protocol summary:
  - Send START_STREAM (ef 00 04 00) to drone port 8800
  - Drone pushes JPEG fragments continuously from its port 1234
  - Packets: 0x93 0x01 magic, LE length at bytes 2-3, max 1080 bytes
  - Frame boundary: byte 32 = 0x00 marks first packet of new frame
  - Payload: byte 56 onwards = raw JPEG scan data (no SOI/DQT/DHT/SOF/SOS)
  - Client must prepend full JPEG headers (including Huffman tables) + append EOI
"""

import ctypes
import queue
import socket
import sys
import threading
import time
from typing import List, Optional

from tyvyx.models.video_frame import VideoFrame
from tyvyx.utils.wifi_uav_packets import START_STREAM
from tyvyx.utils.wifi_uav_jpeg import generate_jpeg_headers_full, EOI


# Protocol constants
MAGIC = b"\x93\x01"
HEADER_SIZE = 56          # Bytes 0-55 are header, 56+ is payload
FRAME_MARKER_OFFSET = 32  # Byte 32: 0x00 = first packet of new frame
MAX_PACKET_SIZE = 1080
KEEPALIVE_INTERVAL = 1.0  # Re-send START_STREAM every N seconds


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

        # Frame assembly
        self._frame_buf = bytearray()
        self._frame_count = 0
        self._frame_ready = False

        # Threading
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._keepalive_thread: Optional[threading.Thread] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=4)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []

        # Stats
        self.frames_ok = 0
        self.frames_dropped = 0
        self.packets_rx = 0
        self.packets_rejected = 0

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
        return self._running and self._rx_thread is not None and self._rx_thread.is_alive()

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        with self._pkt_lock:
            pkts = self._pkt_buffer
            self._pkt_buffer = []
            return pkts

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

    def _keepalive_loop(self) -> None:
        """Periodically re-send START_STREAM to keep the video flowing."""
        while self._running:
            time.sleep(KEEPALIVE_INTERVAL)
            if self._running:
                self._send_start()

    def _rx_loop(self) -> None:
        """Receive packets, filter by magic, assemble JPEG frames."""
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

            # Diagnostic buffer
            with self._pkt_lock:
                self._pkt_buffer.append(data)

            # Log first few packets
            if self.packets_rx <= 5:
                head = data[:32].hex(" ") if data else "(empty)"
                self._dbg(f"[push-jpeg] RX #{self.packets_rx}: {len(data)} bytes from {addr}  head={head}")

            # Filter: must start with 0x93 0x01
            if len(data) < HEADER_SIZE or data[0:2] != MAGIC:
                self.packets_rejected += 1
                if self.packets_rejected <= 3:
                    head = data[:16].hex(" ") if data else "(empty)"
                    self._dbg(f"[push-jpeg] Rejected: {len(data)} bytes  head={head}")
                continue

            # Check frame boundary
            is_new_frame = (data[FRAME_MARKER_OFFSET] == 0x00)

            if is_new_frame and self._frame_buf:
                # Previous frame is complete — assemble and emit
                self._emit_frame()

            # Append payload (bytes after header)
            payload = data[HEADER_SIZE:]
            if payload:
                self._frame_buf.extend(payload)

        self._dbg(f"[push-jpeg] RX thread stopped, total rx={self.packets_rx}")

    def _emit_frame(self) -> None:
        """Assemble the accumulated payload into a JPEG frame and queue it."""
        if not self._frame_buf:
            return

        self._frame_count += 1
        jpeg = self._jpeg_header + bytes(self._frame_buf) + EOI

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
                      f"ok={self.frames_ok}")

        self._frame_buf = bytearray()
