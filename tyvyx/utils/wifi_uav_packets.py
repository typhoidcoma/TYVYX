"""Static packet templates for the WiFi UAV protocol family.

Ported from turbodrone (utils/wifi_uav_packets.py).
"""

# Sent once to kick off the video stream.
START_STREAM = b"\xef\x00\x04\x00"

# Camera switching (ef 01 wrapper around E88Pro-style 06 XX command)
CAMERA_FRONT = b"\xef\x01\x02\x00\x06\x01"   # Camera 1 (front)
CAMERA_BOTTOM = b"\xef\x01\x02\x00\x06\x02"   # Camera 2 (bottom)

# Both REQUEST_A and REQUEST_B must be sent for each frame.
# The drone will not send the next frame without receiving both.
# Frame-ID bytes are patched at the offsets listed in the video protocol.
REQUEST_A = (
    b"\xef\x02\x58\x00\x02\x02"
    b"\x00\x01\x00\x00\x00\x00\x05\x00\x00\x00\x14\x00\x66\x14\x80\x80"
    b"\x80\x80\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x99"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x32\x4b\x14\x2d"
    b"\x00\x00"
)

REQUEST_B = (
    b"\xef\x02\x6c\x00\x02\x02"
    b"\x00\x01\x02\x00\x00\x00\x09\x00\x00\x00\x14\x00\x66\x14\x80\x80"
    b"\x80\x80\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x99"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x32\x4b\x14\x2d"
    b"\x00\x00\x08\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x14\x00"
    b"\x00\x00\xff\xff\xff\xff\x09\x00\x00\x00\x00\x00\x00\x00\x03\x00"
    b"\x00\x00\x10\x00\x00\x00"
)

# RC control packet header and static components.
# The full packet is ~120 bytes with rolling 16-bit counters.
RC_HEADER = bytes([
    0xef, 0x02, 0x7c, 0x00, 0x02, 0x02,
    0x00, 0x01, 0x02, 0x00, 0x00, 0x00,
])

RC_COUNTER1_SUFFIX = bytes([0x00, 0x00, 0x14, 0x00, 0x66, 0x14])
RC_CONTROL_SUFFIX = bytes(10)  # 10 x 0x00

RC_CHECKSUM_SUFFIX = (
    bytes([0x99]) + bytes(44)
    + bytes([0x32, 0x4b, 0x14, 0x2d, 0x00, 0x00])
)

RC_COUNTER2_SUFFIX = bytes([
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00,
    0x00, 0x00, 0x14, 0x00, 0x00, 0x00,
    0xff, 0xff, 0xff, 0xff,
])

RC_COUNTER3_SUFFIX = bytes([
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x03, 0x00, 0x00, 0x00, 0x10, 0x00,
    0x00, 0x00,
])
