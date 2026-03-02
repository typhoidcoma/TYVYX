"""
Autopilot Service — Closed-loop position hold (drift fight).

Event-driven: PID fires on every position update callback (~21Hz),
giving zero latency between perception and control. A low-rate
watchdog thread handles safety (stale data → center sticks).

Throttle and yaw remain under manual (keyboard) control — this service
only fights XY drift using optical flow feedback.

Usage:
    autopilot_service.enable()   # hold at current position
    autopilot_service.disable()  # revert to center sticks
"""

import logging
import threading
import time
from typing import Optional, Dict, Any

from autonomous.navigation.pid_controller import PIDController
from autonomous.services.position_service import position_service

logger = logging.getLogger(__name__)


class AutopilotService:
    """Singleton service for closed-loop position hold."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # State
        self._enabled = False
        self._target_x = 0.0
        self._target_y = 0.0

        # PID controllers (XY only — no altitude, no yaw)
        self._pid_x = PIDController(
            kp=1.0, ki=0.1, kd=0.05,
            integral_limit=10.0,
            output_min=-1.0, output_max=1.0,
        )
        self._pid_y = PIDController(
            kp=1.0, ki=0.1, kd=0.05,
            integral_limit=10.0,
            output_min=-1.0, output_max=1.0,
        )

        # Watchdog thread (safety: detect stale data)
        self._watchdog_thread = None   # type: Optional[threading.Thread]
        self._stop_event = threading.Event()

        # Configuration
        self.stick_scale = 40.0       # PID ±1.0 → ±40 stick units from center
        self.min_features = 10        # below this → safe hover
        self.stale_timeout = 1.0      # seconds without position update → safe hover
        self.NEUTRAL = 128

        # Axis mapping: which PID axis maps to which stick.
        # pid_x → pitch (forward/back), pid_y → roll (left/right).
        # Flip sign if drone corrects in the wrong direction.
        self.pitch_sign = 1.0
        self.roll_sign = 1.0

        # Telemetry (for UI)
        self._last_output = {
            'roll': 128, 'pitch': 128,
            'error_x': 0.0, 'error_y': 0.0,
            'pid_x': 0.0, 'pid_y': 0.0,
            'safe_mode': False,
            'feature_count': 0,
        }  # type: Dict[str, Any]
        self._state_lock = threading.Lock()
        self._last_tick_time = 0.0
        self._tick_count = 0

        self._initialized = True
        logger.info("AutopilotService singleton created")

    # ── Public API ──

    def enable(self, target_x=None, target_y=None):
        # type: (Optional[float], Optional[float]) -> None
        """Enable position hold. Default target = current position."""
        if self._enabled:
            logger.warning("[autopilot] Already enabled")
            return

        # Auto-start position tracking if initialized but not enabled
        if not position_service.is_enabled():
            if position_service.optical_flow is not None:
                position_service.start()
                logger.info("[autopilot] Auto-started position tracking")
            else:
                raise RuntimeError("Position tracking not initialized")

        # Require FC to be armed (deferred import to avoid circular)
        from autonomous.services.drone_service import drone_service
        fc = drone_service._get_fc()
        if not fc or not getattr(fc, 'is_active', False):
            raise RuntimeError("Flight controller must be armed first")

        # Set target to current position if not specified
        pos = position_service.get_position()
        if target_x is None:
            self._target_x = pos['position']['x']
        else:
            self._target_x = target_x
        if target_y is None:
            self._target_y = pos['position']['y']
        else:
            self._target_y = target_y

        # Reset PIDs
        self._pid_x.reset()
        self._pid_y.reset()
        self._tick_count = 0
        self._last_tick_time = time.time()

        # Register callback — PID fires on every position update (~21Hz)
        position_service.on_update(self._on_position_update)

        # Start watchdog (safety: detect stale data at 5Hz)
        self._stop_event.clear()
        self._enabled = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="AutopilotWatchdog",
        )
        self._watchdog_thread.start()

        logger.info(
            "[autopilot] Position hold ENABLED at (%.3f, %.3f) — event-driven",
            self._target_x, self._target_y,
        )

    def disable(self):
        # type: () -> None
        """Disable position hold. Reverts to center sticks."""
        if not self._enabled:
            return

        self._enabled = False

        # Unregister callback
        position_service.remove_on_update(self._on_position_update)

        # Stop watchdog
        self._stop_event.set()
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=2.0)
            self._watchdog_thread = None

        self._send_neutral()
        logger.info("[autopilot] Position hold DISABLED")

    def set_target(self, x, y):
        # type: (float, float) -> None
        """Update target position while hold is active."""
        self._target_x = x
        self._target_y = y
        # Reset integral to avoid windup on large target jumps
        self._pid_x.integral = 0.0
        self._pid_y.integral = 0.0
        logger.info("[autopilot] Target updated to (%.3f, %.3f)", x, y)

    def is_enabled(self):
        # type: () -> bool
        return self._enabled

    def get_state(self):
        # type: () -> Dict[str, Any]
        """Get current autopilot state for API/UI."""
        with self._state_lock:
            output = dict(self._last_output)
        pos_data = position_service.get_position()
        return {
            'enabled': self._enabled,
            'target': {'x': self._target_x, 'y': self._target_y},
            'output': output,
            'altitude': pos_data.get('altitude', 0.0),
            'pid_x': self._pid_x.get_state(),
            'pid_y': self._pid_y.get_state(),
            'config': {
                'stick_scale': self.stick_scale,
                'min_features': self.min_features,
                'stale_timeout': self.stale_timeout,
                'pitch_sign': self.pitch_sign,
                'roll_sign': self.roll_sign,
            },
        }

    def set_gains(self, axis, kp=None, ki=None, kd=None):
        # type: (str, Optional[float], Optional[float], Optional[float]) -> None
        """Live-tune PID gains."""
        pid = self._pid_x if axis == 'x' else self._pid_y
        pid.set_gains(kp, ki, kd)
        logger.info(
            "[autopilot] %s gains: kp=%.3f ki=%.3f kd=%.3f",
            axis, pid.kp, pid.ki, pid.kd,
        )

    # ── Event-driven control (called from position_service thread) ──

    def _on_position_update(self):
        # type: () -> None
        """Callback fired by position_service after each successful update.
        Runs PID and sends sticks — zero latency between perception and control."""
        if not self._enabled:
            return
        try:
            self._control_tick()
        except Exception as e:
            logger.error("[autopilot] Tick error: %s", e)

    def _control_tick(self):
        # type: () -> None
        """One PID iteration. Called from position update callback (~21Hz)."""
        from autonomous.services.drone_service import drone_service

        # 1. Check FC is armed
        fc = drone_service._get_fc()
        if not fc or not getattr(fc, 'is_active', False):
            return

        # 2. Read position state
        pos_data = position_service.get_position()
        if not pos_data['enabled']:
            self._send_neutral()
            return

        # 3. Safety check: enough features?
        feature_count = pos_data.get('feature_count', 0)
        safe_mode = feature_count < self.min_features

        if safe_mode:
            with self._state_lock:
                self._last_output['safe_mode'] = True
                self._last_output['feature_count'] = feature_count
            self._send_neutral()
            return

        # 4. Compute PID
        now = time.time()
        dt = now - self._last_tick_time if self._last_tick_time > 0 else 0.05
        self._last_tick_time = now

        current_x = pos_data['position']['x']
        current_y = pos_data['position']['y']
        error_x = self._target_x - current_x
        error_y = self._target_y - current_y

        pid_out_x = self._pid_x.update(error_x, dt)
        pid_out_y = self._pid_y.update(error_y, dt)

        # 5. Map PID output → stick values
        pitch_stick = int(self.NEUTRAL + pid_out_x * self.pitch_sign * self.stick_scale)
        roll_stick = int(self.NEUTRAL + pid_out_y * self.roll_sign * self.stick_scale)

        # Clamp to safe range
        pitch_stick = max(40, min(220, pitch_stick))
        roll_stick = max(40, min(220, roll_stick))

        # 6. Send to flight controller (only roll and pitch)
        fc.set_axes(roll=roll_stick, pitch=pitch_stick)

        # 7. Update telemetry
        self._tick_count += 1
        with self._state_lock:
            self._last_output = {
                'roll': roll_stick,
                'pitch': pitch_stick,
                'error_x': error_x,
                'error_y': error_y,
                'pid_x': pid_out_x,
                'pid_y': pid_out_y,
                'safe_mode': False,
                'feature_count': feature_count,
            }

        # Periodic stats
        if self._tick_count <= 3 or self._tick_count % 100 == 0:
            logger.info(
                "[autopilot] tick=%d  dt=%.1fms  err=(%.3f, %.3f)  "
                "pid=(%.3f, %.3f)  sticks=(%d, %d)  features=%d",
                self._tick_count, dt * 1000,
                error_x, error_y, pid_out_x, pid_out_y,
                pitch_stick, roll_stick, feature_count,
            )

    # ── Watchdog (safety thread at 5Hz) ──

    def _watchdog_loop(self):
        # type: () -> None
        """Low-rate safety check: if position data goes stale, center sticks."""
        logger.info("[autopilot] Watchdog started")
        while not self._stop_event.is_set():
            self._stop_event.wait(0.2)  # 5Hz

            if not self._enabled:
                continue

            # Check for stale position data
            pos_data = position_service.get_position()
            last_update = pos_data.get('timestamp', 0)
            age = time.time() - last_update if last_update else 999.0

            if age > self.stale_timeout:
                with self._state_lock:
                    self._last_output['safe_mode'] = True
                self._send_neutral()

        logger.info("[autopilot] Watchdog stopped")

    def _send_neutral(self):
        # type: () -> None
        """Send center sticks (safe hover)."""
        from autonomous.services.drone_service import drone_service
        fc = drone_service._get_fc()
        if fc and getattr(fc, 'is_active', False):
            fc.set_axes(roll=self.NEUTRAL, pitch=self.NEUTRAL)


# Global singleton
autopilot_service = AutopilotService()
