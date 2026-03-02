# TYVYX Drone - React Frontend

React 19 + TypeScript 5.7 + Vite 7 + Tailwind CSS v4 interface for drone control and video streaming.

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server (requires backend at localhost:8000)
npm run dev
# http://localhost:5173
```

Start the backend in another terminal:
```bash
python -m autonomous.api.main
```

## Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Development server with HMR |
| `npm run build` | Production build |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |

## Project Structure

```
frontend/src/
  App.tsx                 Main layout
  components/
    DroneVideo.tsx        WebSocket video canvas
    FlightControls.tsx    Keyboard RC (WASD + arrows)
    SensorPanel.tsx       Optical flow, depth, RSSI, 3D position
    AutopilotPanel.tsx    Position hold controls
    Position3DBox.tsx     3D position visualization
  services/
    api.ts                API client (REST + WebSocket)
  index.css               Tailwind v4 theme (@theme CSS vars)
  main.tsx                Entry point
```

## Key Features

- Live video via WebSocket binary (primary) or MJPEG (fallback)
- Keyboard flight controls with arm/disarm safety
- Sensor fusion panel: optical flow, depth, RSSI, EKF state
- 3D position visualization box
- Autopilot with position hold
- WiFi scanner with auto-detect and connect

## Tech Stack

- React 19
- TypeScript 5.7
- Vite 7
- Tailwind CSS v4 (`@theme` CSS variables in index.css)
- Axios (HTTP client)
- WebSocket API (video + telemetry)

## Related Docs

- [API Reference](../docs/API_REFERENCE.md)
- [Architecture](../docs/technical/architecture.md)
- [Contributing](../docs/contributing/CONTRIBUTING.md)
