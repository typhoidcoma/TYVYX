"""JPEG header generator for WiFi UAV drones.

These drones strip the JPEG SOI/DQT/SOF0/SOS headers from their video stream
to save bandwidth.  The client must prepend this header to the reassembled
JPEG scan data and append the EOI marker.

Ported from turbodrone (utils/wifi_uav_jpeg.py).
"""

from typing import List

# Start / End Of Image markers
SOI = bytearray(b"\xff\xd8")
EOI = bytearray(b"\xff\xd9")

# fmt: off
# Standard luminance quantization table (zigzag order)
std_luminance_qt = [
     16, 11, 10, 16, 24,  40,  51,  61,
     12, 12, 14, 19, 26,  58,  60,  55,
     14, 13, 16, 24, 40,  57,  69,  56,
     14, 17, 22, 29, 51,  87,  80,  62,
     18, 22, 37, 56, 68, 109, 103,  77,
     24, 35, 55, 64, 81, 104, 113,  92,
     49, 64, 78, 87,103, 121, 120, 101,
     72, 92, 95, 98,112, 100, 103,  99
]

# Standard chrominance quantization table
std_chrominance_qt = [
    17, 18, 24, 47, 99,  99,  99,  99,
    18, 21, 26, 66, 99,  99,  99,  99,
    24, 26, 56, 99, 99,  99,  99,  99,
    47, 66, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99,
    99, 99, 99, 99, 99,  99,  99,  99
]
# fmt: on


def _generate_dqt_segment(table_id: int, table: List[int], precision: int = 0) -> bytes:
    """Generate a DQT (Define Quantization Table) segment."""
    segment = bytearray(b"\xff\xdb")
    payload = bytearray()
    payload.append((precision << 4) | table_id)

    if precision == 0:
        payload.extend(table)
    else:
        for val in table:
            payload.extend(val.to_bytes(2, "big"))

    length = len(payload) + 2
    segment.extend(length.to_bytes(2, "big"))
    segment.extend(payload)
    return bytes(segment)


def _generate_sof0_segment(width: int, height: int, num_components: int = 3) -> bytes:
    """Generate a SOF0 (Start of Frame, Baseline DCT) segment.  4:4:4 subsampling."""
    marker = b"\xff\xc0"
    precision = b"\x08"
    height_bytes = height.to_bytes(2, "big")
    width_bytes = width.to_bytes(2, "big")

    if num_components == 1:
        component_info = [{"id": 1, "sampling": (1, 1), "qt_id": 0}]
    else:
        component_info = [
            {"id": 1, "sampling": (1, 1), "qt_id": 0},  # Y
            {"id": 2, "sampling": (1, 1), "qt_id": 1},  # Cb
            {"id": 3, "sampling": (1, 1), "qt_id": 1},  # Cr
        ]

    specs = b""
    for comp in component_info:
        H, V = comp["sampling"]
        specs += comp["id"].to_bytes(1, "big")
        specs += ((H << 4) | V).to_bytes(1, "big")
        specs += comp["qt_id"].to_bytes(1, "big")

    length = (8 + 3 * num_components).to_bytes(2, "big")
    return (
        marker + length + precision + height_bytes + width_bytes
        + num_components.to_bytes(1, "big") + specs
    )


def _generate_sos_segment(num_components: int) -> bytes:
    """Generate the SOS (Start of Scan) segment."""
    if num_components == 1:
        selectors = [{"id": 1, "dc": 0, "ac": 0}]
    else:
        selectors = [
            {"id": 1, "dc": 0, "ac": 0},
            {"id": 2, "dc": 1, "ac": 1},
            {"id": 3, "dc": 1, "ac": 1},
        ]

    segment = bytearray(b"\xff\xda")
    length = 6 + 2 * num_components
    segment += length.to_bytes(2, "big")
    segment.append(num_components)

    for comp in selectors:
        segment.append(comp["id"])
        segment.append((comp["dc"] << 4) | comp["ac"])

    segment.append(0)   # Ss
    segment.append(63)  # Se
    segment.append(0)   # AhAl
    return bytes(segment)


def generate_jpeg_headers(width: int, height: int, num_components: int = 3) -> bytes:
    """Generate a minimal JPEG header (SOI + DQT + SOF0 + SOS) for the given resolution.

    Note: this does NOT include DHT (Huffman) tables.  Some decoders can
    fall back to default Huffman tables, but libjpeg-turbo (used by OpenCV)
    requires explicit DHT.  Use ``generate_jpeg_headers_full`` when the
    drone strips ALL headers including Huffman tables.
    """
    header = bytearray()
    header += SOI
    header += _generate_dqt_segment(0, std_luminance_qt)
    if num_components == 3:
        header += _generate_dqt_segment(1, std_chrominance_qt)
    header += _generate_sof0_segment(width, height, num_components)
    header += _generate_sos_segment(num_components)
    return bytes(header)


# ─── Standard Huffman tables (JPEG spec Tables K.3–K.6) ─── #

# fmt: off
# DC Luminance (Table K.3)
_DC_LUM_BITS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
_DC_LUM_VALS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

# DC Chrominance (Table K.4)
_DC_CHR_BITS = [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
_DC_CHR_VALS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

# AC Luminance (Table K.5)
_AC_LUM_BITS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7d]
_AC_LUM_VALS = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
    0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08,
    0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0a, 0x16,
    0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
    0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
    0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7,
    0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6,
    0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5,
    0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4,
    0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2,
    0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea,
    0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8,
    0xf9, 0xfa,
]

# AC Chrominance (Table K.6)
_AC_CHR_BITS = [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77]
_AC_CHR_VALS = [
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21,
    0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71,
    0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91,
    0xa1, 0xb1, 0xc1, 0x09, 0x23, 0x33, 0x52, 0xf0,
    0x15, 0x62, 0x72, 0xd1, 0x0a, 0x16, 0x24, 0x34,
    0xe1, 0x25, 0xf1, 0x17, 0x18, 0x19, 0x1a, 0x26,
    0x27, 0x28, 0x29, 0x2a, 0x35, 0x36, 0x37, 0x38,
    0x39, 0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48,
    0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58,
    0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68,
    0x69, 0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78,
    0x79, 0x7a, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8a, 0x92, 0x93, 0x94, 0x95, 0x96,
    0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5,
    0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4,
    0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3,
    0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2,
    0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda,
    0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9,
    0xea, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8,
    0xf9, 0xfa,
]
# fmt: on


def _generate_dht_segment(table_class: int, table_id: int,
                           bits: List[int], values: List[int]) -> bytes:
    """Generate a DHT (Define Huffman Table) segment.

    table_class: 0 = DC, 1 = AC
    table_id:    0 = luminance, 1 = chrominance
    """
    segment = bytearray(b"\xff\xc4")
    payload = bytearray()
    payload.append((table_class << 4) | table_id)
    payload.extend(bits)
    payload.extend(values)
    length = len(payload) + 2
    segment.extend(length.to_bytes(2, "big"))
    segment.extend(payload)
    return bytes(segment)


def _generate_all_dht() -> bytes:
    """Generate all four standard DHT segments (DC lum, DC chr, AC lum, AC chr)."""
    dht = bytearray()
    dht += _generate_dht_segment(0, 0, _DC_LUM_BITS, _DC_LUM_VALS)
    dht += _generate_dht_segment(0, 1, _DC_CHR_BITS, _DC_CHR_VALS)
    dht += _generate_dht_segment(1, 0, _AC_LUM_BITS, _AC_LUM_VALS)
    dht += _generate_dht_segment(1, 1, _AC_CHR_BITS, _AC_CHR_VALS)
    return bytes(dht)


def generate_jpeg_headers_full(width: int, height: int, num_components: int = 3) -> bytes:
    """Generate a complete JPEG header including Huffman tables.

    SOI + DQT + DHT (all 4 tables) + SOF0 + SOS

    Required for drones that strip ALL JPEG headers from the stream
    (the 0x93 push-based protocol).  libjpeg-turbo / OpenCV will fail
    without explicit DHT tables.
    """
    header = bytearray()
    header += SOI
    header += _generate_dqt_segment(0, std_luminance_qt)
    if num_components == 3:
        header += _generate_dqt_segment(1, std_chrominance_qt)
    header += _generate_all_dht()
    header += _generate_sof0_segment(width, height, num_components)
    header += _generate_sos_segment(num_components)
    return bytes(header)
