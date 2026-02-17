# TYVYX Drone Reverse Engineering Notes

## Overview
This document contains the reverse engineering findings from the Android app for the TYVYX WiFi drone.

## Network Configuration

### WiFi Connection
- **SSID Pattern**: `HD-720P-|HD-FPV-|HD720-|FHD-`
- **Drone IP Address**: `192.168.1.1`
- **UDP Control Port**: `7099`
- **TCP Server Port**: `5000`
- **UDP Video Port**: `7070`

## Video Stream

### Video Protocol
The drone does **not** use RTSP. It uses a proprietary UDP protocol that sends
JPEG frame fragments after receiving a start command.

- **Start Command**: `[0x08, 0x01]` sent via UDP to port 7099
- **Video Port**: 7070 (UDP, JPEG fragments)
- **Protocol**: S2X-style (8-byte header with `0x40 0x40` sync bytes)
- Original Android app uses IJKPlayer library for decoding
- Supports 480p, 720p resolutions

### HTTP Endpoints
- **DCIM Video Thumbnails**: `http://192.168.1.1/DCIM/[filename]`
- **Recorded Videos**: Available via HTTP/FTP (not streamed)
- **Photo Thumbnails**: `http://192.168.1.1/PHOTO/T/[filename]`
- **Full Photos**: `http://192.168.1.1/PHOTO/O/[filename]`

## UDP Communication Protocol

### Control Communication
- **IP**: `192.168.1.1`
- **Port**: `7099`
- **Protocol**: UDP (User Datagram Protocol)

### Command Format
Commands are sent as byte arrays via UDP.

#### Heartbeat Command
```java
new byte[]{1, 1}  // Sent every 1000ms to maintain connection
```

#### Camera Switch Commands
```java
new byte[]{6, 1}  // Switch to camera 1
new byte[]{6, 2}  // Switch to camera 2
```

#### Screen Switch Commands
```java
new byte[]{9, 1}  // Screen mode 1
new byte[]{9, 2}  // Screen mode 2
```

#### Special Commands (from UAV.java)
```java
new byte[]{100}   // Initialize/activate drone
new byte[]{99}    // Special command (exact function unclear)
```

### Response Format
The drone sends UDP responses back containing:
- **Byte 0**: Device type and resolution information
  - Used to identify if device is GL type (2) or TC type (10)
  - Contains resolution flags
- **Byte 1**: Camera switch reset state
- **Byte 2**: Screen switch state (1 or 2)

## Device Types

### Type Identification
- **GL (OpenGL Type)**: Device Type = 2
- **TC (Texture Type)**: Device Type = 10
- **Unknown**: Device Type = 0

The device type is auto-detected based on the first UDP response from the drone.

## Control Flow

### Initialization Sequence
1. Connect to drone WiFi network
2. Start UDP communication on port 7099
3. Send heartbeat `{1, 1}` every 1 second
4. Wait for response to identify device type
5. Send initialization command `{100}`
6. Send video start command `[0x08, 0x01]` and begin UDP video reception on port 7070

### Native Commands (via JNI)
The app uses native libraries (GLJni and TCJni) for:
- `nativeSendCommand(byte[])` - Send control commands
- `nativeSetCameraIndex(int)` - Switch active camera
- `nativeSetQPara(int, int, int, int)` - Set quality parameters
- Video processing and decoding

## Key Components

### SocketClient
- Manages video stream connection
- Handles video view initialization
- Path: `com.cooingdv.kyufo.socket.SocketClient`

### UdpClient
- Manages UDP communication
- Sends heartbeat packets
- Handles command transmission
- Path: `com.cooingdv.kyufo.socket.UdpClient`

### UdpComm
- Low-level UDP socket communication
- Send/receive threads
- Path: `com.cooingdv.kyufo.socket.UdpComm`

### UAV
- High-level drone control interface
- Device type management
- Command routing to native libraries
- Path: `com.cooingdv.bl60xmjpeg.UAV`

## Python Implementation Notes

### Required Libraries
- **OpenCV**: For video stream capture and processing
- **socket**: For UDP communication
- **threading**: For concurrent heartbeat and video processing

### Implementation Strategy
1. **UDP Control**:
   - Create UDP socket to `192.168.1.1:7099`
   - Send heartbeat every 1 second
   - Send control commands as needed

2. **Video Stream**:
   - Use UDP protocol adapters (`tyvyx/protocols/`) for video reception
   - Receive JPEG fragments and reassemble into complete frames
   - Process frames for display and analysis

3. **Control Interface**:
   - Keyboard input for testing
   - Joystick/gamepad support
   - GUI with OpenCV windows or web interface

## Unknown/To Be Determined

### Flight Control Commands
The native JNI libraries handle the actual flight control commands (throttle, yaw, pitch, roll).
These commands are not visible in the decompiled Java code and would require:
- Reverse engineering the native `.so` libraries
- Packet sniffing during actual flight operations
- Trial and error with different byte patterns

### Possible Command Structure (Speculation)
Based on common drone protocols, flight commands likely follow this pattern:
```
[CMD_ID, THROTTLE, YAW, PITCH, ROLL, CHECKSUM]
```
Where each value is typically 0-255 with 128 being center/neutral.

## Security Notes
- No authentication or encryption observed
- WiFi connection is open or WPA2-PSK
- UDP packets are unencrypted
- Easy to spoof commands if on same network

## File Structure
- FTP Server: `192.168.1.1` (user: ftp, pass: ftp)
- Photo directory: `/PHOTO/`
- Video directory: `/DCIM/`
- Root FTP directory: `/0/`
