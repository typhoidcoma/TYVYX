"""
Control Profile System

Defines control behavior characteristics like acceleration, deceleration,
and exponential response curves. Adapted from turbodrone architecture.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class StickRange:
    """
    Stick input range definition

    Defines the min/mid/max values for control inputs.
    These are the "logical" values before mapping to drone protocol values.
    """
    min: float
    mid: float
    max: float

    def __post_init__(self):
        if not (self.min < self.mid < self.max):
            raise ValueError(f"Invalid stick range: min={self.min}, mid={self.mid}, max={self.max}")

    def normalize(self, value: float) -> float:
        """
        Normalize value from stick range to -1.0 to +1.0

        Args:
            value: Value in stick range (min to max)

        Returns:
            Normalized value (-1.0 to +1.0)
        """
        if value < self.mid:
            # Map min->mid to -1.0->0.0
            return (value - self.mid) / (self.mid - self.min)
        else:
            # Map mid->max to 0.0->+1.0
            return (value - self.mid) / (self.max - self.mid)

    def denormalize(self, normalized: float) -> float:
        """
        Convert normalized value (-1.0 to +1.0) back to stick range

        Args:
            normalized: Value in range -1.0 to +1.0

        Returns:
            Value in stick range
        """
        if normalized < 0:
            # Map -1.0->0.0 to min->mid
            return self.mid + normalized * (self.mid - self.min)
        else:
            # Map 0.0->+1.0 to mid->max
            return self.mid + normalized * (self.max - self.mid)


@dataclass
class ControlProfile:
    """
    Control behavior profile

    Defines how controls respond to input:
    - acceleration: How quickly control values increase (higher = faster)
    - deceleration: How quickly control values decrease (higher = faster)
    - expo: Exponential curve (0=linear, >0=more gradual near center, >1=aggressive)
    - immediate: Threshold for immediate response (bypass accel curve)

    Based on turbodrone's proven profiles.
    """
    name: str
    acceleration: float
    deceleration: float
    expo: float
    immediate: float = 0.02

    def apply_expo(self, value: float) -> float:
        """
        Apply exponential curve to normalized value

        Args:
            value: Normalized value (-1.0 to +1.0)

        Returns:
            Expo-adjusted value
        """
        if self.expo == 0:
            return value

        sign = 1 if value >= 0 else -1
        abs_val = abs(value)

        # Exponential mapping: output = (input ^ expo)
        expo_val = abs_val ** self.expo

        return sign * expo_val


# Predefined profiles (adapted from turbodrone)
PROFILES: Dict[str, ControlProfile] = {
    "normal": ControlProfile(
        name="normal",
        acceleration=2.08,
        deceleration=4.86,
        expo=0.5,
        immediate=0.02
    ),
    "precise": ControlProfile(
        name="precise",
        acceleration=1.39,
        deceleration=5.56,
        expo=0.3,
        immediate=0.01
    ),
    "aggressive": ControlProfile(
        name="aggressive",
        acceleration=4.17,
        deceleration=3.89,
        expo=1.5,
        immediate=0.11
    ),
    "autonomous": ControlProfile(
        name="autonomous",
        acceleration=1.0,
        deceleration=2.0,
        expo=0.0,  # Linear for PID control
        immediate=0.0
    )
}


def get_profile(name: str) -> ControlProfile:
    """Get control profile by name"""
    return PROFILES.get(name, PROFILES["normal"])
