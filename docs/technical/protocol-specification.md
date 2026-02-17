# TYVYX Drone Protocol Specification

This document provides a formal specification of the TYVYX WiFi drone communication protocol, extracted from reverse engineering efforts.

## Table of Contents

- [Network Configuration](#network-configuration)
- [UDP Command Protocol](#udp-command-protocol)
- [Video Streaming Protocol](#video-streaming-protocol)
- [File Access Protocol](#file-access-protocol)
- [Device Types](#device-types)
- [Security Considerations](#security-considerations)

---

## Network Configuration

### WiFi Network

| Parameter | Value | Notes |
|-----------|-------|-------|
| **SSID Pattern** | `HD-720P-*`, `HD-FPV-*`, `HD720-*`, `FHD-*` | Drone creates its own WiFi access point |
| **Drone IP** | `192.168.1.1` | Fixed IP address |
| **Network Type** | 2.4 GHz WiFi | No encryption or WPA2-PSK |

### Port Configuration

| Service | Protocol | Port | Purpose |
|---------|----------|------|---------|
| **UDP Control** | UDP | 7099 | Command and control |
| **UDP Video** | UDP | 7070 | Video streaming (proprietary JPEG fragments) |
| **HTTP Server** | HTTP/TCP | 80 | File access (photos/videos) |
| **TCP Server** | TCP | 5000 | Unknown (possibly web interface) |
| **FTP Server** | FTP/TCP | 21 | File transfer (username: `ftp`, password: `ftp`) |

---

## UDP Command Protocol

### Overview

- **Destination IP**: `192.168.1.1`
- **Destination Port**: `7099`
- **Protocol**: UDP (connectionless)
- **Format**: Raw byte arrays
- **Encoding**: Binary (no text encoding)

### Command Format

Commands are sent as byte arrays with no header or trailer:

```
[BYTE_0, BYTE_1, ..., BYTE_N]
```

Variable length depending on command type.

### Known Commands

#### 1. Heartbeat Command

**Purpose**: Maintain connection with drone

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 1 | 0x01 | Command ID |
| 1 | 1 | 0x01 | Sub-command |

**Format**:
```python
[0x01, 0x01]
```

**Frequency**: Must be sent every 1000ms (1 second)

**Notes**: If heartbeat stops, drone may disconnect or enter failsafe mode.

---

#### 2. Initialize Drone Command

**Purpose**: Activate/initialize drone after connection

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 100 | 0x64 | Initialize command |

**Format**:
```python
[0x64]
```

**Usage**: Sent once after establishing UDP connection and identifying device type.

---

#### 3. Camera Switch Commands

**Purpose**: Switch between front and rear cameras

##### Camera 1 (Front)

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 6 | 0x06 | Camera command ID |
| 1 | 1 | 0x01 | Camera 1 selector |

**Format**:
```python
[0x06, 0x01]
```

##### Camera 2 (Rear)

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 6 | 0x06 | Camera command ID |
| 1 | 2 | 0x02 | Camera 2 selector |

**Format**:
```python
[0x06, 0x02]
```

---

#### 4. Screen Mode Switch Commands

**Purpose**: Toggle screen display mode

##### Screen Mode 1

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 9 | 0x09 | Screen mode command ID |
| 1 | 1 | 0x01 | Mode 1 selector |

**Format**:
```python
[0x09, 0x01]
```

##### Screen Mode 2

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 9 | 0x09 | Screen mode command ID |
| 1 | 2 | 0x02 | Mode 2 selector |

**Format**:
```python
[0x09, 0x02]
```

---

#### 5. Special Command (Unknown Function)

| Byte | Value | Hex | Description |
|------|-------|-----|-------------|
| 0 | 99 | 0x63 | Special command (function unclear) |

**Format**:
```python
[0x63]
```

**Notes**: Purpose not fully understood from reverse engineering.

---

### UDP Response Format

The drone sends UDP responses back to the client.

#### Response Structure

| Byte | Description | Example Values |
|------|-------------|----------------|
| **Byte 0** | Device type and resolution | `2` (GL type), `10` (TC type), `0` (unknown) |
| **Byte 1** | Camera switch reset state | `0` or `1` |
| **Byte 2** | Screen switch state | `1` or `2` |

**Length**: Typically 3 bytes minimum

**Usage**:
- Parse Byte 0 to determine device type (GL vs TC)
- Parse Byte 2 to verify current screen mode

---

### Flight Control Commands (Experimental)

**Status**: Not officially documented; reverse engineered

#### Hypothetical Format

Based on common drone protocols and testing:

```
[CMD_ID, THROTTLE, YAW, PITCH, ROLL, CHECKSUM]
```

| Field | Size | Range | Neutral | Description |
|-------|------|-------|---------|-------------|
| **CMD_ID** | 1 byte | 0x50 | - | Flight control command identifier |
| **THROTTLE** | 1 byte | 0-255 | 128 | Vertical velocity (up/down) |
| **YAW** | 1 byte | 0-255 | 128 | Rotation (left/right) |
| **PITCH** | 1 byte | 0-255 | 128 | Forward/backward movement |
| **ROLL** | 1 byte | 0-255 | 128 | Left/right movement |
| **CHECKSUM** | 1 byte | Varies | - | Command validation (algorithm TBD) |

**Value Mapping**:
- **0-127**: Below neutral (descend, backward, left, counter-clockwise)
- **128**: Neutral (no movement)
- **129-255**: Above neutral (ascend, forward, right, clockwise)

**Notes**:
- This format is experimental and may not match actual protocol
- Actual flight commands are in native JNI libraries (`libgl_jni.so`, `libtc_jni.so`)
- Requires packet capture during real flight for verification

---

## Video Streaming Protocol

### UDP Video Stream

| Parameter | Value |
|-----------|-------|
| **Protocol** | Proprietary UDP (JPEG fragment reassembly) |
| **Port** | 7070 |
| **Start Command** | `[0x08, 0x01]` sent via UDP to port 7099 |
| **Codec** | JPEG (sliced, reassembled client-side) |
| **Resolutions** | 480p, 720p (depending on model) |

**Note**: These drones do **not** run an RTSP server. The video start command
tells the drone to begin sending JPEG frame fragments as raw UDP packets.

### How Video Reception Works

1. Send `[0x08, 0x01]` to the drone on UDP port 7099
2. Resend every 2 seconds as a keep-alive
3. Listen for incoming UDP packets on port 7070
4. Parse proprietary headers (S2X-style: 8-byte header with `0x40 0x40` sync bytes)
5. Reassemble JPEG fragments by frame ID and slice ID
6. Validate complete frames using JPEG SOI (`0xFF 0xD8`) / EOI (`0xFF 0xD9`) markers

### Protocol Detection

Use the built-in diagnostic sniffer (`tyvyx/protocols/raw_udp_sniffer.py`)
to capture raw packets and auto-detect the protocol format for unknown drone models.

---

## File Access Protocol

### HTTP Endpoints

The drone exposes an HTTP server on port 80 for file access.

#### Video Thumbnails

```
http://192.168.1.1/DCIM/[filename]
```

**Example**: `http://192.168.1.1/DCIM/video001.mp4`

#### Photo Thumbnails

```
http://192.168.1.1/PHOTO/T/[filename]
```

**Example**: `http://192.168.1.1/PHOTO/T/photo001.jpg`

#### Full-Resolution Photos

```
http://192.168.1.1/PHOTO/O/[filename]
```

**Example**: `http://192.168.1.1/PHOTO/O/photo001.jpg`

### FTP Server

**Connection**:
- **Host**: `192.168.1.1`
- **Port**: `21` (standard FTP)
- **Username**: `ftp`
- **Password**: `ftp`

**Directory Structure**:
```
/0/                 # Root directory
├── PHOTO/          # Photos
│   ├── T/         # Thumbnails
│   └── O/         # Original (full-res)
└── DCIM/           # Videos
```

**Example (command line)**:
```bash
ftp 192.168.1.1
# Username: ftp
# Password: ftp
cd /DCIM
ls
get video001.mp4
```

---

## Device Types

The drone identifies itself via the first UDP response byte.

| Device Type | Value | Description | Native Library |
|-------------|-------|-------------|----------------|
| **GL (OpenGL)** | 2 | OpenGL-based rendering | `libgl_jni.so` |
| **TC (Texture)** | 10 | Texture-based rendering | `libtc_jni.so` |
| **Unknown** | 0 | Device type not identified | - |

### Detection Sequence

1. Send heartbeat command: `[0x01, 0x01]`
2. Wait for UDP response
3. Parse first byte to determine device type
4. Load appropriate control logic for device type

---

## Security Considerations

### Known Vulnerabilities

| Issue | Impact | Mitigation |
|-------|--------|------------|
| **No Authentication** | Anyone on WiFi can control drone | None (inherent design flaw) |
| **No Encryption** | Commands can be intercepted and read | None (UDP is plaintext) |
| **Open WiFi** | WiFi network is unprotected or uses weak WPA2-PSK | Use strong password if configurable |
| **Predictable IP** | Drone always uses 192.168.1.1 | None |
| **Command Spoofing** | Easy to send malicious commands | Implement application-level verification |
| **FTP Access** | Default credentials (`ftp`/`ftp`) provide full file access | Change credentials if possible |

### Recommendations

1. **Fly in isolated areas**: Avoid public WiFi interference
2. **Monitor for interference**: Watch for unexpected commands
3. **Implement timeouts**: Detect lost connections quickly
4. **Use official app as backup**: Keep manufacturer's app ready
5. **Be aware**: This protocol was not designed for security

---

## Communication Flow

### Initialization Sequence

```
1. User connects to drone WiFi (HD-720P-*, etc.)
2. Application opens UDP socket to 192.168.1.1:7099
3. Application sends heartbeat: [0x01, 0x01]
4. Drone responds with device type (Byte 0)
5. Application identifies device as GL (2) or TC (10)
6. Application sends initialize command: [0x64]
7. Application sends video start command: [0x08, 0x01] and begins UDP video reception
8. Heartbeat continues every 1000ms
9. Application sends control commands as needed
```

### Command Flow

```
Application                          Drone
    |                                   |
    |--- Heartbeat [0x01, 0x01] ------->|
    |<-- Device Type Response [2, 0, 1]-|
    |                                   |
    |--- Initialize [0x64] ------------->|
    |                                   |
    |--- Camera 1 [0x06, 0x01] -------->|
    |<-- Confirmation Response ----------|
    |                                   |
    |--- Heartbeat [0x01, 0x01] ------->|
    |                                   |
    (Continues every 1 second)
```

---

## Implementation Notes

### Python Example (UDP Control)

```python
import socket
import time

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
drone_address = ("192.168.1.1", 7099)

# Send heartbeat
heartbeat = bytes([0x01, 0x01])
sock.sendto(heartbeat, drone_address)

# Wait for response
sock.settimeout(2.0)
try:
    response, addr = sock.recvfrom(1024)
    device_type = response[0]
    print(f"Device type: {device_type}")
except socket.timeout:
    print("No response from drone")

# Initialize drone
init_cmd = bytes([0x64])
sock.sendto(init_cmd, drone_address)

# Switch to camera 1
camera_cmd = bytes([0x06, 0x01])
sock.sendto(camera_cmd, drone_address)

# Continue sending heartbeat every 1 second
while True:
    sock.sendto(heartbeat, drone_address)
    time.sleep(1.0)
```

### Video Stream Example (UDP Protocol)

```python
from tyvyx.protocols.s2x_video_protocol import S2xVideoProtocolAdapter

# Create protocol adapter for TEKY drone
adapter = S2xVideoProtocolAdapter(
    drone_ip="192.168.1.1",
    control_port=7099,
    video_port=7070,
)
adapter.start()

# Read assembled JPEG frames
while True:
    frame = adapter.get_frame(timeout=1.0)
    if frame:
        print(f"Frame {frame.frame_id}: {frame.size} bytes")
        # frame.data contains raw JPEG bytes

adapter.stop()
```

---

## Future Research

### Unknown/To Be Determined

1. **Flight Control Commands**: Actual byte sequences for throttle, pitch, roll, yaw
2. **Checksum Algorithm**: How to calculate checksums for flight commands
3. **Advanced Features**: Photo capture, video recording triggers, gimbal control
4. **Telemetry Data**: Battery level, altitude, GPS (if available), sensor readings
5. **Configuration Commands**: WiFi settings, video quality, flight modes
6. **Emergency Commands**: Emergency stop, return-to-home (if supported)

### Research Methods

1. **Packet Sniffing**: Use Wireshark while flying with official Android app
2. **Native Library Analysis**: Reverse engineer `.so` files with IDA Pro or Ghidra
3. **Fuzzing**: Send systematic command patterns and observe drone behavior
4. **Community Collaboration**: Share findings with other developers

---

## References

- **Source**: Reverse engineering of official Android app (`com.cooingdv.kyufo`)
- **Native Libraries**: `libgl_jni.so`, `libtc_jni.so`
- **Key Java Classes**: `UdpClient`, `SocketClient`, `UAV`, `UdpComm`
- **Video Library**: IJKPlayer (based on FFmpeg)

For detailed reverse engineering process, see [Reverse Engineering Notes](reverse-engineering.md).

---

*Last Updated: February 2026*
*Protocol Version: Unknown (reverse engineered)*
*Firmware Version: Unknown (varies by model)*
