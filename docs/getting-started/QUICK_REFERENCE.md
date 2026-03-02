# TYVYX Drone Quick Reference Card

## Network Details

### K417 (WiFi UAV) - Primary
```
Drone IP:       192.168.169.1
Port:           8800 (video AND control - single port)
Video Source:   Port 1234 (drone pushes from here)
SSID Pattern:   Drone-* | FLOW_* | K417 | HD-* | FHD-*
Protocol:       Pull-based REQUEST_A/B for 21fps, push fallback
```

### E88Pro (Legacy)
```
Drone IP:       192.168.1.1
Video Port:     7070
Control Port:   7099
SSID Pattern:   WIFI_* | GD89Pro_* | WTECH-*
```

## Quick Start
```bash
# Backend
python -m autonomous.api.main

# Frontend (separate terminal)
cd frontend && npm run dev

# Open http://localhost:5173
```

## API Endpoints

| Group | Path | Key Operations |
|-------|------|---------------|
| Drone | `/api/drone/connect` | Connect (auto-detect protocol) |
| Drone | `/api/drone/command` | arm, disarm, takeoff, land, calibrate, headless, camera1, camera2 |
| Video | `/api/video/ws` | WebSocket binary frames (primary) |
| Video | `/api/video/feed` | MJPEG HTTP stream (fallback) |
| Position | `/api/position/current` | x, y, z, velocity, altitude, camera mode |
| Position | `/api/position/ground_zero` | Set (0,0,0) reference |
| Position | `/api/position/camera_mode` | Switch front/bottom camera |
| Depth | `/api/depth/data` | Depth + altitude data |
| RSSI | `/api/rssi/data` | WiFi signal distance |
| RC | `/api/rc/ws` | WebSocket real-time sticks |
| Autopilot | `/api/autopilot/enable` | Position hold |
| Debug | `/api/debug/pipeline` | Full sensor fusion status |
| Debug | `/api/debug/ekf/state` | EKF state vector + covariance |
| Network | `/api/network/scan` | WiFi scan with drone detection |

## Keyboard Flight Controls (when armed)

| Key | Action |
|-----|--------|
| W / S | Pitch forward / backward |
| A / D | Roll left / right |
| Arrow Up / Down | Throttle up / down |
| Arrow Left / Right | Yaw left / right |

## K417 UDP Commands

| Command | Hex | Description |
|---------|-----|-------------|
| Start video | `ef 00 04 00` | Start push JPEG (re-sent as keepalive) |
| Front camera | `ef 01 02 00 06 01` | Switch to front camera |
| Bottom camera | `ef 01 02 00 06 02` | Switch to bottom/optical flow camera |
| RC control | `ef 02 7c 00 ...` | ~120-byte packet with rolling counters |

## File Structure
```
TEKY/
├── autonomous/api/main.py          # FastAPI entry point
├── autonomous/api/routes/          # drone, video, position, rc, autopilot,
│                                   # depth, rssi, network, debug
├── autonomous/services/            # DroneService, PositionService, DepthService,
│                                   # WifiRssiService, AutopilotService
├── tyvyx/protocols/                # K417 engine, push JPEG, S2x adapters
├── tyvyx/wifi_uav_controller.py    # K417 controller
├── frontend/src/App.tsx            # React UI
├── frontend/src/components/        # DroneVideo, FlightControls, SensorPanel,
│                                   # AutopilotPanel, Position3DBox
├── config/drone_config.yaml        # All settings
└── docs/                           # Documentation
```

## Troubleshooting Quick Checks

```bash
# Check drone is reachable
ping 192.168.169.1    # K417
ping 192.168.1.1      # E88Pro

# Kill stuck backend (Windows PowerShell)
Get-Process python* | Stop-Process -Force
```

## Feature Status

| Feature | Status |
|---------|--------|
| Video streaming (K417) | 21fps pull-based protocol engine |
| Flight control | Arm, disarm, takeoff, land, calibrate, headless, manual axes |
| Camera switch | Front and bottom cameras |
| Position tracking | Optical flow + EKF + depth + RSSI (bottom camera) |
| Depth estimation | Monocular depth (Depth Anything V2) |
| RSSI distance | WiFi signal path-loss model |
| Debug/testing | Individual sensor injection endpoints |
| SLAM / Mapping | Not started (Phase 4) |
| Battery / telemetry | Not available from drone |
