#!/usr/bin/env python3
"""
Drone Packet Analyzer

Captures video packets from the drone and analyzes the header format,
frame boundaries, and payload encoding (H264 vs JPEG).

Usage:
    python scripts/analyze_packets.py [--drone-ip 192.168.169.1] [--bind-ip 192.168.169.2]
"""

import argparse
import ctypes
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tyvyx.utils.wifi_uav_packets import START_STREAM


def create_socket(bind_ip: str, timeout: float = 2.0) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if sys.platform == "win32":
        ret = ctypes.c_ulong(0)
        ctypes.windll.ws2_32.WSAIoctl(
            sock.fileno(), 0x9800000C,
            b"\x00\x00\x00\x00", 4, None, 0,
            ctypes.byref(ret), None, None,
        )
    sock.bind((bind_ip, 0))
    sock.settimeout(timeout)
    return sock


def auto_detect():
    try:
        from autonomous.services.network_service import find_drone_interface
        iface = find_drone_interface()
        if iface:
            return iface.gateway_ip, iface.local_ip
    except Exception:
        pass
    return None, None


def capture_packets(sock, drone_ip, count=300, duration=5.0):
    """Capture up to `count` packets within `duration` seconds."""
    packets = []
    deadline = time.monotonic() + duration

    # Send START_STREAM to kick off video
    sock.sendto(START_STREAM, (drone_ip, 8800))
    print(f"Sent START_STREAM to {drone_ip}:8800")

    while len(packets) < count and time.monotonic() < deadline:
        # Re-send START_STREAM periodically to keep stream alive
        if len(packets) % 50 == 0 and len(packets) > 0:
            sock.sendto(START_STREAM, (drone_ip, 8800))

        try:
            data, addr = sock.recvfrom(65535)
            packets.append((data, addr, time.monotonic()))
        except socket.timeout:
            # Re-send to keep stream going
            sock.sendto(START_STREAM, (drone_ip, 8800))
            continue
        except ConnectionResetError:
            continue

    return packets


def analyze_headers(packets):
    """Analyze packet headers to determine the protocol structure."""
    print(f"\n{'='*70}")
    print(f"HEADER ANALYSIS ({len(packets)} packets)")
    print(f"{'='*70}")

    if not packets:
        print("No packets to analyze!")
        return

    # Basic stats
    sizes = [len(p[0]) for p in packets]
    print(f"\n  Packet sizes: min={min(sizes)}, max={max(sizes)}, "
          f"unique={sorted(set(sizes))[:10]}")

    # Analyze which bytes are constant vs variable across all packets
    min_len = min(len(p[0]) for p in packets)
    header_len = min(min_len, 64)  # Analyze up to 64 bytes

    print(f"\n  Analyzing first {header_len} bytes across all packets:")
    print(f"  {'Offset':<8} {'Hex':<6} {'Dec':<6} {'Constant?':<12} {'Values seen'}")
    print(f"  {'-'*60}")

    for offset in range(header_len):
        values = set()
        for data, _, _ in packets:
            if offset < len(data):
                values.add(data[offset])

        val_list = sorted(values)
        is_const = len(values) == 1
        hex_val = f"0x{val_list[0]:02x}" if is_const else "varies"
        dec_val = f"{val_list[0]:3d}" if is_const else "---"

        if is_const:
            print(f"  {offset:<8} {hex_val:<6} {dec_val:<6} {'CONSTANT':<12} "
                  f"{{{', '.join(f'0x{v:02x}' for v in val_list[:10])}}}")
        else:
            vals_str = ', '.join(f'0x{v:02x}' for v in val_list[:15])
            if len(val_list) > 15:
                vals_str += f" ... ({len(val_list)} unique)"
            print(f"  {offset:<8} {hex_val:<6} {dec_val:<6} {'VARIABLE':<12} "
                  f"{{{vals_str}}}")

    # Analyze bytes 2-3 as LE length
    print(f"\n  Testing bytes 2-3 as LE length field:")
    match_count = 0
    for data, _, _ in packets[:20]:
        if len(data) >= 4:
            le_val = struct.unpack_from("<H", data, 2)[0]
            match = "MATCH" if le_val == len(data) else f"MISMATCH (expected {len(data)})"
            if le_val == len(data):
                match_count += 1
            print(f"    Bytes 2-3: 0x{data[2]:02x} 0x{data[3]:02x} = {le_val}  "
                  f"pkt_size={len(data)}  {match}")
    print(f"  Length field matches: {match_count}/{min(20, len(packets))}")


def find_frame_boundaries(packets):
    """Try to determine where frame boundaries are."""
    print(f"\n{'='*70}")
    print(f"FRAME BOUNDARY ANALYSIS")
    print(f"{'='*70}")

    if not packets:
        return

    # Group consecutive full (1080) and short packets
    groups = []
    current_group = []
    for i, (data, addr, ts) in enumerate(packets):
        current_group.append((i, len(data)))
        if len(data) < 1080:
            # Short packet = likely end of frame
            groups.append(current_group)
            current_group = []

    if current_group:
        groups.append(current_group)

    print(f"\n  Detected {len(groups)} potential frames:")
    for fi, group in enumerate(groups[:20]):
        sizes = [s for _, s in group]
        total = sum(sizes)
        n_full = sum(1 for s in sizes if s == 1080)
        last_size = sizes[-1] if sizes else 0
        print(f"    Frame {fi}: {len(group)} packets, "
              f"{n_full} full + 1x{last_size}b, total={total}b")

    # Check if any header bytes differ between "first in frame" and "middle" packets
    if len(groups) >= 2:
        print(f"\n  Comparing first-in-frame vs middle-of-frame headers:")
        first_pkts = [packets[g[0][0]][0] for g in groups if len(g) > 1]
        mid_pkts = [packets[g[1][0]][0] for g in groups if len(g) > 2]
        last_pkts = [packets[g[-1][0]][0] for g in groups]

        if first_pkts and mid_pkts:
            for offset in range(min(64, min(len(first_pkts[0]), len(mid_pkts[0])))):
                first_vals = set(p[offset] for p in first_pkts[:10] if offset < len(p))
                mid_vals = set(p[offset] for p in mid_pkts[:10] if offset < len(p))
                if first_vals != mid_vals:
                    print(f"    Offset {offset}: first={{{', '.join(f'0x{v:02x}' for v in sorted(first_vals))}}}"
                          f"  mid={{{', '.join(f'0x{v:02x}' for v in sorted(mid_vals))}}}")


def check_h264(packets):
    """Search for H264 NAL unit start codes in the payload."""
    print(f"\n{'='*70}")
    print(f"H264 DETECTION")
    print(f"{'='*70}")

    # H264 NAL start codes
    nal_4byte = b"\x00\x00\x00\x01"
    nal_3byte = b"\x00\x00\x01"

    # JPEG markers
    jpeg_soi = b"\xff\xd8"
    jpeg_eoi = b"\xff\xd9"

    # Check at various offsets in first packet of each potential frame
    all_data = b""
    for data, _, _ in packets:
        all_data += data

    # Search concatenated data
    print(f"\n  Searching {len(all_data)} bytes of concatenated data:")

    # H264 4-byte start codes
    idx = 0
    h264_locs = []
    while True:
        pos = all_data.find(nal_4byte, idx)
        if pos < 0:
            break
        h264_locs.append(pos)
        idx = pos + 1
    print(f"  H264 4-byte NAL codes (00 00 00 01): {len(h264_locs)} found")
    for loc in h264_locs[:10]:
        nal_type = all_data[loc + 4] & 0x1F if loc + 4 < len(all_data) else -1
        nal_names = {
            1: "non-IDR slice", 2: "slice A", 3: "slice B", 4: "slice C",
            5: "IDR slice", 6: "SEI", 7: "SPS", 8: "PPS", 9: "AUD",
        }
        name = nal_names.get(nal_type, f"type={nal_type}")
        print(f"    offset {loc}: NAL type {nal_type} ({name})  "
              f"next bytes: {all_data[loc+4:loc+8].hex(' ')}")

    # H264 3-byte start codes
    idx = 0
    h264_3_locs = []
    while True:
        pos = all_data.find(nal_3byte, idx)
        if pos < 0:
            break
        # Exclude 4-byte start codes (they contain 3-byte as substring)
        if pos > 0 and all_data[pos - 1] == 0:
            idx = pos + 1
            continue
        h264_3_locs.append(pos)
        idx = pos + 1
    print(f"  H264 3-byte NAL codes (00 00 01): {len(h264_3_locs)} found")

    # JPEG markers
    soi_count = all_data.count(jpeg_soi)
    eoi_count = all_data.count(jpeg_eoi)
    print(f"  JPEG SOI markers (ff d8): {soi_count}")
    print(f"  JPEG EOI markers (ff d9): {eoi_count}")

    # Now search within individual packets' payloads (after header)
    # Try different header sizes
    for hdr_size in [32, 36, 40, 48, 56]:
        h264_found = 0
        jpeg_found = 0
        for data, _, _ in packets[:50]:
            if len(data) > hdr_size:
                payload = data[hdr_size:]
                if payload[:4] == nal_4byte or payload[:3] == nal_3byte:
                    h264_found += 1
                if payload[:2] == jpeg_soi:
                    jpeg_found += 1
        if h264_found or jpeg_found:
            print(f"\n  Header size {hdr_size}: H264 at payload start={h264_found}/50, "
                  f"JPEG at payload start={jpeg_found}/50")

    # Dump first few bytes of payload at different header offsets for first packet
    first_pkt = packets[0][0]
    print(f"\n  First packet ({len(first_pkt)} bytes) — payload at various offsets:")
    for offset in [16, 20, 24, 28, 32, 36, 40, 48, 56]:
        if offset < len(first_pkt):
            chunk = first_pkt[offset:offset + 16]
            hex_str = chunk.hex(" ")
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print(f"    @{offset:3d}: {hex_str}  |{ascii_str}|")


def analyze_fragment_fields(packets):
    """Map header bytes to BL-UAVSDK's image_fragment_header fields.

    SDK structure (from libuav_lib.so reverse engineering):
      - magic_num:       identifies packet type
      - i_fragment_id:   fragment index within frame
      - i_fragment_total: total fragments in this frame
      - i_seq_fly:       frame sequence number
      - i_len:           payload length
      - i_payload:       payload start offset
    """
    print(f"\n{'='*70}")
    print(f"BL-UAVSDK FRAGMENT FIELD ANALYSIS")
    print(f"{'='*70}")

    if len(packets) < 10:
        print("  Not enough packets for analysis")
        return

    # Group packets into frames using byte 32 == 0x00 (known frame boundary)
    frames = []
    current_frame = []
    for data, addr, ts in packets:
        if len(data) < 56:
            continue
        if data[0:2] != b"\x93\x01":
            continue
        is_first = (data[32] == 0x00)
        if is_first and current_frame:
            frames.append(current_frame)
            current_frame = []
        current_frame.append(data)
    if current_frame:
        frames.append(current_frame)

    print(f"\n  Assembled {len(frames)} frames from {len(packets)} packets")

    # For each frame, show all header fields
    print(f"\n  --- Per-frame fragment analysis (first 10 frames) ---")
    for fi, frame_pkts in enumerate(frames[:10]):
        n = len(frame_pkts)
        print(f"\n  Frame {fi}: {n} fragments")
        for pi, pkt in enumerate(frame_pkts):
            # Test various 16-bit LE fields as potential fragment counters
            b2_3 = struct.unpack_from("<H", pkt, 2)[0]    # bytes 2-3
            b4_5 = struct.unpack_from("<H", pkt, 4)[0]    # bytes 4-5
            b6_7 = struct.unpack_from("<H", pkt, 6)[0]    # bytes 6-7
            b8_9 = struct.unpack_from("<H", pkt, 8)[0]    # bytes 8-9
            b10_11 = struct.unpack_from("<H", pkt, 10)[0]
            b12_13 = struct.unpack_from("<H", pkt, 12)[0]
            b14_15 = struct.unpack_from("<H", pkt, 14)[0]
            b16_17 = struct.unpack_from("<H", pkt, 16)[0]  # known: frame_id
            b32_33 = struct.unpack_from("<H", pkt, 32)[0]  # known: frag_id
            b34_35 = struct.unpack_from("<H", pkt, 34)[0]
            b36_37 = struct.unpack_from("<H", pkt, 36)[0]
            b38_39 = struct.unpack_from("<H", pkt, 38)[0]

            # Also try 32-bit LE fields
            b4_7 = struct.unpack_from("<I", pkt, 4)[0]
            b8_11 = struct.unpack_from("<I", pkt, 8)[0]

            payload_len = len(pkt) - 56

            if pi < 5 or pi == n - 1:
                print(f"    [{pi:2d}] size={len(pkt):4d}  pay={payload_len:4d}  "
                      f"b[2:4]={b2_3:5d}  b[4:6]={b4_5:5d}  b[6:8]={b6_7:5d}  "
                      f"b[8:10]={b8_9:5d}  b[10:12]={b10_11:5d}  b[12:14]={b12_13:5d}  "
                      f"b[14:16]={b14_15:5d}  b[16:18]={b16_17:5d}  b[32:34]={b32_33:5d}  "
                      f"b[34:36]={b34_35:5d}  b[36:38]={b36_37:5d}  b[38:40]={b38_39:5d}")
            elif pi == 5:
                print(f"    ... ({n - 6} more fragments) ...")

    # Heuristic: find which field correlates with fragment count
    print(f"\n  --- Candidate for fragment_total ---")
    for fi, frame_pkts in enumerate(frames[:20]):
        n = len(frame_pkts)
        first = frame_pkts[0]
        # Check various offsets in the first packet for a value == n
        candidates = []
        for off in range(2, 56, 2):
            if off + 2 <= len(first):
                val = struct.unpack_from("<H", first, off)[0]
                if val == n:
                    candidates.append(f"b[{off}:{off+2}]={val}")
        if candidates:
            print(f"  Frame {fi} ({n} frags): MATCH at {', '.join(candidates)}")
        else:
            # Also check single bytes
            for off in range(2, 56):
                if first[off] == n:
                    candidates.append(f"byte[{off}]={n}")
            if candidates:
                print(f"  Frame {fi} ({n} frags): byte MATCH at {', '.join(candidates)}")
            else:
                print(f"  Frame {fi} ({n} frags): no match found")

    # Heuristic: find which field correlates with payload length
    print(f"\n  --- Candidate for payload length field ---")
    for pkt, _, _ in packets[:10]:
        if len(pkt) < 56 or pkt[0:2] != b"\x93\x01":
            continue
        payload_len = len(pkt) - 56
        candidates = []
        for off in range(2, 56, 2):
            if off + 2 <= len(pkt):
                val = struct.unpack_from("<H", pkt, off)[0]
                if val == payload_len:
                    candidates.append(f"b[{off}:{off+2}]")
                if val == len(pkt):
                    candidates.append(f"b[{off}:{off+2}]=pkt_len")
        if candidates:
            print(f"  pkt size={len(pkt)} pay={payload_len}: {', '.join(candidates)}")

    # Full hex dump of first packet header
    print(f"\n  --- Full header hex dump (first packet of first frame) ---")
    if frames:
        pkt = frames[0][0]
        for row_start in range(0, 56, 16):
            row_end = min(row_start + 16, 56)
            hex_bytes = " ".join(f"{pkt[i]:02x}" for i in range(row_start, row_end))
            dec_bytes = " ".join(f"{pkt[i]:3d}" for i in range(row_start, row_end))
            print(f"    @{row_start:3d}: {hex_bytes}")
            print(f"          {dec_bytes}")

    # Hex dump of first packet of second frame (to compare)
    if len(frames) >= 2:
        print(f"\n  --- Full header hex dump (first packet of SECOND frame) ---")
        pkt = frames[1][0]
        for row_start in range(0, 56, 16):
            row_end = min(row_start + 16, 56)
            hex_bytes = " ".join(f"{pkt[i]:02x}" for i in range(row_start, row_end))
            print(f"    @{row_start:3d}: {hex_bytes}")


def probe_port_8801(sock, drone_ip):
    """Probe port 8801 to see if the drone responds to control commands there."""
    print(f"\n{'='*70}")
    print(f"PORT 8801 PROBE (BL-UAVSDK control port)")
    print(f"{'='*70}")

    # Try sending START_STREAM to port 8801
    test_packets = [
        ("START_STREAM", START_STREAM, 8801),
        ("START_STREAM", START_STREAM, 8800),  # baseline comparison
        ("0x66 neutral", b"\x66\x80\x80\x80\x80\x00\x00\x99", 8801),
        ("0x66 neutral", b"\x66\x80\x80\x80\x80\x00\x00\x99", 8800),
    ]

    for name, data, port in test_packets:
        try:
            sock.sendto(data, (drone_ip, port))
            print(f"  Sent {name} ({len(data)} bytes) to {drone_ip}:{port}")
        except OSError as e:
            print(f"  Error sending to port {port}: {e}")

    # Listen for any responses
    print(f"\n  Listening for responses (2s)...")
    deadline = time.monotonic() + 2.0
    responses = []
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
            responses.append((data, addr))
        except socket.timeout:
            break
        except ConnectionResetError:
            continue

    if responses:
        print(f"  Received {len(responses)} responses:")
        for data, addr in responses[:10]:
            print(f"    From {addr}: {len(data)} bytes  head={data[:16].hex(' ')}")
    else:
        print(f"  No responses received")


def probe_camera_module(bind_ip):
    """Probe 192.168.100.1 (JieLi camera module) for reachability."""
    print(f"\n{'='*70}")
    print(f"CAMERA MODULE PROBE (192.168.100.1)")
    print(f"{'='*70}")

    camera_ip = "192.168.100.1"

    # Try UDP probe on common ports
    test_ports = [80, 554, 8080, 8554, 8800, 9090, 6220, 4040]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    if bind_ip:
        try:
            sock.bind((bind_ip, 0))
        except OSError:
            pass

    for port in test_ports:
        try:
            sock.sendto(b"\x00\x00\x00\x00", (camera_ip, port))
        except OSError:
            pass

    # Listen
    print(f"  Sent probes to {camera_ip} on ports {test_ports}")
    deadline = time.monotonic() + 2.0
    got_response = False
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
            print(f"  RESPONSE from {addr}: {len(data)} bytes  head={data[:16].hex(' ')}")
            got_response = True
        except socket.timeout:
            break
        except ConnectionResetError:
            # ICMP port unreachable = host exists but port closed
            print(f"  Got ICMP unreachable — {camera_ip} IS reachable but port closed")
            got_response = True
            break

    # Also try TCP on port 80
    try:
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.settimeout(2.0)
        result = tcp_sock.connect_ex((camera_ip, 80))
        if result == 0:
            print(f"  TCP port 80 OPEN on {camera_ip}")
            got_response = True
        else:
            print(f"  TCP port 80 closed (error={result})")
        tcp_sock.close()
    except Exception as e:
        print(f"  TCP probe failed: {e}")

    sock.close()

    if not got_response:
        print(f"  {camera_ip} appears UNREACHABLE from this network")


def dump_raw_packets(packets, output_dir="packet_dumps"):
    """Dump raw packets to disk for offline analysis."""
    os.makedirs(output_dir, exist_ok=True)

    # Dump all raw packets as binary
    raw_path = os.path.join(output_dir, "raw_packets.bin")
    with open(raw_path, "wb") as f:
        for data, addr, ts in packets:
            # Write: 4-byte length prefix + raw data
            f.write(struct.pack("<I", len(data)))
            f.write(data)
    print(f"\n  Raw packets saved to {raw_path}")

    # Dump first 10 individual packets as hex
    for i, (data, addr, ts) in enumerate(packets[:10]):
        path = os.path.join(output_dir, f"pkt_{i:04d}_{len(data)}b.bin")
        with open(path, "wb") as f:
            f.write(data)

    # Assemble potential frames (strip assumed header, concatenate)
    # Try header_size = 32 (based on probe observations)
    for hdr_size in [32]:
        frame_data = bytearray()
        frame_idx = 0
        for data, _, _ in packets:
            if len(data) > hdr_size:
                frame_data.extend(data[hdr_size:])

            if len(data) < 1080:
                # End of frame
                if frame_data:
                    path = os.path.join(output_dir, f"frame_{frame_idx:04d}_hdr{hdr_size}.bin")
                    with open(path, "wb") as f:
                        f.write(frame_data)
                    if frame_idx < 5:
                        print(f"  Frame {frame_idx}: {len(frame_data)} bytes "
                              f"(header={hdr_size}) saved to {path}")
                    frame_idx += 1
                    frame_data = bytearray()

        print(f"  Assembled {frame_idx} frames with header_size={hdr_size}")


def main():
    parser = argparse.ArgumentParser(description="Analyze drone video packets")
    parser.add_argument("--drone-ip", default="")
    parser.add_argument("--bind-ip", default="")
    parser.add_argument("--count", type=int, default=300, help="Packets to capture")
    parser.add_argument("--duration", type=float, default=10.0, help="Max capture time (s)")
    parser.add_argument("--dump", action="store_true", help="Dump raw packets to disk")
    args = parser.parse_args()

    drone_ip, bind_ip = args.drone_ip, args.bind_ip
    if not drone_ip or not bind_ip:
        auto_ip, auto_bind = auto_detect()
        drone_ip = drone_ip or auto_ip or ""
        bind_ip = bind_ip or auto_bind or ""

    if not drone_ip:
        print("ERROR: Could not detect drone IP.")
        sys.exit(1)

    print(f"Drone: {drone_ip}  Bind: {bind_ip}")

    sock = create_socket(bind_ip)
    print(f"Socket: {sock.getsockname()}")

    # Capture packets
    print(f"\nCapturing up to {args.count} packets ({args.duration}s max)...")
    packets = capture_packets(sock, drone_ip, args.count, args.duration)
    print(f"Captured {len(packets)} packets")

    sock.close()

    if not packets:
        print("No packets received! Is the drone connected?")
        return

    # Analyze
    analyze_headers(packets)
    find_frame_boundaries(packets)
    analyze_fragment_fields(packets)
    check_h264(packets)

    # Probe port 8801 (BL-UAVSDK control port)
    print("\nProbing port 8801 (need fresh socket)...")
    probe_sock = create_socket(bind_ip)
    probe_port_8801(probe_sock, drone_ip)
    probe_sock.close()

    # Probe camera module at 192.168.100.1
    probe_camera_module(bind_ip)

    # Optionally dump
    if args.dump:
        print(f"\n{'='*70}")
        print("DUMPING PACKETS")
        print(f"{'='*70}")
        dump_raw_packets(packets)

    print(f"\n{'='*70}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
