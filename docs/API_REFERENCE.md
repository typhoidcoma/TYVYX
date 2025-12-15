# TEKY Project — API Reference

This document provides a concise reference to the main modules, classes,
and public methods in the TEKY repository. It is intended as a quick
starting guide for contributors and users.

## Modules

- `app.py`: Minimal Flask web front-end. Provides a single route `/`
  that returns a short status string.

- `drone_controller.py`: Basic controller for video and camera-related
  commands.

- `drone_controller_advanced.py`: Experimental advanced controller that
  includes an experimental `FlightController` for throttle/yaw/pitch/roll.

- `drone_controller_yolo.py`: Video processing pipeline prepared for
  YOLO11 integration and recording support.

- `network_diagnostics.py`: Network diagnostic utilities for testing
  connectivity, capturing UDP packets, and experimenting with commands.

## Key Classes and Methods

- `TEKYDroneController` (in `drone_controller.py`)
  - `connect() -> bool`: Establish UDP connection and start threads.
  - `disconnect()`: Stop threads and close sockets.
  - `start_video_stream() -> bool`: Open RTSP stream via OpenCV.
  - `get_frame() -> (bool, np.ndarray)`: Grab a frame from the stream.
  - `send_command(command: bytes) -> bool`: Send a UDP command to drone.

- `TEKYDroneControllerAdvanced` (in `drone_controller_advanced.py`)
  - Same API as `TEKYDroneController` plus a `flight_controller` attribute.

- `FlightController` (in `drone_controller_advanced.py`)
  - `start()` / `stop()`: Start/stop background command sending.
  - `increase_throttle()`, `yaw_left()`, etc.: Small helpers to mutate
    control channels (throttle/yaw/pitch/roll).

- `DroneVideoProcessor` (in `drone_controller_yolo.py`)
  - `load_yolo_model(model_path: str)`: Hook to load ultralytics YOLO11 model.
  - `process_frame(frame: np.ndarray) -> (np.ndarray, list)`: Process a
    frame, optionally run detection, and return annotated frame + detections.

- `TEKYDroneYOLO` (in `drone_controller_yolo.py`)
  - Adds recording and processing features on top of the base controller.

- `DroneNetworkDiagnostics` (in `network_diagnostics.py`)
  - `test_ping()`, `test_udp_connection()`, `capture_udp_packets(duration)`
    and other helpers for diagnosing network issues and experimental commands.

## Common Constants

- `DRONE_IP`: 192.168.1.1 (default drone address)
- `UDP_PORT`: 7099 (control channel)
- `RTSP_PORT`: 7070 (video stream)
- `RTSP_URL`: rtsp://192.168.1.1:7070/webcam

## Quick Start Examples

- Run the basic controller:

```
python drone_controller.py
```

- Run the advanced controller (experimental flight controls):

```
python drone_controller_advanced.py
```

- Run the YOLO-ready processor (enable YOLO by installing ultralytics and
  uncommenting the code in `drone_controller_yolo.py`):

```
python drone_controller_yolo.py
```

- Run network diagnostics:

```
python network_diagnostics.py
```

## Notes & Safety

- Flight control features are experimental. Do not attempt to fly in
  constrained or unsafe environments when using experimental commands.
- Several methods assume you are connected to the drone's WiFi network
  and that FFmpeg/OpenCV are correctly installed on the host.

## Contribution

If you add or change public APIs, update this file with method signatures
and short descriptions so other contributors can find and use them.
