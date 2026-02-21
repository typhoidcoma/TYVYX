"""K417 Unified Protocol Engine — TX (RC) + RX (video) on a single socket.

Reverse-engineered from Wireshark capture of YN Fly Android app (Feb 2026).

This engine replaces the split architecture of PushJpegVideoProtocolAdapter
(keepalive only) + WifiUavDroneController (idle heartbeat).  It owns the UDP
socket and handles both directions:

  TX:
    - ef 00 (START_STREAM) at ~10Hz — video keepalive + frame re-request
    - 88-byte RC packets (ef 02 58 00) at 40Hz — stick data + frame ACK
    - Both carry a LE uint32 counter at bytes [12:16] = completed frame count

  RX (continuous):
    - 0x93 0x01 JPEG fragments (56-byte header + payload)
    - Fragment reassembly → complete JPEG frame
    - Frame completion immediately sends START_STREAM to request next frame

Startup state machine:
  INIT      → ef 00 at 10Hz only, wait for first frame
  STREAMING → ef 00 at 10Hz + 88B RC at 40Hz

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
from tyvyx.utils.k417_packets import START_STREAM, build_rc_88b


# 0x93 protocol constants (same as push_jpeg adapter)
MAGIC = b"\x93\x01"
HEADER_SIZE = 56
OFF_FRAG_ID = 32
OFF_FRAG_TOTAL = 36
OFF_SEQ_FLY = 8

# State machine phases
_PHASE_INIT = 0       # ef 00 only — wait for first frame
_PHASE_STREAMING = 1  # ef 00 + 88B RC at 40Hz


class K417ProtocolEngine:
    """Unified TX/RX protocol engine for K417 drones.

    Implements the VideoReceiverService adapter interface so it drops
    into the existing video pipeline without changes.
    """

    # TX mode constants
    MODE_EF00_ONLY = "ef00"       # START_STREAM only (baseline, ~2fps)
    MODE_EF02_ONLY = "ef02"       # ef 02 RC packets only
    MODE_BOTH = "both"            # ef 00 + ef 02 (full protocol)

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
        tx_mode="both",
        **kwargs,
    ):
        self.drone_ip = drone_ip
        self.port = port
        self.bind_ip = bind_ip
        self._fc = flight_controller  # WifiUavFlightController (reads sticks/flags)

        self._debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)
        self._tx_mode = tx_mode  # "ef00", "ef02", or "both"

        # Pre-built JPEG header
        self._jpeg_header = generate_jpeg_headers_full(jpeg_width, jpeg_height, components)

        # Socket
        self._sock = self._create_socket()

        # ── TX state ──
        self._tx_counter = 0         # uint32: = frame_count (increments per completed frame)
        self._tx_tick = 0            # counts TX ticks for periodic START_STREAM
        self._phase = _PHASE_INIT

        # ── RX state (fragment reassembly) ──
        self._fragments = {}  # type: Dict[int, bytes]
        self._frag_total = 0
        self._seq_fly = 0            # from drone header (constant=1 on K417)
        self._frame_count = 0

        # Threading
        self._running = False
        self._tx_thread = None   # type: Optional[threading.Thread]
        self._rx_thread = None   # type: Optional[threading.Thread]
        self._frame_q = queue.Queue(maxsize=4)  # type: queue.Queue[VideoFrame]

        # Stats
        self.frames_ok = 0
        self.frames_dropped = 0
        self.packets_rx = 0
        self.packets_rejected = 0
        self._last_frame_time = 0.0
        self._last_rx_time = 0.0
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
        self._phase = _PHASE_INIT

        # Send initial START_STREAM burst
        self._send(START_STREAM)

        # RX thread
        self._rx_thread = threading.Thread(
            target=self._rx_loop, daemon=True, name="K417-RX",
        )
        self._rx_thread.start()

        # TX thread
        self._tx_thread = threading.Thread(
            target=self._tx_loop, daemon=True, name="K417-TX",
        )
        self._tx_thread.start()

        print(f"[k417] Engine started (tx_mode={self._tx_mode})")

    def stop(self):
        # type: () -> None
        self._running = False

        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        if self._tx_thread and self._tx_thread.is_alive():
            self._tx_thread.join(timeout=1.5)

        try:
            self._sock.close()
        except Exception:
            pass

        print(f"[k417] Engine stopped  ok={self.frames_ok}  dropped={self.frames_dropped}  "
              f"rx={self.packets_rx}  rejected={self.packets_rejected}")

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

    # ── TX thread ──

    def _tx_loop(self):
        # type: () -> None
        """Send ef 00 (START_STREAM) at ~10Hz as video keepalive.

        RC packets are NOT sent from this loop — sustained ef 02 at 40Hz
        kills the video stream.  Instead, RC is burst-sent from _emit_frame()
        right after each completed frame (option 3: frame-synced RC).
        """
        print("[k417] TX thread started")
        interval = 0.1  # 100ms = 10Hz

        while self._running:
            self._tx_tick += 1
            self._send(START_STREAM)
            time.sleep(interval)

        self._dbg("[k417] TX thread stopped")

    def _send_rc_tick(self):
        # type: () -> None
        """Send one 88-byte RC packet.

        Counter at bytes [12:16] = number of completed frames received.
        The drone reads this as a frame ACK.
        """
        roll, pitch, throttle, yaw, flags = self._get_fc_state()
        pkt = build_rc_88b(self._tx_counter, roll, pitch, throttle, yaw, flags)
        self._send(pkt)

    def _get_fc_state(self):
        # type: () -> tuple
        """Read RC state from flight controller, or return neutral."""
        if self._fc is not None and hasattr(self._fc, 'get_rc_state'):
            return self._fc.get_rc_state()
        return (128, 128, 128, 128, 0x40)

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
            self._last_rx_time = time.time()

            # Periodic stats (every 5s)
            now = time.time()
            if now - self._stats_time >= 5.0:
                elapsed = now - self._stats_time
                pps = self._stats_pkts / elapsed
                fps = self._stats_frames / elapsed
                nfrags = len(self._fragments)
                phase_name = "INIT" if self._phase == _PHASE_INIT else "STREAMING"
                print(f"[k417] STATS: {pps:.1f} pkt/s | {fps:.1f} fps | "
                      f"frags={nfrags}/{self._frag_total} | "
                      f"tx_ctr={self._tx_counter} | phase={phase_name}")
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
            seq_fly = struct.unpack_from("<Q", data, OFF_SEQ_FLY)[0]

            # New frame: frag_id == 0 resets assembly
            if frag_id == 0:
                if self._fragments:
                    self.frames_dropped += 1
                self._fragments.clear()
                self._frag_total = frag_total
                self._seq_fly = seq_fly

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
        """Assemble fragments into JPEG, queue it, advance frame ACK counter."""
        if not self._fragments:
            return

        self._last_frame_time = time.time()
        self._frame_count += 1
        self._stats_frames += 1

        # Advance frame ACK counter — tells the drone we've received this frame
        self._tx_counter = self._frame_count & 0xFFFFFFFF

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
                  f"seq_fly={self._seq_fly}  tx_ctr={self._tx_counter}")

        self._fragments.clear()

        # Immediately request next frame (critical for sustained streaming —
        # the old PushJpegVideoProtocolAdapter does this at line 387)
        self._send(START_STREAM)

        # Burst RC: send one 88B RC packet right after START_STREAM.
        # Sustained 40Hz ef 02 kills video, but a single burst per frame
        # (~1.7 RC/s synced to video cadence) should be tolerated.
        if self._tx_mode != self.MODE_EF00_ONLY and self._phase == _PHASE_STREAMING:
            self._send_rc_tick()

        # Transition INIT → STREAMING after first frame
        if self._phase == _PHASE_INIT:
            self._phase = _PHASE_STREAMING
            print("[k417] -> STREAMING phase (first frame received, enabling RC)")
