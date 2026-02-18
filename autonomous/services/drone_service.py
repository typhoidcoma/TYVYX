"""
Drone Service

High-level service that manages drone operations.
Supports both E88Pro (S2x) and WiFi UAV (K417) protocols.
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
from tyvyx.wifi_uav_controller import WifiUavDroneController
from tyvyx.services.video_receiver import VideoReceiverService
from tyvyx.protocols.s2x_video_protocol import S2xVideoProtocolAdapter
from tyvyx.protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter
from tyvyx.protocols.push_jpeg_video_protocol import PushJpegVideoProtocolAdapter
from tyvyx.protocols.raw_udp_sniffer import RawUdpSnifferProtocol
from tyvyx.utils.dropping_queue import DroppingQueue
from tyvyx.frame_hub import FrameHub
from autonomous.services.position_service import position_service

logger = logging.getLogger(__name__)

# Thread pool for position processing (shared, avoid blocking video stream)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="position")

# Protocol type constants
PROTOCOL_E88PRO = "e88pro"
PROTOCOL_WIFI_UAV = "wifi_uav"


def detect_protocol(drone_ip: str) -> str:
    """Detect drone protocol based on IP address.

    WiFi UAV drones (K417, etc.) use 192.168.169.x subnet.
    E88Pro drones use 192.168.1.x subnet.
    """
    if drone_ip.startswith("192.168.169."):
        return PROTOCOL_WIFI_UAV
    return PROTOCOL_E88PRO


class DroneService:
    """
    High-level drone service

    Singleton service that manages drone connection, video streaming,
    and provides async interface to TYVYX controllers.
    Supports both E88Pro and WiFi UAV protocol families.
    """

    def __init__(self):
        self.drone = None  # TYVYXDroneControllerAdvanced or WifiUavDroneController

        self._connected = False
        self._video_streaming = False
        self._video_protocol = None
        self._drone_protocol = None  # "e88pro" or "wifi_uav"

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

    async def connect(self, drone_ip: str,
                      bind_ip: str = "",
                      protocol: str = "") -> bool:
        # Auto-disconnect stale connection before reconnecting
        if self._connected or self.drone:
            logger.info("Cleaning up previous connection before reconnecting...")
            await self.disconnect()

        try:
            # Auto-detect protocol if not explicitly provided
            self._drone_protocol = protocol or detect_protocol(drone_ip)
            self._bind_ip = bind_ip

            logger.info(f"Connecting to drone at {drone_ip} "
                        f"(protocol={self._drone_protocol}, bind_ip={bind_ip or 'auto'})...")

            if self._drone_protocol == PROTOCOL_WIFI_UAV:
                self.drone = WifiUavDroneController(drone_ip=drone_ip, bind_ip=bind_ip)
            else:
                self.drone = TYVYXDroneControllerAdvanced(drone_ip=drone_ip, bind_ip=bind_ip)

            loop = asyncio.get_event_loop()
            connected = await loop.run_in_executor(None, self.drone.connect)

            if connected:
                self._connected = True
                logger.info(f"Connected to drone (protocol={self._drone_protocol})")
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
        if not self._connected and not self.drone:
            return

        try:
            logger.info("Disconnecting from drone...")
            if self._video_streaming:
                await self.stop_video()

            if self.drone:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.drone.disconnect)
                except Exception as e:
                    logger.error(f"Error in drone.disconnect(): {e}")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
        finally:
            # Always reset state, even if cleanup failed
            self._connected = False
            self.drone = None
            self._drone_protocol = None
            logger.info("Disconnected from drone")

    async def start_video(self, protocol: str = "") -> dict:
        """
        Start video stream using UDP video receiver.

        Args:
            protocol: "s2x" / "wifi_uav" (auto-detected if empty), "sniffer" (diagnostic)

        Returns:
            dict with 'success' bool and 'message' str
        """
        if not self._connected or not self.drone:
            return {"success": False, "message": "Not connected to drone - connect first"}

        if self._video_streaming:
            return {"success": True, "message": "Video already streaming"}

        # Default video protocol based on drone protocol
        if not protocol:
            if self._drone_protocol == PROTOCOL_WIFI_UAV:
                protocol = "wifi_uav"
            else:
                protocol = "s2x"

        try:
            logger.info(f"Starting video stream (protocol={protocol})...")

            if protocol == "wifi_uav":
                return await self._start_video_wifi_uav()
            elif protocol == "s2x":
                return await self._start_video_s2x()
            elif protocol == "sniffer":
                return await self._start_video_sniffer()
            else:
                return {"success": False, "message": f"Unknown protocol: {protocol}"}

        except Exception as e:
            logger.error(f"Error starting video: {e}", exc_info=True)
            return {"success": False, "message": f"Video error: {e}"}

    async def _start_video_wifi_uav(self) -> dict:
        """Start video using push-based JPEG protocol (K417 / Drone-XXXXXX).

        The drone sends JPEG fragments continuously after receiving
        START_STREAM — no per-frame request needed.  Packets use the
        0x93 0x01 header format with payload at byte 56.
        """
        adapter_cls = PushJpegVideoProtocolAdapter
        adapter_args = {
            "drone_ip": self.drone.DRONE_IP,
            "control_port": self.drone.UDP_PORT,
            "video_port": self.drone.UDP_PORT,
            "bind_ip": getattr(self, '_bind_ip', ""),
            "debug": True,
        }

        return self._start_video_pipeline(adapter_cls, adapter_args, "wifi_uav")

    async def _start_video_s2x(self) -> dict:
        """Start video using S2x/E88Pro protocol."""
        loop = asyncio.get_event_loop()

        # Select front camera first (required by E88Pro before video flows)
        await loop.run_in_executor(
            None, self.drone.send_command, self.drone.CMD_CAMERA_1
        )
        await asyncio.sleep(0.3)

        # Send CMD_START_VIDEO to the drone a few times
        for i in range(3):
            await loop.run_in_executor(
                None, self.drone.send_command, self.drone.CMD_START_VIDEO
            )
            await asyncio.sleep(0.3)

        adapter_cls = S2xVideoProtocolAdapter
        adapter_args = {
            "drone_ip": self.drone.DRONE_IP,
            "control_port": self.drone.UDP_PORT,
            "video_port": 7070,
            "start_command": self.drone.CMD_START_VIDEO,
            "debug": True,
            "bind_ip": getattr(self, '_bind_ip', ""),
        }

        return self._start_video_pipeline(adapter_cls, adapter_args, "s2x")

    async def _start_video_sniffer(self) -> dict:
        """Start video using raw UDP sniffer (diagnostic)."""
        loop = asyncio.get_event_loop()
        for i in range(3):
            await loop.run_in_executor(
                None, self.drone.send_command, self.drone.CMD_START_VIDEO
            )
            await asyncio.sleep(0.3)

        adapter_cls = RawUdpSnifferProtocol
        adapter_args = {
            "drone_ip": self.drone.DRONE_IP,
            "control_port": self.drone.UDP_PORT,
            "video_port": 7070,
            "start_command": self.drone.CMD_START_VIDEO,
            "bind_ip": getattr(self, '_bind_ip', ""),
        }

        return self._start_video_pipeline(adapter_cls, adapter_args, "sniffer")

    def _start_video_pipeline(self, adapter_cls, adapter_args: dict,
                              protocol_name: str) -> dict:
        """Common video pipeline setup for all protocols."""
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
        self._video_protocol = protocol_name
        logger.info(f"Video stream started (protocol={protocol_name})")

        return {"success": True, "message": f"Video started (protocol={protocol_name})"}

    @staticmethod
    def _frame_pump_worker(raw_q, frame_hub, stop_event, loop):
        """Bridge thread: pulls VideoFrames from queue, publishes to asyncio FrameHub.
        Also feeds position tracking every 3rd frame.
        Detects stream stalls and notifies clients (borrowed from turbodrone)."""
        frame_counter = 0
        total_frames = 0
        first_frame_seen = False
        last_frame_time = time.monotonic()
        last_log_time = time.monotonic()
        stall_notified = False
        STALL_TIMEOUT = 3.0
        LOG_INTERVAL = 5.0  # print stats every 5s

        while not stop_event.is_set():
            try:
                frame = raw_q.get(timeout=1.0)
                if frame and frame.data:
                    now = time.monotonic()
                    if not first_frame_seen:
                        logger.info("[pump] First frame received (%d bytes)", len(frame.data))
                    first_frame_seen = True
                    last_frame_time = now
                    stall_notified = False
                    total_frames += 1

                    # Periodic stats
                    elapsed = now - last_log_time
                    if elapsed >= LOG_INTERVAL:
                        fps = total_frames / elapsed
                        clients = len(frame_hub._clients)
                        logger.info(
                            "[pump] %.1f fps | %d bytes/frame | %d clients | %d total frames",
                            fps, len(frame.data), clients, total_frames,
                        )
                        total_frames = 0
                        last_log_time = now

                    # Publish raw JPEG to MJPEG/WS clients
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
                # Stream stall detection: notify clients periodically while stalled
                if first_frame_seen and (time.monotonic() - last_frame_time) > STALL_TIMEOUT:
                    if not stall_notified:
                        logger.warning("[pump] Stream stall detected (no frames for %.1fs)", STALL_TIMEOUT)
                        stall_notified = True
                    # Re-publish None every cycle so new clients get the signal too
                    try:
                        asyncio.run_coroutine_threadsafe(
                            frame_hub.publish(None), loop
                        )
                    except Exception:
                        pass
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

            # Stop video receiver
            if self._video_receiver:
                self._video_receiver.stop()
        except Exception as e:
            logger.error(f"Error stopping video: {e}")
        finally:
            # Always reset state, even if cleanup failed
            self._pump_thread = None
            self._pump_stop = None
            self._video_receiver = None
            self._video_streaming = False
            self._video_protocol = None
            logger.info("Video stream stopped")

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

    # ── Flight control ──

    def _get_fc(self):
        """Get the flight controller, or None."""
        if not self._connected or not self.drone:
            return None
        return getattr(self.drone, 'flight_controller', None)

    def is_flight_armed(self) -> bool:
        fc = self._get_fc()
        return fc is not None and getattr(fc, 'is_active', False)

    async def arm_flight(self) -> bool:
        fc = self._get_fc()
        if fc and hasattr(fc, 'start'):
            fc.start()
            logger.info("Flight controller armed")
            return True
        return False

    async def disarm_flight(self) -> bool:
        fc = self._get_fc()
        if fc and hasattr(fc, 'stop'):
            fc.stop()
            logger.info("Flight controller disarmed")
            return True
        return False

    async def flight_takeoff(self) -> bool:
        fc = self._get_fc()
        if fc and getattr(fc, 'is_active', False):
            fc.takeoff()
            return True
        return False

    async def flight_land(self) -> bool:
        fc = self._get_fc()
        if fc and getattr(fc, 'is_active', False):
            fc.land()
            return True
        return False

    async def flight_calibrate(self) -> bool:
        fc = self._get_fc()
        if fc and getattr(fc, 'is_active', False):
            fc.calibrate_gyro()
            return True
        return False

    async def flight_headless(self) -> bool:
        fc = self._get_fc()
        if fc and getattr(fc, 'is_active', False):
            fc.toggle_headless()
            return True
        return False

    async def flight_set_axes(self, throttle=None, yaw=None,
                              pitch=None, roll=None) -> bool:
        fc = self._get_fc()
        if fc and getattr(fc, 'is_active', False) and hasattr(fc, 'set_axes'):
            fc.set_axes(throttle=throttle, yaw=yaw, pitch=pitch, roll=roll)
            return True
        return False

    def get_status(self) -> dict:
        status = {
            "connected": self._connected,
            "video_streaming": self._video_streaming,
            "flight_armed": self.is_flight_armed(),
            "timestamp": time.time(),
            "bind_ip": getattr(self, '_bind_ip', None),
            "drone_protocol": self._drone_protocol,
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
