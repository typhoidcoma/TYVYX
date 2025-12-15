# TEKY WiFi Drone Controller

This project provides Python applications to receive the WiFi video feed and control a TEKY WiFi drone, based on reverse engineering the Android app.

## Features

### ✅ Implemented
- **UDP Communication**: Heartbeat and command transmission on port 7099
- **RTSP Video Stream**: Live video feed from drone at `rtsp://192.168.1.1:7070/webcam`
- **Camera Switching**: Switch between multiple cameras (if available)
- **Screen Mode Toggle**: Switch between screen display modes
- **Screenshot Capture**: Save frames from the video feed
- **Device Type Detection**: Auto-detect drone type (GL/TC)

### ⚠️ Experimental
- **Flight Controls**: Throttle, yaw, pitch, and roll commands (may not work without native library reverse engineering)

### 📋 Documentation
- **REVERSE_ENGINEERING_NOTES.md**: Detailed technical documentation of the drone protocol

## Requirements

- Python 3.7+
- OpenCV with FFmpeg support
- WiFi connection to drone network

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Ensure FFmpeg is installed** (required for RTSP stream):
   - **Windows**: Download from https://ffmpeg.org/ and add to PATH
   - **Linux**: `sudo apt-get install ffmpeg`
   - **macOS**: `brew install ffmpeg`

3. **Connect to the drone's WiFi network:**
   - Look for WiFi network matching: `HD-720P-*`, `HD-FPV-*`, `HD720-*`, or `FHD-*`
   - The drone IP is `192.168.1.1`

## Usage

### Basic Controller (Recommended)

```bash
python drone_controller.py
```

**Controls:**
- `Q` - Quit application
- `1` - Switch to camera 1
- `2` - Switch to camera 2  
- `M` - Toggle screen mode
- `I` - Send initialize command
- `S` - Take screenshot

### Advanced Controller (Experimental)

⚠️ **WARNING**: Flight controls are experimental and may not work!

```bash
python drone_controller_advanced.py
```

**Additional Flight Controls:**
- `SPACE` - Start/Stop flight controller
- `ESC` - Emergency reset (center all controls)
- `W/S` - Pitch forward/backward
- `A/D` - Roll left/right
- `↑/↓` - Throttle up/down
- `←/→` - Yaw left/right

## Network Configuration

- **Drone IP**: `192.168.1.1`
- **UDP Control Port**: `7099`
- **RTSP Video Port**: `7070`
- **Video Stream URL**: `rtsp://192.168.1.1:7070/webcam`

## Known Limitations

1. **Flight Controls**: The actual flight control commands are implemented in native libraries (.so files) that are not visible in the decompiled Java code. The experimental flight commands may not work correctly.

2. **Video Latency**: RTSP streams can have 1-3 seconds of latency depending on network conditions.

3. **Connection Stability**: Requires stable WiFi connection. UDP packets may be lost.

## Troubleshooting

### Video Stream Won't Connect
- Ensure you're connected to the drone's WiFi
- Check that FFmpeg is installed and in PATH
- Verify drone is powered on
- Try restarting the drone

### No Response from Drone
- Check WiFi connection
- Verify IP address (192.168.1.1)
- Ensure no firewall is blocking UDP port 7099
- Try power cycling the drone

### Flight Controls Don't Work
- This is expected - flight controls are experimental
- Would require reverse engineering the native .so libraries
- Consider using network packet capture (Wireshark) during app usage to discover actual commands

## Development Notes

The project includes:
- `drone_controller.py` - Basic video and camera control
- `drone_controller_advanced.py` - Experimental flight controls
- `REVERSE_ENGINEERING_NOTES.md` - Technical documentation
- `app.py` - Original web app (deprecated)

## Contributing

To improve flight control implementation:
1. Use Wireshark to capture UDP packets during Android app flight
2. Reverse engineer native .so libraries (libbl60xmjpeg.so, etc.)
3. Test different command byte patterns safely

## Safety Warning

⚠️ **Always fly responsibly:**
- Test in open, safe areas
- Keep drone in visual line of sight  
- Be prepared for unexpected behavior
- Have emergency stop ready
- Follow local regulations

## License

This project is for educational purposes. Use at your own risk.