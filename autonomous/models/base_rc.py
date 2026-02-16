"""
Base RC Model

Abstract base class for drone control models.
Adapted from turbodrone architecture for TEKY.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from dataclasses import dataclass
import time

from .control_profile import ControlProfile, StickRange, get_profile


@dataclass
class ControlState:
    """Current control state"""
    throttle: float
    yaw: float
    pitch: float
    roll: float
    timestamp: float

    def __post_init__(self):
        self.timestamp = time.time()


class BaseRCModel(ABC):
    """
    Abstract base class for RC drone control models

    Provides common interface for all drones regardless of protocol.
    Handles control value management, profiles, and state tracking.

    Subclasses implement protocol-specific packet building.
    """

    def __init__(
        self,
        stick_range: StickRange,
        profile_name: str = "normal",
        update_rate_hz: float = 80.0
    ):
        """
        Initialize RC model

        Args:
            stick_range: Control input range definition
            profile_name: Control profile ("normal", "precise", "aggressive", "autonomous")
            update_rate_hz: Control update rate (Hz)
        """
        self.stick_range = stick_range
        self.profile = get_profile(profile_name)
        self.update_rate_hz = update_rate_hz
        self.update_interval = 1.0 / update_rate_hz

        # Current control values (in stick range)
        self._throttle = stick_range.mid
        self._yaw = stick_range.mid
        self._pitch = stick_range.mid
        self._roll = stick_range.mid

        # Target control values (for acceleration/deceleration)
        self._target_throttle = stick_range.mid
        self._target_yaw = stick_range.mid
        self._target_pitch = stick_range.mid
        self._target_roll = stick_range.mid

        # Command flags
        self._takeoff_flag = False
        self._land_flag = False
        self._stop_flag = False

        # State tracking
        self._last_update = time.time()
        self._is_armed = False

    # Properties for control values
    @property
    def throttle(self) -> float:
        return self._throttle

    @throttle.setter
    def throttle(self, value: float):
        self._target_throttle = max(self.stick_range.min, min(value, self.stick_range.max))

    @property
    def yaw(self) -> float:
        return self._yaw

    @yaw.setter
    def yaw(self, value: float):
        self._target_yaw = max(self.stick_range.min, min(value, self.stick_range.max))

    @property
    def pitch(self) -> float:
        return self._pitch

    @pitch.setter
    def pitch(self, value: float):
        self._target_pitch = max(self.stick_range.min, min(value, self.stick_range.max))

    @property
    def roll(self) -> float:
        return self._roll

    @roll.setter
    def roll(self, value: float):
        self._target_roll = max(self.stick_range.min, min(value, self.stick_range.max))

    def set_profile(self, profile_name: str):
        """Change control profile"""
        self.profile = get_profile(profile_name)

    def set_normalized_controls(
        self,
        throttle: Optional[float] = None,
        yaw: Optional[float] = None,
        pitch: Optional[float] = None,
        roll: Optional[float] = None
    ):
        """
        Set controls using normalized values (-1.0 to +1.0)

        Args:
            throttle, yaw, pitch, roll: Normalized values (-1.0 to +1.0)
                                        None = no change
        """
        if throttle is not None:
            self.throttle = self.stick_range.denormalize(throttle)
        if yaw is not None:
            self.yaw = self.stick_range.denormalize(yaw)
        if pitch is not None:
            self.pitch = self.stick_range.denormalize(pitch)
        if roll is not None:
            self.roll = self.stick_range.denormalize(roll)

    def get_normalized_controls(self) -> Dict[str, float]:
        """
        Get current controls as normalized values (-1.0 to +1.0)

        Returns:
            Dictionary with throttle, yaw, pitch, roll
        """
        return {
            'throttle': self.stick_range.normalize(self._throttle),
            'yaw': self.stick_range.normalize(self._yaw),
            'pitch': self.stick_range.normalize(self._pitch),
            'roll': self.stick_range.normalize(self._roll)
        }

    def update(self, dt: Optional[float] = None) -> bool:
        """
        Update control values with acceleration/deceleration

        Args:
            dt: Time delta (seconds). If None, calculates from last update.

        Returns:
            True if values changed
        """
        current_time = time.time()
        if dt is None:
            dt = current_time - self._last_update
        self._last_update = current_time

        # Avoid division by zero
        if dt <= 0:
            dt = self.update_interval

        changed = False

        # Update each axis with accel/decel curves
        changed |= self._update_axis('throttle', dt)
        changed |= self._update_axis('yaw', dt)
        changed |= self._update_axis('pitch', dt)
        changed |= self._update_axis('roll', dt)

        return changed

    def _update_axis(self, axis: str, dt: float) -> bool:
        """
        Update single axis with acceleration/deceleration

        Args:
            axis: 'throttle', 'yaw', 'pitch', or 'roll'
            dt: Time delta

        Returns:
            True if value changed
        """
        current = getattr(self, f'_{axis}')
        target = getattr(self, f'_target_{axis}')

        if abs(target - current) < 0.01:
            return False

        # Calculate normalized difference
        diff_normalized = self.stick_range.normalize(target) - self.stick_range.normalize(current)

        # Check if immediate response threshold met
        if abs(diff_normalized) < self.profile.immediate:
            setattr(self, f'_{axis}', target)
            return True

        # Apply acceleration or deceleration
        if abs(diff_normalized) > 0.01:
            rate = self.profile.acceleration if target > current else self.profile.deceleration
            step = rate * dt * (self.stick_range.max - self.stick_range.min)

            if target > current:
                new_value = min(current + step, target)
            else:
                new_value = max(current - step, target)

            setattr(self, f'_{axis}', new_value)
            return True

        return False

    def takeoff(self):
        """Trigger takeoff command"""
        self._takeoff_flag = True
        self._is_armed = True

    def land(self):
        """Trigger land command"""
        self._land_flag = True

    def stop(self):
        """Trigger emergency stop"""
        self._stop_flag = True
        self.reset_controls()

    def reset_controls(self):
        """Reset all controls to neutral"""
        self.throttle = self.stick_range.mid
        self.yaw = self.stick_range.mid
        self.pitch = self.stick_range.mid
        self.roll = self.stick_range.mid

        self._throttle = self.stick_range.mid
        self._yaw = self.stick_range.mid
        self._pitch = self.stick_range.mid
        self._roll = self.stick_range.mid

    def get_control_state(self) -> ControlState:
        """Get current control state"""
        return ControlState(
            throttle=self._throttle,
            yaw=self._yaw,
            pitch=self._pitch,
            roll=self._roll,
            timestamp=self._last_update
        )

    def clear_flags(self):
        """Clear command flags (call after packet is sent)"""
        self._takeoff_flag = False
        self._land_flag = False
        self._stop_flag = False

    @abstractmethod
    def build_control_packet(self) -> bytes:
        """
        Build protocol-specific control packet

        Subclasses implement this to create the actual UDP packet
        based on current control values and flags.

        Returns:
            Packet bytes ready to send
        """
        pass

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"T={self._throttle:.1f}, Y={self._yaw:.1f}, "
            f"P={self._pitch:.1f}, R={self._roll:.1f}, "
            f"profile={self.profile.name})"
        )
