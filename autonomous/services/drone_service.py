"""
Drone Service

High-level service that manages drone operations.
Wraps existing TYVYXDroneControllerAdvanced for use in FastAPI.
"""

import asyncio
import concurrent.futures
import logging
import queue
import sys
import threading
from pathlib import Path
from typing import Optional
import time

import cv2
import numpy as np

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tyvyx.drone_controller_advanced import TYVYXDroneControllerAdvanced
from tyvyx.services.video_receiver import VideoReceiverService
from tyvyx.protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from tyvyx.protocols.raw_udp_sniffer import RawUdpSnifferProtocol
from tyvyx.utils.dropping_queue import DroppingQueue
from tyvyx.frame_hub import FrameHub
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

        self._connected = False
        self._video_streaming = False
        self._video_protocol = None

        # State
        self._last_telemetry = {}
        self._last_update = 0.0
        self._frame_counter = 0

        # UDP video pipeline
        self._video_receiver: Optional[VideoReceiverService] = None
        self._raw_frame_queue: DroppingQueue = DroppingQueue(maxsize=2)
        self.frame_hub: FrameHub = FrameHub(per_client_queue_size=2)
        self._pump_thread: Optional[threading.Thread] = None
        self._pump_stop: Optional[threading.Event] = None

    async def initialize(self):
        """Initialize service (called on startup)"""
        logger.info("Initializing drone service...")

    async def shutdown(self):
        """Shutdown service (called on app shutdown)"""
        logger.info("Shutting down drone service...")
        if self._connected:
            await self.disconnect()

    async def connect(self, drone_ip: str = "192.168.1.1") -> bool:
        if self._connected:
            logger.warning("Already connected to drone")
            return True

        try:
            logger.info(f"Connecting to drone at {drone_ip}...")
            self.drone = TYVYXDroneControllerAdvanced(drone_ip=drone_ip)
            loop = asyncio.get_event_loop()
            connected = await loop.run_in_executor(None, self.drone.connect)

            if connected:
                self._connected = True
                logger.info("Connected to drone")
                return True
            else:
                logger.error("Failed to connect to drone")
                self.drone = None
                return False

        except Exception as e:
            logger.error(f"Error connecting to drone: {e}", exc_info=True)
            self.drone = None
            return False

    async def disconnect(self):
        if not self._connected or not self.drone:
            return

        try:
            logger.info("Disconnecting from drone...")
            if self._video_streaming:
                await self.stop_video()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.drone.disconnect)

            self._connected = False
            self.drone = None
            logger.info("Disconnected from drone")

        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    async def start_video(self, protocol: str = "s2x") -> dict:
        """
        Start video stream using UDP video receiver.

        Args:
            protocol: "s2x" (default), "sniffer" (diagnostic)

        Returns:
            dict with 'success' bool and 'message' str
        """
        if not self._connected or not self.drone:
            return {"success": False, "message": "Not connected to drone — connect first"}

        if self._video_streaming:
            return {"success": True, "message": "Video already streaming"}

        try:
            logger.info(f"Starting video stream (protocol={protocol})...")

            # Send CMD_START_VIDEO to the drone a few times
            loop = asyncio.get_event_loop()
            for i in range(3):
                await loop.run_in_executor(
                    None, self.drone.send_command, self.drone.CMD_START_VIDEO
                )
                await asyncio.sleep(0.3)

            # Choose protocol adapter
            if protocol == "s2x":
                adapter_cls = S2xVideoProtocolAdapter
                adapter_args = {
                    "drone_ip": self.drone.DRONE_IP,
                    "control_port": self.drone.UDP_PORT,
                    "video_port": 7070,
                    "start_command": self.drone.CMD_START_VIDEO,
                    "debug": True,
                }
            elif protocol == "sniffer":
                adapter_cls = RawUdpSnifferProtocol
                adapter_args = {
                    "drone_ip": self.drone.DRONE_IP,
                    "control_port": self.drone.UDP_PORT,
                    "video_port": 7070,
                    "start_command": self.drone.CMD_START_VIDEO,
                }
            else:
                return {"success": False, "message": f"Unknown protocol: {protocol}"}

            # Create and start video receiver
            self._raw_frame_queue = DroppingQueue(maxsize=2)
            self._video_receiver = VideoReceiverService(
                protocol_adapter_class=adapter_cls,
                protocol_adapter_args=adapter_args,
                frame_queue=self._raw_frame_queue,
            )
            self._video_receiver.start()

            # Start frame pump (bridge thread -> asyncio FrameHub)
            self._pump_stop = threading.Event()
            main_loop = asyncio.get_running_loop()
            self._pump_thread = threading.Thread(
                target=self._frame_pump_worker,
                args=(
                    self._raw_frame_queue,
                    self.frame_hub,
                    self._pump_stop,
                    main_loop,
                ),
                daemon=True,
                name="FramePump",
            )
            self._pump_thread.start()

            self._video_streaming = True
            self._video_protocol = protocol
            logger.info(f"Video stream started (protocol={protocol})")
            return {"success": True, "message": f"Video started (protocol={protocol})"}

        except Exception as e:
            logger.error(f"Error starting video: {e}", exc_info=True)
            return {"success": False, "message": f"Video error: {e}"}

    @staticmethod
    def _frame_pump_worker(raw_q, frame_hub, stop_event, loop):
        """Bridge thread: pulls VideoFrames from queue, publishes to asyncio FrameHub.
        Also feeds position tracking every 3rd frame."""
        frame_counter = 0
        while not stop_event.is_set():
            try:
                frame = raw_q.get(timeout=1.0)
                if frame and frame.data:
                    # Publish raw JPEG to MJPEG clients
                    asyncio.run_coroutine_threadsafe(
                        frame_hub.publish(frame.data), loop
                    )

                    # Position tracking at reduced rate (~10 Hz)
                    frame_counter += 1
                    if frame_counter >= 3 and position_service.is_enabled():
                        frame_counter = 0
                        np_arr = np.frombuffer(frame.data, dtype=np.uint8)
                        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                        if img is not None:
                            _executor.submit(position_service.process_frame, img)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Frame pump error: {e}")
                continue

    async def stop_video(self):
        """Stop video stream."""
        if not self._video_streaming:
            return

        try:
            # Stop frame pump
            if self._pump_stop:
                self._pump_stop.set()
            if self._pump_thread:
                self._pump_thread.join(timeout=2.0)
                self._pump_thread = None

            # Stop video receiver
            if self._video_receiver:
                self._video_receiver.stop()
                self._video_receiver = None

            self._video_streaming = False
            self._video_protocol = None
            logger.info("Video stream stopped")

        except Exception as e:
            logger.error(f"Error stopping video: {e}")

    async def send_command(self, command: bytes) -> bool:
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
        if not self._connected or not self.drone:
            return False

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, self.drone.switch_camera, camera_num
            )
            return success

        except Exception as e:
            logger.error(f"Error switching camera: {e}")
            return False

    async def switch_screen_mode(self, mode: int) -> bool:
        if not self._connected or not self.drone:
            return False

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, self.drone.switch_screen_mode, mode
            )
            return success

        except Exception as e:
            logger.error(f"Error switching screen mode: {e}")
            return False

    def get_frame(self):
        """Get current video frame (backward compat for legacy consumers)."""
        if not self._video_streaming:
            return False, None

        try:
            frame = self._raw_frame_queue.get_nowait()
            if frame and frame.data:
                np_arr = np.frombuffer(frame.data, dtype=np.uint8)
                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if img is not None:
                    return True, img
        except queue.Empty:
            pass
        return False, None

    def is_connected(self) -> bool:
        return self._connected

    def is_video_streaming(self) -> bool:
        return self._video_streaming

    def get_status(self) -> dict:
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
        telemetry = {
            "connected": self._connected,
            "video_streaming": self._video_streaming,
            "timestamp": time.time()
        }

        if position_service.is_enabled():
            telemetry["position"] = position_service.get_position()

        return telemetry


# Singleton instance
drone_service = DroneService()
