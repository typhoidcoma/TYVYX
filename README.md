# TYVYX WiFi Drone Controller

![TYVYX Logo](assets/logo/tyvyx_logo_1.svg)

> Reverse-engineered AI control system for cheap Chinese hobby drones

Cheap WiFi drones from Amazon — like the **Karuisrc K417** and similar sub-$50 models — ship with a basic Android app and no open API. This project reverse-engineers their UDP control protocol and proprietary video stream to replace the stock app with a full AI-capable control stack: computer vision, autonomous navigation, and a modern web interface.

The goal is to use these mass-produced, disposable hobby drones as a low-cost platform for AI and robotics research.

## Key Achievement

**21fps video** from a $25 drone — achieved by reverse-engineering the pull-based REQUEST_A/REQUEST_B protocol that properly ACKs frames and advances the drone's sliding window. The K417 protocol engine handles video reception, fragment reassembly, frame requesting, and RC control all on a single UDP socket.

## Overview

These drones communicate over a simple WiFi hotspot using an undocumented UDP command protocol and a proprietary UDP video stream (JPEG fragments reassembled client-side). By sniffing traffic between the drone and its official Android app (YN Fly / com.lcfld.ynfly), we reconstructed the full command set and built a Python control layer on top of it.

From there, the project adds what the manufacturer never intended: optical flow position estimation, YOLO object detection, autonomous flight planning, and a React web interface — all running on commodity hardware with no drone modifications required.

**Project Status**:
- ✅ Phase 1: Flight control calibration tools
- ✅ Phase 2: React + FastAPI modern web interface with 21fps live video
- 🚧 Phase 3-7: Autonomous navigation (in progress)

## Features

### Core Functionality

- ✅ **K417 Protocol Engine** — Pull-based video at 21fps with REQUEST_A/REQUEST_B frame ACKs
- ✅ **UDP Video Streaming** — 0x93 JPEG fragment reassembly, 640x360 resolution
- ✅ **RC Flight Control** — Frame-synced burst RC packets (takeoff, land, calibrate, sticks)
- ✅ **Camera Switching** — Front/bottom camera toggle
- ✅ **Device Auto-Detection** — WiFi UAV vs E88Pro protocol detection (SSID + port probe + IP fallback)
- ✅ **Network Diagnostics** — Adapter detection, firewall diagnostics, connection testing

### Web Interface (Phase 2)

- 🚀 **React 19 + TypeScript + Vite** — Modern frontend at port 5173
- 🚀 **FastAPI Backend** — Async REST API at port 8000 with WebSocket video
- 🚀 **Live Video Feed** — WebSocket binary (primary) + MJPEG (fallback)
- 🚀 **WiFi Scanner** — Auto-detect and connect to drone networks
- 🚀 **Flight Controls** — Keyboard RC with takeoff/land/calibrate buttons

### Experimental

- ⚠️ **Position Estimation** — Optical flow-based dead reckoning (Phase 3)
- ⚠️ **SLAM Integration** — Visual SLAM for mapping (Phase 4+)
- 🤖 **YOLO11 Integration** — Real-time object detection (GPU-accelerated)

## Quick Start

### Prerequisites

- Python 3.8+
- Node.js 18+ (for frontend)
- A compatible WiFi drone (K417 recommended)

### Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### Connect and Fly

```bash
# 1. Connect to drone WiFi (SSID: "Drone-xxxxxx", "FLOW_xxxxxx", or "K417-*")
# 2. Verify connection
ping 192.168.169.1

# 3. Start the web interface
# Terminal 1: Backend
python -m autonomous.api.main
# Backend at http://localhost:8000, API docs at http://localhost:8000/docs

# Terminal 2: Frontend
cd frontend && npm run dev
# Frontend at http://localhost:5173
```

### Quick Test (no web interface)

```bash
# Test K417 protocol engine directly with OpenCV window
python tools/test_k417_engine.py
# Keys: q=quit, s=save frame, d=toggle debug
```

## Project Structure

```
TYVYX/
├── tyvyx/                     # Core drone control package
│   ├── protocols/
│   │   ├── k417_protocol_engine.py  # K417 unified TX/RX engine (21fps)
│   │   ├── s2x_video_protocol.py    # E88Pro video adapter
│   │   ├── tcp_video_protocol.py    # TCP video (Mten/FLOW-UFO)
│   │   ├── rtsp_video_protocol.py   # RTSP/RTP video
│   │   ├── raw_udp_sniffer.py       # Diagnostic packet sniffer
│   │   └── base_video_protocol.py   # Base adapter interface
│   ├── utils/
│   │   ├── k417_packets.py          # K417 RC packet builder (20-byte format)
│   │   ├── wifi_uav_packets.py      # REQUEST_A/B templates, START_STREAM
│   │   ├── wifi_uav_jpeg.py         # JPEG header generation
│   │   └── dropping_queue.py        # Overflow-safe queue
│   ├── models/                      # Video frame models
│   ├── services/                    # Video receiver service
│   ├── wifi_uav_controller.py       # WiFi UAV (K417) drone controller
│   ├── drone_controller_advanced.py # E88Pro drone controller
│   ├── frame_hub.py                 # Async MJPEG fan-out hub
│   └── network_diagnostics.py       # Connection testing
│
├── autonomous/               # Autonomous navigation system
│   ├── api/                  # FastAPI backend (Phase 2)
│   │   ├── main.py           # App entry point
│   │   └── routes/           # drone, video, position, network
│   ├── services/             # Business logic
│   │   ├── drone_service.py  # High-level drone operations
│   │   ├── network_service.py
│   │   └── position_service.py
│   ├── models/               # RC models and control profiles
│   ├── navigation/           # PID controllers, path planning
│   ├── perception/           # Computer vision (Phase 3+)
│   └── localization/         # Position estimation (Phase 3+)
│
├── frontend/                 # React 19 + TypeScript + Vite + Tailwind v4
│   └── src/
│       ├── App.tsx           # Main layout with tabs
│       ├── components/       # DroneVideo, FlightControls, WifiScanner, etc.
│       └── services/         # API client
│
├── tools/                    # Test harnesses
│   └── test_k417_engine.py   # K417 engine test with OpenCV HUD
│
├── scripts/                  # Diagnostic scripts
│   ├── probe_drone.py        # Network + firewall diagnostics
│   ├── fingerprint_9301.py   # 0x93 packet fingerprinting
│   └── ...                   # Camera, protocol probing tools
│
├── config/
│   └── drone_config.yaml     # Calibration + PID + safety config
│
├── docs/                     # Documentation
│   ├── INDEX.md
│   ├── technical/            # Protocol spec, architecture, RE notes
│   ├── guides/               # Phase implementation guides
│   └── contributing/         # Contributor docs
│
└── tests/                    # Unit tests
```

## Documentation

**[Full Documentation](docs/INDEX.md)**

- **[Quick Reference](docs/getting-started/QUICK_REFERENCE.md)** — Command cheat sheet
- **[Troubleshooting](docs/getting-started/TROUBLESHOOTING.md)** — Common issues
- **[Protocol Specification](docs/technical/protocol-specification.md)** — UDP protocol details
- **[System Architecture](docs/technical/architecture.md)** — Component relationships
- **[API Reference](docs/API_REFERENCE.md)** — Module and class docs

## Network Configuration

### K417 (WiFi UAV — Primary)

| Service | Protocol | Address | Description |
|---------|----------|---------|-------------|
| **Video + Control** | UDP | 192.168.169.1:8800 | Single port for everything |
| **Video Source** | UDP | drone:1234 → client | Drone pushes from port 1234 |

### E88Pro (Legacy)

| Service | Protocol | Address | Description |
|---------|----------|---------|-------------|
| **Control** | UDP | 192.168.1.1:7099 | Command and control |
| **Video** | UDP/TCP | 192.168.1.1:7070 | Video streaming |

See [Protocol Specification](docs/technical/protocol-specification.md) for details.

## Technology Stack

**Backend**: Python 3.8+, FastAPI, OpenCV, NumPy, Ultralytics YOLO11
**Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4
**Communication**: UDP (K417 protocol engine), WebSocket, REST API
**AI/GPU**: NVIDIA RTX 3090 (CUDA 12.x) — YOLO inference, optical flow, future SLAM

## Host Hardware

AI inference runs on the control laptop — not the drone itself.

| Component | Spec |
|-----------|------|
| **Platform** | Windows laptop |
| **GPU** | NVIDIA RTX 3090 (sm_86, 24 GB VRAM) |
| **Driver** | 581.57 (CUDA 12.x) |
| **Python** | 3.8 (venv) |

The RTX 3090 handles all GPU-accelerated workloads: YOLO11 inference, future SLAM pipelines, and depth estimation models. Wherever a choice exists between CPU and GPU execution, **prefer CUDA**.

## Supported Drones

| Model | IP | Port | Protocol | Status |
|-------|-----|------|----------|--------|
| **K417** (Karuisrc) | 192.168.169.1 | 8800 | WiFi UAV (pull-based, 21fps) | Primary |
| HD-720P-* | 192.168.1.1 | 7099 | E88Pro | Tested |
| HD-FPV-* | 192.168.1.1 | 7099 | E88Pro | Tested |
| FLOW-UFO (Mten) | 192.168.1.1 | 7099 | lxPro (TCP video) | Partial |

Any WiFi drone creating a hotspot at `192.168.169.1` (WiFi UAV) or `192.168.1.1` (E88Pro) is likely compatible. Protocol is auto-detected via SSID, port probe, and IP subnet.

## Roadmap

- [x] **Phase 1**: Flight control calibration
- [x] **Phase 2**: React + FastAPI web interface (21fps live video)
- [ ] **Phase 3**: Optical flow position estimation 🚧
- [ ] **Phase 4**: SLAM integration
- [ ] **Phase 5**: Waypoint navigation
- [ ] **Phase 6**: Autonomous mapping
- [ ] **Phase 7**: Advanced SLAM (ORB-SLAM3, RTAB-Map)

## Contributing

Contributions welcome! We're especially interested in:

- Protocol discoveries (new UDP commands)
- Flight control calibration data
- SLAM and computer vision improvements
- Bug fixes and testing

See [Contributing Guide](docs/contributing/CONTRIBUTING.md) and [Development Setup](docs/contributing/DEVELOPMENT.md).

## Safety Warning

**Always fly responsibly:**

- Test in open, safe areas away from people and obstacles
- Keep drone in visual line of sight at all times
- Be prepared for unexpected behavior during development
- Have emergency stop procedures ready
- Follow all local drone regulations and laws
- Ensure fully charged battery before flight testing

This is experimental software — use at your own risk!

## Acknowledgments

- **Turbodrone Project** — Architecture patterns and REQUEST_A/B pull-based protocol
- **OpenCV Community** — Video processing libraries
- **Ultralytics** — YOLO11 object detection
- **FastAPI** — Modern async web framework

## License

Educational purposes only. Use at your own risk.

This project is not affiliated with or endorsed by any drone manufacturer. All trademarks are property of their respective owners. The reverse engineering was performed for interoperability purposes.

---

**Ready to start?** Connect to your drone's WiFi and run `python -m autonomous.api.main`
