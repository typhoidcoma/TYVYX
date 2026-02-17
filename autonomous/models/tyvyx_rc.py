"""
TYVYX RC Model

Implements BaseRCModel for TYVYX WiFi drone.
Based on reverse-engineered protocol from existing tyvyx/ package.
"""

from typing import Optional
from .base_rc import BaseRCModel, ControlState
from .control_profile import StickRange, PROFILES


class TYVYXRCModel(BaseRCModel):
    """
    RC control model for TYVYX drone (E88Pro-proven protocol)

    Protocol details:
    - UDP port: 7099
    - Heartbeat: [0x01, 0x01]
    - Init: [0x64]
    - Start Video (RTSP activation): [0x08, 0x01]
    - Camera switch: [0x06, 0x01] or [0x06, 0x02]
    - Screen mode: [0x09, 0x01] or [0x09, 0x02]

    Flight Control (E88Pro-proven format):
    - Packet: [0x03, 0x66, roll, pitch, throttle, yaw, flags, xor_checksum, 0x99]
    - Values: 50-200 (128 = neutral)
    - Checksum: XOR of roll ^ pitch ^ throttle ^ yaw ^ flags
    - Flags: takeoff=0x01, land=0x02, flip=0x08, headless=0x10, calibrate=0x80
    """

    # TYVYX protocol constants
    CMD_HEARTBEAT = bytes([0x01, 0x01])
    CMD_INIT = bytes([0x64])
    CMD_START_VIDEO = bytes([0x08, 0x01])
    CMD_CAMERA_1 = bytes([0x06, 0x01])
    CMD_CAMERA_2 = bytes([0x06, 0x02])
    CMD_SCREEN_1 = bytes([0x09, 0x01])
    CMD_SCREEN_2 = bytes([0x09, 0x02])

    # E88Pro-proven stick range
    DEFAULT_STICK_RANGE = StickRange(min=50.0, mid=128.0, max=200.0)

    def __init__(
        self,
        stick_range: Optional[StickRange] = None,
        profile_name: str = "normal",
        update_rate_hz: float = 80.0
    ):
        """
        Initialize TYVYX RC model

        Args:
            stick_range: Control range (default: 0-128-255)
            profile_name: Control profile
            update_rate_hz: Update rate (Hz)
        """
        if stick_range is None:
            stick_range = self.DEFAULT_STICK_RANGE

        super().__init__(stick_range, profile_name, update_rate_hz)

        # TYVYX-specific state
        self._camera_num = 1
        self._screen_mode = 1

    def build_control_packet(self) -> bytes:
        """
        Build TYVYX flight control packet (E88Pro-proven format).

        9-byte packet: [0x03, 0x66, roll, pitch, throttle, yaw, flags, xor, 0x99]

        Returns:
            9-byte control packet
        """
        roll_byte = max(50, min(200, int(self._roll)))
        pitch_byte = max(50, min(200, int(self._pitch)))
        throttle_byte = max(50, min(200, int(self._throttle)))
        yaw_byte = max(50, min(200, int(self._yaw)))

        # Build flags from model state
        flags = 0
        if getattr(self, '_takeoff_flag', False):
            flags |= 0x01
        if getattr(self, '_land_flag', False):
            flags |= 0x02

        # XOR checksum
        xor = roll_byte ^ pitch_byte ^ throttle_byte ^ yaw_byte ^ flags

        return bytes([
            0x03,           # command prefix
            0x66,           # protocol marker
            roll_byte,
            pitch_byte,
            throttle_byte,
            yaw_byte,
            flags,
            xor,
            0x99,           # end marker
        ])

    def build_heartbeat_packet(self) -> bytes:
        """Build heartbeat packet"""
        return self.CMD_HEARTBEAT

    def build_camera_switch_packet(self, camera_num: int) -> bytes:
        """
        Build camera switch packet

        Args:
            camera_num: 1 or 2

        Returns:
            Camera switch command
        """
        self._camera_num = camera_num
        if camera_num == 1:
            return self.CMD_CAMERA_1
        elif camera_num == 2:
            return self.CMD_CAMERA_2
        else:
            raise ValueError(f"Invalid camera number: {camera_num}")

    def build_screen_mode_packet(self, mode: int) -> bytes:
        """
        Build screen mode packet

        Args:
            mode: 1 or 2

        Returns:
            Screen mode command
        """
        self._screen_mode = mode
        if mode == 1:
            return self.CMD_SCREEN_1
        elif mode == 2:
            return self.CMD_SCREEN_2
        else:
            raise ValueError(f"Invalid screen mode: {mode}")

    @classmethod
    def from_calibration(cls, calibration_data: dict, profile_name: str = "normal") -> 'TYVYXRCModel':
        """
        Create TYVYX RC model from calibration data

        Args:
            calibration_data: Dict with 'throttle', 'pitch', 'roll', 'yaw' velocity maps
            profile_name: Control profile to use

        Returns:
            Configured TYVYXRCModel
        """
        # Extract hover value for throttle (this is the "mid" point)
        hover_value = calibration_data.get('throttle', {}).get('hover_value', 128.0)

        # For now, use symmetric range around hover value
        # This can be refined with actual calibration data
        stick_range = StickRange(min=0.0, mid=hover_value, max=255.0)

        return cls(stick_range=stick_range, profile_name=profile_name)

    def __repr__(self):
        return (
            f"TYVYXRCModel("
            f"T={self._throttle:.0f}, Y={self._yaw:.0f}, "
            f"P={self._pitch:.0f}, R={self._roll:.0f}, "
            f"profile={self.profile.name}, "
            f"cam={self._camera_num}, screen={self._screen_mode})"
        )


# Predefined TYVYX RC model instances
def create_tyvyx_rc(profile: str = "normal") -> TYVYXRCModel:
    """
    Create TYVYX RC model with default settings

    Args:
        profile: Control profile name

    Returns:
        Configured TYVYXRCModel
    """
    return TYVYXRCModel(profile_name=profile)


def create_autonomous_tyvyx_rc() -> TYVYXRCModel:
    """
    Create TYVYX RC model optimized for autonomous control

    Uses linear response (no expo) for PID control

    Returns:
        TYVYXRCModel configured for autonomous operation
    """
    return TYVYXRCModel(profile_name="autonomous", update_rate_hz=50.0)
