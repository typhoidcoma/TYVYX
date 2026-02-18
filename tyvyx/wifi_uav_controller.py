"""WiFi UAV Drone Controller for K417 and similar drones.

Uses the wifi_uav protocol family:
  - Single UDP socket shared between control and video (port 8800)
  - ~120-byte RC control packets with rolling counters
  - No separate handshake/heartbeat needed

The socket is created by WifiUavVideoProtocolAdapter and shared here.
"""

import socket
import sys
import threading
import time
from typing import List, Optional

from tyvyx.utils.wifi_uav_packets import (
    RC_HEADER, RC_COUNTER1_SUFFIX, RC_CONTROL_SUFFIX,
    RC_CHECKSUM_SUFFIX, RC_COUNTER2_SUFFIX, RC_COUNTER3_SUFFIX,
)


class WifiUavFlightController:
    """Flight controller for WiFi UAV drones (K417, etc.)."""

    def __init__(self, send_fn):
        self.send_command = send_fn

        # Control values (0-255, center=127)
        self.throttle = 127
        self.yaw = 127
        self.pitch = 127
        self.roll = 127

        self.MIN_VAL = 40
        self.MAX_VAL = 220
        self.NEUTRAL = 127
        self.STEP = 50
        self.DECEL_STEP = 5

        # One-shot flags
        self._takeoff_flag = False
        self._land_flag = False
        self._calibrate_flag = False
        self._headless_mode = False

        self.control_thread = None
        self.is_active = False
        self.last_command_time = 0
        self.command_interval = 0.0125  # 80 Hz (wifi_uav recommended rate)

    def start(self):
        if not self.is_active:
            self.is_active = True
            self.control_thread = threading.Thread(
                target=self._control_loop, daemon=True
            )
            self.control_thread.start()

    def stop(self):
        self.is_active = False
        self.reset()
        if self.control_thread:
            self.control_thread.join(timeout=1)

    def reset(self):
        self.throttle = self.NEUTRAL
        self.yaw = self.NEUTRAL
        self.pitch = self.NEUTRAL
        self.roll = self.NEUTRAL

    def takeoff(self):
        self._takeoff_flag = True

    def land(self):
        self._land_flag = True

    def calibrate_gyro(self):
        self._calibrate_flag = True

    def toggle_headless(self):
        self._headless_mode = not self._headless_mode

    def increase_throttle(self):
        self.throttle = min(self.throttle + self.STEP, self.MAX_VAL)

    def decrease_throttle(self):
        self.throttle = max(self.throttle - self.STEP, self.MIN_VAL)

    def yaw_left(self):
        self.yaw = max(self.yaw - self.STEP, self.MIN_VAL)

    def yaw_right(self):
        self.yaw = min(self.yaw + self.STEP, self.MAX_VAL)

    def pitch_forward(self):
        self.pitch = min(self.pitch + self.STEP, self.MAX_VAL)

    def pitch_backward(self):
        self.pitch = max(self.pitch - self.STEP, self.MIN_VAL)

    def roll_left(self):
        self.roll = max(self.roll - self.STEP, self.MIN_VAL)

    def roll_right(self):
        self.roll = min(self.roll + self.STEP, self.MAX_VAL)

    def _control_loop(self):
        while self.is_active:
            now = time.time()
            if now - self.last_command_time >= self.command_interval:
                self._send_rc_packet()
                self.last_command_time = now
            time.sleep(0.005)

    def _send_rc_packet(self):
        """Build and send a wifi_uav RC control packet (~120 bytes)."""
        # Determine command flag
        if self._takeoff_flag:
            command = 0x01
        elif self._land_flag:
            command = 0x02
        elif self._calibrate_flag:
            command = 0x04
        else:
            command = 0x00

        headless = 0x03 if self._headless_mode else 0x02

        controls = [
            int(self.roll) & 0xFF,
            int(self.pitch) & 0xFF,
            int(self.throttle) & 0xFF,
            int(self.yaw) & 0xFF,
            command & 0xFF,
            headless & 0xFF,
        ]

        checksum = 0
        for b in controls:
            checksum ^= b

        try:
            self.send_command(bytes(controls), checksum)
        except Exception:
            pass

        # Clear one-shot flags
        self._takeoff_flag = False
        self._land_flag = False
        self._calibrate_flag = False

        # Auto-decel
        if self.DECEL_STEP > 0:
            for attr in ('roll', 'pitch', 'throttle', 'yaw'):
                val = getattr(self, attr)
                if val > self.NEUTRAL:
                    setattr(self, attr, max(val - self.DECEL_STEP, self.NEUTRAL))
                elif val < self.NEUTRAL:
                    setattr(self, attr, min(val + self.DECEL_STEP, self.NEUTRAL))

    def get_status_text(self) -> List[str]:
        lines = [
            f"Throttle: {self.throttle:3d} ({((self.throttle-127)/127*100):+.0f}%)",
            f"Yaw:      {self.yaw:3d} ({((self.yaw-127)/127*100):+.0f}%)",
            f"Pitch:    {self.pitch:3d} ({((self.pitch-127)/127*100):+.0f}%)",
            f"Roll:     {self.roll:3d} ({((self.roll-127)/127*100):+.0f}%)",
        ]
        if self._headless_mode:
            lines.append("HEADLESS MODE: ON")
        return lines


class WifiUavDroneController:
    """Controller for WiFi UAV drones (K417, etc.).

    Unlike E88Pro, wifi_uav uses a single duplex UDP socket for both
    control and video on port 8800.  The socket is created by the video
    protocol adapter and shared here for sending RC commands.
    """

    DRONE_IP = "192.168.169.1"
    UDP_PORT = 8800

    def __init__(self, drone_ip: str = "192.168.169.1", bind_ip: str = ""):
        self.DRONE_IP = drone_ip
        self.UDP_PORT = 8800
        self.bind_ip = bind_ip

        self.udp_socket: Optional[socket.socket] = None
        self.is_running = False
        self.is_connected = False
        self.device_type = 0

        # Rolling counters for RC packets
        self._ctr1 = 0x0000
        self._ctr2 = 0x0001
        self._ctr3 = 0x0002

        self.flight_controller = WifiUavFlightController(self._send_rc_raw)

    def connect(self) -> bool:
        """Mark as connected.  WiFi UAV doesn't need a handshake."""
        print(f"[wifi-uav] Connecting to {self.DRONE_IP}:{self.UDP_PORT} "
              f"(bind={self.bind_ip or 'auto'})...")

        # Create a socket for control commands if we don't have a shared one yet
        if not self.udp_socket:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(2.0)

            if sys.platform == "win32":
                import ctypes
                SIO_UDP_CONNRESET = 0x9800000C
                ret = ctypes.c_ulong(0)
                false = b"\x00\x00\x00\x00"
                ctypes.windll.ws2_32.WSAIoctl(
                    self.udp_socket.fileno(), SIO_UDP_CONNRESET,
                    false, len(false), None, 0,
                    ctypes.byref(ret), None, None,
                )

            if self.bind_ip:
                self.udp_socket.bind((self.bind_ip, 0))

        self.is_connected = True
        self.is_running = True
        print("[wifi-uav] Connected (no handshake required for wifi_uav)")
        return True

    def set_shared_socket(self, sock: socket.socket) -> None:
        """Use the video protocol's duplex socket for RC commands."""
        if self.udp_socket and self.udp_socket is not sock:
            try:
                self.udp_socket.close()
            except Exception:
                pass
        self.udp_socket = sock

    def disconnect(self):
        print("[wifi-uav] Disconnecting...")
        if self.flight_controller.is_active:
            self.flight_controller.stop()
        self.is_running = False
        self.is_connected = False
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass
            self.udp_socket = None

    def send_command(self, command: bytes, verbose: bool = False) -> bool:
        """Send raw bytes to the drone."""
        if not self.udp_socket:
            return False
        try:
            self.udp_socket.sendto(command, (self.DRONE_IP, self.UDP_PORT))
            if verbose:
                print(f"[wifi-uav] Sent: {command.hex()}")
            return True
        except Exception as e:
            print(f"[wifi-uav] Send error: {e}")
            return False

    def _send_rc_raw(self, controls: bytes, checksum: int) -> None:
        """Build full wifi_uav RC packet from controls and send it."""
        if not self.udp_socket:
            return

        c1 = self._ctr1.to_bytes(2, "little")
        c2 = self._ctr2.to_bytes(2, "little")
        c3 = self._ctr3.to_bytes(2, "little")

        self._ctr1 = (self._ctr1 + 1) & 0xFFFF
        self._ctr2 = (self._ctr2 + 1) & 0xFFFF
        self._ctr3 = (self._ctr3 + 1) & 0xFFFF

        pkt = bytearray()
        pkt += RC_HEADER
        pkt += c1 + RC_COUNTER1_SUFFIX
        pkt += controls
        pkt += RC_CONTROL_SUFFIX
        pkt.append(checksum)
        pkt += RC_CHECKSUM_SUFFIX
        pkt += c2 + RC_COUNTER2_SUFFIX
        pkt += c3 + RC_COUNTER3_SUFFIX

        try:
            self.udp_socket.sendto(bytes(pkt), (self.DRONE_IP, self.UDP_PORT))
        except OSError:
            pass

    def switch_camera(self, camera_num: int) -> bool:
        """WiFi UAV doesn't support camera switching."""
        return False

    def switch_screen_mode(self, mode: int) -> bool:
        """WiFi UAV doesn't support screen mode switching."""
        return False

    # Compatibility stubs matching TYVYXDroneControllerAdvanced interface
    CMD_HEARTBEAT = b""
    CMD_INITIALIZE = b""
    CMD_START_VIDEO = b"\xef\x00\x04\x00"
    CMD_CAMERA_1 = b""
    CMD_CAMERA_2 = b""
