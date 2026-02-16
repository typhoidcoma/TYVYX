# TEKY Drone Quick Reference Card

## Network Details
```
Drone IP:       192.168.1.1
UDP Port:       7099
RTSP Port:      7070
Video URL:      rtsp://192.168.1.1:7070/webcam
WiFi Pattern:   HD-720P-* | HD-FPV-* | HD720-* | FHD-*
```

## Quick Start Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Test connection
python network_diagnostics.py

# Basic controller (recommended)
python drone_controller.py

# Advanced with flight controls (experimental)
python drone_controller_advanced.py
```

## UDP Command Reference

| Command | Bytes | Description |
|---------|-------|-------------|
| Heartbeat | `01 01` | Keep connection alive (send every 1s) |
| Initialize | `64` | Initialize/activate drone |
| Special | `63` | Special command |
| Camera 1 | `06 01` | Switch to camera 1 |
| Camera 2 | `06 02` | Switch to camera 2 |
| Screen Mode 1 | `09 01` | Screen display mode 1 |
| Screen Mode 2 | `09 02` | Screen display mode 2 |

## Response Format

**Byte 0**: Device type & resolution info
- Bit pattern indicates GL (2) or TC (10) device type

**Byte 1**: Camera switch reset state

**Byte 2**: Screen switch state (1 or 2)

## Basic Controller Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Q | Quit application |
| 1 | Switch to camera 1 |
| 2 | Switch to camera 2 |
| M | Toggle screen mode |
| I | Send initialize command |
| S | Take screenshot |

## Advanced Controller Keyboard Shortcuts

### Basic Controls
| Key | Action |
|-----|--------|
| Q | Quit application |
| SPACE | Start/Stop flight controller |
| ESC | Emergency reset (center all controls) |

### Camera Controls
| Key | Action |
|-----|--------|
| 1 | Switch to camera 1 |
| 2 | Switch to camera 2 |
| M | Toggle screen mode |
| S | Take screenshot |

### Flight Controls (when active)
| Key | Action |
|-----|--------|
| W | Pitch forward |
| S | Pitch backward |
| A | Roll left |
| D | Roll right |
| ↑ | Increase throttle |
| ↓ | Decrease throttle |
| ← | Yaw left |
| → | Yaw right |

## Python API Quick Examples

### Connect to Drone
```python
from drone_controller import TEKYDroneController

drone = TEKYDroneController()
if drone.connect():
    print("Connected!")
```

### Send Commands
```python
# Heartbeat
drone.send_command(bytes([1, 1]))

# Initialize
drone.send_command(bytes([100]))

# Switch camera
drone.switch_camera(1)  # Camera 1
drone.switch_camera(2)  # Camera 2
```

### Video Stream
```python
# Start video
if drone.start_video_stream():
    # Get frames
    ret, frame = drone.get_frame()
    if ret:
        cv2.imshow('Video', frame)
```

### Full Example
```python
import cv2
from drone_controller import TEKYDroneController

drone = TEKYDroneController()

if drone.connect():
    if drone.start_video_stream():
        while True:
            ret, frame = drone.get_frame()
            if ret:
                cv2.imshow('Drone', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    drone.disconnect()

cv2.destroyAllWindows()
```

## Troubleshooting Quick Checks

### No Connection
```bash
# Check if drone is reachable
ping 192.168.1.1

# Test UDP with diagnostics
python network_diagnostics.py
```

### No Video
```bash
# Test FFmpeg installation
ffmpeg -version

# Test RTSP stream directly
ffplay rtsp://192.168.1.1:7070/webcam
```

### Python Issues
```bash
# Check Python version (need 3.7+)
python --version

# Reinstall OpenCV
pip uninstall opencv-python
pip install opencv-python
```

## Packet Capture for Research

### Using Wireshark
1. Install Wireshark
2. Connect to drone WiFi
3. Start capture on WiFi interface
4. Filter: `udp.port == 7099`
5. Use Android app to fly
6. Analyze captured packets

### Using tcpdump (Linux/Mac)
```bash
# Capture UDP on port 7099
sudo tcpdump -i wlan0 -n udp port 7099 -XX

# Save to file for later analysis
sudo tcpdump -i wlan0 -n udp port 7099 -w drone_capture.pcap
```

## Common Issues & Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| Can't connect | Power cycle drone, reconnect WiFi |
| No video | Check FFmpeg, try `ffplay` test |
| Controls unresponsive | Press ESC to reset |
| Port in use | Wait 30s or restart app |
| Import error | `pip install opencv-python numpy` |

## Safety Checklist

- [ ] Test area is clear and open
- [ ] Drone battery is charged
- [ ] Emergency stop ready (ESC key)
- [ ] WiFi connection is stable
- [ ] Local regulations checked
- [ ] Visual line of sight maintained

## File Locations

```
TEKY_Working/
├── drone_controller.py              # Basic controller
├── drone_controller_advanced.py     # With flight controls
├── network_diagnostics.py           # Testing tool
├── REVERSE_ENGINEERING_NOTES.md     # Technical docs
├── README.md               # Full guide
├── QUICK_REFERENCE.md               # This file
├── README.md                        # Project overview
└── requirements.txt                 # Dependencies
```

## Useful Links

- **FFmpeg Download**: https://ffmpeg.org/download.html
- **Python Download**: https://www.python.org/downloads/
- **OpenCV Docs**: https://docs.opencv.org/
- **Wireshark**: https://www.wireshark.org/

## Notes

⚠️ **Flight controls are experimental** - actual commands require reverse engineering native libraries

✅ **Video and camera controls work** - based on successful reverse engineering

📝 **Document your findings** - help improve the project!

---

**Need more help?** See [README.md](README.md) for detailed instructions.
