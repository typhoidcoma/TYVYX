# TYVYX WiFi Drone Controller

![TYVYX Logo](assets/logo/tyvyx_logo_1.svg)

> Reverse-engineered AI control system for cheap Chinese hobby drones

Cheap WiFi drones from Amazon (like the **Karuisrc K417**, sub-$50) ship with a basic Android app and no open API. This project reverse-engineers their UDP control protocol and proprietary video stream, replacing the stock app with a full AI-capable control stack: computer vision, autonomous navigation, and a modern web interface.

The goal is to use mass-produced, disposable hobby drones as a low-cost platform for AI and robotics research.

## Key Achievement

**21fps video** from a $25 drone. Achieved by reverse-engineering the pull-based REQUEST_A/REQUEST_B protocol that properly ACKs frames and advances the drone's sliding window. The K417 protocol engine handles video reception, fragment reassembly, frame requesting, and RC control all on a single UDP socket.

## Features

### Core
- K417 Protocol Engine - Pull-based video at 21fps with REQUEST_A/REQUEST_B frame ACKs
- UDP Video Streaming - 0x93 JPEG fragment reassembly, 640x360
- RC Flight Control - Frame-synced burst RC packets (takeoff, land, calibrate, sticks)
- Camera Switching - Front/bottom camera toggle
- Device Auto-Detection - WiFi UAV vs E88Pro protocol detection (SSID + port probe + IP fallback)

### Web Interface (Phase 2)
- React 19 + TypeScript + Vite frontend at port 5173
- FastAPI async REST API at port 8000 with WebSocket video
- Live video feed via WebSocket binary (primary) + MJPEG (fallback)
- Keyboard flight controls (WASD + arrows) with arm/disarm safety
- WiFi scanner with auto-detect and connect

### Sensor Fusion (Phase 3 - in progress)
- Optical flow position tracking (Lucas-Kanade, CPU + CUDA)
- Monocular depth estimation (Depth Anything V2)
- WiFi RSSI distance estimation (path-loss model)
- 6D Extended Kalman Filter (x, y, z, vx, vy, vz)
- Camera mode switching (front/bottom) for optical flow
- 3D position visualization box
- Debug endpoints for individual sensor testing

**Project Status**:
- Phase 1: Flight control calibration tools (complete)
- Phase 2: React + FastAPI web interface with 21fps live video (complete)
- Phase 3: Sensor fusion position tracking (in progress)
- Phase 4-7: SLAM, waypoint navigation, mapping (planned)

## Quick Start

### Prerequisites
- Python 3.8+
- Node.js 18+
- A compatible WiFi drone (K417 recommended)

### Installation

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### Connect and Fly

```bash
# 1. Connect to drone WiFi (SSID: "Drone-xxxxxx", "FLOW_xxxxxx", or "K417-*")
ping 192.168.169.1

# 2. Start backend
python -m autonomous.api.main
# http://localhost:8000, docs at /docs

# 3. Start frontend (separate terminal)
cd frontend && npm run dev
# http://localhost:5173
```

## Project Structure

```
TYVYX/
├── tyvyx/                        # Core drone control package
│   ├── protocols/
│   │   ├── k417_protocol_engine.py   # K417 unified TX/RX engine (21fps)
│   │   ├── push_jpeg_video_protocol.py # Push-based JPEG (fallback)
│   │   ├── s2x_video_protocol.py     # E88Pro video adapter
│   │   └── base_video_protocol.py    # Base adapter interface
│   ├── utils/                        # Packet builders, JPEG headers
│   ├── wifi_uav_controller.py        # K417 drone controller
│   ├── drone_controller_advanced.py  # E88Pro drone controller
│   └── frame_hub.py                  # Async fan-out hub
│
├── autonomous/                  # Autonomous navigation system
│   ├── api/
│   │   ├── main.py              # FastAPI entry point
│   │   └── routes/              # drone, video, position, rc, autopilot,
│   │                            # depth, rssi, network, debug
│   ├── services/
│   │   ├── drone_service.py     # High-level drone operations
│   │   ├── position_service.py  # Optical flow + EKF position tracking
│   │   ├── depth_service.py     # Monocular depth estimation
│   │   ├── wifi_rssi_service.py # WiFi RSSI distance
│   │   └── autopilot_service.py # Autopilot control
│   ├── localization/            # EKF, coordinate transforms
│   └── perception/              # Optical flow tracker
│
├── frontend/                    # React 19 + TypeScript + Vite + Tailwind v4
│   └── src/
│       ├── App.tsx              # Main layout
│       ├── components/          # DroneVideo, FlightControls, SensorPanel,
│       │                        # AutopilotPanel, Position3DBox
│       └── services/api.ts     # API client
│
├── config/drone_config.yaml     # All settings
└── docs/                        # Documentation
```

## Documentation

**[Full Documentation](docs/INDEX.md)**

- [Quick Reference](docs/getting-started/QUICK_REFERENCE.md) - Command cheat sheet
- [Troubleshooting](docs/getting-started/TROUBLESHOOTING.md) - Common issues
- [Protocol Specification](docs/technical/protocol-specification.md) - UDP protocol details
- [System Architecture](docs/technical/architecture.md) - Component relationships
- [API Reference](docs/API_REFERENCE.md) - Endpoints and modules

## Network Configuration

### K417 (WiFi UAV - Primary)

| Service | Protocol | Address |
|---------|----------|---------|
| Video + Control | UDP | 192.168.169.1:8800 (single port) |
| Video Source | UDP | drone:1234 -> client |

### E88Pro (Legacy)

| Service | Protocol | Address |
|---------|----------|---------|
| Control | UDP | 192.168.1.1:7099 |
| Video | UDP/TCP | 192.168.1.1:7070 |

## Technology Stack

**Backend**: Python 3.8+, FastAPI, OpenCV, NumPy, Ultralytics YOLO11
**Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4
**Communication**: UDP (K417 protocol engine), WebSocket, REST API
**AI/GPU**: NVIDIA RTX 3090 (CUDA 12.x) - YOLO inference, optical flow, depth estimation

## Supported Drones

| Model | IP | Port | Protocol | Status |
|-------|-----|------|----------|--------|
| K417 (Karuisrc) | 192.168.169.1 | 8800 | WiFi UAV (pull-based, 21fps) | Primary |
| HD-720P-* | 192.168.1.1 | 7099 | E88Pro | Tested |
| FLOW-UFO (Mten) | 192.168.1.1 | 7099 | lxPro (TCP video) | Partial |

Protocol is auto-detected via SSID, port probe, and IP subnet.

## Roadmap

- [x] Phase 1: Flight control calibration
- [x] Phase 2: React + FastAPI web interface (21fps live video)
- [ ] Phase 3: Sensor fusion position tracking (in progress)
- [ ] Phase 4: SLAM integration
- [ ] Phase 5: Waypoint navigation
- [ ] Phase 6: Autonomous mapping
- [ ] Phase 7: Advanced SLAM (ORB-SLAM3, RTAB-Map)

## Safety Warning

Always fly responsibly. Test in open, safe areas away from people and obstacles. Keep drone in visual line of sight. Be prepared for unexpected behavior during development. This is experimental software - use at your own risk.

## License

Educational purposes only. Use at your own risk. Not affiliated with or endorsed by any drone manufacturer.
