# TYVYX Project — API Reference

Reference for all modules, classes, and endpoints in the current codebase.

## Quick Start

```bash
# Backend (FastAPI, port 8000)
python -m autonomous.api.main

# Frontend (React + Vite, port 5173)
cd frontend && npm run dev
```

Open http://localhost:5173 in your browser.

## REST API Endpoints

### Drone Control — `/api/drone`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/drone/connect` | Connect to drone (auto-detects protocol by subnet) |
| POST | `/api/drone/disconnect` | Disconnect and stop all streams |
| GET | `/api/drone/status` | Connection state, video streaming, flight armed |
| POST | `/api/drone/command` | Send command: `start_video`, `stop_video`, `arm`, `disarm`, `takeoff`, `land`, `calibrate`, `headless`, `camera1`, `camera2` |

### Video Streaming — `/api/video`

| Method | Path | Description |
|--------|------|-------------|
| WS | `/api/video/ws` | WebSocket binary frames (primary, lowest latency) |
| GET | `/api/video/feed` | MJPEG HTTP stream (fallback for browsers) |
| GET | `/api/video/test` | Synthetic test frames (no drone needed) |
| GET | `/api/video/status` | Streaming state and frame stats |
| GET | `/api/video/capabilities` | Available transports |

### Position Tracking — `/api/position`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/position/current` | Position (x, y), velocity, altitude, feature count |
| GET | `/api/position/trajectory` | History with timestamps (max 1000 points) |
| GET | `/api/position/statistics` | Uncertainty, measurement data |
| POST | `/api/position/start` | Enable optical flow tracking |
| POST | `/api/position/stop` | Disable tracking |
| POST | `/api/position/reset` | Reset position to (x, y) |
| POST | `/api/position/altitude` | Set altitude for velocity scaling |
| POST | `/api/position/clear_trajectory` | Clear trajectory history |

### Network — `/api/network`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/network/scan` | Scan WiFi networks, flag drone-like SSIDs |

## Core Modules

### Drone Controllers (`tyvyx/`)

**`WifiUavDroneController`** (`tyvyx/wifi_uav_controller.py`)
- Primary controller for K417 drones (192.168.169.1)
- RC packet construction with rolling 16-bit counters (~120 bytes)
- Heartbeat: 2 Hz neutral, 80 Hz armed
- Socket sharing with video adapter (single-port constraint)
- `WifiUavFlightController` — arm/disarm, takeoff/land, calibrate, headless, axis control

**`TYVYXDroneControllerAdvanced`** (`tyvyx/drone_controller_advanced.py`)
- Legacy E88Pro controller (192.168.1.1)
- 9-byte flight packets: `[0x03, 0x66, roll, pitch, throttle, yaw, flags, xor, 0x99]`
- `FlightController` — same command interface as WifiUavFlightController

### Video Pipeline (`tyvyx/protocols/`, `tyvyx/services/`)

**`PushJpegVideoProtocolAdapter`** (`tyvyx/protocols/push_jpeg_video_protocol.py`)
- K417 push-based JPEG: 0x93 0x01 magic, 56-byte header, fragment reassembly
- Sends `START_STREAM` (0xef 0x00 0x04 0x00) as keepalive every 100ms
- Generates JPEG headers (SOI+DQT+DHT+SOF0+SOS) from raw fragment data

**`S2xVideoProtocolAdapter`** (`tyvyx/protocols/s2x_video_protocol.py`)
- E88Pro pull-based JPEG: 0x40 0x40 sync bytes

**`VideoReceiverService`** (`tyvyx/services/video_receiver.py`)
- Manages protocol adapter lifecycle with auto-reconnect

**`FrameHub`** (`tyvyx/frame_hub.py`)
- Asyncio fan-out hub: distributes JPEG frames to multiple clients via per-client queues (size 2, drop-oldest)

### Position Tracking (`autonomous/perception/`, `autonomous/localization/`)

**`OpticalFlowTracker`** (`autonomous/perception/optical_flow_tracker.py`)
- Sparse Lucas-Kanade optical flow (CPU + CUDA auto-detection)
- Feature re-detection when count drops below threshold
- Outlier rejection by tracking status + flow magnitude

**`PositionEstimator`** (`autonomous/localization/position_estimator.py`)
- Kalman filter (4D state: x, y, vx, vy) with constant velocity model
- Alternative: `SimpleDeadReckoning` (velocity integration)

**`CoordinateTransformer`** (`autonomous/localization/coordinate_transforms.py`)
- Pixel velocity to world velocity conversion (depends on altitude + camera matrix)

### Services (`autonomous/services/`)

**`DroneService`** (`autonomous/services/drone_service.py`)
- Singleton hub managing drone connections, video pipeline, and flight control
- Auto-detects protocol: 192.168.169.x = WiFi UAV (K417), else = E88Pro
- Frame pump bridges threading (UDP) to asyncio (FrameHub)
- Feeds frames to position service at ~10 Hz

**`PositionService`** (`autonomous/services/position_service.py`)
- Singleton wrapping optical flow tracker + Kalman filter

**`NetworkService`** (`autonomous/services/network_service.py`)
- WiFi scanning with drone SSID pattern matching

## Network Constants

| Drone | IP | Video Port | Control Port | Protocol |
|-------|------|-----------|-------------|----------|
| K417 (WiFi UAV) | 192.168.169.1 | 8800 | 8801 | Push-based 0x93 JPEG |
| E88Pro (legacy) | 192.168.1.1 | 7070 | 7099 | Pull-based S2x JPEG |

## Diagnostic Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `probe_drone.py` | Network connectivity + protocol probing |
| `analyze_packets.py` | Packet capture analysis |
| `fingerprint_9301.py` | Classify 0x93 packet variants |
| `probe_camera.py` | JieLi camera module probing (192.168.100.1) |
| `probe_camera_switch.py` | Test camera switch commands |
| `probe_lxpro_handshake.py` | lxPro encrypted protocol research |
| `post_connect.py` | Manual connection test via API |
| `post_drone_command.py` | Send commands via API |
| `get_video_status.py` | Check video streaming status |

## Notes

- FFmpeg is **not** required — the video pipeline uses direct UDP JPEG passthrough
- All sockets bind to the detected drone WiFi adapter IP, not `0.0.0.0`
- The K417 requires all UDP traffic from a single source port (video + control share one socket)
