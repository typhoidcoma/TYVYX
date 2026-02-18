#!/usr/bin/env python3
"""
TCP Video Format Probe for E88Pro/lxPro drones.

Connects to the drone's TCP 7070 port, reads the video stream for a few
seconds, dumps the raw data to a file, and analyses the format (JPEG SOI/EOI,
H.264 NAL, HTTP headers, length-prefix patterns).

Usage:
    python scripts/probe_tcp_video.py [--drone-ip 192.168.1.1] [--bind-ip 192.168.1.100]

If no IPs given, tries auto-detection from the network adapter.
"""

import argparse
import os
import socket
import struct
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def auto_detect():
    """Try to auto-detect drone IP and bind IP from the network adapter."""
    try:
        from autonomous.services.network_service import find_drone_interface
        iface = find_drone_interface()
        if iface:
            return iface.gateway_ip, iface.local_ip
    except Exception:
        pass
    return None, None


def send_e88pro_init(drone_ip, bind_ip, port=7099):
    """Send E88Pro init commands on UDP to wake up video."""
    print(f"\n[init] Sending E88Pro init commands to {drone_ip}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    if bind_ip:
        sock.bind((bind_ip, 0))

    commands = [
        ("heartbeat", bytes([0x01, 0x01])),
        ("init",      bytes([0x08, 0x01])),
        ("camera_1",  bytes([0x06, 0x01])),
        ("start_vid", bytes([0x08, 0x01])),
    ]

    for label, cmd in commands:
        try:
            sock.sendto(cmd, (drone_ip, port))
            print(f"  Sent {label}: {cmd.hex(' ')}")
        except OSError as e:
            print(f"  Send {label} failed: {e}")
        time.sleep(0.2)

    # Drain any responses
    responses = 0
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
            responses += 1
            if responses <= 5:
                print(f"  Response: {len(data)} bytes from {addr}: {data[:20].hex(' ')}")
        except (socket.timeout, ConnectionResetError):
            break
    print(f"  Got {responses} UDP response(s)")
    sock.close()


def probe_tcp_video(drone_ip, bind_ip, tcp_port=7070, duration=10.0):
    """Connect to TCP video port and read the stream."""
    print(f"\n{'='*60}")
    print(f"TCP VIDEO PROBE  ->  {drone_ip}:{tcp_port}  ({duration}s)")
    print(f"{'='*60}")

    # Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    if bind_ip:
        sock.bind((bind_ip, 0))

    print(f"\n[1] Connecting to {drone_ip}:{tcp_port}...")
    try:
        sock.connect((drone_ip, tcp_port))
        print(f"    Connected! Local: {sock.getsockname()}")
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"    FAILED to connect: {e}")
        sock.close()
        return None

    # Read stream
    print(f"\n[2] Reading TCP stream for {duration}s...")
    sock.settimeout(2.0)
    buf = bytearray()
    start = time.monotonic()
    chunks = 0

    while time.monotonic() - start < duration:
        try:
            data = sock.recv(65536)
            if not data:
                print(f"    Connection closed by drone after {len(buf)} bytes")
                break
            buf.extend(data)
            chunks += 1
            if chunks <= 5:
                head = data[:32].hex(" ")
                print(f"    Chunk {chunks}: {len(data)} bytes  head={head}")
            elif chunks == 6:
                print(f"    (suppressing further chunk logs...)")
        except socket.timeout:
            continue
        except (ConnectionResetError, OSError) as e:
            print(f"    Connection error: {e}")
            break

    elapsed = time.monotonic() - start
    print(f"\n    Total: {len(buf)} bytes in {chunks} chunks over {elapsed:.1f}s")
    if len(buf) > 0:
        print(f"    Rate: {len(buf)/elapsed:.0f} bytes/s ({len(buf)/elapsed/1024:.1f} KB/s)")

    sock.close()

    # Dump raw data
    dump_path = os.path.join(os.path.dirname(__file__), "..", "tcp_video_dump.bin")
    dump_path = os.path.abspath(dump_path)
    with open(dump_path, "wb") as f:
        f.write(buf)
    print(f"\n[3] Raw dump saved to: {dump_path}")

    return bytes(buf)


def analyse_stream(data):
    """Analyse the raw TCP stream for known video formats."""
    if not data:
        print("\n[analyse] No data to analyse.")
        return

    print(f"\n{'='*60}")
    print(f"STREAM ANALYSIS  ({len(data)} bytes)")
    print(f"{'='*60}")

    # Show first 256 bytes hex
    print(f"\n[1] First 256 bytes:")
    for offset in range(0, min(256, len(data)), 16):
        hex_part = " ".join(f"{b:02x}" for b in data[offset:offset+16])
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data[offset:offset+16])
        print(f"    {offset:04x}: {hex_part:<48s}  {ascii_part}")

    # Check for HTTP headers
    print(f"\n[2] HTTP header check...")
    if data[:4] in (b"HTTP", b"GET ", b"POST"):
        # Find end of headers
        hdr_end = data.find(b"\r\n\r\n")
        if hdr_end > 0:
            headers = data[:hdr_end].decode("ascii", errors="replace")
            print(f"    HTTP headers found ({hdr_end} bytes):")
            for line in headers.split("\r\n"):
                print(f"      {line}")
        else:
            print(f"    HTTP start detected but no header end found")
    elif data[:20].find(b"HTTP") >= 0 or data[:20].find(b"MJPEG") >= 0:
        print(f"    Partial HTTP/MJPEG marker in first 20 bytes")
    else:
        print(f"    No HTTP headers detected")

    # Scan for JPEG markers
    print(f"\n[3] JPEG marker scan (FF D8 = SOI, FF D9 = EOI)...")
    soi_positions = []
    eoi_positions = []
    for i in range(len(data) - 1):
        if data[i] == 0xFF and data[i+1] == 0xD8:
            soi_positions.append(i)
        elif data[i] == 0xFF and data[i+1] == 0xD9:
            eoi_positions.append(i)

    print(f"    SOI (FF D8) count: {len(soi_positions)}")
    print(f"    EOI (FF D9) count: {len(eoi_positions)}")

    if soi_positions:
        print(f"    First 10 SOI offsets: {soi_positions[:10]}")
    if eoi_positions:
        print(f"    First 10 EOI offsets: {eoi_positions[:10]}")

    # Pair SOI/EOI to find complete JPEG frames
    if soi_positions and eoi_positions:
        frames = []
        for soi in soi_positions:
            for eoi in eoi_positions:
                if eoi > soi:
                    frame_len = eoi - soi + 2  # include EOI marker
                    frames.append((soi, frame_len))
                    break
        print(f"\n    Complete JPEG frames found: {len(frames)}")
        for i, (offset, length) in enumerate(frames[:10]):
            # Check for JPEG markers inside
            frame = data[offset:offset+length]
            has_dht = b"\xff\xc4" in frame
            has_dqt = b"\xff\xdb" in frame
            has_sof = b"\xff\xc0" in frame
            markers = []
            if has_dqt: markers.append("DQT")
            if has_dht: markers.append("DHT")
            if has_sof: markers.append("SOF0")
            print(f"      Frame {i}: offset={offset}, size={length} bytes, "
                  f"markers={','.join(markers) if markers else 'none'}")

            # If SOF0 found, parse dimensions
            if has_sof:
                sof_idx = frame.find(b"\xff\xc0")
                if sof_idx + 9 <= len(frame):
                    height = struct.unpack(">H", frame[sof_idx+5:sof_idx+7])[0]
                    width = struct.unpack(">H", frame[sof_idx+7:sof_idx+9])[0]
                    print(f"              SOF0 dimensions: {width}x{height}")

    # Scan for H.264 NAL units
    print(f"\n[4] H.264 NAL scan (00 00 00 01 / 00 00 01)...")
    nal4_count = 0
    nal3_count = 0
    for i in range(len(data) - 3):
        if data[i:i+4] == b"\x00\x00\x00\x01":
            nal4_count += 1
            if nal4_count <= 5:
                nal_type = data[i+4] & 0x1F if i+4 < len(data) else -1
                print(f"    NAL4 at offset {i}: type={nal_type}")
        elif data[i:i+3] == b"\x00\x00\x01":
            nal3_count += 1
            if nal3_count <= 5:
                nal_type = data[i+3] & 0x1F if i+3 < len(data) else -1
                print(f"    NAL3 at offset {i}: type={nal_type}")
    print(f"    4-byte NAL start codes: {nal4_count}")
    print(f"    3-byte NAL start codes: {nal3_count}")

    # Scan for length-prefixed patterns (common in Chinese drone protocols)
    print(f"\n[5] Length-prefix scan (first 8 frames)...")
    # Try big-endian and little-endian 4-byte length prefix
    for endian, label in [("<", "LE"), (">", "BE")]:
        if len(data) >= 4:
            first_len = struct.unpack(endian + "I", data[:4])[0]
            if 100 < first_len < 500000 and first_len + 4 <= len(data):
                # Check if the next length prefix makes sense
                next_off = first_len + 4
                if next_off + 4 <= len(data):
                    second_len = struct.unpack(endian + "I", data[next_off:next_off+4])[0]
                    if 100 < second_len < 500000:
                        print(f"    {label} 4-byte length prefix detected!")
                        print(f"      Frame 0: offset=0, length={first_len}")
                        print(f"      Frame 1: offset={next_off}, length={second_len}")
                        # Walk the chain
                        off = 0
                        frame_count = 0
                        while off + 4 <= len(data) and frame_count < 8:
                            flen = struct.unpack(endian + "I", data[off:off+4])[0]
                            if flen < 100 or flen > 500000:
                                break
                            print(f"      Frame {frame_count}: offset={off}, length={flen}")
                            off += 4 + flen
                            frame_count += 1

    # Try 2-byte length prefix (LE)
    if len(data) >= 2:
        for endian, label in [("<", "LE"), (">", "BE")]:
            first_len = struct.unpack(endian + "H", data[:2])[0]
            if 100 < first_len < 65000 and first_len + 2 <= len(data):
                next_off = first_len + 2
                if next_off + 2 <= len(data):
                    second_len = struct.unpack(endian + "H", data[next_off:next_off+2])[0]
                    if 100 < second_len < 65000:
                        print(f"    {label} 2-byte length prefix detected!")
                        off = 0
                        frame_count = 0
                        while off + 2 <= len(data) and frame_count < 8:
                            flen = struct.unpack(endian + "H", data[off:off+2])[0]
                            if flen < 100 or flen > 65000:
                                break
                            print(f"      Frame {frame_count}: offset={off}, length={flen}")
                            off += 2 + flen
                            frame_count += 1

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    if soi_positions and eoi_positions:
        print(f"  Format: MJPEG (JPEG SOI/EOI framing)")
        print(f"  Frames detected: {min(len(soi_positions), len(eoi_positions))}")
        if soi_positions[0] > 0:
            print(f"  NOTE: First SOI at offset {soi_positions[0]} (not 0) — check for header/prefix")
    elif nal4_count + nal3_count > 0:
        print(f"  Format: H.264 (NAL start codes)")
        print(f"  NAL units: {nal4_count + nal3_count}")
    else:
        print(f"  Format: UNKNOWN")
        print(f"  No JPEG SOI/EOI or H.264 NAL markers found")
        print(f"  Check the hex dump above for clues")


def main():
    parser = argparse.ArgumentParser(description="Probe TCP video format from drone")
    parser.add_argument("--drone-ip", default="", help="Drone IP (auto-detect if empty)")
    parser.add_argument("--bind-ip", default="", help="Local bind IP (auto-detect if empty)")
    parser.add_argument("--tcp-port", type=int, default=7070, help="TCP video port (default 7070)")
    parser.add_argument("--duration", type=float, default=10.0, help="Read duration in seconds")
    parser.add_argument("--skip-init", action="store_true", help="Skip E88Pro init commands")
    args = parser.parse_args()

    drone_ip = args.drone_ip
    bind_ip = args.bind_ip

    if not drone_ip or not bind_ip:
        print("Auto-detecting drone adapter...")
        auto_ip, auto_bind = auto_detect()
        if auto_ip and not drone_ip:
            drone_ip = auto_ip
            print(f"  Drone IP: {drone_ip}")
        if auto_bind and not bind_ip:
            bind_ip = auto_bind
            print(f"  Bind IP:  {bind_ip}")

    if not drone_ip:
        print("ERROR: Could not detect drone IP. Provide --drone-ip.")
        sys.exit(1)

    print(f"\nDrone: {drone_ip}  Bind: {bind_ip or '(all interfaces)'}")
    print(f"TCP port: {args.tcp_port}  Duration: {args.duration}s")
    print(f"Time: {time.strftime('%H:%M:%S')}")

    # Send E88Pro init commands to wake up video
    if not args.skip_init:
        send_e88pro_init(drone_ip, bind_ip)
        time.sleep(0.5)

    # Probe TCP video
    data = probe_tcp_video(drone_ip, bind_ip, args.tcp_port, args.duration)

    # Analyse
    if data:
        analyse_stream(data)
    else:
        print("\nNo data received. Check:")
        print("  - Is the drone powered on and connected?")
        print("  - Is TCP port 7070 open? (run probe_drone.py first)")
        print("  - Try --skip-init if init commands cause issues")

    print(f"\n{'='*60}")
    print("PROBE COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
