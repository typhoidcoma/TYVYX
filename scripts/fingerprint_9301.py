"""Fingerprint 0x93 0x01 video packets against known drone protocol variants.

Modes:
  1) Live capture on drone WiFi (default)
  2) Offline analysis from a text file containing hex packet lines

Examples:
  python scripts/fingerprint_9301.py --bind-ip 192.168.169.2 --duration 8
  python scripts/fingerprint_9301.py --bind-ip 192.168.169.2 --duration 8 --bootstrap
  python scripts/fingerprint_9301.py --hex-file packets.txt
"""

import argparse
import os
import socket
import sys
import time
from collections import Counter
from typing import List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tyvyx.utils.wifi_uav_packets import START_STREAM  # noqa: E402

DRONE_GATEWAY = "192.168.169.1"
CAMERA_IP = "192.168.100.1"
BOOTSTRAP_PORTS = [2020, 2021, 6220, 6221, 3333, 4040, 7099, 8080, 8800]

BOOTSTRAP_KICK = [
    b"\xef\x00\x04\x00",
    b"\xef\x00\x02\x00\x06\x01",
    b"\xef\x00\x02\x00\x06\x02",
    b"\x01\x01",
    b"\x08\x01",
]

BOOTSTRAP_STAGES = [
    [b"\x00\x00\x00\x00", b"\x01\x00\x00\x00", b"\x08\x01"],
    [b"\x01\x01", b"\x01\x00\x00\x00", b"\x00\x01"],
    [b"\xef\x20\x02\x00\x01\x65", b"\xef\x20\x03\x00\x01\x65\x01"],
    [b"\xef\x00\x04\x00", b"\xef\x00\x02\x00\x06\x01", b"\xef\x00\x02\x00\x06\x02"],
]


def make_udp(bind_ip: str, port: int, timeout: float) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((bind_ip, port))
    s.settimeout(timeout)
    return s


def parse_hex_file(path: str) -> List[bytes]:
    rows: List[bytes] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip().lower()
            if not line:
                continue
            line = line.replace("head=", "").replace("0x", "").replace(",", " ")
            parts = [p for p in line.split() if all(c in "0123456789abcdef" for c in p)]
            if not parts:
                continue
            try:
                data = bytes(int(p, 16) for p in parts)
                rows.append(data)
            except ValueError:
                continue
    return rows


def live_capture(bind_ip: str, duration: float, bootstrap: bool) -> List[bytes]:
    rx = make_udp(bind_ip, 1234, timeout=0.08)
    rx8800 = make_udp(bind_ip, 8800, timeout=0.08)
    rx8801 = make_udp(bind_ip, 8801, timeout=0.08)
    rx7099 = make_udp(bind_ip, 7099, timeout=0.08)
    tx = make_udp(bind_ip, 0, timeout=0.12)

    packets: List[bytes] = []
    end = time.monotonic() + duration
    last_kick = 0.0
    try:
        tx.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
        if bootstrap:
            # Pre-arm using staged warmup seen to unlock 93 01 stream.
            for stage in BOOTSTRAP_STAGES:
                for payload in stage:
                    for port in BOOTSTRAP_PORTS:
                        tx.sendto(payload, (DRONE_GATEWAY, port))
                        tx.sendto(payload, (CAMERA_IP, port))
                time.sleep(0.08)
        while time.monotonic() < end:
            now = time.monotonic()
            if now - last_kick > 0.25:
                tx.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
                if bootstrap:
                    for p in BOOTSTRAP_KICK:
                        tx.sendto(p, (DRONE_GATEWAY, 8800))
                last_kick = now
            for sock in (tx, rx, rx8800, rx8801, rx7099):
                try:
                    data, _ = sock.recvfrom(65535)
                    packets.append(data)
                except socket.timeout:
                    continue
                except ConnectionResetError:
                    continue
    finally:
        rx.close()
        rx8800.close()
        rx8801.close()
        rx7099.close()
        tx.close()
    return packets


def extract_9301(packets: List[bytes]) -> List[bytes]:
    return [p for p in packets if len(p) >= 56 and p[:2] == b"\x93\x01"]


def score_variant(packets_9301: List[bytes]) -> Tuple[str, float, List[str]]:
    notes: List[str] = []
    if not packets_9301:
        return "unknown", 0.0, ["No 93 01 packets detected"]

    src_len = len(packets_9301)
    pkt_len = [int.from_bytes(p[2:4], "little") for p in packets_9301]
    frame_id = [int.from_bytes(p[16:18], "little") for p in packets_9301]
    frag_id = [int.from_bytes(p[32:34], "little") for p in packets_9301]
    frag_total = [int.from_bytes(p[36:38], "little") for p in packets_9301]

    unique_frame = len(set(frame_id))
    unique_frag_total = len(set(frag_total))
    transitions = sum(1 for i in range(1, len(frame_id)) if frame_id[i] != frame_id[i - 1])

    notes.append(f"93 01 packets: {src_len}")
    notes.append(f"packet_length unique: {sorted(set(pkt_len))[:8]}")
    notes.append(f"frame_id unique: {unique_frame}, transitions: {transitions}")
    notes.append(f"frag_id unique: {len(set(frag_id))}")
    notes.append(f"frag_total unique: {sorted(set(frag_total))[:8]}")

    # Heuristic families:
    # 1) "push_jpeg_wifi_uav_like": many packets with varying frag/frame fields
    # 2) "bootstrap_response_only": mostly static headers, no frame progression
    # 3) "unknown"
    if unique_frame >= 4 and transitions >= max(2, src_len // 6) and len(set(frag_id)) >= 3:
        return "push_jpeg_wifi_uav_like", 0.92, notes
    if unique_frame <= 2 and transitions <= 1 and len(set(pkt_len)) <= 3:
        return "bootstrap_response_only", 0.88, notes
    return "mixed_or_partial", 0.65, notes


def print_summary(all_packets: List[bytes]) -> None:
    p9301 = extract_9301(all_packets)
    variant, conf, notes = score_variant(p9301)

    print("=" * 68)
    print("93 01 Fingerprint")
    print("=" * 68)
    print(f"Total UDP packets captured: {len(all_packets)}")
    print(f"93 01 packets: {len(p9301)}")

    if p9301:
        sample = p9301[0][:32].hex(" ")
        print(f"Sample head: {sample}")

        lengths = Counter(int.from_bytes(p[2:4], "little") for p in p9301)
        print("Top packet_length values:")
        for val, cnt in lengths.most_common(5):
            print(f"  {val} -> {cnt}")

    print(f"Best match: {variant} (confidence {conf:.2f})")
    for n in notes:
        print(f"- {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fingerprint 93 01 packets")
    parser.add_argument("--hex-file", default="", help="Analyze hex packets from text file")
    parser.add_argument("--bind-ip", default="", help="Local drone WiFi IP for live capture")
    parser.add_argument("--duration", type=float, default=8.0, help="Live capture duration (seconds)")
    parser.add_argument("--bootstrap", action="store_true", help="Send bootstrap kick payloads during live capture")
    args = parser.parse_args()

    packets: List[bytes]
    if args.hex_file:
        packets = parse_hex_file(args.hex_file)
    else:
        if not args.bind_ip:
            print("Provide --bind-ip for live mode, or use --hex-file.")
            return
        packets = live_capture(args.bind_ip, args.duration, args.bootstrap)

    print_summary(packets)


if __name__ == "__main__":
    main()
