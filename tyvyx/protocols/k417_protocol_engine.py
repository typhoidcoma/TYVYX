"""K417 Unified Protocol Engine — Pull-based video + burst RC on single socket.

Adopted from turbodrone's pull-based approach (I:\\Projects\\turbodrone).
After each completed frame, sends REQUEST_A + REQUEST_B pair to ACK the
frame and pull the next one.  This should yield higher FPS than START_STREAM
keepalives (~1.5fps) by properly advancing the drone's sliding window.

  TX:
    - REQUEST_A (88B) + REQUEST_B (124B) pair after each frame (pull-based)
    - 88B burst RC (20-byte format) per frame (~frame-synced)
    - Warmup: START_STREAM + REQUEST(0) every 200ms until first frame

  RX:
    - 0x93 0x01 JPEG fragments (56-byte header + payload)
    - Fragment reassembly -> complete JPEG frame

  Watchdog:
    - 80ms per-frame timeout, 3 retries before drop + advance

Interface matches VideoReceiverService adapter contract:
  start(), stop(), is_running(), get_frame(), get_shared_socket()
"""

import ctypes
import queue
import socket
import struct
import sys
import threading
import time
from typing import Dict, Optional

from tyvyx.models.video_frame import VideoFrame
from tyvyx.utils.wifi_uav_jpeg import generate_jpeg_headers_full, EOI
from tyvyx.utils.wifi_uav_packets import START_STREAM, REQUEST_A, REQUEST_B
from tyvyx.utils.k417_packets import build_rc_88b


# 0x93 protocol constants
MAGIC = b"\x93\x01"
HEADER_SIZE = 56
OFF_FRAG_ID = 32
OFF_FRAG_TOTAL = 36
OFF_FRAME_ID = 16  # u16LE, same offset turbodrone uses (always 1 on K417)


class K417ProtocolEngine:
    """Pull-based TX/RX protocol engine for K417 drones.

    Implements the VideoReceiverService adapter interface so it drops
    into the existing video pipeline without changes.
    """

    FRAME_TIMEOUT = 0.08     # 80ms before watchdog retries a request
    MAX_RETRIES = 3          # retries per frame before dropping
    WATCHDOG_SLEEP = 0.05    # 50ms between watchdog checks
    WARMUP_INTERVAL = 0.2    # 200ms between warmup re-sends

    def __init__(
        self,
        drone_ip="192.168.169.1",
        port=8800,
        bind_ip="",
        flight_controller=None,
        jpeg_width=640,
        jpeg_height=360,
        components=3,
        debug=False,
        **kwargs,
    ):
        self.drone_ip = drone_ip
        self.port = port
        self.bind_ip = bind_ip
        self._fc = flight_controller

        self._debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)

        # Pre-built JPEG header
        self._jpeg_header = generate_jpeg_headers_full(jpeg_width, jpeg_height, components)

        # Socket
        self._sock = self._create_socket()

        # ── RX state (fragment reassembly) ──
        self._fragments = {}  # type: Dict[int, bytes]
        self._frag_total = 0
        self._frame_id = 0       # from drone header bytes [16:17]
        self._frame_count = 0

        # ── Request / retry state ──
        self._last_req_time = 0.0
        self._retry_cnt = 0
        self._warmup = True      # True until first frame received

        # Threading
        self._running = False
        self._rx_thread = None       # type: Optional[threading.Thread]
        self._warmup_thread = None   # type: Optional[threading.Thread]
        self._watchdog_thread = None # type: Optional[threading.Thread]
        self._frame_q = queue.Queue(maxsize=4)  # type: queue.Queue[VideoFrame]

        # Stats
        self.frames_ok = 0
        self.frames_dropped = 0
        self.packets_rx = 0
        self.packets_rejected = 0
        self.retry_attempts = 0
        self._last_frame_time = 0.0
        self._stall_timeout = 30.0
        self._stats_time = time.time()
        self._stats_pkts = 0
        self._stats_frames = 0

        self._dbg(f"[k417] Engine created  drone={drone_ip}:{port}  "
                  f"bind={bind_ip or '*'}  sock={self._sock.getsockname()}")

    # ── Lifecycle (VideoReceiverService adapter interface) ──

    def start(self):
        # type: () -> None
        if self._running:
            return

        self._running = True
        self._warmup = True

        # Kick-off: START_STREAM + request frame 0 (drone responds with frame 1)
        self._send(START_STREAM)
        self._send_frame_request(0)

        # RX thread
        self._rx_thread = threading.Thread(
            target=self._rx_loop, daemon=True, name="K417-RX",
        )
        self._rx_thread.start()

        # Warmup: resend START_STREAM + request every 200ms until first frame
        self._warmup_thread = threading.Thread(
            target=self._warmup_loop, daemon=True, name="K417-Warmup",
        )
        self._warmup_thread.start()

        # Watchdog: 80ms per-frame timeout, retries
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="K417-Watchdog",
        )
        self._watchdog_thread.start()

        print("[k417] Engine started (pull-based REQUEST_A+B)")

    def stop(self):
        # type: () -> None
        self._running = False

        for t in [self._rx_thread, self._warmup_thread, self._watchdog_thread]:
            if t and t.is_alive():
                t.join(timeout=1.0)

        try:
            self._sock.close()
        except Exception:
            pass

        print(f"[k417] Engine stopped  ok={self.frames_ok}  dropped={self.frames_dropped}  "
              f"rx={self.packets_rx}  rejected={self.packets_rejected}  "
              f"retries={self.retry_attempts}")

    def is_running(self):
        # type: () -> bool
        if not self._running or self._rx_thread is None or not self._rx_thread.is_alive():
            return False
        if self._last_frame_time > 0 and (time.time() - self._last_frame_time) > self._stall_timeout:
            print(f"[k417] Stall detected ({self._stall_timeout}s), stopping for reconnect")
            self._running = False
            return False
        return True

    def get_frame(self, timeout=1.0):
        # type: (float) -> Optional[VideoFrame]
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_shared_socket(self):
        # type: () -> socket.socket
        return self._sock

    # Unused but required by adapter interface
    def get_packets(self):
        return []

    def start_keepalive(self, interval=1.0):
        pass

    def stop_keepalive(self):
        pass

    # ── Socket ──

    def _create_socket(self):
        # type: () -> socket.socket
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

    def _send(self, data):
        # type: (bytes) -> None
        try:
            self._sock.sendto(data, (self.drone_ip, self.port))
        except OSError:
            pass

    # ── Frame request (pull-based, ported from turbodrone) ──

    def _send_frame_request(self, frame_id):
        # type: (int) -> None
        """Send REQUEST_A + REQUEST_B pair to ACK frame and pull next.

        The pair is byte-identical to turbodrone's implementation.
        frame_id is patched at bytes [12:13] (REQUEST_A) and
        [12:13], [88:89], [107:108] (REQUEST_B).
        """
        lo = frame_id & 0xFF
        hi = (frame_id >> 8) & 0xFF

        rqst_a = bytearray(REQUEST_A)
        rqst_a[12] = lo
        rqst_a[13] = hi

        rqst_b = bytearray(REQUEST_B)
        for base in (12, 88, 107):
            rqst_b[base] = lo
            rqst_b[base + 1] = hi

        self._send(bytes(rqst_a))
        self._send(bytes(rqst_b))
        self._last_req_time = time.time()
        self._dbg(f"[k417] REQ fid={frame_id}")

    # ── Warmup loop ──

    def _warmup_loop(self):
        # type: () -> None
        """Resend START_STREAM + frame request every 200ms until first frame."""
        while self._running and self._warmup:
            try:
                self._send(START_STREAM)
                self._send_frame_request(0)
            except Exception:
                pass
            time.sleep(self.WARMUP_INTERVAL)
        self._dbg("[k417] Warmup loop stopped")

    # ── Watchdog loop ──

    def _watchdog_loop(self):
        # type: () -> None
        """Per-frame timeout: retry request after 80ms, drop after MAX_RETRIES."""
        while self._running:
            time.sleep(self.WATCHDOG_SLEEP)
            now = time.time()

            if now - self._last_req_time < self.FRAME_TIMEOUT:
                continue  # still within timeout

            if self._retry_cnt < self.MAX_RETRIES:
                self._dbg(f"[k417] Watchdog retry {self._retry_cnt + 1}/{self.MAX_RETRIES}")
                self._send_frame_request(self._frame_id or 0)
                self._retry_cnt += 1
                self.retry_attempts += 1
            else:
                # Drop current frame, request fresh
                self.frames_dropped += 1
                self._fragments.clear()
                self._retry_cnt = 0
                self._send_frame_request(self._frame_id or 0)
                self._dbg("[k417] Watchdog drop + re-request")

    # ── RC burst (frame-synced) ──

    def _send_rc_burst(self):
        # type: () -> None
        """Send one 88B RC packet with 20-byte format, synced to frame."""
        roll, pitch, throttle, yaw, cmd, headless = self._get_fc_state()
        pkt = build_rc_88b(
            self._frame_id, roll, pitch, throttle, yaw, cmd, headless,
        )
        self._send(pkt)

    def _get_fc_state(self):
        # type: () -> tuple
        """Read RC state from flight controller, convert to 20-byte format.

        Returns (roll, pitch, throttle, yaw, cmd, headless).
        """
        if self._fc is not None and hasattr(self._fc, 'get_rc_state'):
            roll, pitch, throttle, yaw, flags = self._fc.get_rc_state()
            # Convert 8-byte flags → 20-byte cmd+headless
            cmd = flags & 0x07   # takeoff=1, land=2, calibrate=4
            return (roll, pitch, throttle, yaw, cmd, 2)
        return (128, 128, 128, 128, 0, 2)

    # ── RX thread — receive 0x93 video fragments, assemble JPEG ──

    def _rx_loop(self):
        # type: () -> None
        """Receive packets, filter by 0x93 magic, assemble JPEG frames."""
        sock = self._sock
        self._dbg(f"[k417] RX thread started, socket={sock.getsockname()}")

        while self._running:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
            except OSError:
                if self._running:
                    print("[k417] Socket error in RX loop")
                break

            self.packets_rx += 1
            self._stats_pkts += 1
            self._retry_cnt = 0  # Reset retry on any received data

            # Periodic stats (every 5s)
            now = time.time()
            if now - self._stats_time >= 5.0:
                elapsed = now - self._stats_time
                pps = self._stats_pkts / elapsed
                fps = self._stats_frames / elapsed
                nfrags = len(self._fragments)
                state = "WARMUP" if self._warmup else "STREAMING"
                print(f"[k417] STATS: {pps:.1f} pkt/s | {fps:.1f} fps | "
                      f"frags={nfrags}/{self._frag_total} | "
                      f"retries={self.retry_attempts} | {state}")
                self._stats_pkts = 0
                self._stats_frames = 0
                self._stats_time = now

            # Log non-video packets (first 20)
            if len(data) < HEADER_SIZE or data[0:2] != MAGIC:
                self.packets_rejected += 1
                if self.packets_rejected <= 20:
                    head = data[:32].hex(" ") if data else "(empty)"
                    ascii_part = ""
                    if len(data) >= 4 and data[0] == 0x93 and data[1] == 0x04:
                        try:
                            ascii_part = "  ascii=" + data[4:].decode("ascii", errors="replace")
                        except Exception:
                            pass
                    print(f"[k417] NON-VIDEO: {len(data)}B from {addr}  head={head}{ascii_part}")
                continue

            # Parse header
            frag_id = struct.unpack_from("<H", data, OFF_FRAG_ID)[0]
            frag_total = struct.unpack_from("<H", data, OFF_FRAG_TOTAL)[0]
            frame_id = struct.unpack_from("<H", data, OFF_FRAME_ID)[0]

            # New frame: frag_id == 0 resets assembly
            if frag_id == 0:
                if self._fragments:
                    self.frames_dropped += 1
                self._fragments.clear()
                self._frag_total = frag_total
                self._frame_id = frame_id

            # Store fragment
            payload = data[HEADER_SIZE:]
            if payload:
                self._fragments[frag_id] = payload

            # Frame complete?
            if self._frag_total > 0 and len(self._fragments) == self._frag_total:
                self._emit_frame()

        self._dbg(f"[k417] RX thread stopped, total rx={self.packets_rx}")

    def _emit_frame(self):
        # type: () -> None
        """Assemble fragments into JPEG, queue it, pull next frame."""
        if not self._fragments:
            return

        self._last_frame_time = time.time()
        self._frame_count += 1
        self._stats_frames += 1
        self._retry_cnt = 0

        # Reassemble in order
        ordered = [self._fragments[i] for i in sorted(self._fragments)]
        jpeg = self._jpeg_header + b"".join(ordered) + EOI

        frame = VideoFrame(frame_id=self._frame_count, data=jpeg)
        self.frames_ok += 1

        # Queue frame
        try:
            self._frame_q.put(frame, timeout=0.1)
        except queue.Full:
            try:
                self._frame_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_q.put_nowait(frame)
            except queue.Full:
                self.frames_dropped += 1

        if self.frames_ok <= 5 or self.frames_ok % 100 == 0:
            print(f"[k417] Frame {self._frame_count}: {len(jpeg)} bytes  "
                  f"({len(self._fragments)}/{self._frag_total} frags)  "
                  f"fid={self._frame_id}  retries={self.retry_attempts}")

        self._fragments.clear()

        # Pull next frame: send REQUEST_A + REQUEST_B pair
        self._send_frame_request(self._frame_id)

        # Burst RC: one 88B per frame (frame-synced, won't kill video)
        self._send_rc_burst()

        # Stop warmup after first frame
        if self._warmup:
            self._warmup = False
            print("[k417] -> STREAMING (first frame received, warmup stopped)")
