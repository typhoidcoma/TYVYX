# TYVYX Drone Quick Reference Card

## Network Details

### K417 (WiFi UAV) — Primary
```
Drone IP:       192.168.169.1
Video Port:     8800 (push-based 0x93 JPEG fragments)
Control Port:   8801
SSID Pattern:   Drone-* | FLOW_* | FlOW_* | K417 | HD-* | FHD-*
Video Source:   Port 1234 (not 8800)
Protocol:       Push-based — send START_STREAM, drone pushes JPEG
```

### E88Pro (Legacy)
```
Drone IP:       192.168.1.1
Video Port:     7070 (pull-based S2x JPEG fragments)
Control Port:   7099
SSID Pattern:   WIFI_* | GD89Pro_* | WTECH-*
Protocol:       Pull-based — S2x 0x40 0x40 sync
```

## Quick Start
```bash
# Backend
python -m autonomous.api.main

# Frontend (separate terminal)
cd frontend && npm run dev

# Open browser
# http://localhost:5173
```

## API Endpoints

| Group | Path | Key Operations |
|-------|------|---------------|
| Drone | `/api/drone/connect` | Connect (auto-detect protocol) |
| Drone | `/api/drone/command` | arm, disarm, takeoff, land, calibrate, headless, camera1, camera2 |
| Video | `/api/video/ws` | WebSocket binary frames (primary) |
| Video | `/api/video/feed` | MJPEG HTTP stream (fallback) |
| Position | `/api/position/current` | x, y, velocity, altitude, features |
| Position | `/api/position/trajectory` | History (max 1000 points) |
| Network | `/api/network/scan` | WiFi scan with drone detection |

## Frontend Keyboard Shortcuts

### Flight Controls (when armed)
| Key | Action |
|-----|--------|
| W | Pitch forward |
| S | Pitch backward |
| A | Roll left |
| D | Roll right |
| Arrow Up | Increase throttle |
| Arrow Down | Decrease throttle |
| Arrow Left | Yaw left |
| Arrow Right | Yaw right |

### UI Controls
| Action | Location |
|--------|----------|
| Connect/Disconnect | Top bar button |
| Start/Stop Video | Top bar button |
| Arm/Disarm | Flight controls panel |
| Takeoff/Land | Flight controls panel |
| Calibrate | Flight controls panel |
| Camera 1/2 | Camera switch buttons |

## K417 UDP Commands

| Command | Bytes | Purpose |
|---------|-------|---------|
| Start video stream | `ef 00 04 00` | Kick off push JPEG (re-sent every 100ms as keepalive) |
| Front camera | `ef 01 02 00 06 01` | Switch to front camera |
| Bottom camera | `ef 01 02 00 06 02` | Switch to bottom/optical flow camera |
| RC control | `ef 02 7c 00 ...` | ~120-byte packet with rolling counters |

## E88Pro UDP Commands

| Command | Bytes | Purpose |
|---------|-------|---------|
| Heartbeat | `01 01` | Keep alive (every 1s) |
| Initialize | `08 01` | Init drone |
| Camera 1 | `06 01` | Switch camera |
| Camera 2 | `06 02` | Switch camera |
| Flight | `03 66 R P T Y F X 99` | 9-byte RC packet |

## Python API

```python
from tyvyx import TYVYXDroneControllerAdvanced, FlightController

# E88Pro direct control (no web UI)
drone = TYVYXDroneControllerAdvanced()
if drone.connect():
    drone.start_video_stream()
    ret, frame = drone.get_frame()
    drone.disconnect()
```

## File Structure
```
TEKY/
├── autonomous/api/main.py          # FastAPI entry point
├── autonomous/services/            # DroneService, PositionService
├── tyvyx/wifi_uav_controller.py    # K417 controller
├── tyvyx/drone_controller_advanced.py  # E88Pro controller
├── tyvyx/protocols/                # Video protocol adapters
├── frontend/src/App.tsx            # React UI
├── scripts/                        # Diagnostic tools
├── config/drone_config.yaml        # All settings
└── docs/                           # Documentation
```

## Troubleshooting Quick Checks

```bash
# Check drone is reachable (K417)
ping 192.168.169.1

# Check drone is reachable (E88Pro)
ping 192.168.1.1

# Run tests
python -m pytest tests/ -v

# Kill stuck backend (Windows)
Get-Process python* | Stop-Process -Force
```

## What Works / What Doesn't

| Feature | Status |
|---------|--------|
| Video streaming (K417) | ~2 FPS (push protocol bottleneck) |
| Video streaming (E88Pro) | Works |
| Flight control | Arm, disarm, takeoff, land, calibrate, headless, manual axes |
| Camera switch | Front and bottom cameras |
| Position tracking | Optical flow + Kalman filter (needs calibration) |
| SLAM / Mapping | Not started (Phase 4) |
| Waypoint navigation | Not started (Phase 5) |
| Battery / telemetry | Not available from drone |
