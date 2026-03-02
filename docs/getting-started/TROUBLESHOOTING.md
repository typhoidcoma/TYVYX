# Troubleshooting Guide

## Connection Issues

### Can't connect to drone

1. Verify you're on the drone's WiFi (not home WiFi)
   - K417 SSIDs: `Drone-*`, `FLOW_*`, `K417`
   - E88Pro SSIDs: `HD-720P-*`, `HD-FPV-*`, `WIFI_*`
2. Test connectivity: `ping 192.168.169.1` (K417) or `ping 192.168.1.1` (E88Pro)
3. Power cycle the drone (off, wait 10s, on)
4. Check Windows Firewall allows Python on public networks

### Port already in use

```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <process_id> /F

# Kill all Python processes (Windows PowerShell)
Get-Process python* | Stop-Process -Force
```

## Video Issues

### No video in browser

1. Check backend logs for video errors
2. Verify drone is connected and reachable
3. Check video endpoint: http://localhost:8000/api/video/status
4. Check browser console (F12) for WebSocket errors
5. Try MJPEG fallback: http://localhost:8000/api/video/feed

### Video is laggy

- Move closer to drone (reduce WiFi distance)
- Reduce WiFi interference (2.4 GHz band congestion)
- Close other applications using WiFi bandwidth

## Web Interface Issues

### Backend won't start

```bash
pip install -r requirements.txt
python --version  # Need 3.8+
python -m autonomous.api.main
```

### Frontend won't start

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
node --version  # Need 18+
npm run dev
```

### CORS errors in browser

- Verify backend is running on http://localhost:8000
- Verify frontend is running on http://localhost:5173
- Hard refresh: Ctrl+Shift+R

## Flight Control Issues

### Drone doesn't respond to commands

Flight controls use reverse-engineered commands that may not work perfectly on all models. Verify basic connectivity by checking that camera switching works in the web interface.

### Drone behaves erratically

- Start with smaller value changes (use precise control mode)
- Test in calm environment (no wind/drafts)
- Ensure full battery charge
- Test one axis at a time

## Position Tracking Issues

### Position not updating

- Verify position tracking is started (POST `/api/position/start`)
- Check that bottom camera is active (camera mode should be "bottom" for optical flow)
- Check debug pipeline: GET `/api/debug/pipeline`
- Verify optical flow has features: GET `/api/debug/optical_flow`

### Altitude stuck at zero

- Start depth estimation (POST `/api/depth/start`)
- Depth only feeds altitude when bottom camera is active
- Check depth status: GET `/api/depth/data`

### EKF not getting updates

Use debug endpoints to check individual sensor feeds:
- GET `/api/debug/ekf/state` - check update counts
- POST `/api/debug/ekf/inject_velocity` - test velocity input
- POST `/api/debug/ekf/inject_altitude` - test altitude input
- GET `/api/debug/pipeline` - full pipeline overview

## Network Diagnostics

```bash
# Check drone is reachable
ping 192.168.169.1

# Check if port is open (K417)
# The drone uses port 8800 for everything (single port)

# Run network scan via API
curl http://localhost:8000/api/network/scan
```
