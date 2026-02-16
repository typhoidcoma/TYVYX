# TEKY Drone Control - Getting Started Guide

## Quick Start

### 1. Prerequisites Check

Before you begin, ensure you have:

- ✅ Python 3.7 or higher installed
- ✅ WiFi-capable computer
- ✅ TEKY WiFi drone (powered on)
- ✅ Basic understanding of command line/terminal

### 2. Installation

```bash
# Clone or navigate to the project directory
cd TEKY_Working

# Install Python dependencies
pip install -r requirements.txt
```

**Important**: You need FFmpeg for video streaming!

- **Windows**: 
   1. Download from https://ffmpeg.org/download.html
   2. Extract and add to PATH environment variable
   3. Verify: `ffmpeg -version`

Also install Python packages into the project's virtual environment:

```powershell
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for running tests and linters (optional)
```

- **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt-get update
  sudo apt-get install ffmpeg
  ```

- **macOS**:
  ```bash
  brew install ffmpeg
  ```

### 3. Connect to Drone

1. Turn on your TEKY drone
2. On your computer, look for WiFi network starting with:
   - `HD-720P-`
   - `HD-FPV-`
   - `HD720-`
   - `FHD-`
3. Connect to this WiFi network
4. Wait for connection to establish (no internet is normal!)

### 4. Test Connection

Run the network diagnostics tool:

```bash
python network_diagnostics.py
```

Select option `1` to run all tests. You should see:
- ✓ Ping successful
- ✓ UDP response received
- Packet capture showing communication

If tests fail, see [Troubleshooting](#troubleshooting) section.

### 5. Run Basic Controller

```bash
python drone_controller.py
```

You should see:
- Console output showing connection status
- Video window displaying drone camera feed (if successful)

**Basic controls**:
- Press `Q` to quit
- Press `S` to take a screenshot
- Press `1` or `2` to switch cameras
- Press `M` to toggle screen mode

### 6. (Optional) Try Advanced Controller

⚠️ **Warning**: Flight controls are experimental!

```bash
python drone_controller_advanced.py
```

Additional controls:
- Press `SPACE` to activate flight controller
- Use `W/A/S/D` for pitch/roll
- Use arrow keys for throttle/yaw
- Press `ESC` for emergency reset

## Understanding the System

### How It Works

The TEKY drone uses:
1. **WiFi Access Point**: Drone creates its own WiFi network
2. **UDP Commands**: Control commands sent to `192.168.1.1:7099`
3. **RTSP Video**: Live video stream at `rtsp://192.168.1.1:7070/webcam`

### Command Protocol

The app sends UDP packets to control the drone:

```python
# Heartbeat (keeps connection alive)
[0x01, 0x01]  # Sent every 1 second

# Initialize drone
[0x64]  # 100 in decimal

# Switch camera
[0x06, 0x01]  # Camera 1
[0x06, 0x02]  # Camera 2
```

### Video Streaming

The drone streams video using RTSP (Real-Time Streaming Protocol):
- URL: `rtsp://192.168.1.1:7070/webcam`
- Codec: H.264/MJPEG
- Typical resolution: 720p or 1080p
- Latency: 1-3 seconds

## Advanced Usage

### Capturing and Analyzing Packets

Use Wireshark to capture UDP traffic:

1. Install Wireshark
2. Connect to drone WiFi
3. Start capturing on WiFi interface
4. Filter: `udp.port == 7099`
5. Use official Android app to fly drone
6. Analyze captured packets to discover flight commands

### Reverse Engineering Native Libraries

The Android app uses native libraries for flight control:
- `libgl_jni.so` - OpenGL type drone
- `libtc_jni.so` - Texture type drone

To extract command protocol:
1. Extract APK from Android device
2. Locate .so files in `lib/` folder
3. Use IDA Pro or Ghidra to decompile
4. Look for functions like `nativeSendCommand()`

### Web Interface (Future Development)

The `app.py` file is a Flask starter template for building a web-based controller:

```bash
python app.py
```

Then visit `http://localhost:5000` in your browser.

## Troubleshooting

### "Failed to connect to drone"

**Symptoms**: UDP connection fails, no response from drone

**Solutions**:
1. Verify you're connected to drone's WiFi (not your home WiFi!)
2. Check drone is powered on and WiFi is active
3. Try power cycling the drone
4. Check firewall isn't blocking Python
5. Run `python network_diagnostics.py` to test

### "Failed to open video stream"

**Symptoms**: Video window doesn't appear or shows error

**Solutions**:
1. Ensure FFmpeg is installed: `ffmpeg -version`
2. Test RTSP URL manually:
   ```bash
   ffplay rtsp://192.168.1.1:7070/webcam
   ```
3. Check drone is streaming (usually automatic)
4. Try restarting the controller
5. Increase timeout in code

### Video is very laggy

**Symptoms**: 3+ seconds delay, choppy playback

**Solutions**:
1. Move closer to drone (reduce WiFi distance)
2. Reduce other WiFi interference
3. Lower buffer size in code:
   ```python
   video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
   ```
4. Use wired Ethernet if drone supports it

### Flight controls don't work

**Symptoms**: Drone doesn't respond to commands

**Expected Behavior**: This is normal! Flight controls are experimental.

**Why**: The actual flight commands are in native code that wasn't fully reverse engineered.

**Solutions**:
1. Capture packets during real flight (see above)
2. Try different command byte patterns
3. Use Android app for actual flying
4. Wait for community to discover protocol

### "ModuleNotFoundError: No module named 'cv2'"

**Symptoms**: Error when running Python script

**Solution**:
```bash
pip install opencv-python
```

### Port 7099 already in use

**Symptoms**: "Address already in use" error

**Solutions**:
1. Close other instances of the controller
2. Wait 30 seconds for OS to release port
3. Restart computer if persistent

## Safety Tips

⚠️ **Always follow these safety guidelines:**

1. **Test in Open Areas**: Use large, open spaces away from people
2. **Visual Line of Sight**: Keep drone where you can see it
3. **Emergency Procedures**: Know how to stop the drone quickly
4. **Battery Awareness**: Land before battery gets too low
5. **Weather Conditions**: Don't fly in wind, rain, or poor visibility
6. **Legal Compliance**: Follow local drone regulations
7. **Start Slow**: Test basic controls before attempting complex maneuvers
8. **Backup Control**: Keep official Android app ready as backup

## File Reference

- `drone_controller.py` - Basic video and control (recommended)
- `drone_controller_advanced.py` - Experimental flight controls
- `network_diagnostics.py` - Connection testing tool
- `REVERSE_ENGINEERING_NOTES.md` - Technical protocol documentation
- `requirements.txt` - Python dependencies
- `README.md` - Project overview

## Getting Help

If you encounter issues:

1. Check this guide's troubleshooting section
2. Read `REVERSE_ENGINEERING_NOTES.md` for technical details
3. Run `network_diagnostics.py` to identify problems
4. Check Python and OpenCV versions
5. Review error messages carefully

## Next Steps

Once you have basic control working:

1. **Improve Video Quality**: Experiment with OpenCV settings
2. **Discover Flight Commands**: Use packet capture during flights
3. **Build Web Interface**: Enhance `app.py` for browser control
4. **Add Features**: 
   - Recording video to file
   - Telemetry display (battery, altitude, etc.)
   - Waypoint navigation
   - Gesture control
5. **Share Findings**: Help the community by documenting discovered commands

## Contributing

Found a working flight command? Discovered new features?

Please document your findings in `REVERSE_ENGINEERING_NOTES.md` and share with the community!

---

**Have fun and fly safe! 🚁**
