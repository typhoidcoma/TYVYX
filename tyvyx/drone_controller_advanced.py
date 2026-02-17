"""TYVYX WiFi Drone Controller - Advanced (packaged copy)

This is the packaged copy of `drone_controller_advanced.py`. Imports
are package-relative so it can be used inside `tyvyx`.
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

		# Control values (0x80=128 is neutral, range 50-200 per E88Pro protocol)
		self.throttle = 128
		self.yaw = 128
		self.pitch = 128
		self.roll = 128

		# Control limits (E88Pro proven range)
		self.MIN_VAL = 50
		self.MAX_VAL = 200
		self.NEUTRAL = 128
		self.STEP = 50  # Control increment step (matches E88Pro accel)
		self.DECEL_STEP = 5  # Auto-deceleration toward center (0 to disable)

		# One-shot command flags
		self._takeoff_flag = False
		self._land_flag = False
		self._calibrate_flag = False
		self._flip_flag = False
		self._headless_mode = False  # toggle, persists until toggled again

		# Command sending
		self.control_thread = None
		self.is_active = False
		self.last_command_time = 0
		self.command_interval = 0.03  # 30ms between commands (~33 Hz, matches E88Pro)

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

	def takeoff(self):
		"""Trigger one-touch takeoff (flag 0x01)"""
		self._takeoff_flag = True

	def land(self):
		"""Trigger land (flag 0x02)"""
		self._land_flag = True

	def calibrate_gyro(self):
		"""Trigger gyro calibration (flag 0x80)"""
		self._calibrate_flag = True

	def flip(self):
		"""Trigger somersault/flip (flag 0x08). Combine with direction input."""
		self._flip_flag = True

	def toggle_headless(self):
		"""Toggle headless mode (flag 0x10)"""
		self._headless_mode = not self._headless_mode

	def _build_flags(self) -> int:
		"""Build the flags byte from current flag state."""
		flags = 0
		if self._takeoff_flag:
			flags |= 0x01
		if self._land_flag:
			flags |= 0x02
		if self._flip_flag:
			flags |= 0x08
		if self._headless_mode:
			flags |= 0x10
		if self._calibrate_flag:
			flags |= 0x80
		return flags

	def _clear_flags(self):
		"""Clear one-shot flags after sending. Headless is a toggle, not cleared."""
		self._takeoff_flag = False
		self._land_flag = False
		self._calibrate_flag = False
		self._flip_flag = False

	def _auto_decel(self):
		"""Decay control values toward center (128) by DECEL_STEP."""
		if self.DECEL_STEP <= 0:
			return
		for attr in ('roll', 'pitch', 'throttle', 'yaw'):
			val = getattr(self, attr)
			if val > self.NEUTRAL:
				setattr(self, attr, max(val - self.DECEL_STEP, self.NEUTRAL))
			elif val < self.NEUTRAL:
				setattr(self, attr, min(val + self.DECEL_STEP, self.NEUTRAL))

	def _send_flight_command(self):
		"""
		Send flight control command using E88Pro-proven packet format.

		9-byte packet: [0x03, 0x66, roll, pitch, throttle, yaw, flags, xor, 0x99]
		"""
		flags = self._build_flags()

		basebytes = bytearray(8)
		basebytes[0] = 0x66                       # protocol marker
		basebytes[1] = self.roll & 0xFF
		basebytes[2] = self.pitch & 0xFF
		basebytes[3] = self.throttle & 0xFF
		basebytes[4] = self.yaw & 0xFF
		basebytes[5] = flags
		basebytes[6] = basebytes[1] ^ basebytes[2] ^ basebytes[3] ^ basebytes[4] ^ basebytes[5]
		basebytes[7] = 0x99                       # end marker

		packet = bytes([0x03]) + bytes(basebytes)

		try:
			self.send_command(packet)
		except Exception as e:
			print(f"Error sending flight command: {e}")

		self._clear_flags()
		self._auto_decel()

	def get_status_text(self) -> List[str]:
		"""Get status text for display"""
		lines = [
			f"Throttle: {self.throttle:3d} ({((self.throttle-128)/128*100):+.0f}%)",
			f"Yaw:      {self.yaw:3d} ({((self.yaw-128)/128*100):+.0f}%)",
			f"Pitch:    {self.pitch:3d} ({((self.pitch-128)/128*100):+.0f}%)",
			f"Roll:     {self.roll:3d} ({((self.roll-128)/128*100):+.0f}%)",
		]
		if self._headless_mode:
			lines.append("HEADLESS MODE: ON")
		return lines


class TYVYXDroneControllerAdvanced:
	"""Advanced controller for TYVYX WiFi Drone with flight controls"""

	# Network Configuration
	DRONE_IP = "192.168.1.1"
	UDP_PORT = 7099
	RTSP_PORT = 7070
	RTSP_URL = f"rtsp://{DRONE_IP}:{RTSP_PORT}/webcam"

	# Command bytes
	CMD_HEARTBEAT = bytes([0x01, 0x01])
	CMD_INITIALIZE = bytes([0x64])               # connection init
	CMD_START_VIDEO = bytes([0x08, 0x01])        # activates RTSP server (E88Pro proven)
	CMD_SPECIAL = bytes([0x63])
	CMD_CAMERA_1 = bytes([0x06, 0x01])
	CMD_CAMERA_2 = bytes([0x06, 0x02])
	CMD_SCREEN_MODE_1 = bytes([0x09, 0x01])
	CMD_SCREEN_MODE_2 = bytes([0x09, 0x02])

	def __init__(self, drone_ip: str = "192.168.1.1"):
		"""Initialize the drone controller"""
		# Allow per-instance IP override (class vars remain as defaults)
		self.DRONE_IP = drone_ip
		self.RTSP_URL = f"rtsp://{drone_ip}:{self.RTSP_PORT}/webcam"

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
			except (socket.timeout, ConnectionResetError, OSError):
				# No response or ICMP port-unreachable (WinError 10054 on Windows
				# when sending UDP to a host that isn't listening). Treat as
				# "drone present but silent" and continue — heartbeats will tell.
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
			except (socket.timeout, ConnectionResetError):
				# timeout or ICMP port-unreachable — drone not yet reachable
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

			# Send video activation command (activates RTSP server on drone)
			self.send_command(self.CMD_START_VIDEO, verbose=True)
			time.sleep(1.0)  # give RTSP server time to start

			from .video_stream import OpenCVVideoStream

			self.video_stream = OpenCVVideoStream(
				self.RTSP_URL, buffer_size=1, prefer_tcp=True,
				max_retries=2, retry_delay=1.0, rtsp_timeout=5.0,
			)
			if not self.video_stream.start(timeout=5.0):
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
			# E88Pro pattern: pause stream, wait, send switch, wait, reinitialize
			if getattr(self, 'video_stream', None):
				try:
					self.video_stream.stop()
					time.sleep(1.0)  # pause before switch (E88Pro uses 1s)
					self.send_command(cmd, verbose=True)
					time.sleep(1.0)  # wait for camera to switch
					started = self.start_video_stream()
					return bool(started)
				except Exception:
					return False
			# No active video stream — just send the command
			return bool(self.send_command(cmd, verbose=True))
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
	print("TYVYX WiFi Drone Controller - ADVANCED EDITION")
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
	print("\nFlight Controls (E88Pro protocol):")
	print("  W/S     - Pitch Forward/Backward")
	print("  A/D     - Roll Left/Right")
	print("  UP/DOWN - Throttle Up/Down")
	print("  LEFT/RIGHT - Yaw Left/Right")
	print("  Z       - One-touch Takeoff")
	print("  X       - Land")
	print("  C       - Calibrate Gyro")
	print("  F       - Flip (combine with direction)")
	print("  H       - Toggle Headless Mode")
	print("=" * 70)

	# Create drone controller
	drone = TYVYXDroneControllerAdvanced()

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
						"TYVYX Drone Controller - Press Q to quit",
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

					cv2.imshow("TYVYX Drone Video Feed", frame)
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
				elif key == ord("z") or key == ord("Z"):
					drone.flight_controller.takeoff()
					print("TAKEOFF command sent")
				elif key == ord("x") or key == ord("X"):
					drone.flight_controller.land()
					print("LAND command sent")
				elif key == ord("c") or key == ord("C"):
					drone.flight_controller.calibrate_gyro()
					print("CALIBRATE GYRO command sent")
				elif key == ord("f") or key == ord("F"):
					drone.flight_controller.flip()
					print("FLIP command sent")
				elif key == ord("h") or key == ord("H"):
					drone.flight_controller.toggle_headless()
					print(f"HEADLESS MODE: {'ON' if drone.flight_controller._headless_mode else 'OFF'}")

	except KeyboardInterrupt:
		print("\nInterrupted by user")

	finally:
		# Cleanup
		drone.disconnect()
		cv2.destroyAllWindows()
		print("Application closed.")


if __name__ == "__main__":
	main()
