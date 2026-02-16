# TEKY Drone Troubleshooting Guide

This guide covers common issues and solutions when working with the TEKY drone controller.

## Table of Contents

- [Connection Issues](#connection-issues)
- [Video Streaming Issues](#video-streaming-issues)
- [Flight Control Issues](#flight-control-issues)
- [Dependency and Installation Issues](#dependency-and-installation-issues)
- [Phase 2 Web Interface Issues](#phase-2-web-interface-issues)
- [Network Diagnostics](#network-diagnostics)

---

## Connection Issues

### Failed to connect to drone

**Symptoms**: UDP connection fails, no response from drone

**Solutions**:
1. **Verify WiFi connection**: Make sure you're connected to the drone's WiFi (not your home WiFi!)
   - Look for networks starting with: `HD-720P-*`, `HD-FPV-*`, `HD720-*`, or `FHD-*`
   - Drone IP should be: `192.168.1.1`

2. **Check drone is powered on**: Ensure the drone is turned on and WiFi is active

3. **Power cycle the drone**: Turn off, wait 10 seconds, then turn back on

4. **Test connectivity**:
   ```bash
   ping 192.168.1.1
   ```
   Should receive responses. If not, WiFi connection is the issue.

5. **Run network diagnostics**:
   ```bash
   python -m teky.network_diagnostics
   ```
   Select option `1` to run all tests.

6. **Check firewall**: Ensure your firewall isn't blocking Python
   - Windows: Allow Python through Windows Firewall
   - macOS: System Preferences → Security & Privacy → Firewall → Allow Python
   - Linux: Check iptables rules

7. **Try the original app first**: If problems persist, test with the original Flask app:
   ```bash
   python -m teky.app
   ```
   Visit http://localhost:5000 to verify basic connectivity.

### Port 7099 already in use

**Symptoms**: "Address already in use" error when starting controller

**Solutions**:
1. **Close other instances**: Close any running drone controller instances
2. **Wait for OS to release port**: Wait 30-60 seconds
3. **Find and kill process** (if needed):
   ```bash
   # Windows
   netstat -ano | findstr :7099
   taskkill /PID <process_id> /F

   # Linux/macOS
   lsof -i :7099
   kill -9 <process_id>
   ```
4. **Restart computer**: If the port remains locked

---

## Video Streaming Issues

### Failed to open video stream

**Symptoms**: Video window doesn't appear or shows error

**Solutions**:
1. **Verify FFmpeg is installed**:
   ```bash
   ffmpeg -version
   ```
   If not installed, see installation instructions in [Getting Started Guide](README.md#2-installation).

2. **Test RTSP URL manually**:
   ```bash
   ffplay rtsp://192.168.1.1:7070/webcam
   ```
   If this works, the issue is in the Python code.

3. **Check drone is streaming**: Video usually starts automatically when drone powers on

4. **Restart the controller**: Close and restart the drone controller

5. **Increase timeout**: The stream may need more time to initialize
   - For Phase 2 web interface, check backend logs for initialization errors

6. **Check firewall**: Ensure RTSP port 7070 isn't blocked

### Video is very laggy

**Symptoms**: 3+ seconds delay, choppy playback, freezing

**Solutions**:
1. **Move closer to drone**: Reduce WiFi distance to improve signal strength

2. **Reduce WiFi interference**:
   - Move away from routers, microwaves, and other 2.4GHz devices
   - Close other applications using WiFi bandwidth

3. **Lower buffer size** (for Python controller):
   - Edit the video stream code to reduce buffer:
   ```python
   video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
   ```

4. **Check WiFi signal strength**: Weak signal = laggy video

5. **Use wired connection if available**: Some drones support Ethernet

6. **Close unnecessary applications**: Free up CPU and network resources

### Video not working (Phase 2 Web Interface)

**Symptoms**: No video feed in browser

**Solutions**:
1. **Check FFmpeg installation**:
   ```bash
   ffmpeg -version
   ```

2. **Check backend logs**: Look for video initialization errors in the terminal running the FastAPI server

3. **Try starting video manually**: Use the original app first to verify video works:
   ```bash
   python -m teky.app
   ```

4. **Verify RTSP stream**:
   ```bash
   ffplay rtsp://192.168.1.1:7070/webcam
   ```

5. **Check browser console**: Press F12 and look for errors in the Console tab

6. **Check video endpoint**: Visit http://localhost:8000/api/video/status to check stream status

---

## Flight Control Issues

### Drone doesn't respond to flight commands

**Symptoms**: Drone doesn't respond to throttle, pitch, roll, or yaw commands

**Expected Behavior**: This is often normal! Flight controls are experimental.

**Why**: The actual flight commands are in native code that may not be fully reverse engineered.

**Solutions**:
1. **Test basic connectivity first**:
   ```bash
   python -m teky.app
   ```
   Visit http://localhost:5000 and test camera switching. If that works, UDP connection is good.

2. **Capture packets during real flight**:
   ```bash
   # Run packet sniffer while controlling from official Android app
   python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30
   ```
   Compare captured commands with your code.

3. **Verify command format**: Check that you're using the correct command format:
   ```python
   [CMD_ID, throttle, yaw, pitch, roll, checksum]
   ```
   Where CMD_ID = 0x50, values are 0-255, and 128 = neutral.

4. **Use Android app for actual flying**: Keep the official app as backup

5. **Wait for community discoveries**: The protocol may not be fully documented yet

### Drone behaves erratically

**Symptoms**: Unpredictable movements, spinning, sudden acceleration

**Solutions**:
1. **Start with smaller value changes**: Use ±5 instead of ±10 when testing

2. **Test in calm environment**: Avoid wind, drafts, and air conditioning

3. **Ensure full battery**: Low battery can cause erratic behavior

4. **Verify command format**: May need to adjust based on packet sniffing results

5. **Reset to neutral frequently**: Use 128 for all values to return to neutral

6. **Test one axis at a time**: Don't combine throttle + pitch + roll + yaw initially

7. **Consider tethering**: Use a string to tether the drone during initial tests

---

## Dependency and Installation Issues

### ModuleNotFoundError: No module named 'cv2'

**Symptoms**: ImportError when running Python script

**Solution**:
```bash
pip install opencv-python
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

### ModuleNotFoundError: No module named 'fastapi' (or other)

**Symptoms**: ImportError for FastAPI, uvicorn, or other backend dependencies

**Solution**:
```bash
pip install -r requirements.txt
```

### FFmpeg not found

**Symptoms**: "ffmpeg: command not found" or "Failed to open video stream"

**Solution**: Install FFmpeg for your platform:

**Windows**:
1. Download from https://ffmpeg.org/download.html
2. Extract and add to PATH environment variable
3. Verify: `ffmpeg -version`

**Linux (Ubuntu/Debian)**:
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**macOS**:
```bash
brew install ffmpeg
```

### Python version too old

**Symptoms**: Syntax errors, "async/await" not supported

**Solution**: Upgrade to Python 3.8 or higher:
```bash
python --version  # Check current version
```

Download latest from https://www.python.org/downloads/

---

## Phase 2 Web Interface Issues

### Backend won't start

**Symptoms**: FastAPI server fails to start

**Solutions**:
1. **Check dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Check Python version** (need 3.8+):
   ```bash
   python --version
   ```

3. **Check if port 8000 is free**:
   ```bash
   # Windows
   netstat -an | findstr :8000

   # Linux/macOS
   lsof -i :8000
   ```
   If in use, kill the process or change the port in `autonomous/api/main.py`.

4. **Check for syntax errors**: Look at the error message in the terminal

5. **Try running directly**:
   ```bash
   python -m autonomous.api.main
   ```

### Frontend won't start

**Symptoms**: Vite dev server fails to start, npm errors

**Solutions**:
1. **Reinstall dependencies**:
   ```bash
   cd frontend
   rm -rf node_modules package-lock.json
   npm install
   ```

2. **Check Node version** (need 16+):
   ```bash
   node --version
   ```
   Download latest LTS from https://nodejs.org/

3. **Check if port 5173 is free**:
   ```bash
   # Windows
   netstat -an | findstr :5173

   # Linux/macOS
   lsof -i :5173
   ```

4. **Clear Vite cache**:
   ```bash
   rm -rf frontend/.vite
   ```

5. **Try running with verbose output**:
   ```bash
   npm run dev -- --debug
   ```

### CORS errors in browser

**Symptoms**: "Access-Control-Allow-Origin" errors in browser console

**Solutions**:
1. **Verify backend is running** on http://localhost:8000
   - Check the backend terminal for "Uvicorn running on..."

2. **Verify frontend is running** on http://localhost:5173
   - Check the frontend terminal for "Local: http://localhost:5173"

3. **Check CORS configuration**: CORS is configured in `autonomous/api/main.py` for these ports

4. **Try different browser**: Test in Chrome, Firefox, or Edge

5. **Clear browser cache**: Hard refresh with Ctrl+Shift+R (Cmd+Shift+R on Mac)

### WebSocket telemetry not working

**Symptoms**: No real-time updates in browser

**Solutions**:
1. **Check browser console** (F12): Look for WebSocket connection errors

2. **Verify WebSocket URL**: Should be `ws://localhost:8000/ws/telemetry`

3. **Check backend is connected to drone**: WebSocket only streams when drone is connected

4. **Test WebSocket manually**:
   - Use a WebSocket client extension for your browser
   - Connect to `ws://localhost:8000/ws/telemetry`

5. **Check backend logs**: Look for WebSocket connection messages

---

## Network Diagnostics

### Running comprehensive network tests

Use the built-in diagnostics tool:

```bash
python -m teky.network_diagnostics
```

**Available tests**:
1. **Run all tests** - Comprehensive check of connectivity
2. **Ping test** - Basic IP connectivity
3. **UDP test** - Command protocol test
4. **Packet capture** - Record communication for analysis

### Expected results

**Ping test**:
```
Ping test: Success
Round-trip time: 2-10ms
```

**UDP test**:
```
UDP test: Success
Response received from 192.168.1.1
```

### If all tests fail

1. **Verify WiFi connection**: Check you're connected to drone WiFi
2. **Check drone IP**: May not be 192.168.1.1 (check WiFi settings)
3. **Try different network interface**: Disable other adapters
4. **Check VPN**: Disconnect VPN if active
5. **Test with official app**: Verify drone works with manufacturer's app

---

## Getting Additional Help

If you've tried the solutions above and still have issues:

1. **Check documentation**:
   - [Getting Started Guide](README.md) - Setup and basic usage
   - [Quick Reference](QUICK_REFERENCE.md) - Command reference
   - [Reverse Engineering Notes](../technical/reverse-engineering.md) - Protocol details

2. **Run diagnostics**:
   ```bash
   python -m teky.network_diagnostics
   ```

3. **Review error messages**: Error messages often contain helpful information

4. **Check Python and dependency versions**:
   ```bash
   python --version
   pip list
   ```

5. **Test with original Flask app**: Verify basic functionality:
   ```bash
   python -m teky.app
   ```

6. **Capture packets**: Use Wireshark or the packet sniffer to analyze communication

---

## Safety Reminders

When troubleshooting flight control issues:

- ✅ Test in open, safe areas
- ✅ Keep drone in visual line of sight
- ✅ Be prepared to emergency stop
- ✅ Have fully charged battery
- ✅ Consider tethering drone during tests
- ✅ Keep official Android app as backup
- ✅ Test at low altitude (0.5-1.0m) first

---

*For detailed technical information, see [Reverse Engineering Notes](../technical/reverse-engineering.md) and [System Architecture](../technical/architecture.md).*
