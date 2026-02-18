# TYVYX Drone Control — Getting Started

## Prerequisites

- Python 3.8+ with pip
- Node.js 18+ (for the web frontend)
- WiFi-capable computer
- Karuisrc K417 drone (or E88Pro-family drone)

**FFmpeg is NOT required** — the video pipeline uses direct UDP JPEG passthrough.

## Installation

```bash
# Clone and enter the project
cd TEKY

# Create Python virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
& .\.venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # optional, for tests and linting

# Install frontend dependencies
cd frontend
npm install
cd ..
```

## Connect to Your Drone

1. Power on the drone
2. On your computer, look for a WiFi network matching one of these patterns:
   - `Drone-*` (e.g., Drone-4C5C87) — K417
   - `FLOW_*`, `FlOW_*` — K417 variant
   - `HD-*`, `FHD-*`, `HD720-*`, `K417` — other variants
3. Connect to the drone's WiFi (no internet access is normal — the drone IS the access point)
4. The system auto-detects the drone type by IP subnet:
   - **192.168.169.x** = K417 (WiFi UAV, push-based JPEG)
   - **192.168.1.x** = E88Pro (legacy, pull-based JPEG)

## Start the Application

Open two terminals:

```bash
# Terminal 1: Backend (FastAPI on port 8000)
python -m autonomous.api.main

# Terminal 2: Frontend (React + Vite on port 5173)
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

## Using the Web Interface

1. Click **Connect** — the backend auto-detects your drone and protocol
2. Click **Start Video** — live JPEG video stream appears
3. Use **Cam 1 / Cam 2** to switch between front and bottom cameras
4. Flight controls:
   - **Arm** to enable motors, **Disarm** to disable
   - **Takeoff** / **Land** for auto takeoff/landing
   - **Calibrate** to calibrate gyroscope (do this on a flat surface)
   - **Headless** to toggle headless mode
   - Keyboard: **W/A/S/D** for pitch/roll, **Arrow keys** for throttle/yaw

## What Works

- Video streaming (push-based JPEG, ~2 FPS with K417)
- Flight control: arm/disarm, takeoff/land, gyro calibrate, headless mode, manual axis control
- Camera switching (front / bottom)
- WiFi network scanning with drone detection
- Position tracking via optical flow (Phase 3, ~85% complete)
- Trajectory visualization on canvas map

## Known Limitations

- **~2 FPS video** — the K417 push protocol may need ACK handling for higher frame rates
- **Position accuracy unvalidated** — camera calibration uses placeholder values, no real-world ground truth testing yet
- **No altitude sensor** — altitude is manually set in the UI, not measured from the drone
- **No telemetry from drone** — battery level, signal strength, etc. are not available
- **Windows firewall** — drone WiFi is classified as "Public" network; ensure Python has UDP access

## Project Structure

```
TEKY/
├── autonomous/           # FastAPI backend + autonomous services
│   ├── api/             # REST API (main.py, routes/)
│   ├── services/        # DroneService, PositionService, NetworkService
│   ├── perception/      # Optical flow tracker
│   ├── localization/    # Kalman filter, coordinate transforms
│   └── navigation/      # PID controllers (Phase 5, not wired yet)
├── tyvyx/               # Core drone protocols and controllers
│   ├── protocols/       # PushJpeg, S2x, RawUdpSniffer adapters
│   ├── services/        # VideoReceiverService
│   └── utils/           # Packet templates, JPEG headers
├── frontend/            # React + TypeScript + Vite + Tailwind v4
├── scripts/             # Diagnostic and reverse-engineering tools
├── tests/               # pytest test suite
├── config/              # drone_config.yaml
└── docs/                # This documentation
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## Next Steps

- [Phase 1: Flight Control Calibration](../guides/phase1-calibration.md) — calibrate flight controls
- [Phase 2: Web App Guide](../guides/phase2-webapp.md) — detailed backend/frontend docs
- [API Reference](../API_REFERENCE.md) — all endpoints and modules
- [Protocol Specification](../technical/protocol-specification.md) — packet formats
