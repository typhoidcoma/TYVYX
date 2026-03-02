# TYVYX Project - API Reference

## Quick Start

```bash
# Backend (FastAPI, port 8000)
python -m autonomous.api.main

# Frontend (React + Vite, port 5173)
cd frontend && npm run dev
```

API docs at http://localhost:8000/docs.

## REST API Endpoints

### Drone Control - `/api/drone`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/connect` | Connect to drone (auto-detects protocol by subnet) |
| POST | `/disconnect` | Disconnect and stop all streams |
| GET | `/status` | Connection state, video streaming, flight armed |
| POST | `/command` | Send command: `start_video`, `stop_video`, `arm`, `disarm`, `takeoff`, `land`, `calibrate`, `headless`, `camera1`, `camera2`, `raw` |
| GET | `/telemetry` | Get telemetry data |

### Video Streaming - `/api/video`

| Method | Path | Description |
|--------|------|-------------|
| WS | `/ws` | WebSocket binary frames (primary, lowest latency) |
| GET | `/feed` | MJPEG HTTP stream (fallback) |
| GET | `/status` | Streaming state and frame stats |
| GET | `/capabilities` | Available transports |
| WS | `/test` | Synthetic test frames (no drone needed) |

### Position Tracking - `/api/position`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/current` | Position (x, y, z), velocity, altitude, feature count, camera mode |
| GET | `/trajectory` | Trajectory history with timestamps |
| GET | `/statistics` | Uncertainty, measurement data, EKF stats |
| POST | `/start` | Start position tracking (auto-switches to bottom camera) |
| POST | `/stop` | Stop tracking (restores front camera) |
| POST | `/ground_zero` | Set current position as (0,0,0) reference, anchor RSSI |
| POST | `/camera_mode` | Set camera mode: `bottom` (optical flow) or `front` |
| POST | `/reset` | Reset position to (x, y) |
| POST | `/altitude` | Set altitude for velocity scaling |
| POST | `/clear_trajectory` | Clear trajectory history |

### RC Control - `/api/rc`

| Method | Path | Description |
|--------|------|-------------|
| WS | `/ws` | Real-time stick control via WebSocket (JSON: `{t, y, p, r}`) |

### Autopilot - `/api/autopilot`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/state` | Current autopilot state |
| POST | `/enable` | Enable position hold (current or specified position) |
| POST | `/disable` | Disable position hold |
| POST | `/target` | Update target position |
| POST | `/gains` | Tune PID gains for axis (`x` or `y`) |

### Depth Estimation - `/api/depth`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Depth service status |
| GET | `/data` | Current depth data (avg_depth, altitude, timing) |
| GET | `/map` | Colorized depth map as JPEG |
| POST | `/start` | Start depth estimation |
| POST | `/stop` | Stop depth estimation |
| POST | `/sensitivity` | Set visualization sensitivity (0-100) |
| POST | `/max_depth` | Set max depth clamp (meters) |
| POST | `/depth_scale` | Set depth scale multiplier |

### WiFi RSSI - `/api/rssi`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | RSSI service status |
| GET | `/data` | Current RSSI + distance data |
| GET | `/calibration` | Calibration points + model |
| POST | `/start` | Start RSSI polling |
| POST | `/stop` | Stop RSSI polling |
| POST | `/calibrate` | Record calibration point at known distance |

### Debug / Sensor Testing - `/api/debug`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/optical_flow` | Pixel velocity, feature count, GPU status |
| POST | `/transform/pixel_to_world` | Test pixel-to-world velocity conversion |
| GET | `/transform/camera` | Camera intrinsics (fx, fy, FOV) |
| GET | `/ekf/state` | Full 6D state vector, covariance, update counts |
| POST | `/ekf/inject_velocity` | Inject synthetic velocity measurement |
| POST | `/ekf/inject_altitude` | Inject synthetic altitude measurement |
| POST | `/ekf/inject_rssi` | Inject synthetic RSSI distance |
| GET | `/depth` | Depth service diagnostics |
| GET | `/rssi` | RSSI diagnostics (model params, calibration) |
| POST | `/rssi/set_model` | Set path-loss model parameters |
| POST | `/rssi/reset_calibration` | Clear calibration points |
| GET | `/pipeline` | Full sensor fusion pipeline overview |

### Network - `/api/network`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scan` | Scan WiFi networks, flag drone-like SSIDs |

### WebSocket - `/ws`

| Path | Description |
|------|-------------|
| `/telemetry` | Telemetry stream at ~10 Hz |

## Core Modules

### Drone Controllers (`tyvyx/`)

**`WifiUavDroneController`** (`tyvyx/wifi_uav_controller.py`)
- Primary controller for K417 drones (192.168.169.1:8800, single port)
- RC packet construction with rolling 16-bit counters
- Heartbeat: 2 Hz neutral, 80 Hz armed
- Socket sharing with video adapter (single-port constraint)

**`TYVYXDroneControllerAdvanced`** (`tyvyx/drone_controller_advanced.py`)
- Legacy E88Pro controller (192.168.1.1, ports 7099/7070)
- 9-byte flight packets

### Video Pipeline (`tyvyx/protocols/`, `tyvyx/frame_hub.py`)

**`K417ProtocolEngine`** (`tyvyx/protocols/k417_protocol_engine.py`)
- Pull-based video at 21fps with REQUEST_A/REQUEST_B frame ACKs
- Frame-synced RC burst (1 per frame)
- Warmup + watchdog threads

**`PushJpegVideoProtocolAdapter`** (`tyvyx/protocols/push_jpeg_video_protocol.py`)
- K417 push-based JPEG fallback: 0x93 0x01 magic, 56-byte header, fragment reassembly

**`FrameHub`** (`tyvyx/frame_hub.py`)
- Asyncio fan-out: distributes JPEG frames to clients via per-client queues (size 2, drop-oldest)

No FFmpeg or transcoding needed. Raw JPEG passthrough end-to-end.

### Sensor Fusion (`autonomous/`)

**`PositionService`** (`autonomous/services/position_service.py`)
- Singleton wrapping optical flow + EKF + coordinate transformer
- Camera mode switching (front/bottom) for optical flow
- Feeds from depth (altitude) and RSSI (distance)

**`EKFPositionEstimator`** (`autonomous/localization/ekf_position_estimator.py`)
- 6D state: [x, y, z, vx, vy, vz]
- Fuses optical flow velocity, depth altitude, RSSI distance

**`DepthService`** (`autonomous/services/depth_service.py`)
- Monocular depth estimation (Depth Anything V2)
- Feeds altitude to EKF when bottom camera active

**`WifiRssiService`** (`autonomous/services/wifi_rssi_service.py`)
- WiFi signal strength to distance via log-distance path-loss model
- Calibratable with known-distance measurements

### Services (`autonomous/services/`)

**`DroneService`** (`autonomous/services/drone_service.py`)
- Singleton managing drone connections, video pipeline, flight control
- 3-tier protocol detection: port probe -> SSID -> IP fallback
- Frame pump bridges threading (UDP) to asyncio (FrameHub)

## Network Constants

| Drone | IP | Port | Protocol |
|-------|------|------|----------|
| K417 (WiFi UAV) | 192.168.169.1 | 8800 | Push/Pull 0x93 JPEG (single port, video + control) |
| E88Pro (legacy) | 192.168.1.1 | 7099/7070 | Pull-based S2x JPEG |
