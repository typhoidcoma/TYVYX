# System Architecture

## Overview

Multi-layered Python and TypeScript application that interfaces with WiFi drones using UDP commands and a proprietary UDP video protocol.

```
┌─────────────────────────────────────────────────────────┐
│                   React 19 Frontend                      │
│  DroneVideo, FlightControls, SensorPanel, AutopilotPanel│
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend                        │
│  Routes: drone, video, position, rc, autopilot,         │
│          depth, rssi, network, debug                    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────────┐
│              Autonomous Services                         │
│  ┌──────────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ │
│  │ DroneService │ │ Position │ │  Depth  │ │  RSSI  │ │
│  │              │ │ Service  │ │ Service │ │ Service│ │
│  └──────┬───────┘ └────┬─────┘ └────┬────┘ └───┬────┘ │
│         │              │            │           │       │
│         │         ┌────┴────────────┴───────────┘       │
│         │         │ EKF Sensor Fusion                   │
│         │         │ (optical flow + depth + RSSI)       │
│         │         └─────────────────────────────        │
└─────────┼───────────────────────────────────────────────┘
          │
┌─────────┼───────────────────────────────────────────────┐
│         │        Core Control (tyvyx/)                   │
│  ┌──────┴──────┐ ┌───────────────┐ ┌─────────────────┐ │
│  │ Controllers │ │ K417 Protocol │ │    FrameHub     │ │
│  │ (K417,E88)  │ │ Engine (21fps)│ │  (fan-out hub)  │ │
│  └─────────────┘ └───────┬───────┘ └─────────────────┘ │
└───────────────────────────┼─────────────────────────────┘
                            │ UDP (port 8800, single socket)
                            ▼
┌─────────────────────────────────────────────────────────┐
│              WiFi Drone Hardware (K417)                   │
│  Video + Control on port 8800, video source port 1234   │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### Command Flow (User -> Drone)
```
React Button Click -> api.ts -> FastAPI route -> DroneService
  -> WifiUavDroneController -> UDP packet -> Drone (port 8800)
```

### Video Flow (Drone -> User)
```
Drone (port 1234) -> UDP JPEG fragments -> K417ProtocolEngine
  -> JPEG reassembly -> FrameHub (asyncio fan-out)
  -> WebSocket binary / MJPEG -> React <canvas>
```

### Sensor Fusion Flow
```
Video frames (10 Hz) -> OpticalFlowTracker -> pixel velocity
  -> CoordinateTransformer -> world velocity (m/s)
  -> EKF predict + update velocity
                                    ↑
Depth service -> altitude ──────────┘ (bottom camera only)
RSSI service -> distance ──────────── EKF update RSSI
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript 5.7, Vite 7, Tailwind CSS v4 |
| Backend | Python 3.8, FastAPI, Uvicorn, WebSockets |
| Vision | OpenCV (optical flow), Depth Anything V2, Ultralytics YOLO11 |
| Math | NumPy, SciPy (EKF) |
| GPU | NVIDIA RTX 3090, CUDA 12.x |
| Protocol | UDP (K417 protocol engine), single-port constraint |

## Key Components

### Core (`tyvyx/`)
- `wifi_uav_controller.py` - K417 controller with socket sharing
- `drone_controller_advanced.py` - E88Pro legacy controller
- `protocols/k417_protocol_engine.py` - Pull-based 21fps video engine
- `frame_hub.py` - Asyncio JPEG fan-out to multiple clients

### Services (`autonomous/services/`)
- `drone_service.py` - Connection lifecycle, protocol auto-detection, frame pump
- `position_service.py` - Optical flow + EKF wrapper, camera mode management
- `depth_service.py` - Monocular depth estimation
- `wifi_rssi_service.py` - WiFi RSSI distance estimation
- `autopilot_service.py` - Position hold with PID control

### Localization (`autonomous/localization/`)
- `ekf_position_estimator.py` - 6D state EKF [x, y, z, vx, vy, vz]
- `coordinate_transforms.py` - Pixel velocity to world velocity (pinhole camera model)
- `optical_flow_tracker.py` - Sparse Lucas-Kanade (CPU + CUDA)

## Development Phases

- Phase 1: Flight control calibration (complete)
- Phase 2: React + FastAPI web interface (complete)
- Phase 3: Sensor fusion position tracking (in progress)
- Phase 4-7: SLAM, waypoints, mapping (planned)
