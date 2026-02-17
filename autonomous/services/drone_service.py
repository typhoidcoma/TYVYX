"""
Drone Service

High-level service that manages drone operations.
Wraps existing TYVYXDroneControllerAdvanced for use in FastAPI.
"""

import asyncio
import concurrent.futures
import logging
import sys
from pathlib import Path
from typing import Optional
import time

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tyvyx.drone_controller_advanced import TYVYXDroneControllerAdvanced
from tyvyx.video_stream import OpenCVVideoStream
from autonomous.services.position_service import position_service

logger = logging.getLogger(__name__)

# Thread pool for position processing (shared, avoid blocking video stream)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="position")


class DroneService:
    """
    High-level drone service

    Singleton service that manages drone connection, video streaming,
    and provides async interface to existing TYVYX controller.
    """

    def __init__(self):
        self.drone: Optional[TYVYXDroneControllerAdvanced] = None
        self.video_stream: Optional[OpenCVVideoStream] = None

        self._connected = False
        self._video_streaming = False

        # State
        self._last_telemetry = {}
        self._last_update = 0.0
        self._frame_counter = 0  # For position tracking rate limiting

    async def initialize(self):
        """Initialize service (called on startup)"""
        logger.info("Initializing drone service...")
        # Don't create drone controller yet - wait for explicit connect
        pass

    async def shutdown(self):
        """Shutdown service (called on app shutdown)"""
        logger.info("Shutting down drone service...")
        if self._connected:
            await self.disconnect()

    async def connect(self, drone_ip: str = "192.168.1.1") -> bool:
        """
        Connect to drone

        Args:
            drone_ip: Drone IP address

        Returns:
            True if connected successfully
        """
        if self._connected:
            logger.warning("Already connected to drone")
            return True

        try:
            logger.info(f"Connecting to drone at {drone_ip}...")

            # Create drone controller
            self.drone = TYVYXDroneControllerAdvanced(drone_ip=drone_ip)

            # Connect in thread pool (blocking operation)
            loop = asyncio.get_event_loop()
            connected = await loop.run_in_executor(None, self.drone.connect)

            if connected:
                self._connected = True
                logger.info("✅ Connected to drone")
                return True
            else:
                logger.error("❌ Failed to connect to drone")
                self.drone = None
                return False

        except Exception as e:
            logger.error(f"❌ Error connecting to drone: {e}", exc_info=True)
            self.drone = None
            return False

    async def disconnect(self):
        """Disconnect from drone"""
        if not self._connected or not self.drone:
            return

        try:
            logger.info("Disconnecting from drone...")

            # Stop video if running
            if self._video_streaming:
                await self.stop_video()

            # Disconnect in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.drone.disconnect)

            self._connected = False
            self.drone = None
            logger.info("✅ Disconnected from drone")

        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    async def start_video(self) -> dict:
        """
        Start video stream.

        Returns:
            dict with 'success' bool and 'message' str
        """
        if not self._connected or not self.drone:
            return {"success": False, "message": "Not connected to drone — connect first"}

        if self._video_streaming:
            return {"success": True, "message": "Video already streaming"}

        try:
            logger.info("Starting video stream...")

            # Start video in thread pool (blocks while RTSP connects)
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self.drone.start_video_stream)

            if success:
                self._video_streaming = True
                self.video_stream = self.drone.video_stream
                logger.info("✅ Video stream started")
                return {"success": True, "message": "Video started"}
            else:
                logger.error("❌ Failed to start video stream")
                return {
                    "success": False,
                    "message": "Could not open RTSP stream — is the drone powered on and WiFi connected?",
                }

        except Exception as e:
            logger.error(f"Error starting video: {e}", exc_info=True)
            return {"success": False, "message": f"Video error: {e}"}

    async def stop_video(self):
        """Stop video stream"""
        if not self._video_streaming:
            return

        try:
            if self.drone:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.drone.stop_video_stream)

            self._video_streaming = False
            self.video_stream = None
            logger.info("✅ Video stream stopped")

        except Exception as e:
            logger.error(f"Error stopping video: {e}")

    async def send_command(self, command: bytes) -> bool:
        """
        Send raw command to drone

        Args:
            command: Command bytes

        Returns:
            True if sent successfully
        """
        if not self._connected or not self.drone:
            logger.error("Not connected to drone")
            return False

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self.drone.send_command, command)
            return success

        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return False

    async def switch_camera(self, camera_num: int) -> bool:
        """
        Switch camera

        Args:
            camera_num: 1 or 2

        Returns:
            True if successful
        """
        if not self._connected or not self.drone:
            return False

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self.drone.switch_camera,
                camera_num
            )
            return success

        except Exception as e:
            logger.error(f"Error switching camera: {e}")
            return False

    async def switch_screen_mode(self, mode: int) -> bool:
        """
        Switch screen mode

        Args:
            mode: 1 or 2

        Returns:
            True if successful
        """
        if not self._connected or not self.drone:
            return False

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self.drone.switch_screen_mode,
                mode
            )
            return success

        except Exception as e:
            logger.error(f"Error switching screen mode: {e}")
            return False

    def get_frame(self):
        """
        Get current video frame

        Also processes frames for position tracking at controlled rate (10 Hz).

        Returns:
            (success, frame) tuple
        """
        if not self._video_streaming or not self.video_stream:
            return False, None

        success, frame = self.video_stream.read()

        # Process frame for position tracking
        if success and frame is not None:
            self._frame_counter += 1

            # Process every 3rd frame for 10 Hz position updates (assuming 30 fps)
            if self._frame_counter >= 3:
                self._frame_counter = 0

                # Process in thread pool to avoid blocking video stream
                if position_service.is_enabled():
                    _executor.submit(position_service.process_frame, frame.copy())

        return success, frame

    def is_connected(self) -> bool:
        """Check if connected to drone"""
        return self._connected

    def is_video_streaming(self) -> bool:
        """Check if video is streaming"""
        return self._video_streaming

    def get_status(self) -> dict:
        """
        Get drone status

        Returns:
            Status dictionary
        """
        status = {
            "connected": self._connected,
            "video_streaming": self._video_streaming,
            "timestamp": time.time()
        }

        if self.drone:
            status["is_running"] = self.drone.is_running
            status["device_type"] = self.drone.device_type

        return status

    def get_telemetry(self) -> dict:
        """
        Get telemetry data

        Returns:
            Telemetry dictionary with position data (Phase 3)
        """
        telemetry = {
            "connected": self._connected,
            "video_streaming": self._video_streaming,
            "timestamp": time.time()
        }

        # Add position data if tracking is enabled (Phase 3)
        if position_service.is_enabled():
            telemetry["position"] = position_service.get_position()

        return telemetry


# Singleton instance
drone_service = DroneService()
