"""TEKY WiFi Drone Controller - Advanced (packaged copy)

This is the packaged copy of `drone_controller_advanced.py`. Imports
are package-relative so it can be used inside `teky`.
"""

import cv2
import socket
import threading
import time
from typing import Optional, Tuple, List


class FlightController:
	"""Experimental flight control for drone"""

	def __init__(self, send_command_callback):
		"""
		Initialize flight controller
		Args:
			send_command_callback: Function to send UDP commands
		"""
		self.send_command = send_command_callback

		# Control values (0-255, 128 is neutral)
		self.throttle = 128
		self.yaw = 128
		self.pitch = 128
		self.roll = 128

		# Control limits
		self.MIN_VAL = 0
		self.MAX_VAL = 255
		self.NEUTRAL = 128
		self.STEP = 10  # Control increment step

		# Command sending
		self.control_thread = None
		self.is_active = False
		self.last_command_time = 0
		self.command_interval = 0.04  # 40ms between commands (25 Hz)

	def start(self):
		"""Start sending flight commands"""
		if not self.is_active:
			self.is_active = True
			self.control_thread = threading.Thread(
				target=self._control_loop, daemon=True
			)
			self.control_thread.start()
			print("Flight controller started")

	def stop(self):
		"""Stop sending flight commands and reset to neutral"""
		self.is_active = False
		self.reset()
		if self.control_thread:
			self.control_thread.join(timeout=1)
		print("Flight controller stopped")

	def reset(self):
		"""Reset all controls to neutral"""
		self.throttle = self.NEUTRAL
		self.yaw = self.NEUTRAL
		self.pitch = self.NEUTRAL
		self.roll = self.NEUTRAL

	def increase_throttle(self):
		"""Increase throttle (up)"""
		self.throttle = min(self.throttle + self.STEP, self.MAX_VAL)

	def decrease_throttle(self):
		"""Decrease throttle (down)"""
		self.throttle = max(self.throttle - self.STEP, self.MIN_VAL)

	def yaw_left(self):
		"""Rotate left"""
		self.yaw = max(self.yaw - self.STEP, self.MIN_VAL)

	def yaw_right(self):
		"""Rotate right"""
		self.yaw = min(self.yaw + self.STEP, self.MAX_VAL)

	def pitch_forward(self):
		"""Move forward"""
		self.pitch = min(self.pitch + self.STEP, self.MAX_VAL)

	def pitch_backward(self):
		"""Move backward"""
		self.pitch = max(self.pitch - self.STEP, self.MIN_VAL)

	def roll_left(self):
		"""Move left"""
		self.roll = max(self.roll - self.STEP, self.MIN_VAL)

	def roll_right(self):
		"""Move right"""
		self.roll = min(self.roll + self.STEP, self.MAX_VAL)

	def _control_loop(self):
		"""Background thread to send control commands"""
		while self.is_active:
			current_time = time.time()

			# Send command at specified interval
			if current_time - self.last_command_time >= self.command_interval:
				self._send_flight_command()
				self.last_command_time = current_time

			time.sleep(0.01)  # Small sleep to prevent CPU spinning

	def _send_flight_command(self):
		"""
		Send flight control command

		EXPERIMENTAL COMMAND FORMAT:
		Based on common drone protocols, trying multiple possible formats:
		"""
		# Format 1: Simple 5-byte command with checksum
		cmd_id = 0x50
		checksum = (cmd_id + self.throttle + self.yaw + self.pitch + self.roll) & 0xFF
		command = bytes(
			[cmd_id, self.throttle, self.yaw, self.pitch, self.roll, checksum]
		)

		# Send command
		try:
			self.send_command(command)
		except Exception as e:
			print(f"Error sending flight command: {e}")

	def get_status_text(self) -> List[str]:
		"""Get status text for display"""
		return [
			f"Throttle: {self.throttle:3d} ({((self.throttle-128)/128*100):+.0f}%)",
			f"Yaw:      {self.yaw:3d} ({((self.yaw-128)/128*100):+.0f}%)",
			f"Pitch:    {self.pitch:3d} ({((self.pitch-128)/128*100):+.0f}%)",
			f"Roll:     {self.roll:3d} ({((self.roll-128)/128*100):+.0f}%)",
		]


class TEKYDroneControllerAdvanced:
	"""Advanced controller for TEKY WiFi Drone with flight controls"""

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
		# Threaded video stream helper (set when starting video)
		self.video_stream = None
		self.is_running = False
		self.is_connected = False
		self.device_type = 0
		self.heartbeat_thread: Optional[threading.Thread] = None
		self.receive_thread: Optional[threading.Thread] = None

		# Flight controller
		self.flight_controller = FlightController(self.send_command)

	def connect(self) -> bool:
		"""Establish UDP connection with the drone"""
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
		"""Disconnect from the drone"""
		print("Disconnecting from drone...")

		# Stop flight controller first
		if self.flight_controller.is_active:
			self.flight_controller.stop()

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

	def send_command(self, command: bytes, verbose: bool = False) -> bool:
		"""Send a command to the drone via UDP"""
		if not self.udp_socket:
			return False

		try:
			self.udp_socket.sendto(command, (self.DRONE_IP, self.UDP_PORT))
			if verbose or len(command) < 6:  # Don't spam flight commands
				print(f"Sent command: {command.hex()}")
			return True
		except Exception as e:
			print(f"Error sending command: {e}")
			return False

	def _heartbeat_loop(self):
		"""Background thread to send heartbeat packets"""
		while self.is_running:
			try:
				self.send_command(self.CMD_HEARTBEAT)
				time.sleep(1.0)
			except Exception as e:
				print(f"Heartbeat error: {e}")
				break

	def _receive_loop(self):
		"""Background thread to receive UDP responses"""
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
		"""Parse response data from drone"""
		if len(data) >= 1:
			device_info = data[0]
			if device_info & 0x02:
				self.device_type = 2
			elif device_info & 0x0A:
				self.device_type = 10

	def start_video_stream(self) -> bool:
		"""Start receiving video stream from drone"""
		try:
			print(f"Starting video stream from {self.RTSP_URL}...")

			from .video_stream import OpenCVVideoStream

			self.video_stream = OpenCVVideoStream(self.RTSP_URL, buffer_size=1, prefer_tcp=True, max_retries=5, retry_delay=1.5)
			if not self.video_stream.start(timeout=6.0):
				print("Failed to open video stream")
				return False

			print("Video stream started successfully!")
			return True

		except Exception as e:
			print(f"Error starting video stream: {e}")
			return False

	def get_frame(self) -> Tuple[bool, Optional[Tuple[int, int]]]:
		"""Get a frame from the video stream"""
		if getattr(self, "video_stream", None):
			return self.video_stream.read()

		if self.video_capture:
			ret, frame = self.video_capture.read()
			return ret, frame

		return False, None

	def switch_camera(self, camera_num: int):
		"""Switch between cameras (if drone has multiple).
		Args:
			camera_num: 1 or 2
		"""
		try:
			if camera_num == 1:
				cmd = self.CMD_CAMERA_1
			elif camera_num == 2:
				cmd = self.CMD_CAMERA_2
			else:
				return False
			sent = self.send_command(cmd, verbose=True)
			# If a threaded video stream is active, restart it so the new camera feed is picked up
			if getattr(self, 'video_stream', None):
				try:
					self.video_stream.stop()
					time.sleep(0.35)
					# attempt to start stream again
					started = self.start_video_stream()
					return bool(started)
				except Exception:
					return bool(sent)
			return bool(sent)
		except Exception:
			return False

	def switch_screen_mode(self, mode: int):
		"""Switch screen mode.
		Args:
			mode: 1 or 2
		"""
		if mode == 1:
			self.send_command(self.CMD_SCREEN_MODE_1, verbose=True)
		elif mode == 2:
			self.send_command(self.CMD_SCREEN_MODE_2, verbose=True)


def main():
	"""Main application loop with flight controls"""
	print("=" * 70)
	print("TEKY WiFi Drone Controller - ADVANCED EDITION")
	print("=" * 70)
	print("\n⚠️  WARNING: Flight controls are EXPERIMENTAL!")
	print("   They may not work or could behave unexpectedly.")
	print("   Use at your own risk!")
	print("\nBasic Controls:")
	print("  Q       - Quit")
	print("  SPACE   - Start/Stop Flight Controller")
	print("  ESC     - Emergency Reset (center all controls)")
	print("\nCamera Controls:")
	print("  1       - Switch to Camera 1")
	print("  2       - Switch to Camera 2")
	print("  M       - Switch Screen Mode")
	print("  S       - Take Screenshot")
	print("\nFlight Controls (EXPERIMENTAL):")
	print("  W/S     - Pitch Forward/Backward")
	print("  A/D     - Roll Left/Right")
	print("  ↑/↓     - Throttle Up/Down")
	print("  ←/→     - Yaw Left/Right")
	print("=" * 70)

	# Create drone controller
	drone = TEKYDroneControllerAdvanced()

	# Connect to drone
	if not drone.connect():
		print("Failed to connect to drone. Exiting.")
		return

	# Start video stream
	video_enabled = drone.start_video_stream()

	# Main loop
	screen_mode = 1
	screenshot_count = 0
	flight_active = False

	try:
		while True:
			# Get and display video frame
			if video_enabled:
				ret, frame = drone.get_frame()

				if ret and frame is not None:
					# Add overlay
					y_offset = 30
					cv2.putText(
						frame,
						"TEKY Drone Controller - Press Q to quit",
						(10, y_offset),
						cv2.FONT_HERSHEY_SIMPLEX,
						0.6,
						(0, 255, 0),
						2,
					)

					y_offset += 25
					cv2.putText(
						frame,
						f"Device Type: {drone.device_type} | Connected: {drone.is_connected}",
						(10, y_offset),
						cv2.FONT_HERSHEY_SIMPLEX,
						0.5,
						(0, 255, 0),
						1,
					)

					# Flight status
					y_offset += 25
					status_color = (0, 255, 0) if flight_active else (0, 165, 255)
					status_text = "ACTIVE" if flight_active else "INACTIVE"
					cv2.putText(
						frame,
						f"Flight Controller: {status_text}",
						(10, y_offset),
						cv2.FONT_HERSHEY_SIMPLEX,
						0.5,
						status_color,
						2,
					)

					# Show flight controls if active
					if flight_active:
						y_offset += 25
						for line in drone.flight_controller.get_status_text():
							cv2.putText(
								frame,
								line,
								(10, y_offset),
								cv2.FONT_HERSHEY_SIMPLEX,
								0.4,
								(255, 255, 0),
								1,
							)
							y_offset += 20

					cv2.imshow("TEKY Drone Video Feed", frame)
				else:
					print("Failed to get frame")

			# Handle keyboard input
			key = cv2.waitKey(1) & 0xFF

			if key == ord("q") or key == ord("Q"):
				break

			# Flight control toggle
			elif key == ord(" "):
				if flight_active:
					drone.flight_controller.stop()
					flight_active = False
					print("Flight controller STOPPED")
				else:
					drone.flight_controller.start()
					flight_active = True
					print("Flight controller STARTED")

			# Emergency reset
			elif key == 27:  # ESC
				drone.flight_controller.reset()
				print("EMERGENCY RESET - All controls centered")

			# Camera controls
			elif key == ord("1"):
				drone.send_command(drone.CMD_CAMERA_1, verbose=True)
			elif key == ord("2"):
				drone.send_command(drone.CMD_CAMERA_2, verbose=True)
			elif key == ord("m") or key == ord("M"):
				screen_mode = 2 if screen_mode == 1 else 1
				drone.send_command(
					(
						drone.CMD_SCREEN_MODE_1
						if screen_mode == 1
						else drone.CMD_SCREEN_MODE_2
					),
					verbose=True,
				)
			elif key == ord("s") or key == ord("S"):
				if video_enabled and ret and frame is not None:
					filename = f"screenshot_{screenshot_count:04d}.jpg"
					cv2.imwrite(filename, frame)
					print(f"Screenshot saved: {filename}")
					screenshot_count += 1

			# Flight controls (only work when flight controller is active)
			elif flight_active:
				if key == ord("w") or key == ord("W"):
					drone.flight_controller.pitch_forward()
				elif key == ord("s") or key == ord("S"):
					drone.flight_controller.pitch_backward()
				elif key == ord("a") or key == ord("A"):
					drone.flight_controller.roll_left()
				elif key == ord("d") or key == ord("D"):
					drone.flight_controller.roll_right()
				elif key == 82 or key == 0:  # Up arrow
					drone.flight_controller.increase_throttle()
				elif key == 84 or key == 1:  # Down arrow
					drone.flight_controller.decrease_throttle()
				elif key == 81 or key == 2:  # Left arrow
					drone.flight_controller.yaw_left()
				elif key == 83 or key == 3:  # Right arrow
					drone.flight_controller.yaw_right()

	except KeyboardInterrupt:
		print("\nInterrupted by user")

	finally:
		# Cleanup
		drone.disconnect()
		cv2.destroyAllWindows()
		print("Application closed.")


if __name__ == "__main__":
	main()
