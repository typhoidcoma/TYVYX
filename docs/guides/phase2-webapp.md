# Phase 2: React + FastAPI Web Interface

Phase 2 built the web interface for drone control and video streaming.

## What Was Built

**Backend (FastAPI, port 8000)**:
- REST API for drone control (connect, disconnect, status, commands)
- WebSocket video streaming (`/api/video/ws`) and MJPEG fallback (`/api/video/feed`)
- WebSocket telemetry (`/ws/telemetry`, 10 Hz)
- Protocol auto-detection (K417 vs E88Pro)
- K417 protocol engine with 21fps pull-based video

**Frontend (React 19 + TypeScript + Vite 7 + Tailwind v4, port 5173)**:
- Live video feed via WebSocket binary
- Keyboard flight controls (WASD + arrows) with arm/disarm
- Sensor panel with 3D position visualization
- Autopilot panel for position hold
- WiFi scanner with auto-detect and connect
- Real-time status indicators

## Running

```bash
# Terminal 1: Backend
python -m autonomous.api.main
# http://localhost:8000, docs at /docs

# Terminal 2: Frontend
cd frontend && npm run dev
# http://localhost:5173
```

## Key Files

**Backend**:
- `autonomous/api/main.py` - FastAPI app
- `autonomous/api/routes/` - drone, video, position, rc, autopilot, depth, rssi, network, debug
- `autonomous/services/drone_service.py` - Connection lifecycle, protocol engine

**Frontend**:
- `frontend/src/App.tsx` - Main layout
- `frontend/src/components/` - DroneVideo, FlightControls, SensorPanel, AutopilotPanel
- `frontend/src/services/api.ts` - API client

See [API Reference](../API_REFERENCE.md) for all endpoints.
