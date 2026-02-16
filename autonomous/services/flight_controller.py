"""
Flight Controller Service

80 Hz control loop for drone command transmission.
Adapted from turbodrone architecture.
"""

import asyncio
import socket
import logging
import time
from typing import Optional, Callable
from ..models.base_rc import BaseRCModel

logger = logging.getLogger(__name__)


class FlightController:
    """
    Flight controller service with high-frequency control loop

    Maintains 80 Hz (12.5ms) control update rate for smooth drone response.
    Sends control packets via UDP to drone.

    Based on turbodrone's proven architecture.
    """

    def __init__(
        self,
        rc_model: BaseRCModel,
        drone_ip: str = "192.168.1.1",
        control_port: int = 7099,
        update_rate_hz: float = 80.0
    ):
        """
        Initialize flight controller

        Args:
            rc_model: RC model instance (handles packet building)
            drone_ip: Drone IP address
            control_port: UDP control port
            update_rate_hz: Control update rate (Hz)
        """
        self.rc_model = rc_model
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.update_rate_hz = update_rate_hz
        self.update_interval = 1.0 / update_rate_hz

        # UDP socket
        self.socket: Optional[socket.socket] = None

        # Control loop state
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

        # Statistics
        self._packet_count = 0
        self._error_count = 0
        self._last_packet_time = 0.0

        # Callbacks
        self.on_packet_sent: Optional[Callable[[bytes, int], None]] = None

    def connect(self) -> bool:
        """
        Create UDP socket for control

        Returns:
            True if successful
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(1.0)
            logger.info(f"Flight controller connected to {self.drone_ip}:{self.control_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to create UDP socket: {e}")
            return False

    def disconnect(self):
        """Close UDP socket"""
        if self.socket:
            self.socket.close()
            self.socket = None
            logger.info("Flight controller disconnected")

    async def start(self):
        """Start control loop"""
        if self._running:
            logger.warning("Control loop already running")
            return

        if not self.socket:
            if not self.connect():
                raise RuntimeError("Failed to connect socket")

        self._running = True
        self._loop_task = asyncio.create_task(self._control_loop())
        logger.info(f"Control loop started at {self.update_rate_hz} Hz")

    async def stop(self):
        """Stop control loop"""
        if not self._running:
            return

        self._running = False

        if self._loop_task:
            await self._loop_task
            self._loop_task = None

        logger.info("Control loop stopped")

    async def _control_loop(self):
        """
        Main control loop

        Runs at specified update rate (default 80 Hz).
        Updates RC model and sends control packets.
        """
        logger.info(f"Control loop running (update interval: {self.update_interval*1000:.1f}ms)")

        last_update = time.time()

        while self._running:
            loop_start = time.time()

            try:
                # Calculate dt
                dt = loop_start - last_update
                last_update = loop_start

                # Update RC model (applies accel/decel)
                self.rc_model.update(dt)

                # Build and send control packet
                packet = self.rc_model.build_control_packet()
                self._send_packet(packet)

                # Clear flags after sending
                self.rc_model.clear_flags()

                # Call callback if registered
                if self.on_packet_sent:
                    self.on_packet_sent(packet, self._packet_count)

                # Sleep for remaining time in update interval
                elapsed = time.time() - loop_start
                sleep_time = max(0, self.update_interval - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    # Warn if loop is running behind
                    if elapsed > self.update_interval * 1.5:
                        logger.warning(f"Control loop behind schedule: {elapsed*1000:.1f}ms (target: {self.update_interval*1000:.1f}ms)")

            except Exception as e:
                logger.error(f"Error in control loop: {e}", exc_info=True)
                self._error_count += 1
                await asyncio.sleep(0.01)  # Brief pause on error

        logger.info("Control loop exited")

    def _send_packet(self, packet: bytes):
        """
        Send UDP packet to drone

        Args:
            packet: Packet bytes to send
        """
        if not self.socket:
            logger.error("Socket not connected")
            return

        try:
            self.socket.sendto(packet, (self.drone_ip, self.control_port))
            self._packet_count += 1
            self._last_packet_time = time.time()

        except Exception as e:
            logger.error(f"Failed to send packet: {e}")
            self._error_count += 1

    def send_packet_once(self, packet: bytes):
        """
        Send a single packet (for non-flight commands)

        Args:
            packet: Packet bytes to send
        """
        self._send_packet(packet)

    def get_stats(self) -> dict:
        """
        Get controller statistics

        Returns:
            Dict with packet_count, error_count, etc.
        """
        return {
            'running': self._running,
            'packet_count': self._packet_count,
            'error_count': self._error_count,
            'last_packet_time': self._last_packet_time,
            'update_rate_hz': self.update_rate_hz,
            'rc_model': repr(self.rc_model)
        }

    def __repr__(self):
        return (
            f"FlightController("
            f"drone={self.drone_ip}:{self.control_port}, "
            f"rate={self.update_rate_hz}Hz, "
            f"running={self._running}, "
            f"packets={self._packet_count})"
        )


class FlightControllerSync:
    """
    Synchronous version of FlightController

    For use in non-async contexts (like Phase 1 testing).
    Uses threading instead of asyncio.
    """

    def __init__(
        self,
        rc_model: BaseRCModel,
        drone_ip: str = "192.168.1.1",
        control_port: int = 7099,
        update_rate_hz: float = 80.0
    ):
        """Initialize sync flight controller"""
        self.rc_model = rc_model
        self.drone_ip = drone_ip
        self.control_port = control_port
        self.update_rate_hz = update_rate_hz
        self.update_interval = 1.0 / update_rate_hz

        self.socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[object] = None  # Will be threading.Thread

        self._packet_count = 0
        self._error_count = 0

    def connect(self) -> bool:
        """Create UDP socket"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(1.0)
            return True
        except Exception as e:
            logger.error(f"Failed to create socket: {e}")
            return False

    def disconnect(self):
        """Close socket"""
        if self.socket:
            self.socket.close()
            self.socket = None

    def start(self):
        """Start control loop in background thread"""
        if self._running:
            return

        if not self.socket:
            if not self.connect():
                raise RuntimeError("Failed to connect")

        import threading
        self._running = True
        self._thread = threading.Thread(target=self._control_loop, daemon=True)
        self._thread.start()
        logger.info(f"Sync control loop started at {self.update_rate_hz} Hz")

    def stop(self):
        """Stop control loop"""
        if not self._running:
            return

        self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        logger.info("Sync control loop stopped")

    def _control_loop(self):
        """Control loop (runs in thread)"""
        last_update = time.time()

        while self._running:
            loop_start = time.time()

            try:
                dt = loop_start - last_update
                last_update = loop_start

                self.rc_model.update(dt)
                packet = self.rc_model.build_control_packet()
                self._send_packet(packet)
                self.rc_model.clear_flags()

                elapsed = time.time() - loop_start
                sleep_time = max(0, self.update_interval - elapsed)

                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in sync control loop: {e}")
                self._error_count += 1
                time.sleep(0.01)

    def _send_packet(self, packet: bytes):
        """Send packet via UDP"""
        if not self.socket:
            return

        try:
            self.socket.sendto(packet, (self.drone_ip, self.control_port))
            self._packet_count += 1
        except Exception as e:
            logger.error(f"Failed to send packet: {e}")
            self._error_count += 1

    def send_packet_once(self, packet: bytes):
        """Send single packet"""
        self._send_packet(packet)
