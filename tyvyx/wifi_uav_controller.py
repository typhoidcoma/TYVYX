"""WiFi UAV Drone Controller for K417 and similar drones.

Uses the wifi_uav protocol family (BL-UAVSDK / BL608 chipset):
  - Port 8800: video streaming AND control commands (RC, camera switch)
  - Port 8801: does NOT exist on K417 (ICMP unreachable)
  - ~120-byte RC control packets with rolling counters
  - Socket shared with video adapter (single source port required)

The socket is created by PushJpegVideoProtocolAdapter and shared here.
"""

import socket
import sys
import threading
import time
from typing import List, Optional

from tyvyx.utils.wifi_uav_packets import (
    RC_HEADER, RC_COUNTER1_SUFFIX, RC_CONTROL_SUFFIX,
    RC_CHECKSUM_SUFFIX, RC_COUNTER2_SUFFIX, RC_COUNTER3_SUFFIX,
    CAMERA_FRONT, CAMERA_BOTTOM,
)


class WifiUavFlightController:
    """Flight controller for WiFi UAV drones (K417, etc.)."""

    def __init__(self, send_fn):
        self.send_command = send_fn

        # Control values (0-255, center=128/0x80)
        self.throttle = 128
        self.yaw = 128
        self.pitch = 128
        self.roll = 128

        self.MIN_VAL = 40
        self.MAX_VAL = 220
        self.NEUTRAL = 128
        self.STEP = 50
        self.DECEL_STEP = 5

        # One-shot flags
        self._takeoff_flag = False
        self._land_flag = False
        self._calibrate_flag = False
        self._headless_mode = False

        # External axis control (suppresses auto-decel for 200ms after set_axes)
        self._last_axes_set = 0.0

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

    def set_axes(self, throttle=None, yaw=None, pitch=None, roll=None):
        """Set axis values directly (0-255, 127=center).

        Suppresses auto-decel for 200ms so the values aren't immediately
        erased.  Call periodically (10-20 Hz) while keys are held.
        """
        self._last_axes_set = time.time()
        _clamp = lambda v: max(self.MIN_VAL, min(self.MAX_VAL, int(v)))
        if throttle is not None:
            self.throttle = _clamp(throttle)
        if yaw is not None:
            self.yaw = _clamp(yaw)
        if pitch is not None:
            self.pitch = _clamp(pitch)
        if roll is not None:
            self.roll = _clamp(roll)

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

    def get_rc_state(self):
        """Return current (roll, pitch, throttle, yaw, flags) for the engine.

        flags: 0x40=normal, 0x01=takeoff, 0x02=land, 0x04=calibrate.
        One-shot flags are cleared after being read.
        """
        flags = 0x40  # normal
        if self._takeoff_flag:
            flags = 0x01
            self._takeoff_flag = False
        elif self._land_flag:
            flags = 0x02
            self._land_flag = False
        elif self._calibrate_flag:
            flags = 0x04
            self._calibrate_flag = False

        return (
            int(self.roll) & 0xFF,
            int(self.pitch) & 0xFF,
            int(self.throttle) & 0xFF,
            int(self.yaw) & 0xFF,
            flags,
        )

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

        # Auto-decel (suppressed for 200ms after set_axes)
        if self.DECEL_STEP > 0 and (time.time() - self._last_axes_set) > 0.2:
            for attr in ('roll', 'pitch', 'throttle', 'yaw'):
                val = getattr(self, attr)
                if val > self.NEUTRAL:
                    setattr(self, attr, max(val - self.DECEL_STEP, self.NEUTRAL))
                elif val < self.NEUTRAL:
                    setattr(self, attr, min(val + self.DECEL_STEP, self.NEUTRAL))

    def get_status_text(self) -> List[str]:
        lines = [
            f"Throttle: {self.throttle:3d} ({((self.throttle-128)/128*100):+.0f}%)",
            f"Yaw:      {self.yaw:3d} ({((self.yaw-128)/128*100):+.0f}%)",
            f"Pitch:    {self.pitch:3d} ({((self.pitch-128)/128*100):+.0f}%)",
            f"Roll:     {self.roll:3d} ({((self.roll-128)/128*100):+.0f}%)",
        ]
        if self._headless_mode:
            lines.append("HEADLESS MODE: ON")
        return lines


class WifiUavDroneController:
    """Controller for WiFi UAV drones (K417, etc.).

    The BL-UAVSDK uses two ports:
      - Port 8800: video stream (START_STREAM + MJPEG fragments)
      - Port 8801: control commands (RC, camera switch, heartbeat)

    The video adapter creates the UDP socket and shares it here.
    RC commands target port 8801 to avoid contention with video on 8800.
    """

    DRONE_IP = "192.168.169.1"
    UDP_PORT = 8800          # video stream port (used by video adapter)
    CONTROL_PORT = 8800      # all traffic to 8800 (emulator-verified)

    def __init__(self, drone_ip: str = "192.168.169.1", bind_ip: str = ""):
        self.DRONE_IP = drone_ip
        self.UDP_PORT = 8800
        self.CONTROL_PORT = 8800
        self.bind_ip = bind_ip

        self.udp_socket: Optional[socket.socket] = None
        self.is_running = False
        self.is_connected = False
        self.device_type = 0

        # Rolling counters for RC packets
        self._ctr1 = 0x0000
        self._ctr2 = 0x0001
        self._ctr3 = 0x0002

        # Heartbeat: low-rate neutral RC packets to keep drone alive
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_running = False

        # K417 protocol engine (set when video starts)
        self._engine = None  # type: Optional[object]

        self.flight_controller = WifiUavFlightController(self._send_rc_raw)

    def connect(self) -> bool:
        """Mark as connected.  WiFi UAV doesn't need a handshake."""
        print(f"[wifi-uav] Connecting to {self.DRONE_IP} "
              f"(video={self.UDP_PORT}, ctrl={self.CONTROL_PORT}, "
              f"bind={self.bind_ip or 'auto'})...")

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

        # Heartbeat is started by drone_service AFTER video starts and the
        # video adapter's socket is shared with this controller.  The drone
        # requires ALL traffic from a single UDP source port.

        print("[wifi-uav] Connected (heartbeat deferred until video starts)")
        return True

    def set_shared_socket(self, sock: socket.socket) -> None:
        """Use the video protocol's duplex socket for RC commands."""
        if self.udp_socket and self.udp_socket is not sock:
            try:
                self.udp_socket.close()
            except Exception:
                pass
        self.udp_socket = sock

    def set_engine(self, engine) -> None:
        """Register the K417 protocol engine (handles all TX when active)."""
        self._engine = engine

    def disconnect(self):
        print("[wifi-uav] Disconnecting...")
        self._engine = None
        self._stop_heartbeat()
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

    def _start_heartbeat(self):
        """Start alternating RC + keepalive heartbeat at ~40Hz."""
        if self._heartbeat_running:
            return
        # Init commands deferred to heartbeat loop (after delay)
        self._heartbeat_running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="WifiUavHeartbeat"
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1.0)
            self._heartbeat_thread = None

    def _heartbeat_loop(self):
        """Heartbeat loop — idle when K417 engine is active.

        When the K417ProtocolEngine is running, it handles all TX (RC + ACK)
        at 40Hz.  The heartbeat just monitors and stays out of the way.
        """
        print("[wifi-uav] Heartbeat: idle (engine handles TX)")
        while self._heartbeat_running:
            time.sleep(1.0)

    def send_one_shot_rc(self, command_flag: int = 0x00):
        """Send a single RC packet with a command flag (e.g. calibrate=0x04).

        Works even when the flight controller is not armed.
        If engine is active, sends via engine's packet format instead.
        """
        if self._engine is not None:
            # Engine handles all TX — inject the command flag
            fc = self.flight_controller
            if command_flag == 0x01:
                fc._takeoff_flag = True
            elif command_flag == 0x02:
                fc._land_flag = True
            elif command_flag == 0x04:
                fc._calibrate_flag = True
            return

        controls = bytes([128, 128, 128, 128, command_flag & 0xFF, 0x02])
        checksum = 0
        for b in controls:
            checksum ^= b
        self._send_rc_raw(controls, checksum)

    def send_command(self, command: bytes, verbose: bool = False) -> bool:
        """Send raw bytes to the drone control port (8801)."""
        if not self.udp_socket:
            return False
        try:
            self.udp_socket.sendto(command, (self.DRONE_IP, self.CONTROL_PORT))
            if verbose:
                print(f"[wifi-uav] Sent: {command.hex()}")
            return True
        except Exception as e:
            print(f"[wifi-uav] Send error: {e}")
            return False

    # 88-byte RC header: carries stick data (byte 8=0x00, inner len=0x14=20).
    _RC_SHORT_HEADER = bytes([
        0xef, 0x02, 0x58, 0x00,   # magic + length=88
        0x02, 0x02, 0x00, 0x01,   # version
        0x00, 0x00, 0x00, 0x00,   # byte 8 = 0x00
    ])

    # 124-byte keepalive header: no stick data (byte 8=0x02, inner len=0x08=8).
    # This is the video keepalive that replaces START_STREAM after initial kick.
    _KEEPALIVE_HEADER = bytes([
        0xef, 0x02, 0x7c, 0x00,   # magic + length=124
        0x02, 0x02, 0x00, 0x01,   # version
        0x02, 0x00, 0x00, 0x00,   # byte 8 = 0x02
    ])

    _TAIL_CONSTANT = bytes([0x32, 0x4b, 0x14, 0x2d, 0x00, 0x00])

    # 25-byte init command from YN Fly: ef 20 type, ASCII config string
    _INIT_CMD = bytes([
        0xef, 0x20, 0x19, 0x00, 0x01, 0x67,
    ]) + b'<i=2^bf_ssid=cmd=2>'

    def _send_rc_raw(self, controls: bytes, checksum: int) -> None:
        """Build 88-byte short RC packet (YN Fly format) and send it."""
        if not self.udp_socket:
            return

        c1 = self._ctr1.to_bytes(2, "little")
        self._ctr1 = (self._ctr1 + 1) & 0xFFFF

        # 88-byte: header(12) + c1(2) + suffix(6) + controls(6) + pad(10)
        #   + checksum(1) + 0x99(1) + zeros(44) + tail(6) = 88
        pkt = bytearray()
        pkt += self._RC_SHORT_HEADER              # 12
        pkt += c1 + RC_COUNTER1_SUFFIX             # 8
        pkt += controls                            # 6
        pkt += RC_CONTROL_SUFFIX                   # 10
        pkt.append(checksum)                       # 1
        pkt += b'\x99'                             # 1
        pkt += bytes(44)                           # 44
        pkt += self._TAIL_CONSTANT                 # 6
        # total = 88

        try:
            self.udp_socket.sendto(bytes(pkt), (self.DRONE_IP, self.CONTROL_PORT))
        except OSError:
            pass

    def _send_keepalive(self) -> None:
        """Build 124-byte video keepalive packet (no stick data, inner len=0x08).

        Emulator format: header(12) + c1(2) + 00 00 08 00 00 00(6) + zeros(62)
          + tail(6) + c2(2) + COUNTER2_SUFFIX(18) + c3(2) + COUNTER3_SUFFIX(14) = 124
        """
        if not self.udp_socket:
            return

        c1 = self._ctr1.to_bytes(2, "little")
        c2 = self._ctr2.to_bytes(2, "little")
        c3 = self._ctr3.to_bytes(2, "little")
        self._ctr1 = (self._ctr1 + 1) & 0xFFFF
        self._ctr2 = (self._ctr2 + 1) & 0xFFFF
        self._ctr3 = (self._ctr3 + 1) & 0xFFFF

        pkt = bytearray()
        pkt += self._KEEPALIVE_HEADER              # 12
        pkt += c1                                  # 2
        pkt += bytes([0x00, 0x00, 0x08, 0x00, 0x00, 0x00])  # inner len=8, no 0x66
        pkt += bytes(62)                           # 62 zeros (no controls/checksum/marker)
        pkt += self._TAIL_CONSTANT                 # 6
        pkt += c2 + RC_COUNTER2_SUFFIX             # 20
        pkt += c3 + RC_COUNTER3_SUFFIX             # 16
        # total = 12+2+6+62+6+20+16 = 124

        try:
            self.udp_socket.sendto(bytes(pkt), (self.DRONE_IP, self.CONTROL_PORT))
        except OSError:
            pass

    def _send_init_cmd(self) -> None:
        """Send the 25-byte ef 20 init command (from YN Fly startup sequence)."""
        if not self.udp_socket:
            return
        try:
            self.udp_socket.sendto(self._INIT_CMD, (self.DRONE_IP, self.CONTROL_PORT))
        except OSError:
            pass

    def switch_camera(self, camera_num: int) -> bool:
        """Switch between front (1) and bottom (2) cameras."""
        if not self.udp_socket:
            return False
        if camera_num == 1:
            cmd = CAMERA_FRONT
        elif camera_num == 2:
            cmd = CAMERA_BOTTOM
        else:
            return False
        try:
            self.udp_socket.sendto(cmd, (self.DRONE_IP, self.CONTROL_PORT))
            print(f"[wifi-uav] Camera switch to {camera_num}: {cmd.hex(' ')}")
            return True
        except OSError as e:
            print(f"[wifi-uav] Camera switch error: {e}")
            return False

    def switch_screen_mode(self, mode: int) -> bool:
        """WiFi UAV doesn't support screen mode switching."""
        return False

    # Compatibility stubs matching TYVYXDroneControllerAdvanced interface
    CMD_HEARTBEAT = b""
    CMD_INITIALIZE = b""
    CMD_START_VIDEO = b"\xef\x00\x04\x00"
    CMD_CAMERA_1 = CAMERA_FRONT
    CMD_CAMERA_2 = CAMERA_BOTTOM
