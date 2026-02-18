import sys
import socket
import threading
import queue
from typing import Optional, List

from tyvyx.models.s2x_video_model import S2xVideoModel
from tyvyx.models.video_frame import VideoFrame
from tyvyx.protocols.base_video_protocol import BaseVideoProtocolAdapter


class S2xVideoProtocolAdapter(BaseVideoProtocolAdapter):
    """Transport + header parser for S2x-style JPEG stream.

    Adapted for TEKY drone (E88Pro): uses CMD_START_VIDEO = 0x08 0x01
    instead of the original S2X 0x08 + client IP format.
    """

    SYNC_BYTES = b"\x40\x40"
    EOS_MARKER = b"\x23\x23"
    HEADER_LEN = 8
    LINK_DEAD_TIMEOUT = 8.0

    def __init__(
        self,
        drone_ip: str = "192.168.1.1",
        control_port: int = 7099,
        video_port: int = 7070,
        start_command: bytes = bytes([0x08, 0x01]),
        debug: bool = False,
        bind_ip: str = "",
    ):
        super().__init__(drone_ip, control_port, video_port, bind_ip=bind_ip)
        self.model = S2xVideoModel()
        self._start_command = start_command
        self._debug = debug
        self._sock_lock = threading.Lock()
        self._sock = self.create_receiver_socket()
        self._keepalive_stop: Optional[threading.Event] = None
        self._running = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []

        if debug:
            addr, port = self._sock.getsockname()
            print(f"[s2x] Video socket on {addr}:{port}")

    # ────────── BaseVideoProtocolAdapter ────────── #
    def send_start_command(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                if self.bind_ip:
                    sock.bind((self.bind_ip, 0))
                sock.sendto(self._start_command, (self.drone_ip, self.control_port))
            if self._debug:
                print(f"[s2x] Start command sent ({self._start_command.hex(' ')})")
        except OSError as e:
            if self._debug:
                print(f"[s2x] Start command failed: {e}")

    def start_keepalive(self, interval: float = 2.0) -> None:
        if self._keepalive_thread is None:
            self._keepalive_stop = threading.Event()
            self._keepalive_thread = threading.Thread(
                target=self._ka_loop,
                args=(interval, self._keepalive_stop),
                daemon=True,
                name="S2xVideoKeepAlive",
            )
            self._keepalive_thread.start()

    def stop_keepalive(self) -> None:
        if self._keepalive_stop:
            self._keepalive_stop.set()
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=1.0)
            self._keepalive_thread = None

    def create_receiver_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "win32":
            import ctypes
            SIO_UDP_CONNRESET = 0x9800000C
            ret = ctypes.c_ulong(0)
            false = b"\x00\x00\x00\x00"
            ctypes.windll.ws2_32.WSAIoctl(
                sock.fileno(),
                SIO_UDP_CONNRESET,
                false, len(false),
                None, 0,
                ctypes.byref(ret), None, None,
            )
        bind_addr = self.bind_ip or "0.0.0.0"
        sock.bind((bind_addr, self.video_port))
        sock.settimeout(1.0)
        return sock

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        if len(payload) <= self.HEADER_LEN or payload[:2] != self.SYNC_BYTES:
            return None

        frame_id = payload[2]
        slice_id_raw = payload[5]
        body = payload[self.HEADER_LEN:]

        if body.endswith(self.EOS_MARKER):
            body = body[: -len(self.EOS_MARKER)]

        return self.model.ingest_chunk(
            stream_id=frame_id,
            chunk_id=slice_id_raw,
            payload=body,
        )

    # ────────── lifecycle ────────── #
    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._running.set()
        self.start_keepalive(2.0)

        def _rx_loop() -> None:
            sock = self._sock
            pkt_count = 0
            frame_count = 0
            reject_count = 0
            while self._running.is_set():
                try:
                    payload = self.recv_from_socket(sock)
                    if not payload:
                        continue
                    pkt_count += 1
                    with self._pkt_lock:
                        self._pkt_buffer.append(payload)

                    if self._debug and pkt_count <= 5:
                        print(f"[s2x] pkt #{pkt_count}: {len(payload)} bytes, "
                              f"header={payload[:8].hex(' ')}")

                    frame = self.handle_payload(payload)
                    if frame is not None:
                        frame_count += 1
                        try:
                            self._frame_q.put(frame, timeout=0.2)
                        except queue.Full:
                            pass
                    else:
                        reject_count += 1

                    if self._debug and pkt_count % 200 == 0:
                        print(f"[s2x] stats: {pkt_count} pkts, "
                              f"{frame_count} frames, "
                              f"{reject_count} rejected")
                except OSError:
                    break
                except Exception:
                    continue

        self._rx_thread = threading.Thread(
            target=_rx_loop, daemon=True, name="S2xVideoRx"
        )
        self._rx_thread.start()

    def stop(self) -> None:
        print("[s2x] Stopping protocol adapter.")
        self.stop_keepalive()
        self._running.clear()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        try:
            self._sock.close()
        except Exception:
            pass

    def is_running(self) -> bool:
        return (
            self._running.is_set()
            and self._rx_thread is not None
            and self._rx_thread.is_alive()
        )

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

    # ────────── helpers ────────── #
    def _ka_loop(self, interval: float, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.send_start_command()
            stop_event.wait(interval)
