"""
TEKY WiFi Drone Controller with YOLO11 Integration Ready
OpenCV-based controller optimized for object detection with YOLO11
"""

import cv2
import socket
import threading
import time
import numpy as np
from typing import Optional, Tuple, List, Dict
# `sys` not used in this module but kept for future debugging imports


class DroneVideoProcessor:
    """Video processing pipeline ready for YOLO11 integration"""

    def __init__(self):
        self.yolo_enabled = False
        self.yolo_model = None
        self.processing_enabled = True
        self.show_fps = True
        self.fps = 0
        self.frame_count = 0
        self.fps_start_time = time.time()

    def load_yolo_model(self, model_path: str = "yolo11n.pt"):
        """
        Load YOLO11 model
        To use: Install ultralytics and uncomment the code below

        pip install ultralytics

        Args:
            model_path: Path to YOLO11 model weights
        """
        try:
            # Uncomment when you have ultralytics installed:
            # from ultralytics import YOLO
            # self.yolo_model = YOLO(model_path)
            # self.yolo_enabled = True
            # print(f"YOLO11 model loaded: {model_path}")
            # return True

            print("YOLO11 integration ready!")
            print("To enable:")
            print("  1. Install: pip install ultralytics")
            print("  2. Uncomment code in load_yolo_model()")
            print("  3. Download model: yolo11n.pt, yolo11s.pt, etc.")
            return False

        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            return False

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        """
        Process frame with YOLO11 detection

        Args:
            frame: Input frame from drone

        Returns:
            Tuple of (processed_frame, detections)
            detections: List of dicts with {class, confidence, bbox}
        """
        if not self.processing_enabled:
            return frame, []

        detections = []
        processed_frame = frame.copy()

        # Update FPS counter
        self.frame_count += 1
        if time.time() - self.fps_start_time >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.fps_start_time = time.time()

        if self.yolo_enabled and self.yolo_model is not None:
            # YOLO11 Detection (uncomment when model is loaded)
            # results = self.yolo_model(frame, verbose=False)
            #
            # for result in results:
            #     boxes = result.boxes
            #     for box in boxes:
            #         # Get box coordinates
            #         x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            #         confidence = float(box.conf[0])
            #         class_id = int(box.cls[0])
            #         class_name = result.names[class_id]
            #
            #         # Store detection
            #         detections.append({
            #             'class': class_name,
            #             'confidence': confidence,
            #             'bbox': (int(x1), int(y1), int(x2), int(y2))
            #         })
            #
            #         # Draw on frame
            #         cv2.rectangle(processed_frame, (int(x1), int(y1)),
            #                      (int(x2), int(y2)), (0, 255, 0), 2)
            #
            #         # Draw label
            #         label = f"{class_name} {confidence:.2f}"
            #         cv2.putText(processed_frame, label,
            #                    (int(x1), int(y1) - 10),
            #                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            #                    (0, 255, 0), 2)
            pass

        # Add FPS overlay
        if self.show_fps:
            cv2.putText(
                processed_frame,
                f"FPS: {self.fps}",
                (10, processed_frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

        return processed_frame, detections

    def toggle_processing(self):
        """Toggle frame processing on/off"""
        self.processing_enabled = not self.processing_enabled
        status = "enabled" if self.processing_enabled else "disabled"
        print(f"Frame processing {status}")


class TEKYDroneYOLO:
    """YOLO-ready drone controller"""

    DRONE_IP = "192.168.1.1"
    UDP_PORT = 7099
    RTSP_PORT = 7070
    RTSP_URL = f"rtsp://{DRONE_IP}:{RTSP_PORT}/webcam"

    CMD_HEARTBEAT = bytes([1, 1])
    CMD_INITIALIZE = bytes([100])
    CMD_CAMERA_1 = bytes([6, 1])
    CMD_CAMERA_2 = bytes([6, 2])
    CMD_SCREEN_MODE_1 = bytes([9, 1])
    CMD_SCREEN_MODE_2 = bytes([9, 2])

    def __init__(self):
        self.udp_socket: Optional[socket.socket] = None
        self.video_capture: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.is_connected = False
        self.device_type = 0
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.receive_thread: Optional[threading.Thread] = None

        # Video processor for YOLO
        self.video_processor = DroneVideoProcessor()

        # Recording
        self.video_writer: Optional[cv2.VideoWriter] = None
        self.is_recording = False

    def connect(self) -> bool:
        """Establish UDP connection with drone"""
        try:
            print(f"Connecting to drone at {self.DRONE_IP}:{self.UDP_PORT}...")

            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(2.0)
            self.send_command(self.CMD_HEARTBEAT)

            try:
                data, addr = self.udp_socket.recvfrom(1024)
                print(f"Received response from {addr}: {data.hex()}")
                self._parse_response(data)
                self.is_connected = True
                print(f"Connected! Device type: {self.device_type}")
            except socket.timeout:
                print("Warning: No response from drone, but continuing...")
                self.is_connected = True

            self.is_running = True
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True
            )
            self.heartbeat_thread.start()

            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True
            )
            self.receive_thread.start()

            time.sleep(0.5)
            self.send_command(self.CMD_INITIALIZE)

            return True

        except Exception as e:
            print(f"Error connecting to drone: {e}")
            return False

    def disconnect(self):
        """Disconnect from drone"""
        print("Disconnecting from drone...")

        if self.is_recording:
            self.stop_recording()

        self.is_running = False
        self.is_connected = False

        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)

        if self.receive_thread:
            self.receive_thread.join(timeout=2)

        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None

        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

        print("Disconnected.")

    def send_command(self, command: bytes) -> bool:
        """Send command to drone"""
        if not self.udp_socket:
            return False

        try:
            self.udp_socket.sendto(command, (self.DRONE_IP, self.UDP_PORT))
            return True
        except Exception as e:
            print(f"Error sending command: {e}")
            return False

    def _heartbeat_loop(self):
        """Background heartbeat thread"""
        while self.is_running:
            try:
                self.send_command(self.CMD_HEARTBEAT)
                time.sleep(1.0)
            except Exception as e:
                print(f"Heartbeat error: {e}")
                break

    def _receive_loop(self):
        """Background receive thread"""
        if not self.udp_socket:
            return

        self.udp_socket.settimeout(0.5)

        while self.is_running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                self._parse_response(data)
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"Receive error: {e}")
                break

    def _parse_response(self, data: bytes):
        """Parse drone response"""
        if len(data) >= 1:
            device_info = data[0]
            if device_info & 0x02:
                self.device_type = 2
            elif device_info & 0x0A:
                self.device_type = 10

    def start_video_stream(self) -> bool:
        """Start video stream"""
        try:
            print(f"Starting video stream from {self.RTSP_URL}...")

            self.video_capture = cv2.VideoCapture(self.RTSP_URL)
            self.video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self.video_capture.isOpened():
                print("Failed to open video stream")
                return False

            print("Video stream started!")
            return True

        except Exception as e:
            print(f"Error starting video stream: {e}")
            return False

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Get frame from video stream"""
        if not self.video_capture:
            return False, None

        ret, frame = self.video_capture.read()
        return ret, frame

    def start_recording(self, filename: str = None):
        """Start recording video"""
        if self.is_recording:
            print("Already recording!")
            return

        if filename is None:
            filename = f"drone_recording_{time.strftime('%Y%m%d_%H%M%S')}.mp4"

        # Get video properties
        ret, frame = self.get_frame()
        if not ret:
            print("Failed to get frame for recording setup")
            return

        height, width = frame.shape[:2]
        fps = 25  # Approximate FPS

        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))

        if self.video_writer.isOpened():
            self.is_recording = True
            print(f"Recording started: {filename}")
        else:
            print("Failed to start recording")

    def stop_recording(self):
        """Stop recording video"""
        if not self.is_recording:
            return

        self.is_recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        print("Recording stopped")


def main():
    """Main application with YOLO11 integration ready"""
    print("=" * 70)
    print("TEKY WiFi Drone Controller - YOLO11 Ready")
    print("=" * 70)
    print("\n📹 OpenCV Video Processing")
    print("🤖 YOLO11 Object Detection Ready")
    print("\nBasic Controls:")
    print("  Q       - Quit")
    print("  SPACE   - Toggle frame processing")
    print("  R       - Start/Stop recording")
    print("  S       - Take screenshot")
    print("\nCamera Controls:")
    print("  1       - Switch to Camera 1")
    print("  2       - Switch to Camera 2")
    print("  M       - Switch Screen Mode")
    print("\nYOLO Integration:")
    print("  Y       - Load YOLO model (when ready)")
    print("  F       - Toggle FPS display")
    print("\n💡 To enable YOLO11:")
    print("  1. pip install ultralytics")
    print("  2. Uncomment YOLO code in DroneVideoProcessor")
    print("  3. Download YOLO11 model (yolo11n.pt, yolo11s.pt, etc.)")
    print("=" * 70)

    # Create drone controller
    drone = TEKYDroneYOLO()

    # Connect to drone
    if not drone.connect():
        print("Failed to connect to drone. Exiting.")
        return

    # Start video stream
    video_enabled = drone.start_video_stream()
    if not video_enabled:
        print("Failed to start video stream.")
        drone.disconnect()
        return

    # Main loop
    screenshot_count = 0

    try:
        while True:
            # Get frame
            ret, frame = drone.get_frame()

            if ret and frame is not None:
                # Process frame with video processor (YOLO will be here)
                processed_frame, detections = drone.video_processor.process_frame(frame)

                # Add overlay info
                y_offset = 30
                cv2.putText(
                    processed_frame,
                    "TEKY Drone - YOLO11 Ready (Press Q to quit)",
                    (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )

                y_offset += 25
                cv2.putText(
                    processed_frame,
                    f"Device: {drone.device_type} | Connected: {drone.is_connected}",
                    (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                )

                # Show recording status
                if drone.is_recording:
                    y_offset += 25
                    cv2.putText(
                        processed_frame,
                        "● REC",
                        (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 0, 255),
                        2,
                    )

                # Show detection count if YOLO is active
                if detections:
                    y_offset += 25
                    cv2.putText(
                        processed_frame,
                        f"Detections: {len(detections)}",
                        (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 255),
                        1,
                    )

                # Display frame
                cv2.imshow("TEKY Drone - YOLO11 Ready", processed_frame)

                # Record if active
                if drone.is_recording and drone.video_writer:
                    drone.video_writer.write(processed_frame)
            else:
                print("Failed to get frame")

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == ord("Q"):
                break

            # Toggle processing
            elif key == ord(" "):
                drone.video_processor.toggle_processing()

            # Recording control
            elif key == ord("r") or key == ord("R"):
                if drone.is_recording:
                    drone.stop_recording()
                else:
                    drone.start_recording()

            # Screenshot
            elif key == ord("s") or key == ord("S"):
                if ret and frame is not None:
                    filename = f"screenshot_{screenshot_count:04d}.jpg"
                    cv2.imwrite(filename, processed_frame)
                    print(f"Screenshot saved: {filename}")
                    screenshot_count += 1

            # Camera controls
            elif key == ord("1"):
                drone.send_command(drone.CMD_CAMERA_1)
                print("Switched to camera 1")
            elif key == ord("2"):
                drone.send_command(drone.CMD_CAMERA_2)
                print("Switched to camera 2")
            elif key == ord("m") or key == ord("M"):
                drone.send_command(drone.CMD_SCREEN_MODE_1)
                print("Toggled screen mode")

            # YOLO controls
            elif key == ord("y") or key == ord("Y"):
                drone.video_processor.load_yolo_model()
            elif key == ord("f") or key == ord("F"):
                drone.video_processor.show_fps = not drone.video_processor.show_fps
                print(
                    f"FPS display: {'ON' if drone.video_processor.show_fps else 'OFF'}"
                )

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    finally:
        # Cleanup
        drone.disconnect()
        cv2.destroyAllWindows()
        print("Application closed.")


if __name__ == "__main__":
    main()
