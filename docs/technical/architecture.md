# TYVYX Drone System Architecture

This document describes the overall architecture of the TYVYX drone control system, including component relationships, data flow, and technology stack.

## Table of Contents

- [System Overview](#system-overview)
- [Architecture Layers](#architecture-layers)
- [Component Details](#component-details)
- [Data Flow](#data-flow)
- [Technology Stack](#technology-stack)
- [Directory Structure](#directory-structure)
- [Development Phases](#development-phases)

---

## System Overview

The TYVYX drone control system is a multi-layered Python and TypeScript application that interfaces with WiFi-enabled drones using UDP commands and a proprietary UDP video protocol.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interfaces                         │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  React Frontend  │  │  Flask Web UI    │                │
│  │  (Phase 2)       │  │  (Legacy)        │                │
│  └────────┬─────────┘  └─────────┬────────┘                │
│           │                       │                          │
└───────────┼───────────────────────┼──────────────────────────┘
            │                       │
            │ HTTP/WebSocket        │ HTTP
            ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend Services                         │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  FastAPI Backend │  │  Flask App       │                │
│  │  (Phase 2)       │  │  (Legacy)        │                │
│  └────────┬─────────┘  └─────────┬────────┘                │
│           │                       │                          │
│  ┌────────┴───────────────────────┴────────┐                │
│  │      Autonomous Services Layer          │                │
│  │  ┌────────────┐  ┌──────────────────┐   │                │
│  │  │ Navigation │  │ Perception/SLAM  │   │                │
│  │  └────────────┘  └──────────────────┘   │                │
│  └──────────────────┬──────────────────────┘                │
└─────────────────────┼──────────────────────────────────────┘
                      │
                      │ UDP Commands / UDP Video
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Control Layer                        │
│  ┌────────────────────────────────────────────────────┐     │
│  │              TYVYX Package (tyvyx/)                  │     │
│  │  ┌──────────────┐  ┌────────────┐  ┌───────────┐  │     │
│  │  │ Controllers  │  │ Video      │  │ Network   │  │     │
│  │  │              │  │ Protocols  │  │ Diag      │  │     │
│  │  └──────────────┘  └────────────┘  └───────────┘  │     │
│  └────────────────┬───────────────────────────────────┘     │
└───────────────────┼──────────────────────────────────────────┘
                    │
                    │ UDP (7099 control, 7070 video)
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                     TYVYX WiFi Drone                          │
│  - UDP Command Reception (port 7099)                        │
│  - UDP Video Streaming (port 7070, JPEG fragments)          │
│  - HTTP File Server (port 80)                               │
│  - FTP Server (port 21)                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture Layers

### 1. User Interface Layer

**Purpose**: Present controls and video feed to users

**Components**:
- **React Frontend** ([frontend/](../../frontend/)) - Modern web UI (Phase 2)
- **Flask Web UI** ([tyvyx/app.py](../../tyvyx/app.py)) - Legacy web interface

**Technologies**: React, TypeScript, Tailwind CSS, Flask, HTML/CSS

### 2. Backend API Layer

**Purpose**: Expose RESTful APIs and WebSocket connections

**Components**:
- **FastAPI Backend** ([autonomous/api/](../../autonomous/api/)) - Modern async API (Phase 2)
  - REST endpoints for drone control
  - WebSocket for real-time telemetry
  - MJPEG video proxy
- **Flask App** ([tyvyx/app.py](../../tyvyx/app.py)) - Legacy synchronous API

**Technologies**: FastAPI, Flask, Uvicorn, WebSockets

### 3. Services Layer

**Purpose**: High-level business logic and autonomous capabilities

**Components**:
- **Drone Service** ([autonomous/services/](../../autonomous/services/)) - High-level control abstraction
- **Navigation** ([autonomous/navigation/](../../autonomous/navigation/)) - PID controllers, path planning
- **Perception** ([autonomous/perception/](../../autonomous/perception/)) - Optical flow, obstacle detection (future)
- **Localization** ([autonomous/localization/](../../autonomous/localization/)) - Position estimation (future)
- **SLAM** ([autonomous/slam/](../../autonomous/slam/)) - Mapping and localization (future)

**Technologies**: Python, NumPy, SciPy (future: OpenCV, SLAM libraries)

### 4. Core Control Layer

**Purpose**: Direct communication with drone hardware

**Components**:
- **Drone Controllers** ([tyvyx/drone_controller*.py](../../tyvyx/)) - UDP command transmission
- **Video Protocols** ([tyvyx/protocols/](../../tyvyx/protocols/)) - UDP video protocol adapters (S2X, sniffer)
- **Video Receiver** ([tyvyx/services/video_receiver.py](../../tyvyx/services/video_receiver.py)) - Supervised video reception with auto-reconnect
- **Frame Hub** ([tyvyx/frame_hub.py](../../tyvyx/frame_hub.py)) - Asyncio fan-out for MJPEG clients
- **Network Diagnostics** ([tyvyx/network_diagnostics.py](../../tyvyx/network_diagnostics.py)) - Connection testing

**Technologies**: Python, OpenCV, sockets, threading

### 5. Drone Hardware Layer

**Purpose**: Physical drone

**Interfaces**:
- **UDP (7099)**: Command reception
- **UDP (7070)**: Video streaming (proprietary JPEG fragment protocol)
- **HTTP (80)**: File access
- **FTP (21)**: File transfer

---

## Component Details

### Core Components (`tyvyx/` package)

#### 1. drone_controller.py
**Purpose**: Basic drone control (video + simple commands)

**Responsibilities**:
- UDP socket management
- Heartbeat transmission
- Camera/screen switching
- Video display

**Key Functions**:
```python
connect_to_drone()      # Establish UDP connection
start_video()           # Activate UDP video receiver
send_command(bytes)     # Send UDP commands
```

#### 2. drone_controller_advanced.py
**Purpose**: Extended control with experimental flight commands

**Responsibilities**:
- All features from basic controller
- Keyboard flight controls
- Throttle, pitch, roll, yaw commands
- Emergency reset

**Key Features**:
- Space bar activation
- WASD for pitch/roll
- Arrow keys for throttle/yaw
- ESC for emergency stop

#### 3. drone_controller_yolo.py
**Purpose**: Computer vision integration (YOLO object detection)

**Responsibilities**:
- All features from advanced controller
- Real-time object detection overlay
- Bounding box visualization
- Object tracking

**Dependencies**: Ultralytics YOLO11

#### 4. Video Protocol Stack (`protocols/`, `services/`, `frame_hub.py`)
**Purpose**: UDP video reception and MJPEG distribution

**Responsibilities**:
- UDP packet reception and JPEG fragment reassembly
- Protocol adapters (S2X-style, diagnostic sniffer)
- Supervised receiver with auto-reconnect
- Asyncio FrameHub for multi-client MJPEG fan-out

#### 5. network_diagnostics.py
**Purpose**: Connection testing and debugging

**Features**:
- Ping test
- UDP echo test
- Packet capture
- Connection diagnostics

---

### Autonomous Components (`autonomous/` package)

#### 1. API Module (`autonomous/api/`)

**Structure**:
```
api/
├── main.py           # FastAPI application
├── routes/
│   ├── drone.py      # Drone control endpoints
│   └── video.py      # Video streaming endpoints
└── websocket.py      # WebSocket telemetry
```

**Endpoints**:
- `POST /api/drone/connect` - Connect to drone
- `POST /api/drone/disconnect` - Disconnect from drone
- `POST /api/drone/command` - Send control commands
- `GET /api/drone/status` - Get connection status
- `GET /api/video/feed` - MJPEG video stream
- `GET /api/video/status` - Video stream status
- `WS /ws/telemetry` - WebSocket telemetry (10 Hz)

#### 2. Services Module (`autonomous/services/`)

**Purpose**: High-level drone control abstraction

**Key Class**: `DroneService`
- Wraps `TYVYXDroneControllerAdvanced`
- Provides async interface
- Manages connection lifecycle
- Streams telemetry data

#### 3. Models Module (`autonomous/models/`)

**Purpose**: Configuration and control models

**Components**:
- `rc_model.py` - RC control profiles (from Turbodrone)
- `control_profile.py` - Flight control configurations

#### 4. Navigation Module (`autonomous/navigation/`)

**Purpose**: Path planning and control algorithms

**Components**:
- `pid_controller.py` - PID controllers for position/velocity control
- Future: Path planners, trajectory generators

#### 5. Testing Module (`autonomous/testing/`)

**Purpose**: Flight control calibration and testing

**Components**:
- `flight_control_test.py` - Interactive testing tool
- Test modes: interactive, calibrate, test_throttle, test_pitch, etc.

---

### Frontend Components (`frontend/` package)

**Structure**:
```
frontend/
├── src/
│   ├── App.tsx              # Main React component
│   ├── services/
│   │   └── api.ts           # API client
│   ├── main.tsx             # Entry point
│   └── index.css            # Tailwind styles
├── public/                  # Static assets
├── package.json             # Dependencies
└── vite.config.ts           # Build configuration
```

**Features**:
- Live video feed (MJPEG)
- Manual controls (connect, video, camera)
- Real-time status indicators
- WebSocket telemetry display

---

## Data Flow

### 1. Command Flow (User → Drone)

```
User Action (Button Click)
        ↓
React Frontend (api.ts)
        ↓ HTTP POST /api/drone/command
FastAPI Backend (routes/drone.py)
        ↓
Drone Service (drone_service.py)
        ↓
TYVYX Controller (drone_controller_advanced.py)
        ↓ UDP Packet (7099)
TYVYX Drone Hardware
```

### 2. Video Flow (Drone → User)

```
TYVYX Drone Hardware
        ↓ UDP JPEG Fragments (port 7070)
Protocol Adapter (S2X) → JPEG reassembly
        ↓ VideoFrame objects
VideoReceiverService → DroppingQueue
        ↓ Frame Pump Worker thread
FrameHub (asyncio fan-out)
        ↓ Raw JPEG bytes per client
FastAPI Video Route (routes/video.py)
        ↓ MJPEG over HTTP
React Frontend (WebRTCVideo / <img>)
        ↓
User Display
```

### 3. Telemetry Flow (Drone → User)

```
TYVYX Drone Hardware
        ↓ UDP Responses (7099)
TYVYX Controller (parsing responses)
        ↓
Drone Service (telemetry collection)
        ↓ WebSocket Message
FastAPI WebSocket (websocket.py)
        ↓ WS Protocol
React Frontend (WebSocket client)
        ↓
User Interface (Status Display)
```

### 4. Heartbeat Flow (Continuous)

```
Timer Thread (1 Hz)
        ↓
TYVYX Controller
        ↓ UDP [0x01, 0x01] every 1 second
TYVYX Drone Hardware
        ↓ UDP Response
TYVYX Controller (updates device status)
```

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.8+ | Core language |
| **FastAPI** | 0.104+ | Modern async web framework |
| **Flask** | 2.3+ | Legacy web framework |
| **Uvicorn** | 0.24+ | ASGI server for FastAPI |
| **OpenCV** | 4.8+ | Video capture and processing |
| **NumPy** | 1.24+ | Numerical computations |
| **Ultralytics** | 8.0+ | YOLO11 object detection |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| **React** | 18.2+ | UI framework |
| **TypeScript** | 5.0+ | Type-safe JavaScript |
| **Vite** | 4.4+ | Build tool and dev server |
| **Tailwind CSS** | 3.3+ | Utility-first CSS |

### Development Tools

| Tool | Purpose |
|------|---------|
| **pytest** | Unit testing |
| **ruff** | Python linting |
| **black** | Python formatting |
| **ESLint** | TypeScript linting |
| **Prettier** | TypeScript formatting |

### Drone Communication

| Protocol | Purpose |
|----------|---------|
| **UDP** | Command and control (port 7099) |
| **UDP** | Video streaming (port 7070, proprietary JPEG fragments) |
| **HTTP** | File access and web interface (port 80) |
| **FTP** | File transfer (port 21) |
| **WebSocket** | Real-time telemetry (FastAPI) |

---

## Directory Structure

```
TYVYX/
│
├── tyvyx/                    # Core drone control package
│   ├── __init__.py
│   ├── drone_controller.py          # Basic controller
│   ├── drone_controller_advanced.py # Advanced with flight controls
│   ├── drone_controller_yolo.py     # With object detection
│   ├── video_stream.py              # Video utilities
│   ├── network_diagnostics.py       # Diagnostics tool
│   ├── app.py                       # Flask web interface
│   ├── templates/                   # Flask HTML templates
│   ├── static/                      # Flask static files
│   └── tools/                       # Utility scripts
│       ├── packet_sniffer.py
│       └── udp_proxy.py
│
├── autonomous/              # Autonomous navigation system
│   ├── __init__.py
│   ├── api/                        # FastAPI backend
│   │   ├── main.py                # Application entry
│   │   ├── routes/
│   │   │   ├── drone.py           # Drone endpoints
│   │   │   └── video.py           # Video endpoints
│   │   └── websocket.py           # WebSocket telemetry
│   │
│   ├── services/                   # High-level services
│   │   └── drone_service.py
│   │
│   ├── models/                     # Data models
│   │   ├── rc_model.py            # RC control profiles
│   │   └── control_profile.py     # Control configurations
│   │
│   ├── navigation/                 # Navigation algorithms
│   │   └── pid_controller.py      # PID controllers
│   │
│   ├── localization/              # Position estimation (future)
│   ├── perception/                # Computer vision (future)
│   ├── slam/                      # SLAM engines (future)
│   │
│   └── testing/                   # Flight testing tools
│       └── flight_control_test.py
│
├── frontend/                # React web interface
│   ├── src/
│   │   ├── App.tsx                # Main component
│   │   ├── services/
│   │   │   └── api.ts             # API client
│   │   ├── main.tsx               # Entry point
│   │   └── index.css              # Styles
│   ├── public/                    # Static assets
│   ├── package.json
│   └── vite.config.ts
│
├── config/                  # Configuration files
│   └── drone_config.yaml          # Main configuration
│
├── scripts/                 # Utility scripts
│   ├── start_phase2.sh
│   ├── verify_psutil.py
│   └── ...
│
├── docs/                    # Documentation
│   ├── INDEX.md                   # Documentation hub
│   ├── API_REFERENCE.md
│   ├── getting-started/
│   ├── guides/
│   ├── technical/
│   └── contributing/
│
├── logs/                    # Runtime logs
│   └── flight_tests/              # Flight test logs
│
├── maps/                    # Map data (future)
├── sniffs/                  # Packet captures
├── tests/                   # Unit tests
│
├── requirements.txt         # Python dependencies
├── requirements-dev.txt     # Development dependencies
└── README.md                # Project overview
```

---

## Development Phases

The TYVYX project follows a phased development approach:

### Phase 1: Flight Control Calibration ✅
**Status**: Complete

**Deliverables**:
- Flight control testing framework
- Interactive calibration tool
- Documented hover values and control mappings
- Updated `drone_config.yaml`

**Key Files**:
- `autonomous/testing/flight_control_test.py`
- `config/drone_config.yaml`

---

### Phase 2: React + FastAPI Web Interface ✅
**Status**: Complete

**Deliverables**:
- FastAPI backend with REST API
- React frontend with Tailwind CSS
- WebSocket telemetry streaming
- MJPEG video proxy
- Manual drone controls via web UI

**Key Files**:
- `autonomous/api/` (backend)
- `frontend/` (React app)

---

### Phase 3: Optical Flow Position Estimation
**Status**: Planned

**Goals**:
- Implement optical flow tracker (OpenCV)
- Dead reckoning position estimation
- Kalman filter for smoothing
- 2D map visualization

**Key Components**:
- `autonomous/perception/optical_flow.py`
- `autonomous/localization/position_estimator.py`
- Frontend map display

---

### Phase 4: SLAM Integration
**Status**: Planned

**Goals**:
- Visual SLAM implementation
- Real-time mapping
- Loop closure detection
- 3D map visualization

**Technologies**: ORB-SLAM3, RTAB-Map

---

### Phase 5: Waypoint Navigation
**Status**: Planned

**Goals**:
- Waypoint definition interface
- Path planning algorithms
- Autonomous navigation
- Obstacle avoidance (basic)

---

### Phase 6: Autonomous Mapping
**Status**: Planned

**Goals**:
- Automated mapping missions
- Coverage path planning
- Map stitching and optimization

---

### Phase 7: Advanced SLAM
**Status**: Planned

**Goals**:
- Multi-sensor fusion
- Advanced SLAM engines
- Large-scale mapping

---

## Design Patterns and Principles

### 1. Separation of Concerns
- **Core layer** (`tyvyx/`) handles hardware communication
- **Services layer** (`autonomous/services/`) provides business logic
- **API layer** (`autonomous/api/`) exposes interfaces
- **UI layer** (`frontend/`) handles presentation

### 2. Asynchronous Architecture
- FastAPI uses async/await for non-blocking I/O
- WebSocket connections for real-time updates
- Threading for concurrent heartbeat and video processing

### 3. Configuration-Driven
- All drone parameters in `config/drone_config.yaml`
- Easy tuning without code changes
- Version-controlled configuration

### 4. Modular Design
- Each component is independent
- Easy to test in isolation
- Reusable across different interfaces (CLI, web, future mobile)

### 5. Layered Architecture
- Clear boundaries between layers
- Dependencies flow downward (UI → API → Services → Core → Hardware)
- Easy to replace/upgrade individual layers

---

## Future Architecture Considerations

### Scalability
- Support multiple simultaneous drones
- Fleet management capabilities
- Distributed control

### Real-Time Performance
- Reduce video latency (<500ms)
- Faster command response times
- Optimized control loops (100+ Hz)

### Advanced Features
- GPS integration
- Sensor fusion (IMU, barometer, GPS)
- Computer vision pipelines
- Autonomous missions

### Security
- Command authentication
- Encrypted communication
- Access control

---

## References

- [Protocol Specification](protocol-specification.md) - Detailed protocol documentation
- [Reverse Engineering Notes](reverse-engineering.md) - Protocol discovery process
- [API Reference](../API_REFERENCE.md) - Module and class documentation
- [TURBODRONE Integration](../guides/turbodrone-architecture.md) - Architecture patterns from Turbodrone project

---

*System architecture evolves with each development phase. This document reflects the current state as of Phase 2.*
