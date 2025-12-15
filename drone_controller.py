"""
TEKY WiFi Drone Controller
A Python application to receive video feed and control a WiFi drone
"""

import cv2
import socket
import threading
import time
import numpy as np
from typing import Optional, Tuple


class TEKYDroneController:
    """Controller for TEKY WiFi Drone"""

    # Network Configuration
    DRONE_IP = "192.168.1.1"
    UDP_PORT = 7099
    RTSP_PORT = 7070
    RTSP_URL = f"rtsp://{DRONE_IP}:{RTSP_PORT}/webcam"

    # Command bytes
    CMD_HEARTBEAT = bytes([1, 1])
    CMD_INITIALIZE = bytes([100])
    CMD_SPECIAL = bytes([99])
    CMD_CAMERA_1 = bytes([6, 1])
    CMD_CAMERA_2 = bytes([6, 2])
    CMD_SCREEN_MODE_1 = bytes([9, 1])
    CMD_SCREEN_MODE_2 = bytes([9, 2])

    def __init__(self):
        """Initialize the drone controller"""
        self.udp_socket: Optional[socket.socket] = None
        self.video_capture: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.is_connected = False
        self.device_type = 0  # 0=Unknown, 2=GL, 10=TC
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.receive_thread: Optional[threading.Thread] = None

    def connect(self) -> bool:
        """
        Establish UDP connection with the drone
        Returns True if successful, False otherwise
        """
        try:
            print(f"Connecting to drone at {self.DRONE_IP}:{self.UDP_PORT}...")

            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(2.0)  # 2 second timeout

            # Send initial heartbeat
            self.send_command(self.CMD_HEARTBEAT)

            # Wait for response to confirm connection
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                print(f"Received response from {addr}: {data.hex()}")
                self._parse_response(data)
                self.is_connected = True
                print(f"Connected! Device type: {self.device_type}")
            except socket.timeout:
                print("Warning: No response from drone, but continuing...")
                self.is_connected = True

            # Start heartbeat thread
            self.is_running = True
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True
            )
            self.heartbeat_thread.start()

            # Start receive thread
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True
            )
            self.receive_thread.start()

            # Send initialize command
            time.sleep(0.5)
            self.send_command(self.CMD_INITIALIZE)

            return True

        except Exception as e:
            print(f"Error connecting to drone: {e}")
            return False

    def disconnect(self):
        """Disconnect from the drone"""
        print("Disconnecting from drone...")
        self.is_running = False
        self.is_connected = False

        # Wait for threads to stop before closing socket
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)

        if self.receive_thread:
            self.receive_thread.join(timeout=2)

        # Gracefully shutdown socket before closing
        if self.udp_socket:
            try:
                # For UDP, shutdown is not strictly necessary but helps signal intent
                # Setting timeout to 0 prevents blocking on any pending operations
                self.udp_socket.settimeout(0)
                # UDP doesn't have shutdown() like TCP, but we can stop sending
                # by simply not calling sendto() anymore (handled by is_running flag)
            except Exception as e:
                print(f"Note: Socket shutdown signal: {e}")

            try:
                self.udp_socket.close()
            except Exception as e:
                print(f"Note: Socket close: {e}")
            finally:
                self.udp_socket = None

        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

        print("Disconnected.")

    def send_command(self, command: bytes) -> bool:
        """
        Send a command to the drone via UDP
        Args:
            command: Byte array command
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.udp_socket or not self.is_connected:
            print("Error: Not connected to drone")
            return False

        try:
            self.udp_socket.sendto(command, (self.DRONE_IP, self.UDP_PORT))
            print(f"Sent command: {command.hex()}")
            return True
        except OSError as e:
            # Handle socket errors gracefully (including WinError 10054)
            print(f"Socket error sending command: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"Error sending command: {e}")
            return False

    def _heartbeat_loop(self):
        """Background thread to send heartbeat packets"""
        print("Heartbeat thread started")
        while self.is_running:
            try:
                self.send_command(self.CMD_HEARTBEAT)
                time.sleep(1.0)  # Send heartbeat every second
            except Exception as e:
                print(f"Heartbeat error: {e}")
                break
        print("Heartbeat thread stopped")

    def _receive_loop(self):
        """Background thread to receive UDP responses"""
        print("Receive thread started")
        if not self.udp_socket:
            return

        try:
            self.udp_socket.settimeout(0.5)  # Short timeout for non-blocking
        except Exception:
            return  # Socket already closed

        while self.is_running:
            try:
                if not self.udp_socket:  # Check if socket still exists
                    break
                data, addr = self.udp_socket.recvfrom(1024)
                self._parse_response(data)
            except socket.timeout:
                continue
            except OSError as e:
                # OSError includes WinError 10054 and other socket errors
                if self.is_running:
                    # Only print if we're still supposed to be running (not a planned shutdown)
                    print(f"Connection closed by drone: {e}")
                break
            except Exception as e:
                if self.is_running:
                    print(f"Receive error: {e}")
                break
        print("Receive thread stopped")

    def _parse_response(self, data: bytes):
        """Parse response data from drone"""
        if len(data) >= 1:
            # Byte 0 contains device type and resolution info
            device_info = data[0]
            if device_info & 0x02:  # Check if GL type
                self.device_type = 2
            elif device_info & 0x0A:  # Check if TC type
                self.device_type = 10

        if len(data) >= 2:
            # Byte 1 is camera switch reset state (value retained for debugging)
            _ = data[1]

        if len(data) >= 3:
            # Byte 2 is screen switch state (value retained for debugging)
            _ = data[2]

    def start_video_stream(self) -> bool:
        """
        Start receiving video stream from drone
        Returns True if successful, False otherwise
        """
        try:
            print(f"Starting video stream from {self.RTSP_URL}...")

            # Try OpenCV first
            self.video_capture = cv2.VideoCapture(self.RTSP_URL)

            # Set buffer size to reduce latency
            self.video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self.video_capture.isOpened():
                print("Failed to open video stream with OpenCV")
                print("Please ensure:")
                print("1. You're connected to the drone's WiFi network")
                print("2. FFmpeg is installed and in PATH")
                print("3. The drone is powered on and streaming")
                return False

            print("Video stream started successfully!")
            return True

        except Exception as e:
            print(f"Error starting video stream: {e}")
            return False

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Get a frame from the video stream
        Returns (success, frame) tuple
        """
        if not self.video_capture:
            return False, None

        ret, frame = self.video_capture.read()
        return ret, frame

    def switch_camera(self, camera_num: int):
        """
        Switch between cameras (if drone has multiple)
        Args:
            camera_num: 1 or 2
        """
        if camera_num == 1:
            self.send_command(self.CMD_CAMERA_1)
        elif camera_num == 2:
            self.send_command(self.CMD_CAMERA_2)

    def switch_screen_mode(self, mode: int):
        """
        Switch screen mode
        Args:
            mode: 1 or 2
        """
        if mode == 1:
            self.send_command(self.CMD_SCREEN_MODE_1)
        elif mode == 2:
            self.send_command(self.CMD_SCREEN_MODE_2)


def main():
    """Main application loop"""
    print("=" * 60)
    print("TEKY WiFi Drone Controller")
    print("=" * 60)
    print("\nControls:")
    print("  Q - Quit")
    print("  1 - Switch to Camera 1")
    print("  2 - Switch to Camera 2")
    print("  M - Switch Screen Mode")
    print("  I - Send Initialize Command")
    print("  S - Take Screenshot")
    print("\nNote: Flight controls not yet implemented")
    print("      (requires reverse engineering native libraries)")
    print("=" * 60)

    # Create drone controller
    drone = TEKYDroneController()

    # Connect to drone
    if not drone.connect():
        print("Failed to connect to drone. Exiting.")
        return

    # Start video stream
    if not drone.start_video_stream():
        print("Failed to start video stream. Continuing with control only...")
        video_enabled = False
    else:
        video_enabled = True

    # Main loop
    screen_mode = 1
    screenshot_count = 0

    try:
        while True:
            # Get and display video frame
            if video_enabled:
                ret, frame = drone.get_frame()

                if ret and frame is not None:
                    # Add overlay text
                    cv2.putText(
                        frame,
                        "TEKY Drone - Press Q to quit",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
                    cv2.putText(
                        frame,
                        f"Device Type: {drone.device_type}",
                        (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        1,
                    )
                    cv2.putText(
                        frame,
                        f"Connected: {drone.is_connected}",
                        (10, 85),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        1,
                    )

                    # Display frame
                    cv2.imshow("TEKY Drone Video Feed", frame)
                else:
                    print("Failed to get frame")

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == ord("Q"):
                print("Quitting...")
                break
            elif key == ord("1"):
                print("Switching to camera 1...")
                drone.switch_camera(1)
            elif key == ord("2"):
                print("Switching to camera 2...")
                drone.switch_camera(2)
            elif key == ord("m") or key == ord("M"):
                screen_mode = 2 if screen_mode == 1 else 1
                print(f"Switching to screen mode {screen_mode}...")
                drone.switch_screen_mode(screen_mode)
            elif key == ord("i") or key == ord("I"):
                print("Sending initialize command...")
                drone.send_command(drone.CMD_INITIALIZE)
            elif key == ord("s") or key == ord("S"):
                if video_enabled and ret and frame is not None:
                    filename = f"screenshot_{screenshot_count:04d}.jpg"
                    cv2.imwrite(filename, frame)
                    print(f"Screenshot saved: {filename}")
                    screenshot_count += 1

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    finally:
        # Cleanup
        drone.disconnect()
        cv2.destroyAllWindows()
        print("Application closed.")


if __name__ == "__main__":
    main()
