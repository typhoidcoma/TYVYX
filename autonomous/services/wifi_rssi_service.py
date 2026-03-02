"""
WiFi RSSI Distance Estimation Service

Polls the WiFi signal strength of the drone connection and converts
it to an approximate distance using the log-distance path-loss model.

This single distance constraint acts as a "leash" to limit position
drift when fused with optical flow in the EKF.

Windows reports signal quality as 0-100%. The Microsoft conversion is:
  dBm = (signal_quality / 2) - 100
So 80% signal ≈ -60 dBm.
"""

import logging
import math
import re
import subprocess
import threading
import time
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class WifiRssiService:
    """
    Singleton service for WiFi RSSI distance estimation.

    Polls netsh wlan show interfaces to read the signal strength of
    the connected drone WiFi, converts to dBm, then to distance via
    the log-distance path-loss model.
    """

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
        self._last_rssi_dbm = -100.0
        self._last_signal_pct = 0
        self._last_distance = 0.0
        self._last_ssid = ""
        self._last_timestamp = 0.0

        # Log-distance path-loss model:
        # d = d_ref * 10^((rssi_ref - rssi) / (10 * n))
        self.rssi_ref = -30.0     # RSSI at reference distance (dBm)
        self.d_ref = 1.0          # Reference distance (meters)
        self.n = 2.5              # Path-loss exponent (indoor: 2.0-3.5)

        # Smoothing
        self._rssi_history = []   # type: List[float]
        self._history_size = 5

        # Calibration
        self._calibration_points = []  # type: List[Tuple[float, float]]  # (distance_m, rssi_dbm)

        # Polling
        self._poll_thread = None   # type: Optional[threading.Thread]
        self._poll_stop = None     # type: Optional[threading.Event]
        self.poll_hz = 3.0

        # Callbacks
        self._on_update_callbacks = []  # type: List[Any]
        self._callbacks_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._initialized = True
        logger.info("WifiRssiService singleton created")

    def initialize(self, config: Dict[str, Any]) -> None:
        """Load configuration for RSSI service."""
        rssi_config = config.get('wifi_rssi', {})
        self.poll_hz = rssi_config.get('poll_hz', 3.0)
        self.rssi_ref = rssi_config.get('rssi_ref', -30.0)
        self.d_ref = rssi_config.get('d_ref', 1.0)
        self.n = rssi_config.get('path_loss_exponent', 2.5)
        self._history_size = rssi_config.get('smoothing_window', 5)

        logger.info(
            "WifiRssiService initialized: poll_hz=%.1f, rssi_ref=%.1f, n=%.2f",
            self.poll_hz, self.rssi_ref, self.n
        )

    def start(self) -> None:
        """Start RSSI polling thread."""
        if self._enabled:
            return

        self._enabled = True
        self._rssi_history.clear()
        self._poll_stop = threading.Event()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="RssiPoll"
        )
        self._poll_thread.start()
        logger.info("WiFi RSSI polling started at %.1f Hz", self.poll_hz)

    def stop(self) -> None:
        """Stop RSSI polling thread."""
        self._enabled = False
        if self._poll_stop:
            self._poll_stop.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=2)
            self._poll_thread = None
        logger.info("WiFi RSSI polling stopped")

    def is_enabled(self) -> bool:
        return self._enabled

    def _poll_loop(self) -> None:
        """Background loop: read RSSI at poll_hz."""
        interval = 1.0 / max(0.1, self.poll_hz)

        while not self._poll_stop.is_set():
            try:
                signal_pct, ssid = self._read_signal()

                if signal_pct is not None:
                    rssi_dbm = self._signal_pct_to_dbm(signal_pct)
                    smoothed_rssi = self._smooth_rssi(rssi_dbm)
                    distance = self._rssi_to_distance(smoothed_rssi)

                    with self._state_lock:
                        self._last_signal_pct = signal_pct
                        self._last_rssi_dbm = smoothed_rssi
                        self._last_distance = distance
                        self._last_ssid = ssid or ""
                        self._last_timestamp = time.time()

                    # Fire callbacks
                    with self._callbacks_lock:
                        cbs = list(self._on_update_callbacks)
                    for cb in cbs:
                        try:
                            cb()
                        except Exception as e:
                            logger.debug("RSSI update callback error: %s", e)

            except Exception as e:
                logger.debug("RSSI poll error: %s", e)

            self._poll_stop.wait(interval)

    def _read_signal(self) -> Tuple[Optional[int], Optional[str]]:
        """
        Read WiFi signal quality from netsh wlan show interfaces.

        Returns:
            (signal_percent, ssid) or (None, None) if not connected
        """
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=3
            )
        except Exception:
            return None, None

        if result.returncode != 0:
            return None, None

        signal_pct = None
        ssid = None
        state = None

        for line in result.stdout.splitlines():
            stripped = line.strip()
            m = re.match(r"^(.+?)\s*:\s*(.*)$", stripped)
            if not m:
                continue

            key = m.group(1).strip().lower()
            val = m.group(2).strip()

            if key == "state":
                state = val.lower()
            elif key == "ssid" and ssid is None:
                ssid = val
            elif key == "signal":
                # "85%" → 85
                pct_match = re.match(r"(\d+)\s*%", val)
                if pct_match:
                    signal_pct = int(pct_match.group(1))

        if state != "connected" or signal_pct is None:
            return None, None

        return signal_pct, ssid

    @staticmethod
    def _signal_pct_to_dbm(signal_pct: int) -> float:
        """Convert Windows signal quality (0-100%) to approximate dBm.

        Microsoft formula: dBm ≈ (quality / 2) - 100
        """
        return (signal_pct / 2.0) - 100.0

    def _smooth_rssi(self, rssi_dbm: float) -> float:
        """Apply moving-average smoothing to RSSI readings."""
        self._rssi_history.append(rssi_dbm)
        if len(self._rssi_history) > self._history_size:
            self._rssi_history.pop(0)
        return sum(self._rssi_history) / len(self._rssi_history)

    def _rssi_to_distance(self, rssi_dbm: float) -> float:
        """Convert RSSI (dBm) to distance (meters) via log-distance model.

        d = d_ref * 10^((rssi_ref - rssi) / (10 * n))
        """
        exponent = (self.rssi_ref - rssi_dbm) / (10.0 * self.n)
        distance = self.d_ref * math.pow(10.0, exponent)
        # Clamp to reasonable range
        return max(0.1, min(distance, 100.0))

    def calibrate(self, known_distance: float) -> Dict[str, Any]:
        """
        Record current RSSI at a known distance for calibration.

        Place the drone at a measured distance and call this to record a
        calibration point. With 2+ points, fits the path-loss model.

        Args:
            known_distance: True distance in meters

        Returns:
            Calibration result dict
        """
        with self._state_lock:
            current_rssi = self._last_rssi_dbm
            current_ssid = self._last_ssid

        if current_rssi <= -100:
            return {'error': 'No RSSI reading available'}

        self._calibration_points.append((known_distance, current_rssi))
        logger.info(
            "Calibration point added: distance=%.2fm, rssi=%.1f dBm (total: %d points)",
            known_distance, current_rssi, len(self._calibration_points)
        )

        # With 2+ points, fit the model
        if len(self._calibration_points) >= 2:
            self._fit_path_loss_model()

        return {
            'distance': known_distance,
            'rssi_dbm': current_rssi,
            'ssid': current_ssid,
            'total_points': len(self._calibration_points),
            'model': {
                'rssi_ref': self.rssi_ref,
                'd_ref': self.d_ref,
                'n': self.n
            }
        }

    def _fit_path_loss_model(self) -> None:
        """Fit rssi_ref and n from calibration points via least squares.

        Model: RSSI = rssi_ref - 10*n*log10(d/d_ref)
        Linear: RSSI = A + B * log10(d), where A = rssi_ref, B = -10*n
        """
        import numpy as np

        distances = [p[0] for p in self._calibration_points]
        rssis = [p[1] for p in self._calibration_points]

        log_d = [math.log10(d / self.d_ref) for d in distances]

        # Least squares: RSSI = A + B * log10(d/d_ref)
        A_mat = [[1.0, ld] for ld in log_d]
        A_np = np.array(A_mat, dtype=np.float64)
        b_np = np.array(rssis, dtype=np.float64)

        result = np.linalg.lstsq(A_np, b_np, rcond=None)
        coeffs = result[0]

        self.rssi_ref = float(coeffs[0])
        self.n = float(-coeffs[1] / 10.0)

        # Clamp n to reasonable range
        self.n = max(1.5, min(self.n, 5.0))

        logger.info(
            "Path-loss model fitted: rssi_ref=%.1f dBm, n=%.2f (from %d points)",
            self.rssi_ref, self.n, len(self._calibration_points)
        )

    def get_distance(self) -> float:
        """Get current estimated distance in meters."""
        with self._state_lock:
            return self._last_distance

    def get_data(self) -> Dict[str, Any]:
        """Get current RSSI data."""
        with self._state_lock:
            return {
                'enabled': self._enabled,
                'signal_pct': self._last_signal_pct,
                'rssi_dbm': self._last_rssi_dbm,
                'distance': self._last_distance,
                'ssid': self._last_ssid,
                'timestamp': self._last_timestamp,
                'model': {
                    'rssi_ref': self.rssi_ref,
                    'd_ref': self.d_ref,
                    'n': self.n
                },
                'calibration_points': len(self._calibration_points)
            }

    def get_calibration(self) -> Dict[str, Any]:
        """Get calibration data."""
        return {
            'points': [
                {'distance': d, 'rssi_dbm': r}
                for d, r in self._calibration_points
            ],
            'model': {
                'rssi_ref': self.rssi_ref,
                'd_ref': self.d_ref,
                'n': self.n
            }
        }

    def on_update(self, callback) -> None:
        """Register callback fired after each RSSI update."""
        with self._callbacks_lock:
            self._on_update_callbacks.append(callback)

    def remove_on_update(self, callback) -> None:
        """Unregister an RSSI update callback."""
        with self._callbacks_lock:
            try:
                self._on_update_callbacks.remove(callback)
            except ValueError:
                pass


# Global singleton instance
wifi_rssi_service = WifiRssiService()
