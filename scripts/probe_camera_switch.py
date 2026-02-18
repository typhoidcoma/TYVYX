"""Probe for camera-switch command on WiFi UAV (K417 / Drone-XXXXXX).

Run while video is streaming — watch the video feed in the browser and
note which command (if any) causes the image to change.

Usage:
    python scripts/probe_camera_switch.py [--drone-ip 192.168.169.1] [--port 8800]
"""

import argparse
import ctypes
import socket
import sys
import time


def make_socket(bind_ip: str = "") -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if sys.platform == "win32":
        SIO_UDP_CONNRESET = 0x9800000C
        ret = ctypes.c_ulong(0)
        false = b"\x00\x00\x00\x00"
        ctypes.windll.ws2_32.WSAIoctl(
            sock.fileno(), SIO_UDP_CONNRESET,
            false, len(false), None, 0,
            ctypes.byref(ret), None, None,
        )
    sock.bind((bind_ip or "", 0))
    sock.settimeout(1.0)
    return sock


def build_ef20_text_cmd(text: str) -> bytes:
    """Wrap a text command in an ef 20 packet (matching SSID2/SSID3 format)."""
    payload = b"\x01\x67" + text.encode("ascii")
    length = len(payload)
    return b"\xef\x20" + length.to_bytes(2, "little") + payload


def build_ef20_binary_cmd(subcmd: int, data: bytes = b"") -> bytes:
    """Build an ef 20 binary command with a sub-command byte."""
    payload = b"\x01" + bytes([subcmd]) + data
    length = len(payload)
    return b"\xef\x20" + length.to_bytes(2, "little") + payload


def build_ef_cmd(cmd_type: int, data: bytes) -> bytes:
    """Build a generic ef XX packet."""
    length = len(data)
    return bytes([0xef, cmd_type]) + length.to_bytes(2, "little") + data


def send_and_report(sock: socket.socket, drone_ip: str, port: int,
                    label: str, packet: bytes, delay: float = 0.5):
    """Send a packet and wait for user observation."""
    hex_str = packet.hex(" ")
    print(f"\n{'='*60}")
    print(f"  [{label}]")
    print(f"  Sending: {hex_str}")
    print(f"  ({len(packet)} bytes to {drone_ip}:{port})")
    print(f"{'='*60}")

    try:
        sock.sendto(packet, (drone_ip, port))
    except OSError as e:
        print(f"  Send error: {e}")
        return

    # Try to read any response
    responses = 0
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
            responses += 1
            if responses <= 3:
                head = data[:20].hex(" ") if data else "(empty)"
                print(f"  Response #{responses}: {len(data)} bytes from {addr}  head={head}")
        except socket.timeout:
            break
        except ConnectionResetError:
            break

    if responses == 0:
        print(f"  No response")
    else:
        print(f"  Total responses: {responses}")

    print(f"  Waiting {delay}s — check the video feed...")
    time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="Probe camera switch commands")
    parser.add_argument("--drone-ip", default="192.168.169.1")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--bind-ip", default="")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Seconds to wait between commands (watch the feed)")
    parser.add_argument("--group", type=int, default=0,
                        help="Run only one group (1-6), 0=all")
    args = parser.parse_args()

    sock = make_socket(args.bind_ip)
    ip = args.drone_ip
    port = args.port
    delay = args.delay

    print(f"Camera switch probe — target {ip}:{port}")
    print(f"Socket bound to {sock.getsockname()}")
    print(f"Delay between probes: {delay}s")
    print(f"\nMAKE SURE VIDEO IS STREAMING in the browser!")
    print(f"Watch for the image to change (front <-> bottom camera).\n")
    input("Press Enter to start probing...")

    # ────────────────────────────────────────────────────────────────
    # Group 1: E88Pro-style raw commands (no ef wrapper)
    # ────────────────────────────────────────────────────────────────
    if args.group in (0, 1):
        print("\n" + "━"*60)
        print("  GROUP 1: E88Pro-style raw commands")
        print("━"*60)

        send_and_report(sock, ip, port, "E88Pro CAM1: 06 01",
                        b"\x06\x01", delay)
        send_and_report(sock, ip, port, "E88Pro CAM2: 06 02",
                        b"\x06\x02", delay)

    # ────────────────────────────────────────────────────────────────
    # Group 2: Text commands in ef 20 wrapper (SSID format)
    # ────────────────────────────────────────────────────────────────
    if args.group in (0, 2):
        print("\n" + "━"*60)
        print("  GROUP 2: Text commands (ef 20 wrapper)")
        print("━"*60)

        # Camera switch variations
        text_cmds = [
            ("bf_cam=cmd=1", "<i=2^bf_cam=cmd=1>"),
            ("bf_cam=cmd=2", "<i=2^bf_cam=cmd=2>"),
            ("camera=cmd=1", "<i=2^camera=cmd=1>"),
            ("camera=cmd=2", "<i=2^camera=cmd=2>"),
            ("bf_switch=cmd=1", "<i=2^bf_switch=cmd=1>"),
            ("bf_switch=cmd=2", "<i=2^bf_switch=cmd=2>"),
            ("bf_video=cmd=1", "<i=2^bf_video=cmd=1>"),
            ("bf_video=cmd=2", "<i=2^bf_video=cmd=2>"),
            ("bf_camera=cmd=1", "<i=2^bf_camera=cmd=1>"),
            ("bf_camera=cmd=2", "<i=2^bf_camera=cmd=2>"),
        ]

        for label, text in text_cmds:
            pkt = build_ef20_text_cmd(text)
            send_and_report(sock, ip, port, f"Text: {text}", pkt, delay)

    # ────────────────────────────────────────────────────────────────
    # Group 3: Binary ef 20 commands (UNK_FRAME-like)
    # ────────────────────────────────────────────────────────────────
    if args.group in (0, 3):
        print("\n" + "━"*60)
        print("  GROUP 3: Binary ef 20 commands")
        print("━"*60)

        # UNK_FRAME is ef 20 06 00 01 65 — try nearby sub-commands
        for subcmd in [0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A]:
            pkt = build_ef20_binary_cmd(subcmd)
            send_and_report(sock, ip, port,
                            f"ef 20 binary subcmd=0x{subcmd:02x}", pkt, delay)

        # With extra data byte (camera number)
        for subcmd in [0x60, 0x65, 0x66]:
            for cam_byte in [0x01, 0x02]:
                pkt = build_ef20_binary_cmd(subcmd, bytes([cam_byte]))
                send_and_report(sock, ip, port,
                                f"ef 20 subcmd=0x{subcmd:02x} cam={cam_byte}", pkt, delay)

    # ────────────────────────────────────────────────────────────────
    # Group 4: ef 00 commands (START_STREAM family)
    # ────────────────────────────────────────────────────────────────
    if args.group in (0, 4):
        print("\n" + "━"*60)
        print("  GROUP 4: ef 00 commands (short)")
        print("━"*60)

        # START_STREAM is ef 00 04 00 — try variations
        for cmd_byte in [0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x08]:
            pkt = b"\xef\x00" + (2).to_bytes(2, "little") + bytes([cmd_byte, 0x00])
            send_and_report(sock, ip, port,
                            f"ef 00 cmd=0x{cmd_byte:02x} 0x00", pkt, delay)

        # Two-byte payload with camera number
        for cam in [0x01, 0x02]:
            pkt = b"\xef\x00" + (2).to_bytes(2, "little") + bytes([0x06, cam])
            send_and_report(sock, ip, port,
                            f"ef 00 06 cam={cam}", pkt, delay)

    # ────────────────────────────────────────────────────────────────
    # Group 5: ef 01 commands (potential command prefix)
    # ────────────────────────────────────────────────────────────────
    if args.group in (0, 5):
        print("\n" + "━"*60)
        print("  GROUP 5: ef 01 commands")
        print("━"*60)

        for cmd in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06]:
            for val in [0x01, 0x02]:
                pkt = bytes([0xef, 0x01]) + (2).to_bytes(2, "little") + bytes([cmd, val])
                send_and_report(sock, ip, port,
                                f"ef 01 cmd=0x{cmd:02x} val=0x{val:02x}", pkt, delay)

    # ────────────────────────────────────────────────────────────────
    # Group 6: Common Chinese drone camera patterns
    # ────────────────────────────────────────────────────────────────
    if args.group in (0, 6):
        print("\n" + "━"*60)
        print("  GROUP 6: Common patterns from other Chinese drones")
        print("━"*60)

        # Some drones use 0x40/0x80 prefix for commands
        for prefix in [0x40, 0x80, 0xFF]:
            for cam in [0x01, 0x02]:
                pkt = bytes([prefix, 0x06, cam])
                send_and_report(sock, ip, port,
                                f"0x{prefix:02x} 06 cam={cam}", pkt, delay)

        # Raw single-byte toggle
        for b in [0x06, 0x07, 0x20, 0x21, 0x22]:
            pkt = bytes([b])
            send_and_report(sock, ip, port, f"Single byte 0x{b:02x}", pkt, delay)

    print("\n" + "━"*60)
    print("  PROBE COMPLETE")
    print("━"*60)
    print("\nDid you see the camera view change at any point?")
    print("If yes, note the command label and we'll wire it up.")

    sock.close()


if __name__ == "__main__":
    main()
