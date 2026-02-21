"""K417 protocol packet builders — byte-exact match to Wireshark capture.

All packet formats reverse-engineered from YN Fly Android app traffic
captured via Wireshark (Feb 2026).  Every builder produces bytes that
match the capture frame-for-frame.

Protocol summary:
  - All traffic: UDP from ONE source port → drone port 8800
  - RC packets (ef 02): two sizes alternate at ~40Hz
      88-byte  "short" (format flag 0x00)
      124-byte "long"  (format flag 0x02, extra 36-byte tail)
  - Both carry: LE uint32 video frame ACK counter at bytes [12:16]
  - RC sub-packet: 8-byte gn.d() format  66 R P T Y F XOR 99
  - Center stick value: 0x80 (128)
  - Normal flags: 0x40
"""

import struct

# ── Command constants ──

START_STREAM = b"\xef\x00\x04\x00"
CAMERA_FRONT = b"\xef\x01\x02\x00\x06\x01"
CAMERA_BOTTOM = b"\xef\x01\x02\x00\x06\x02"

# ── Init / config commands (from YN Fly startup sequence) ──

INIT_CMD = b"\xef\x20\x06\x00\x01\x65"


def build_config_cmd(cmd_num):
    # type: (int) -> bytes
    """Build ef 20 AT-config command: ef 20 19 00 01 67 <i=2^bf_ssid=cmd=N>"""
    payload = "<i=2^bf_ssid=cmd={}>".format(cmd_num).encode("ascii")
    header = b"\xef\x20\x19\x00\x01\x67"
    return header + payload


# Pre-built config commands (sent during handshake)
CONFIG_CMD_2 = build_config_cmd(2)
CONFIG_CMD_3 = build_config_cmd(3)

# ── Quality/threshold constants at bytes [80:84] ──

_QUALITY_MAGIC = b"\x32\x4b\x14\x2d"  # quality1=50, quality2=75, q_thresh1=20, q_thresh2=45


def _build_rc_common(counter, roll, pitch, throttle, yaw, flags, rc_present):
    # type: (int, int, int, int, int, int, bool) -> bytearray
    """Build the first 88 bytes shared by both 88B and 124B formats.

    Layout (from Wireshark capture):
      [0]     0xef magic
      [1]     0x02 type
      [2-3]   LE uint16 total packet length (filled by caller)
      [4-7]   0x02 0x02 0x00 0x01 (version)
      [8]     format flag (filled by caller: 0x00=short, 0x02=long)
      [9-11]  zeros
      [12-15] LE uint32 counter (video frame ACK)
      [16-17] LE uint16 RC data length (0x0008 or 0x0000)
      [18]    0x66 RC marker
      [19-22] roll, pitch, throttle, yaw
      [23]    flags
      [24]    XOR checksum of bytes [19:24]
      [25]    0x99 end marker
      [26-79] zeros
      [80-83] quality magic 0x32 0x4b 0x14 0x2d
      [84-87] zeros
    """
    buf = bytearray(88)

    # Header
    buf[0] = 0xef
    buf[1] = 0x02
    # [2-3] length — filled by caller
    buf[4] = 0x02
    buf[5] = 0x02
    buf[6] = 0x00
    buf[7] = 0x01
    # [8] format flag — filled by caller
    # [9-11] zeros (already zero)

    # Counter (LE uint32)
    struct.pack_into("<I", buf, 12, counter & 0xFFFFFFFF)

    # RC sub-packet
    if rc_present:
        struct.pack_into("<H", buf, 16, 0x0008)  # rc_len = 8

        buf[18] = 0x66  # RC marker

        r = roll & 0xFF
        p = pitch & 0xFF
        t = throttle & 0xFF
        y = yaw & 0xFF
        f = flags & 0xFF

        buf[19] = r
        buf[20] = p
        buf[21] = t
        buf[22] = y
        buf[23] = f
        buf[24] = r ^ p ^ t ^ y ^ f  # XOR checksum
        buf[25] = 0x99  # end marker
    # else: rc_len=0, bytes [18:26] stay zero

    # [26-79] zeros (already zero)

    # Quality magic at [80:84]
    buf[80] = 0x32
    buf[81] = 0x4b
    buf[82] = 0x14
    buf[83] = 0x2d
    # [84-87] zeros (already zero)

    return buf


def build_rc_88b(counter, roll=128, pitch=128, throttle=128, yaw=128,
                 flags=0x40, rc_present=True):
    # type: (int, int, int, int, int, int, bool) -> bytes
    """Build 88-byte RC packet (ef 02 58 00).

    Format flag = 0x00 (short format, no tail).
    """
    buf = _build_rc_common(counter, roll, pitch, throttle, yaw, flags, rc_present)

    # Length = 88 (0x0058)
    struct.pack_into("<H", buf, 2, 88)
    # Format flag = 0x00 (short)
    buf[8] = 0x00

    return bytes(buf)


def build_rc_124b(counter, tail_counter, roll=128, pitch=128, throttle=128,
                  yaw=128, flags=0x40, rc_present=True):
    # type: (int, int, int, int, int, int, int, bool) -> bytes
    """Build 124-byte RC packet (ef 02 7c 00).

    Format flag = 0x02 (long format), plus 36-byte tail.

    Tail layout (from Wireshark capture, bytes [88:124]):
      [88-91]   LE uint32 tail_counter
      [92-95]   zeros
      [96-99]   0x01 0x00 0x00 0x00
      [100-103] 0x14 0x00 0x00 0x00  (= 20)
      [104-107] 0xff 0xff 0xff 0xff
      [108-111] LE uint32 tail_counter2
      [112-115] zeros
      [116-119] 0x03 0x00 0x00 0x00
      [120-123] 0x10 0x00 0x00 0x00  (= 16)
    """
    buf = _build_rc_common(counter, roll, pitch, throttle, yaw, flags, rc_present)

    # Length = 124 (0x007c)
    struct.pack_into("<H", buf, 2, 124)
    # Format flag = 0x02 (long)
    buf[8] = 0x02

    # Extend to 124 bytes
    tail = bytearray(36)

    # tail_counter at tail[0:4]
    struct.pack_into("<I", tail, 0, tail_counter & 0xFFFFFFFF)
    # tail[4:8] zeros
    # tail[8:12] = 0x01 0x00 0x00 0x00
    struct.pack_into("<I", tail, 8, 1)
    # tail[12:16] = 0x14 0x00 0x00 0x00 (= 20)
    struct.pack_into("<I", tail, 12, 0x14)
    # tail[16:20] = 0xff 0xff 0xff 0xff
    struct.pack_into("<I", tail, 16, 0xFFFFFFFF)
    # tail[20:24] = tail_counter2 (same as tail_counter from capture)
    struct.pack_into("<I", tail, 20, tail_counter & 0xFFFFFFFF)
    # tail[24:28] zeros
    # tail[28:32] = 0x03 0x00 0x00 0x00
    struct.pack_into("<I", tail, 28, 3)
    # tail[32:36] = 0x10 0x00 0x00 0x00 (= 16)
    struct.pack_into("<I", tail, 32, 0x10)

    return bytes(buf) + bytes(tail)
