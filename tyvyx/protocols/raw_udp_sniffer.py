"""Diagnostic UDP sniffer to discover the drone's video packet format.

Captures all UDP packets on a port after sending CMD_START_VIDEO,
logs hex headers and sizes, and attempts auto-detection of known formats.
"""

import socket
import threading
import queue
import time
from typing import Optional, List

from tyvyx.models.video_frame import VideoFrame
from tyvyx.protocols.base_video_protocol import BaseVideoProtocolAdapter


class RawUdpSnifferProtocol(BaseVideoProtocolAdapter):
    """Diagnostic protocol that captures raw UDP packets to determine
    the drone's video format."""

    def __init__(
        self,
        drone_ip: str = "192.168.1.1",
        control_port: int = 7099,
        video_port: int = 7070,
        start_command: bytes = bytes([0x08, 0x01]),
        max_log_packets: int = 50,
        bind_ip: str = "",
    ):
        super().__init__(drone_ip, control_port, video_port, bind_ip=bind_ip)
        self._start_command = start_command
        self._max_log_packets = max_log_packets

        self._sock = self.create_receiver_socket()
        self._running = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_q: "queue.Queue[VideoFrame]" = queue.Queue(maxsize=2)
        self._pkt_lock = threading.Lock()
        self._pkt_buffer: List[bytes] = []

        # Statistics
        self._pkt_count = 0
        self._s2x_count = 0
        self._wifi_uav_count = 0
        self._unknown_count = 0
        self._start_time = 0.0

    def send_start_command(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            if self.bind_ip:
                sock.bind((self.bind_ip, 0))
            sock.sendto(self._start_command, (self.drone_ip, self.control_port))
        print(f"[sniffer] Start command sent ({self._start_command.hex(' ')}) "
              f"to {self.drone_ip}:{self.control_port}")

    def create_receiver_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_addr = self.bind_ip or "0.0.0.0"
        sock.bind((bind_addr, self.video_port))
        sock.settimeout(1.0)
        print(f"[sniffer] Listening on {bind_addr}:{self.video_port}")
        return sock

    def handle_payload(self, payload: bytes) -> Optional[VideoFrame]:
        self._pkt_count += 1

        # Classify packet
        fmt = "unknown"
        if len(payload) > 8 and payload[:2] == b"\x40\x40":
            fmt = "S2X"
            self._s2x_count += 1
        elif len(payload) > 56 and payload[1:2] == b"\x01":
            fmt = "WiFi-UAV"
            self._wifi_uav_count += 1
        else:
            self._unknown_count += 1

        # Log first N packets
        if self._pkt_count <= self._max_log_packets:
            header_hex = payload[:32].hex(" ")
            print(f"[sniffer] #{self._pkt_count} ({fmt}) "
                  f"len={len(payload)} header={header_hex}")

        # Print summary every 100 packets
        if self._pkt_count % 100 == 0:
            elapsed = time.time() - self._start_time
            print(f"[sniffer] === {self._pkt_count} packets in {elapsed:.1f}s: "
                  f"S2X={self._s2x_count} WiFi-UAV={self._wifi_uav_count} "
                  f"unknown={self._unknown_count} ===")

        return None  # Diagnostic only, no frame assembly

    def start(self) -> None:
        if self._rx_thread and self._rx_thread.is_alive():
            return
        self._running.set()
        self._start_time = time.time()
        self.start_keepalive(2.0)

        def _rx_loop() -> None:
            sock = self._sock
            while self._running.is_set():
                try:
                    payload = self.recv_from_socket(sock)
                    if not payload:
                        continue
                    with self._pkt_lock:
                        self._pkt_buffer.append(payload)
                    self.handle_payload(payload)
                except OSError:
                    break
                except Exception:
                    continue

            # Final summary
            elapsed = time.time() - self._start_time
            print(f"\n[sniffer] === FINAL SUMMARY ===")
            print(f"[sniffer] Total packets: {self._pkt_count} in {elapsed:.1f}s")
            print(f"[sniffer] S2X format: {self._s2x_count}")
            print(f"[sniffer] WiFi-UAV format: {self._wifi_uav_count}")
            print(f"[sniffer] Unknown: {self._unknown_count}")
            if self._s2x_count > self._wifi_uav_count:
                print(f"[sniffer] RECOMMENDATION: Use protocol='s2x'")
            elif self._wifi_uav_count > 0:
                print(f"[sniffer] RECOMMENDATION: Use protocol='wifi_uav'")
            else:
                print(f"[sniffer] No recognized format. Try a different video_port.")

        self._rx_thread = threading.Thread(
            target=_rx_loop, daemon=True, name="UdpSniffer"
        )
        self._rx_thread.start()

    def stop(self) -> None:
        print("[sniffer] Stopping.")
        self.stop_keepalive()
        self._running.clear()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
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
