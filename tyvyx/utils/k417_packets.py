"""K417 protocol packet builders — 20-byte RC format matching REQUEST templates.

All packet formats reverse-engineered from YN Fly Android app traffic
and validated against turbodrone's implementation (I:\\Projects\\turbodrone).

Protocol summary:
  - All traffic: UDP from ONE source port -> drone port 8800
  - RC packets (ef 02): 88-byte with 20-byte gn.e() RC sub-packet
  - Counter at bytes [12:13]: LE uint16 frame_id (matches REQUEST templates)
  - RC sub-packet: 66 14 R P T Y cmd headless 00*10 XOR 99
  - Center stick value: 0x80 (128)
  - Normal: cmd=0, headless=2
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


def build_rc_88b(counter, roll=128, pitch=128, throttle=128, yaw=128,
                 cmd=0, headless=2, rc_present=True):
    # type: (int, int, int, int, int, int, int, bool) -> bytes
    """Build 88-byte RC packet (ef 02 58 00) with 20-byte gn.e() RC format.

    Matches the REQUEST_A template structure from turbodrone.  The 20-byte
    RC sub-packet layout is:

      [18]    0x66 RC marker
      [19]    0x14 inner length (= 20)
      [20-23] roll, pitch, throttle, yaw
      [24]    cmd (0x00=none, 0x01=takeoff, 0x02=land, 0x04=calibrate)
      [25]    headless (0x02=normal, 0x03=headless)
      [26-35] 10 zeros (padding)
      [36]    XOR checksum of bytes [20:36]
      [37]    0x99 end marker
    """
    buf = bytearray(88)

    # Header
    buf[0] = 0xef
    buf[1] = 0x02
    struct.pack_into("<H", buf, 2, 88)    # length = 88
    buf[4] = 0x02
    buf[5] = 0x02
    buf[6] = 0x00
    buf[7] = 0x01
    buf[8] = 0x00                          # format flag = short

    # Counter as u16 at [12:13] (matches turbodrone REQUEST format)
    struct.pack_into("<H", buf, 12, counter & 0xFFFF)

    # 20-byte RC sub-packet
    if rc_present:
        struct.pack_into("<H", buf, 16, 0x0014)  # rc_len = 20

        buf[18] = 0x66  # RC marker
        buf[19] = 0x14  # inner length = 20

        r = roll & 0xFF
        p = pitch & 0xFF
        t = throttle & 0xFF
        y = yaw & 0xFF
        c = cmd & 0xFF
        h = headless & 0xFF

        buf[20] = r
        buf[21] = p
        buf[22] = t
        buf[23] = y
        buf[24] = c
        buf[25] = h
        # [26:36] = 10 zeros (already zero)

        # XOR checksum covers bytes [20:36]
        xor = 0
        for i in range(20, 36):
            xor ^= buf[i]
        buf[36] = xor
        buf[37] = 0x99  # end marker

    # Quality magic at [80:84]
    buf[80] = 0x32
    buf[81] = 0x4b
    buf[82] = 0x14
    buf[83] = 0x2d

    return bytes(buf)
