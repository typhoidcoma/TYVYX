# TEKY Drone - React Frontend

Modern React + TypeScript interface for TEKY drone control (Phase 2).

## Features

- 🎥 **Live Video Feed** - MJPEG streaming from backend
- 🎮 **Manual Drone Controls** - Connect, video start/stop, camera switching
- 📊 **Real-time Telemetry** - WebSocket connection for live status updates
- 🎨 **Modern UI** - Tailwind CSS styling with responsive design
- ⚡ **Fast Development** - Vite with Hot Module Replacement (HMR)
- 🔒 **Type Safe** - Full TypeScript support

## Quick Start

### Prerequisites

- Node.js 16 or higher
- npm (comes with Node.js)
- Backend server running (FastAPI at http://localhost:8000)

### Install Dependencies

```bash
npm install
```

### Development Server

```bash
npm run dev
```

Frontend runs at: **http://localhost:5173**

### Connect to Backend

Make sure the FastAPI backend is running:

```bash
cd ..
python -m autonomous.api.main
```

Backend runs at: **http://localhost:8000**

## Available Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server with HMR |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |

## Project Structure

```
frontend/
├── src/
│   ├── App.tsx              # Main application component
│   ├── services/
│   │   └── api.ts           # API client for backend communication
│   ├── main.tsx             # Application entry point
│   └── index.css            # Tailwind CSS styles
├── public/                  # Static assets
├── index.html               # HTML template
├── package.json             # Dependencies and scripts
├── tsconfig.json            # TypeScript configuration
├── vite.config.ts           # Vite configuration
└── tailwind.config.js       # Tailwind CSS configuration
```

## Key Components

### App.tsx

Main application component that provides:
- Video feed display (MJPEG stream from backend)
- Connection controls (connect/disconnect)
- Video controls (start/stop video)
- Camera switching (Camera 1/2)
- Status indicators (connection, video streaming)
- WebSocket telemetry integration

### API Service (`services/api.ts`)

Axios-based API client with methods for:
- `connectDrone()` - Establish connection to drone
- `disconnectDrone()` - Disconnect from drone
- `sendCommand(action, params)` - Send control commands
- `getStatus()` - Get current drone status
- `getVideoStatus()` - Get video stream status

WebSocket connection for real-time telemetry at: `ws://localhost:8000/ws/telemetry`

## API Integration

### Backend Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/drone/connect` | Connect to drone |
| POST | `/api/drone/disconnect` | Disconnect from drone |
| POST | `/api/drone/command` | Send control command |
| GET | `/api/drone/status` | Get connection status |
| GET | `/api/video/feed` | MJPEG video stream |
| GET | `/api/video/status` | Video stream status |
| WS | `/ws/telemetry` | WebSocket telemetry (10 Hz) |

### Example API Usage

```typescript
import api from './services/api';

// Connect to drone
await api.connectDrone();

// Start video
await api.sendCommand('start_video');

// Switch to camera 2
await api.sendCommand('switch_camera', { camera: 2 });

// Get status
const status = await api.getStatus();
console.log(status.connected, status.video_streaming);
```

## Styling

Uses **Tailwind CSS** for styling:
- Utility-first CSS framework
- Responsive design
- Dark mode ready
- Customizable theme

Tailwind config: `tailwind.config.js`

## Development

### Hot Module Replacement

Vite provides instant HMR - changes appear immediately without full page reload.

### TypeScript

Full TypeScript support with strict type checking:
- `tsconfig.json` - App TypeScript config
- `tsconfig.node.json` - Vite config TypeScript settings

### Linting

ESLint configuration included:

```bash
npm run lint
```

## Building for Production

### Build

```bash
npm run build
```

Output in `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

Preview at http://localhost:4173

## Features Roadmap

### Phase 2 (Current) ✅
- [x] Basic connection and video controls
- [x] WebSocket telemetry streaming
- [x] Camera switching
- [x] Status indicators

### Future Phases 🚧
- [ ] Flight controls UI (Phase 5)
- [ ] Map visualization (Phase 4)
- [ ] Position overlay on video (Phase 3)
- [ ] PID tuning interface (Phase 5)
- [ ] Waypoint selection on map (Phase 5)
- [ ] Autonomous mission planning (Phase 6)

## Troubleshooting

### Frontend Won't Start

```bash
# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Check Node version (need 16+)
node --version
```

### Can't Connect to Backend

- Ensure backend is running: `python -m autonomous.api.main`
- Check backend URL in `src/services/api.ts` (default: http://localhost:8000)
- Check browser console for CORS errors
- Verify no firewall blocking ports 8000 or 5173

### Video Not Loading

- Check backend logs for video initialization errors
- Ensure drone is connected to backend
- Verify video endpoint: http://localhost:8000/api/video/status
- Check browser console (F12) for errors

### WebSocket Not Connecting

- Ensure backend is running
- Check WebSocket URL: `ws://localhost:8000/ws/telemetry`
- View browser console for connection errors
- Backend must be connected to drone for telemetry

## Technology Stack

- **React 18** - UI library
- **TypeScript 5** - Type-safe JavaScript
- **Vite 4** - Build tool and dev server
- **Tailwind CSS 3** - Utility-first CSS
- **Axios** - HTTP client
- **WebSocket API** - Real-time communication

## Documentation

- **Phase 2 Guide**: [../docs/guides/phase2-webapp.md](../docs/guides/phase2-webapp.md)
- **API Reference**: [../docs/API_REFERENCE.md](../docs/API_REFERENCE.md)
- **System Architecture**: [../docs/technical/architecture.md](../docs/technical/architecture.md)

## Contributing

See [Contributing Guidelines](../docs/contributing/CONTRIBUTING.md) for:
- Code style (ESLint + Prettier)
- Component patterns
- Pull request process

## License

Part of the TEKY drone controller project. Educational purposes only.

---

**Need help?** See [Troubleshooting Guide](../docs/getting-started/TROUBLESHOOTING.md) or the [Phase 2 documentation](../docs/guides/phase2-webapp.md).
