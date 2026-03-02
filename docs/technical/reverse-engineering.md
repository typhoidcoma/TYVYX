# Reverse Engineering Notes

These notes cover the E88Pro (lxPro) protocol family reverse engineering from the Android app `com.cooingdv.kyufo`. For K417 protocol details, see [protocol-specification.md](protocol-specification.md).

## E88Pro Network

- SSID: `HD-720P-*`, `HD-FPV-*`, `HD720-*`, `FHD-*`
- Drone IP: `192.168.1.1`
- Control: UDP port 7099
- Video: UDP port 7070
- HTTP: port 80, FTP: port 21 (user: `ftp`, pass: `ftp`)

## Video Protocol

The drone does **not** use RTSP. It uses a proprietary UDP protocol that sends JPEG frame fragments after receiving a start command.

- Start command: `[0x08, 0x01]` via UDP to port 7099 (resend every 2s)
- Video reception: port 7070, S2X-style (8-byte header with `0x40 0x40` sync bytes)
- Reassemble fragments by frame ID and slice ID
- Validate using JPEG SOI (`0xFF 0xD8`) / EOI (`0xFF 0xD9`) markers

## UDP Commands

| Command | Bytes | Purpose |
|---------|-------|---------|
| Heartbeat | `01 01` | Keep-alive, every 1s |
| Initialize | `64` | Activate drone after connection |
| Camera front | `06 01` | Switch to front camera |
| Camera rear | `06 02` | Switch to rear camera |
| Screen mode 1 | `09 01` | Display mode toggle |
| Screen mode 2 | `09 02` | Display mode toggle |
| Unknown | `63` | Purpose unclear |

## Response Format

- Byte 0: device type (2 = GL, 10 = TC, 0 = unknown)
- Byte 1: camera switch reset state
- Byte 2: screen switch state (1 or 2)

## Device Types

Auto-detected from first UDP response byte:
- **GL (2)**: OpenGL-based, uses `libgl_jni.so`
- **TC (10)**: Texture-based, uses `libtc_jni.so`

## Key Java Classes (from APK)

- `com.cooingdv.kyufo.socket.UdpClient` - UDP command handling
- `com.cooingdv.kyufo.socket.UdpComm` - Low-level UDP socket
- `com.cooingdv.kyufo.socket.SocketClient` - Video stream management
- `com.cooingdv.bl60xmjpeg.UAV` - High-level drone control, device type routing

## Native JNI Interface

The app uses native libraries for flight control:
- `nativeSendCommand(byte[])` - Send control commands
- `nativeSetCameraIndex(int)` - Switch camera
- `nativeSetQPara(int, int, int, int)` - Quality parameters

Flight control commands are handled entirely in native code and are not visible in the decompiled Java.

## File Access

FTP directory structure:
```
/0/
  PHOTO/T/   (thumbnails)
  PHOTO/O/   (full resolution)
  DCIM/      (videos)
```
