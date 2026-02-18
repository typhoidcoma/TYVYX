"""WiFi UAV video protocol adapter.

Protocol adapter for the inexpensive "WiFi UAV" drone family (includes K417).

Key differences from S2x/E88Pro:
  - Single duplex UDP socket for both control AND video (port 8800)
  - Pull-based: drone stops streaming unless it receives REQUEST_A + REQUEST_B
    for every JPEG frame
  - 56-byte proprietary header on each packet; JPEG SOI/DQT headers are stripped
    and must be reconstructed on the client

Ported from turbodrone, adapted for TEKY architecture with bind_ip support.
"""

import sys
import socket
import queue
import threading
import time
from typing import Dict, List, Optional

from tyvyx.models.video_frame import VideoFrame
from tyvyx.protocols.base_video_protocol import BaseVideoProtocolAdapter
from tyvyx.utils.wifi_uav_packets import START_STREAM, REQUEST_A, REQUEST_B
from tyvyx.utils.wifi_uav_jpeg import generate_jpeg_headers_full, EOI


class WifiUavVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Transport + JPEG reassembly for WiFi UAV drones (K417 etc.)."""

    DEFAULT_DRONE_IP = "192.168.169.1"
    DEFAULT_PORT = 8800

    REQUEST_A_OFFSETS = (12, 13)
    REQUEST_B_OFFSETS = (12, 13, 88, 89, 107, 108)

    FRAME_TIMEOUT = 0.08   # 80 ms
    MAX_RETRIES = 3
    WATCHDOG_SLEEP = 0.05  # 50 ms

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
        super().__init__(drone_ip, control_port, video_port, bind_ip=bind_ip)

        self._debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)
        self._sock_lock = threading.Lock()
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []

        self._sock = self._create_duplex_socket()

        # Pre-built JPEG header (SOI + quant tables + SOF0 + SOS)
        self._jpeg_header = generate_jpeg_headers_full(jpeg_width, jpeg_height, components)

        # Frame assembly state
        self._current_fid: int = 1
        self._fragments: Dict[int, bytes] = {}
        self._last_req_ts = time.time()
        self._last_rx_ts = time.time()

        # Stats
        self.frames_ok = 0
        self.frames_dropped = 0
        self._retry_cnt = 0
        self._had_retry = False
        self.retry_attempts = 0
        self.retry_successes = 0

        # Kick off the stream and request frame 0 (drone responds with frame 1)
        self.send_start_command()
        self._send_frame_request(0)

        # Warmup: resend until first frame arrives
        self._first_frame = True
        self._running = True
        self._warmup_thread = threading.Thread(
            target=self._warmup_loop, daemon=True, name="WifiUavWarmup"
        )
        self._warmup_thread.start()

        # Watchdog for per-frame timeouts
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="WifiUavWatchdog"
        )
        self._watchdog.start()

        self._dbg(f"[wifi-uav] Adapter ready  drone={drone_ip}:{control_port}  "
                  f"bind={bind_ip or '*'}  sock={self._sock.getsockname()}")

    # ── disable keep-alive (not needed for wifi_uav) ────────── #

    def start_keepalive(self, interval: float = 1.0) -> None:
        return

    def stop_keepalive(self) -> None:
        return

    # ── BaseVideoProtocolAdapter hooks ────────── #

    def create_receiver_socket(self) -> socket.socket:
        return self._sock

    def send_start_command(self) -> None:
        self._sock.sendto(START_STREAM, (self.drone_ip, self.control_port))
        self._dbg("[wifi-uav] START_STREAM sent")

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        """Collect JPEG fragments belonging to the current frame.

        Packet layout:
          byte  1     : must be 0x01 for video
          bytes 16-17 : little-endian frame counter
          bytes 32-33 : little-endian fragment counter
          byte  2     : 0x38 = continuation, != 0x38 = last fragment
          bytes 56+   : JPEG payload (no SOI/DQT headers)
        """
        if len(payload) < 56 or payload[1] != 0x01:
            # Log rejected packets for diagnostics
            head = payload[:20].hex(" ") if payload else "(empty)"
            self._dbg(f"[wifi-uav] RX non-video: {len(payload)} bytes  head={head}")
            return None

        self._last_rx_ts = time.time()
        self._retry_cnt = 0

        frame_id = int.from_bytes(payload[16:18], "little")

        # Re-synchronise if the drone skipped ahead
        if frame_id != self._current_fid:
            self.frames_dropped += 1
            self._dbg(f"[wifi-uav] skip: expected {self._current_fid:04x} got {frame_id:04x}")
            self._fragments.clear()
            self._current_fid = frame_id

        frag_id = int.from_bytes(payload[32:34], "little")
        if frag_id not in self._fragments:
            self._fragments[frag_id] = payload[56:]

        # Not the last fragment? Wait for more.
        if payload[2] == 0x38:
            return None

        # Last fragment received — assemble JPEG
        ordered = [self._fragments[i] for i in sorted(self._fragments)]
        jpeg = self._jpeg_header + b"".join(ordered) + EOI
        frame = VideoFrame(frame_id=frame_id, data=jpeg)

        self.frames_ok += 1

        if self._had_retry:
            self.retry_successes += 1
            self._had_retry = False

        self._dbg(f"[wifi-uav] frame {frame_id:04x} ({len(self._fragments)} frags, "
                  f"{len(jpeg)} bytes)  ok={self.frames_ok}  drop={self.frames_dropped}")

        # Prepare next frame
        self._fragments.clear()
        self._send_frame_request(frame_id)
        self._current_fid = (frame_id + 1) & 0xFFFF
        self._last_rx_ts = self._last_req_ts = time.time()

        # Mark warmup complete
        if self._first_frame:
            self._first_frame = False

        return frame

    # ── lifecycle (expected by VideoReceiverService) ────────── #

    def start(self) -> None:
        if hasattr(self, "_rx_thread") and self._rx_thread and self._rx_thread.is_alive():
            return

        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        with self._pkt_lock:
            self._pkt_buffer = []

        def _rx_loop() -> None:
            sock = self._sock
            self._dbg(f"[wifi-uav] RX thread started, socket={sock.getsockname()}")
            rx_count = 0
            while self._running:
                try:
                    payload = self.recv_from_socket(sock)
                    if not payload:
                        continue
                    rx_count += 1
                    if rx_count <= 5:
                        head = payload[:20].hex(" ") if payload else "(empty)"
                        self._dbg(f"[wifi-uav] RX #{rx_count}: {len(payload)} bytes  head={head}")
                    with self._pkt_lock:
                        if len(self._pkt_buffer) < 100:
                            self._pkt_buffer.append(payload)
                    frame = self.handle_payload(payload)
                    if frame is not None:
                        try:
                            self._frame_q.put(frame, timeout=0.2)
                        except queue.Full:
                            pass
                except OSError:
                    break
                except Exception as e:
                    self._dbg(f"[wifi-uav] rx error: {e}")
                    continue
            self._dbg(f"[wifi-uav] RX thread stopped, total packets={rx_count}")

        self._rx_thread = threading.Thread(
            target=_rx_loop, daemon=True, name="WifiUavVideoRx"
        )
        self._rx_thread.start()

    def is_running(self) -> bool:
        if not self._running or not getattr(self, "_rx_thread", None) or not self._rx_thread.is_alive():
            return False
        # Stall detection: if no packets received for 5s, trigger reconnect
        if self._last_rx_ts > 0 and (time.time() - self._last_rx_ts) > 5.0:
            self._dbg("[wifi-uav] Stall detected (5s), stopping for reconnect")
            self._running = False
            return False
        return True

    def get_frame(self, timeout: float = 1.0) -> Optional[VideoFrame]:
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self) -> List[bytes]:
        with self._pkt_lock:
            packets = self._pkt_buffer
            self._pkt_buffer = []
            return packets

    def stop(self) -> None:
        self._dbg("[wifi-uav] Stopping protocol adapter...")
        self._running = False
        self._first_frame = False
        try:
            if hasattr(self, "_watchdog") and self._watchdog.is_alive():
                self._watchdog.join(timeout=0.5)
            if hasattr(self, "_rx_thread") and self._rx_thread and self._rx_thread.is_alive():
                self._rx_thread.join(timeout=0.5)
            self._sock.close()
        except Exception as e:
            self._dbg(f"[wifi-uav] Ignoring error during shutdown: {e}")

        self._dbg(f"[wifi-uav] stats: ok={self.frames_ok}  dropped={self.frames_dropped}  "
                  f"retry_att={self.retry_attempts}  retry_suc={self.retry_successes}")

    # ── shared socket access (for RC adapter) ────────── #

    def get_shared_socket(self) -> socket.socket:
        """Return the duplex socket so the RC adapter can share it."""
        return self._sock

    # ── internal helpers ────────── #

    def _create_duplex_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if sys.platform == "win32":
            import ctypes
            SIO_UDP_CONNRESET = 0x9800000C
            ret = ctypes.c_ulong(0)
            false = b"\x00\x00\x00\x00"
            ctypes.windll.ws2_32.WSAIoctl(
                sock.fileno(), SIO_UDP_CONNRESET,
                false, len(false), None, 0,
                ctypes.byref(ret), None, None,
            )

        bind_addr = self.bind_ip or ""
        sock.bind((bind_addr, 0))  # OS picks a free port
        sock.settimeout(1.0)
        return sock

    def _send_frame_request(self, frame_id: int) -> None:
        lo, hi = frame_id & 0xFF, (frame_id >> 8) & 0xFF

        rqst_a = bytearray(REQUEST_A)
        rqst_a[12], rqst_a[13] = lo, hi

        rqst_b = bytearray(REQUEST_B)
        for base in (12, 88, 107):
            rqst_b[base] = lo
            rqst_b[base + 1] = hi

        self._sock.sendto(rqst_a, (self.drone_ip, self.control_port))
        self._sock.sendto(rqst_b, (self.drone_ip, self.control_port))
        self._last_req_ts = time.time()
        self._dbg(f"[wifi-uav] REQ frame {frame_id:04x}")

    def _warmup_loop(self) -> None:
        """Resend START_STREAM + frame request until the first frame arrives."""
        while getattr(self, "_first_frame", False) and self._running:
            try:
                self.send_start_command()
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
            except Exception:
                pass
            time.sleep(0.2)

    def _watchdog_loop(self) -> None:
        """Retry or drop frames that take too long to assemble."""
        while self._running:
            time.sleep(self.WATCHDOG_SLEEP)
            now = time.time()

            if now - self._last_req_ts < self.FRAME_TIMEOUT:
                continue

            if self._retry_cnt < self.MAX_RETRIES:
                self._dbg(f"[wifi-uav] timeout FID {self._current_fid:04x} - retry "
                          f"({self._retry_cnt + 1}/{self.MAX_RETRIES})")
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
                self._retry_cnt += 1
                self.retry_attempts += 1
                self._had_retry = True
            else:
                self.frames_dropped += 1
                self._dbg(f"[wifi-uav] drop FID {self._current_fid:04x} "
                          f"(after {self._retry_cnt} retries)")
                self._fragments.clear()
                self._retry_cnt = 0
                self._current_fid = (self._current_fid + 1) & 0xFFFF
                self._send_frame_request((self._current_fid - 1) & 0xFFFF)
                self._had_retry = False
