"""
PID Controller for Drone Position Control

Implements PID (Proportional-Integral-Derivative) controllers for
stabilizing drone position and tracking targets.
"""

import time
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class PIDGains:
    """PID controller gains"""
    kp: float  # Proportional gain
    ki: float  # Integral gain
    kd: float  # Derivative gain

    # Anti-windup limits
    integral_limit: float = 10.0

    # Output limits
    output_min: float = -100.0
    output_max: float = 100.0


class PIDController:
    """
    Generic PID controller implementation

    Usage:
        pid = PIDController(kp=1.0, ki=0.1, kd=0.05)
        while True:
            current = get_current_position()
            target = get_target_position()
            error = target - current
            output = pid.update(error, dt)
            apply_control(output)
    """

    def __init__(
        self,
        kp: float = 1.0,
        ki: float = 0.0,
        kd: float = 0.0,
        integral_limit: float = 10.0,
        output_min: float = -100.0,
        output_max: float = 100.0
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral_limit = integral_limit
        self.output_min = output_min
        self.output_max = output_max

        # State variables
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time: Optional[float] = None

    def update(self, error: float, dt: Optional[float] = None) -> float:
        """
        Update PID controller with new error value

        Args:
            error: Current error (target - current)
            dt: Time delta since last update (seconds).
                If None, will calculate automatically.

        Returns:
            Control output value
        """
        # Calculate dt if not provided
        current_time = time.time()
        if dt is None:
            if self.last_time is not None:
                dt = current_time - self.last_time
            else:
                dt = 0.0
        self.last_time = current_time

        # Avoid division by zero
        if dt <= 0:
            dt = 0.01

        # Proportional term
        p_term = self.kp * error

        # Integral term with anti-windup
        self.integral += error * dt
        self.integral = max(min(self.integral, self.integral_limit), -self.integral_limit)
        i_term = self.ki * self.integral

        # Derivative term
        derivative = (error - self.last_error) / dt
        d_term = self.kd * derivative

        # Store for next iteration
        self.last_error = error

        # Calculate output
        output = p_term + i_term + d_term

        # Clamp output
        output = max(min(output, self.output_max), self.output_min)

        return output

    def reset(self):
        """Reset controller state"""
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = None

    def set_gains(self, kp: Optional[float] = None, ki: Optional[float] = None, kd: Optional[float] = None):
        """Update PID gains"""
        if kp is not None:
            self.kp = kp
        if ki is not None:
            self.ki = ki
        if kd is not None:
            self.kd = kd

    def get_state(self) -> dict:
        """Get current controller state (for debugging/tuning)"""
        return {
            "kp": self.kp,
            "ki": self.ki,
            "kd": self.kd,
            "integral": self.integral,
            "last_error": self.last_error
        }


class DronePositionController:
    """
    High-level position controller for drone using separate PIDs for each axis

    This class manages X, Y, Z position control and converts position errors
    to velocity commands, which are then mapped to drone control values.
    """

    def __init__(
        self,
        pid_x: Optional[PIDController] = None,
        pid_y: Optional[PIDController] = None,
        pid_z: Optional[PIDController] = None,
        pid_yaw: Optional[PIDController] = None
    ):
        # Create default PIDs if not provided
        self.pid_x = pid_x or PIDController(kp=1.0, ki=0.1, kd=0.05, output_min=-2.0, output_max=2.0)
        self.pid_y = pid_y or PIDController(kp=1.0, ki=0.1, kd=0.05, output_min=-2.0, output_max=2.0)
        self.pid_z = pid_z or PIDController(kp=1.2, ki=0.1, kd=0.05, output_min=-1.0, output_max=1.0)
        self.pid_yaw = pid_yaw or PIDController(kp=0.8, ki=0.0, kd=0.1, output_min=-90.0, output_max=90.0)

        # Target position
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0
        self.target_yaw = 0.0

    def set_target(self, x: float, y: float, z: float, yaw: float = 0.0):
        """Set target position"""
        self.target_x = x
        self.target_y = y
        self.target_z = z
        self.target_yaw = yaw

    def update(
        self,
        current_x: float,
        current_y: float,
        current_z: float,
        current_yaw: float = 0.0,
        dt: Optional[float] = None
    ) -> dict:
        """
        Update position controller

        Args:
            current_x, current_y, current_z: Current position
            current_yaw: Current heading (degrees)
            dt: Time delta

        Returns:
            Dictionary with velocity commands:
            {
                'vx': forward/back velocity (m/s),
                'vy': left/right velocity (m/s),
                'vz': up/down velocity (m/s),
                'vyaw': rotation velocity (deg/s)
            }
        """
        # Calculate errors
        error_x = self.target_x - current_x
        error_y = self.target_y - current_y
        error_z = self.target_z - current_z
        error_yaw = self.target_yaw - current_yaw

        # Normalize yaw error to [-180, 180]
        while error_yaw > 180:
            error_yaw -= 360
        while error_yaw < -180:
            error_yaw += 360

        # Update PIDs to get velocity commands
        vx = self.pid_x.update(error_x, dt)
        vy = self.pid_y.update(error_y, dt)
        vz = self.pid_z.update(error_z, dt)
        vyaw = self.pid_yaw.update(error_yaw, dt)

        return {
            'vx': vx,
            'vy': vy,
            'vz': vz,
            'vyaw': vyaw,
            'error_x': error_x,
            'error_y': error_y,
            'error_z': error_z,
            'error_yaw': error_yaw
        }

    def reset(self):
        """Reset all PID controllers"""
        self.pid_x.reset()
        self.pid_y.reset()
        self.pid_z.reset()
        self.pid_yaw.reset()

    def is_at_target(self, tolerance: float = 0.3, yaw_tolerance: float = 10.0) -> bool:
        """
        Check if drone is at target position within tolerance

        Args:
            tolerance: Position tolerance in meters
            yaw_tolerance: Yaw tolerance in degrees

        Returns:
            True if at target
        """
        # This requires the last update's errors
        # In practice, you'd compare current position against target
        # For now, return False (will be checked externally)
        return False

    def tune_gains(self, axis: str, kp: Optional[float] = None, ki: Optional[float] = None, kd: Optional[float] = None):
        """
        Tune PID gains for a specific axis

        Args:
            axis: 'x', 'y', 'z', or 'yaw'
            kp, ki, kd: New gain values (None = no change)
        """
        if axis == 'x':
            self.pid_x.set_gains(kp, ki, kd)
        elif axis == 'y':
            self.pid_y.set_gains(kp, ki, kd)
        elif axis == 'z':
            self.pid_z.set_gains(kp, ki, kd)
        elif axis == 'yaw':
            self.pid_yaw.set_gains(kp, ki, kd)
        else:
            raise ValueError(f"Unknown axis: {axis}")

    def get_state(self) -> dict:
        """Get state of all PIDs (for monitoring/debugging)"""
        return {
            'target': {
                'x': self.target_x,
                'y': self.target_y,
                'z': self.target_z,
                'yaw': self.target_yaw
            },
            'pid_x': self.pid_x.get_state(),
            'pid_y': self.pid_y.get_state(),
            'pid_z': self.pid_z.get_state(),
            'pid_yaw': self.pid_yaw.get_state()
        }


if __name__ == "__main__":
    # Simple test
    print("Testing PID Controller...")

    pid = PIDController(kp=1.0, ki=0.1, kd=0.05)

    # Simulate reaching target
    target = 10.0
    current = 0.0
    dt = 0.1

    print(f"Target: {target}")
    for i in range(50):
        error = target - current
        output = pid.update(error, dt)
        current += output * dt  # Simple integration

        if i % 5 == 0:
            print(f"Step {i}: current={current:.2f}, error={error:.2f}, output={output:.2f}")

    print("\n✅ PID test complete")
