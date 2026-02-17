# Phase 2: React Frontend + FastAPI Backend ✅

Phase 2 is complete! You now have a modern web interface with manual drone control.

## 🎉 What's Been Built

### Backend (FastAPI)
- ✅ **RESTful API** - Modern async endpoints
- ✅ **Drone control** - Connect, video, camera switching
- ✅ **WebSocket support** - Real-time telemetry streaming
- ✅ **CORS enabled** - Frontend can connect
- ✅ **Wraps existing code** - Uses TYVYXDroneControllerAdvanced

**Key Files:**
- [`autonomous/api/main.py`](autonomous/api/main.py) - FastAPI app
- [`autonomous/api/routes/drone.py`](autonomous/api/routes/drone.py) - Drone endpoints
- [`autonomous/api/routes/video.py`](autonomous/api/routes/video.py) - Video streaming
- [`autonomous/api/websocket.py`](autonomous/api/websocket.py) - WebSocket telemetry
- [`autonomous/services/drone_service.py`](autonomous/services/drone_service.py) - High-level service

### Frontend (React + TypeScript + Vite)
- ✅ **Modern React UI** - TypeScript + Tailwind CSS
- ✅ **Video feed display** - MJPEG streaming
- ✅ **Manual controls** - Connect, video, camera switching
- ✅ **Status monitoring** - Real-time connection status
- ✅ **WebSocket telemetry** - Live updates from backend

**Key Files:**
- [`frontend/src/App.tsx`](frontend/src/App.tsx) - Main application
- [`frontend/src/services/api.ts`](frontend/src/services/api.ts) - API client

## 🚀 Quick Start

### Terminal 1: Start Backend

```bash
cd i:/Projects/Drones/TYVYX

# Make sure dependencies are installed
pip install -r requirements.txt

# Start FastAPI server
python -m autonomous.api.main
```

Backend will run at: **http://localhost:8000**
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

### Terminal 2: Start Frontend

```bash
cd frontend

# First time only: install dependencies
npm install

# Start Vite dev server
npm run dev
```

Frontend will run at: **http://localhost:5173**

## 📱 Using the Interface

### 1. Connect to Drone

1. Power on your TYVYX drone
2. Connect your computer to drone WiFi (HD-720P-*, HD-FPV-*, etc.)
3. Verify drone is at 192.168.1.1: `ping 192.168.1.1`
4. Click **"Connect"** button in the web interface

### 2. Start Video

1. Once connected, click **"Start Video"**
2. Video feed will appear in the left panel
3. Video streams via MJPEG at http://localhost:8000/api/video/feed

### 3. Control Drone

- **Camera 1/2** - Switch between cameras
- **Stop Video** - Stop video stream
- **Disconnect** - Disconnect from drone

### Status Indicators

- **Green ●** - Connected/streaming
- **Red ○** - Disconnected
- **Gray ○** - Not active

## 📊 API Endpoints

### Drone Control

```http
POST /api/drone/connect
POST /api/drone/disconnect
GET  /api/drone/status
POST /api/drone/command
GET  /api/drone/telemetry
```

### Video Streaming

```http
GET /api/video/feed       # MJPEG stream
GET /api/video/status     # Stream status
```

### WebSocket

```
ws://localhost:8000/ws/telemetry   # Real-time telemetry (10 Hz)
```

## 🔧 API Usage Examples

### Connect to Drone

```javascript
POST /api/drone/connect
{
  "drone_ip": "192.168.1.1"
}
```

### Send Command

```javascript
POST /api/drone/command
{
  "action": "start_video"
}

POST /api/drone/command
{
  "action": "switch_camera",
  "params": { "camera": 1 }
}
```

### Get Status

```javascript
GET /api/drone/status

Response:
{
  "connected": true,
  "video_streaming": true,
  "is_running": true,
  "device_type": 2,
  "timestamp": 1708106400.123
}
```

## 🛠️ Development

### Backend Development

```bash
# Run with auto-reload
cd i:/Projects/Drones/TYVYX
python -m autonomous.api.main

# The server auto-reloads on code changes
```

### Frontend Development

```bash
# Run with hot module replacement
cd frontend
npm run dev

# Vite provides instant HMR
```

### Build for Production

```bash
# Backend: No build needed (Python)

# Frontend: Build static files
cd frontend
npm run build

# Output in frontend/dist/
# Serve with: npm run preview
```

## 📂 Project Structure

```
TYVYX/
├── autonomous/
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── drone.py         # Drone endpoints
│   │   │   └── video.py         # Video endpoints
│   │   └── websocket.py         # WebSocket telemetry
│   ├── services/
│   │   └── drone_service.py     # High-level drone service
│   ├── models/                  # From Phase 1
│   └── navigation/              # From Phase 1
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main React component
│   │   ├── services/
│   │   │   └── api.ts           # API client
│   │   ├── index.css            # Tailwind styles
│   │   └── main.tsx             # Entry point
│   ├── package.json
│   └── vite.config.ts
│
└── tyvyx/                        # Existing code (preserved)
```

## ✅ Phase 2 Verification

Test these features:

- [ ] Backend starts without errors
- [ ] Frontend starts and displays UI
- [ ] Connect button works (connects to drone)
- [ ] Status indicators update correctly
- [ ] Start Video works
- [ ] Video feed displays in browser
- [ ] Camera switch works (switches between cameras)
- [ ] Stop Video works
- [ ] Disconnect works
- [ ] WebSocket telemetry streams (check browser console)

## 🐛 Troubleshooting

### Backend won't start

```bash
# Check dependencies
pip install -r requirements.txt

# Check Python version (need 3.8+)
python --version

# Check if port 8000 is free
netstat -an | findstr :8000
```

### Frontend won't start

```bash
# Reinstall dependencies
cd frontend
rm -rf node_modules package-lock.json
npm install

# Check Node version (need 16+)
node --version
```

### Can't connect to drone

```bash
# Verify WiFi connection
ping 192.168.1.1

# Check if drone is powered on
# Check WiFi network name (HD-720P-*, etc.)

# Try original Flask app first
python -m tyvyx.app
# Visit http://localhost:5000
```

### Video not working

- Check FFmpeg is installed: `ffmpeg -version`
- Try starting video manually in backend logs
- Check browser console for errors
- Verify RTSP stream works: `ffplay rtsp://192.168.1.1:7070/webcam`

### CORS errors

- Check backend is running on http://localhost:8000
- Check frontend is running on http://localhost:5173
- CORS is configured for these ports in `autonomous/api/main.py`

## 📈 Next Steps: Phase 3

Phase 3 will add **position estimation** using optical flow:

**Features to Add:**
- Optical flow tracker (OpenCV)
- Position estimator (dead reckoning)
- Kalman filter (smoothing)
- Position display on UI
- 2D map visualization

**Stay tuned!** 🚁✨

## 📚 Related Documentation

- **Phase 1**: [Flight Control Calibration](phase1-calibration.md) - Flight control calibration
- **Turbodrone Integration**: [Turbodrone Architecture](turbodrone-architecture.md) - Architecture patterns
- **Getting Started**: [Getting Started Guide](../getting-started/README.md) - Setup and installation

---

**Phase 2 Complete! You now have a modern React frontend with FastAPI backend.** 🎉
