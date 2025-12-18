"""TEKY WiFi Drone Controller with YOLO integration (packaged copy)."""

import cv2
import socket
import threading
import time
import numpy as np
from typing import Optional, Tuple, List, Dict


class DroneVideoProcessor:
	"""Video processing pipeline ready for YOLO integration"""

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
		Load YOLO model
		To use: Install ultralytics and uncomment the code below
		"""
		try:
			print("YOLO integration ready!")
			return False
		except Exception as e:
			print(f"Error loading YOLO model: {e}")
			return False

	def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
		"""
		Process frame with YOLO detection

		Returns processed frame and list of detections
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
		# Threaded video stream helper
		self.video_stream = None
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

		# Stop threaded video stream if active
		try:
			if getattr(self, "video_stream", None):
				self.video_stream.stop()
				self.video_stream = None
		except Exception as e:
			print(f"Note: video stream stop: {e}")

		if self.video_capture:
			try:
				self.video_capture.release()
			except Exception:
				pass
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

			from .video_stream import OpenCVVideoStream

			self.video_stream = OpenCVVideoStream(self.RTSP_URL, buffer_size=1, prefer_tcp=True, max_retries=5, retry_delay=1.5)
			if not self.video_stream.start(timeout=6.0):
				print("Failed to open video stream")
				return False

			print("Video stream started!")
			return True

		except Exception as e:
			print(f"Error starting video stream: {e}")
			return False

	def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
		"""Get frame from video stream"""
		if getattr(self, "video_stream", None):
			return self.video_stream.read()

		if self.video_capture:
			ret, frame = self.video_capture.read()
			return ret, frame

		return False, None

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
	"""Main application with YOLO integration ready"""
	print("=" * 70)
	print("TEKY WiFi Drone Controller - YOLO Ready")
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

				# Display frame
				cv2.imshow("TEKY Drone - YOLO Ready", processed_frame)

				# Record if active
				if drone.is_recording and drone.video_writer:
					drone.video_writer.write(processed_frame)
			else:
				print("Failed to get frame")

			# Handle keyboard input
			key = cv2.waitKey(1) & 0xFF

			if key == ord("q") or key == ord("Q"):
				break

	except KeyboardInterrupt:
		print("\nInterrupted by user")

	finally:
		# Cleanup
		drone.disconnect()
		cv2.destroyAllWindows()
		print("Application closed.")


if __name__ == "__main__":
	main()

