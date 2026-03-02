# Protocol Specification

Two protocol families are supported, auto-detected via SSID, port probe, and IP subnet:

1. **K417 / WiFi UAV** (BL618 chipset) - Primary, 21fps pull-based video
2. **E88Pro / lxPro** (JieLi chipset) - Legacy, S2x video

## K417 WiFi UAV Protocol

### Network

| Parameter | Value |
|-----------|-------|
| SSID Pattern | `Drone-xxxxxx`, `FLOW_xxxxxx`, `K417-*` |
| Drone IP | `192.168.169.1` (gateway) |
| Port | `8800` (video AND control - single port) |
| Port 8801 | Does NOT exist (ICMP unreachable) |
| MAC OUI | `7C:3E:82` (Samsung) |
| Chipset | Bouffalo Lab BL618 (RISC-V) |
| App | YN Fly (com.lcfld.ynfly) |

### Video Protocol (0x93 Push-Based JPEG Fragments)

The drone pushes JPEG fragments as UDP packets with `0x93 0x01` magic header.

#### Packet Format (56-byte header + payload)

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| 0-1 | 2 | Magic | `0x93 0x01` (always) |
| 2-3 | 2 | packet_length | LE uint16 |
| 16-17 | 2 | frame_id | LE uint16, increments with pull-based |
| 32-33 | 2 | fragment_id | LE uint16, 0-based |
| 36-37 | 2 | fragment_total | LE uint16, typically 9-31 |
| 44-45 | 2 | width | LE uint16, 640 |
| 46-47 | 2 | height | LE uint16, 360 |
| 48 | 1 | quality/fps | 0x32 (50) |
| 56+ | var | JPEG payload | Fragment data |

#### JPEG Reassembly

The drone sends raw JPEG scan data without headers. The client must prepend `SOI + DQT + DHT + SOF0 + SOS` and append `EOI`.

- Resolution: 640x360, YCbCr 4:4:4
- DHT (Huffman tables) required - drone omits them
- See `tyvyx/utils/wifi_uav_jpeg.py` for header generation

#### Frame Request Protocol (Pull-Based, 21fps)

After each complete frame, send REQUEST_A (88B) + REQUEST_B (124B) pair:

**REQUEST_A** (88 bytes):
```
ef 02 58 00 02 02 00 01 00 ...
Byte 8 = 0x00 (short format)
Bytes [12:13] = frame_id (LE uint16, patched per-frame)
Bytes [16:17] = 0x14 0x00 (rc_len = 20)
Bytes [18:37] = 20-byte RC sub-packet (gn.e() format)
```

**REQUEST_B** (124 bytes):
```
ef 02 7c 00 02 02 00 01 02 ...
Byte 8 = 0x02 (long format)
Bytes [12:13] = frame_id (patched)
Bytes [88:89] = frame_id (patched)
Bytes [107:108] = frame_id (patched)
```

The pair serves as both **frame ACK** (advances sliding window) and **next-frame request**.

#### Startup Sequence

1. Send `ef 00 04 00` (START_STREAM) - one-time
2. Send REQUEST_A(0) + REQUEST_B(0) - request first frame
3. Warmup: repeat steps 1-2 every 200ms until first frame arrives
4. After first frame: stop warmup, let REQUEST pairs and watchdog drive video

#### Watchdog

- 80ms timeout per frame
- 3 retries before giving up on current frame
- ~44 retries per 1100 frames (rarely fires)
- 30s stall timeout kills video entirely

#### RC Control (20-byte gn.e() format)

RC is embedded in the 88B REQUEST_A packet at bytes [18:37]:

| Offset | Field | Value |
|--------|-------|-------|
| 18 | Marker | `0x66` |
| 19 | Length | `0x14` (20) |
| 20 | Roll | 0-255 (128 = center) |
| 21 | Pitch | 0-255 (128 = center) |
| 22 | Throttle | 0-255 (128 = center) |
| 23 | Yaw | 0-255 (128 = center) |
| 24 | Command | 0x00=none, 0x01=takeoff, 0x02=land, 0x04=calibrate |
| 25 | Headless | 0x02=normal, 0x03=headless |
| 26-35 | Padding | 10 zeros |
| 36 | Checksum | XOR of bytes [20:36] |
| 37 | End marker | `0x99` |

RC is burst 1 per frame (frame-synced). Continuous RC at >10Hz kills video.

#### Other Commands

| Command | Hex | Description |
|---------|-----|-------------|
| START_STREAM | `ef 00 04 00` | Start video stream |
| CAMERA_FRONT | `ef 01 02 00 06 01` | Switch to front camera |
| CAMERA_BOTTOM | `ef 01 02 00 06 02` | Switch to bottom camera |
| INIT_CMD | `ef 20 06 00 01 65` | AT-config init |

#### Critical Constraints

- **Single port**: ALL UDP traffic must come from ONE source port to port 8800
- **Sustained ef 02 kills video**: Continuous RC at >10Hz kills the video stream. Frame-synced burst (1 per frame) works.
- **No port 8801**: SDK references it but it doesn't exist on K417
- **Drone video source port**: 1234 (not 8800)

## E88Pro Legacy Protocol

### Network

| Parameter | Value |
|-----------|-------|
| SSID Pattern | `HD-720P-*`, `HD-FPV-*`, `HD720-*`, `FHD-*` |
| Drone IP | `192.168.1.1` |
| Control Port | 7099 (UDP) |
| Video Port | 7070 (UDP, JPEG fragments) |
| HTTP | Port 80 (file access) |
| FTP | Port 21 (user: `ftp`, pass: `ftp`) |

### Commands

| Command | Bytes | Purpose |
|---------|-------|---------|
| Heartbeat | `01 01` | Keep-alive, every 1s |
| Initialize | `64` | Activate drone |
| Video start | `08 01` | Begin video stream |
| Camera front | `06 01` | Switch to front camera |
| Camera rear | `06 02` | Switch to rear camera |
| Screen mode 1 | `09 01` | Toggle screen mode |
| Screen mode 2 | `09 02` | Toggle screen mode |

### Video Reception

1. Send `[0x08, 0x01]` to port 7099
2. Resend every 2s as keep-alive
3. Listen on port 7070
4. Parse S2X-style headers (8-byte header with `0x40 0x40` sync bytes)
5. Reassemble JPEG fragments by frame ID and slice ID

### Flight Control (Experimental)

```
[CMD_ID, THROTTLE, YAW, PITCH, ROLL, CHECKSUM]
CMD_ID = 0x50, values 0-255, neutral = 128
```

This format is experimental for E88Pro. K417 uses the 20-byte gn.e() format documented above.

### Device Types

| Type | Value | Library |
|------|-------|---------|
| GL (OpenGL) | 2 | `libgl_jni.so` |
| TC (Texture) | 10 | `libtc_jni.so` |

### File Access

HTTP endpoints on port 80:
- Videos: `http://192.168.1.1/DCIM/[filename]`
- Photo thumbnails: `http://192.168.1.1/PHOTO/T/[filename]`
- Full photos: `http://192.168.1.1/PHOTO/O/[filename]`

FTP: `ftp://ftp:ftp@192.168.1.1/0/`

## Protocol Detection

Three-tier detection (in `drone_service.py`):

1. **Port probe** (ground truth): 8800 responds = WiFi UAV, 7099 responds = E88Pro
2. **SSID matching**: `FLOW_` (underscore) = WiFi UAV, `FLOW-` (dash) = E88Pro
3. **IP fallback**: 192.168.169.x = WiFi UAV, else E88Pro

**Critical**: `FLOW_` (underscore) and `FLOW-` (dash) are different protocols.

## References

- K417 APK: YN Fly (com.lcfld.ynfly), native lib `libuav_lib.so` (unstripped, Ghidra-friendly)
- E88Pro APK: com.cooingdv.kyufo, native libs `libgl_jni.so`, `libtc_jni.so`
- Reverse engineering notes: [reverse-engineering.md](reverse-engineering.md)
