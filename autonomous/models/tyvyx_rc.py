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
    RC control model for TYVYX drone

    Protocol details (from tyvyx/drone_controller.py):
    - UDP port: 7099
    - Heartbeat: [0x01, 0x01]
    - Camera switch: [0x06, 0x01] or [0x06, 0x02]
    - Screen mode: [0x09, 0x01] or [0x09, 0x02]

    Flight Control (EXPERIMENTAL - from tyvyx/drone_controller_advanced.py):
    - Format: [CMD_ID, throttle, yaw, pitch, roll, checksum]
    - CMD_ID: 0x50
    - Values: 0-255 (128 = neutral)
    - Checksum: sum of all bytes & 0xFF

    Note: This is experimental and needs validation through Phase 1 testing!
    """

    # TYVYX protocol constants
    CMD_ID_FLIGHT = 0x50
    CMD_HEARTBEAT = bytes([0x01, 0x01])
    CMD_CAMERA_1 = bytes([0x06, 0x01])
    CMD_CAMERA_2 = bytes([0x06, 0x02])
    CMD_SCREEN_1 = bytes([0x09, 0x01])
    CMD_SCREEN_2 = bytes([0x09, 0x02])

    # TYVYX stick range (from existing controller)
    # This is the "logical" range - needs calibration!
    DEFAULT_STICK_RANGE = StickRange(min=0.0, mid=128.0, max=255.0)

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
        Build TYVYX flight control packet

        Format (EXPERIMENTAL):
        [CMD_ID, throttle, yaw, pitch, roll, checksum]

        Where:
        - CMD_ID = 0x50
        - throttle, yaw, pitch, roll: 0-255 (128 = neutral)
        - checksum = (sum of all bytes) & 0xFF

        Returns:
            6-byte control packet
        """
        # Convert from stick range to protocol range (0-255)
        throttle_byte = int(self._throttle)
        yaw_byte = int(self._yaw)
        pitch_byte = int(self._pitch)
        roll_byte = int(self._roll)

        # Clamp to valid range
        throttle_byte = max(0, min(255, throttle_byte))
        yaw_byte = max(0, min(255, yaw_byte))
        pitch_byte = max(0, min(255, pitch_byte))
        roll_byte = max(0, min(255, roll_byte))

        # Build packet
        packet = [
            self.CMD_ID_FLIGHT,
            throttle_byte,
            yaw_byte,
            pitch_byte,
            roll_byte
        ]

        # Calculate checksum
        checksum = sum(packet) & 0xFF
        packet.append(checksum)

        return bytes(packet)

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
