"""
Drone Service

High-level service that manages drone operations.
Supports both E88Pro (S2x) and WiFi UAV (K417) protocols.
"""

import asyncio
import concurrent.futures
import logging
import queue
import socket
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
from tyvyx.protocols.k417_protocol_engine import K417ProtocolEngine
from tyvyx.protocols.raw_udp_sniffer import RawUdpSnifferProtocol
from tyvyx.protocols.tcp_video_protocol import TcpVideoProtocolAdapter
from tyvyx.protocols.rtsp_video_protocol import RtspVideoProtocolAdapter
from tyvyx.utils.dropping_queue import DroppingQueue
from tyvyx.frame_hub import FrameHub
from autonomous.services.position_service import position_service
from autonomous.services.depth_service import depth_service
from autonomous.services.wifi_rssi_service import wifi_rssi_service

logger = logging.getLogger(__name__)

# Thread pool for position processing (shared, avoid blocking video stream)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="position")

# Separate thread pool for depth inference (GPU-bound, must not block position pipeline)
_depth_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="depth")

# Protocol type constants
PROTOCOL_E88PRO = "e88pro"
PROTOCOL_WIFI_UAV = "wifi_uav"


def detect_protocol(drone_ip: str, ssid: str = "",
                    probe_port: int = 0) -> str:
    """Detect drone protocol from probe result, then SSID, then IP.

    Priority 1 — probe port (most reliable, from UDP response):
      Port 8800 → WiFi UAV (push-based 0x93, BL618)
      Port 7099 → E88Pro / lxPro (JieLi-based)

    Priority 2 — SSID (from APK reverse engineering — xo.java):
      FLOW_ / FlOW_ / Drone- / K417 / HD-FPV → WiFi UAV
      WIFI_ / GD89Pro_ / WTECH- / FLOW-      → E88Pro / lxPro
      Note: FLOW_ (underscore) = WiFi UAV, FLOW- (dash) = lxPro

    Priority 3 — IP subnet fallback:
      192.168.169.x → WiFi UAV
      anything else  → E88Pro
    """
    # Probe port is the ground truth
    if probe_port == 8800:
        return PROTOCOL_WIFI_UAV
    if probe_port == 7099:
        return PROTOCOL_E88PRO

    if ssid:
        ssid_upper = ssid.upper()
        # WiFi UAV family (K417, BL618-based)
        # Note: FLOW_ (underscore) NOT FLOW- (dash) — dash is lxPro/E88Pro
        wifi_uav_prefixes = ["FLOW_", "FLOW ", "DRONE-", "K417", "HD-FPV", "TYVYX"]
        if any(ssid_upper.startswith(p) for p in wifi_uav_prefixes):
            return PROTOCOL_WIFI_UAV
        # E88Pro / lxPro family (JieLi-based)
        e88pro_prefixes = ["WIFI_", "GD89PRO_", "WTECH-", "FLOW-"]
        if any(ssid_upper.startswith(p) for p in e88pro_prefixes):
            return PROTOCOL_E88PRO

    # IP-based fallback
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
                      protocol: str = "",
                      ssid: str = "",
                      probe_port: int = 0) -> bool:
        # Auto-disconnect stale connection before reconnecting
        if self._connected or self.drone:
            logger.info("Cleaning up previous connection before reconnecting...")
            await self.disconnect()

        try:
            # Auto-detect protocol if not explicitly provided
            self._drone_protocol = protocol or detect_protocol(
                drone_ip, ssid=ssid, probe_port=probe_port)
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

                # Auto-start RSSI polling so readings are available for ground_zero
                if not wifi_rssi_service.is_enabled():
                    wifi_rssi_service.start()

                # Auto-start position tracking so optical flow processes frames
                from autonomous.services.position_service import position_service
                if not position_service.is_enabled():
                    try:
                        position_service.start()
                    except RuntimeError:
                        logger.warning("Position service not initialized, skipping auto-start")

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

        # Kill autopilot on disconnect
        from autonomous.services.autopilot_service import autopilot_service
        if autopilot_service.is_enabled():
            autopilot_service.disable()

        try:
            logger.info("Disconnecting from drone...")

            # Stop position tracking and RSSI polling
            from autonomous.services.position_service import position_service
            if position_service.is_enabled():
                position_service.stop()

            if wifi_rssi_service.is_enabled():
                wifi_rssi_service.stop()

            if self._video_streaming:
                await self.stop_video()

            # Capture reference, then reset state immediately for fast UI
            drone = self.drone
            self._connected = False
            self.drone = None
            self._drone_protocol = None

            # Blocking cleanup in background (daemon thread handles joins)
            if drone:
                def _bg_disconnect():
                    try:
                        drone.disconnect()
                    except Exception as e:
                        logger.debug("Background disconnect cleanup: %s", e)
                threading.Thread(
                    target=_bg_disconnect, daemon=True,
                    name="DroneDisconnect",
                ).start()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
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
                protocol = self._detect_e88pro_video_protocol()

        try:
            logger.info(f"Starting video stream (protocol={protocol})...")

            if protocol == "wifi_uav":
                return await self._start_video_wifi_uav()
            elif protocol == "s2x":
                return await self._start_video_s2x()
            elif protocol == "rtsp":
                return await self._start_video_rtsp()
            elif protocol == "tcp":
                return await self._start_video_tcp()
            elif protocol == "sniffer":
                return await self._start_video_sniffer()
            else:
                return {"success": False, "message": f"Unknown protocol: {protocol}"}

        except Exception as e:
            logger.error(f"Error starting video: {e}", exc_info=True)
            return {"success": False, "message": f"Video error: {e}"}

    async def _start_video_wifi_uav(self) -> dict:
        """Start video using K417 unified protocol engine.

        The engine handles both TX (40Hz RC packets with frame ACK counter)
        and RX (0x93 JPEG fragment reassembly) on a single UDP socket.
        """
        adapter_cls = K417ProtocolEngine
        adapter_args = {
            "drone_ip": self.drone.DRONE_IP,
            "port": self.drone.UDP_PORT,
            "bind_ip": getattr(self, '_bind_ip', ""),
            "flight_controller": self.drone.flight_controller,
        }

        # Socket sharing callback — called on initial start AND every reconnect.
        # WiFi UAV drones require ALL UDP traffic from a single source port.
        def on_adapter_created(engine):
            if not isinstance(self.drone, WifiUavDroneController):
                return
            sock = engine.get_shared_socket()
            self.drone.set_shared_socket(sock)
            self.drone.set_engine(engine)
            self.drone._start_heartbeat()
            logger.info("[k417] Engine socket shared with controller: %s",
                        sock.getsockname())

        return self._start_video_pipeline(
            adapter_cls, adapter_args, "wifi_uav",
            on_adapter_created=on_adapter_created,
        )

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

    async def _start_video_tcp(self) -> dict:
        """Start video using TCP MJPEG protocol (lxPro / Mten drones).

        These drones serve JPEG video over TCP 7070 instead of UDP.
        E88Pro init commands are sent by the adapter itself.
        """
        adapter_cls = TcpVideoProtocolAdapter
        adapter_args = {
            "drone_ip": self.drone.DRONE_IP,
            "video_port": 7070,
            "control_port": self.drone.UDP_PORT,
            "bind_ip": getattr(self, '_bind_ip', ""),
        }

        return self._start_video_pipeline(adapter_cls, adapter_args, "tcp")

    async def _start_video_rtsp(self) -> dict:
        """Start video using RTSP/RTP MJPEG (lxPro drones like Mten/FLOW-UFO).

        These drones serve RTSP on TCP 7070 with RTP/MJPEG (PT 26) over UDP.
        E88Pro init commands wake up the camera hardware.
        """
        adapter_cls = RtspVideoProtocolAdapter
        adapter_args = {
            "drone_ip": self.drone.DRONE_IP,
            "video_port": 7070,
            "control_port": self.drone.UDP_PORT,
            "bind_ip": getattr(self, '_bind_ip', ""),
            "rtsp_path": "/webcam",
        }

        return self._start_video_pipeline(adapter_cls, adapter_args, "rtsp")

    def _detect_e88pro_video_protocol(self) -> str:
        """Auto-detect whether an E88Pro drone uses RTSP, raw TCP, or UDP video.

        Connects to TCP 7070 and sends an RTSP OPTIONS probe:
          - RTSP response → "rtsp" (RTP/MJPEG, e.g. Mten/FLOW-UFO)
          - TCP open but no RTSP → "tcp" (raw MJPEG stream)
          - TCP closed → "s2x" (UDP)
        """
        if not self.drone:
            return "s2x"

        drone_ip = self.drone.DRONE_IP
        bind_ip = getattr(self, '_bind_ip', "")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            if bind_ip:
                sock.bind((bind_ip, 0))
            result = sock.connect_ex((drone_ip, 7070))
            if result != 0:
                sock.close()
                logger.info("E88Pro video: TCP 7070 closed -> using s2x adapter")
                return "s2x"

            # TCP 7070 is open — check if it speaks RTSP
            try:
                sock.send(b"OPTIONS rtsp://%s:7070/ RTSP/1.0\r\n"
                          b"CSeq: 1\r\n\r\n" % drone_ip.encode())
                sock.settimeout(1.5)
                resp = sock.recv(256)
                if b"RTSP" in resp and b"200" in resp:
                    sock.close()
                    logger.info("E88Pro video: RTSP detected on TCP 7070 -> using rtsp adapter")
                    return "rtsp"
            except (socket.timeout, OSError):
                pass

            sock.close()
            logger.info("E88Pro video: TCP 7070 open (no RTSP) -> using tcp adapter")
            return "tcp"
        except OSError as e:
            logger.debug("E88Pro video: TCP probe error: %s", e)

        logger.info("E88Pro video: TCP 7070 closed -> using s2x adapter")
        return "s2x"

    def _start_video_pipeline(self, adapter_cls, adapter_args: dict,
                              protocol_name: str,
                              on_adapter_created=None) -> dict:
        """Common video pipeline setup for all protocols."""
        self._raw_frame_queue = DroppingQueue(maxsize=2)
        self._video_receiver = VideoReceiverService(
            protocol_adapter_class=adapter_cls,
            protocol_adapter_args=adapter_args,
            frame_queue=self._raw_frame_queue,
            on_adapter_created=on_adapter_created,
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
        total_frames = 0
        first_frame_seen = False
        last_frame_time = time.monotonic()
        last_log_time = time.monotonic()
        stall_notified = False
        STALL_TIMEOUT = 3.0
        LOG_INTERVAL = 30.0  # print stats every 30s

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

                    # Decode JPEG once for all CV consumers
                    img = None
                    if position_service.is_enabled() or depth_service.is_enabled():
                        np_arr = np.frombuffer(frame.data, dtype=np.uint8)
                        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                    # Position tracking — every frame (~21 Hz)
                    if position_service.is_enabled() and img is not None:
                        _executor.submit(position_service.process_frame, img)

                    # Depth estimation — every Nth frame (throttled inside service)
                    if depth_service.is_enabled() and img is not None:
                        _depth_executor.submit(depth_service.process_frame, img)
            except queue.Empty:
                # Log stall but do NOT kill clients — adapter will recover
                if first_frame_seen and (time.monotonic() - last_frame_time) > STALL_TIMEOUT:
                    if not stall_notified:
                        logger.warning("[pump] Stream stall detected (no frames for %.1fs)", STALL_TIMEOUT)
                        stall_notified = True
                continue
            except Exception as e:
                logger.error(f"Frame pump error: {e}")
                continue

    async def stop_video(self):
        """Stop video stream (non-blocking — cleanup runs in background)."""
        if not self._video_streaming:
            return

        # Capture references before clearing state
        receiver = self._video_receiver
        pump_stop = self._pump_stop
        drone = self.drone

        # Reset state immediately for fast UI response
        self._pump_thread = None
        self._pump_stop = None
        self._video_receiver = None
        self._video_streaming = False
        self._video_protocol = None

        try:
            # Signal controller to stop engine TX (instant)
            if isinstance(drone, WifiUavDroneController):
                drone.set_engine(None)
                drone._heartbeat_running = False

            # Signal all WS/MJPEG clients to close gracefully
            await self.frame_hub.shutdown()

            # Signal frame pump to stop (instant)
            if pump_stop:
                pump_stop.set()
        except Exception as e:
            logger.error(f"Error signaling video stop: {e}")

        # Blocking cleanup (joins, socket close) in background daemon thread
        if receiver:
            def _bg_video_cleanup():
                try:
                    receiver.stop()
                except Exception as e:
                    logger.debug("Background video cleanup: %s", e)
            threading.Thread(
                target=_bg_video_cleanup, daemon=True,
                name="VideoStopCleanup",
            ).start()

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
        # Disable autopilot before disarming
        from autonomous.services.autopilot_service import autopilot_service
        if autopilot_service.is_enabled():
            autopilot_service.disable()
            logger.info("Autopilot disabled due to disarm")

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
        if fc:
            if getattr(fc, 'is_active', False):
                # FC running — set the flag, it'll be sent next loop iteration
                fc.calibrate_gyro()
            elif self.drone and hasattr(self.drone, 'send_one_shot_rc'):
                # FC not armed — send calibrate as one-shot RC packets
                # Send a few times since single UDP packets can get lost
                for _ in range(3):
                    self.drone.send_one_shot_rc(command_flag=0x04)
                    await asyncio.sleep(0.05)
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
