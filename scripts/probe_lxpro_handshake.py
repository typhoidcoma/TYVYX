"""Probe lxPro-style handshake paths for JieLi camera modules.

This script focuses on the connection model implied by liblxPro.so:
  - target camera IP is 192.168.100.1
  - gateway/AP is 192.168.169.1
  - Cek/Cmd/Stm channels may be opened after connect initialization

Usage:
  python scripts/probe_lxpro_handshake.py [--add-route] [--cycles 8]
"""

import argparse
import ctypes
import os
import re
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

# Add project root to path for direct script execution.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tyvyx.utils.wifi_uav_packets import REQUEST_A, REQUEST_B, START_STREAM

DRONE_GATEWAY = "192.168.169.1"
CAMERA_IP = "192.168.100.1"
CAMERA_SUBNET = "192.168.100.0"
CAMERA_MASK = "255.255.255.0"

DEFAULT_PORTS = [2020, 2021, 6220, 6221, 8080, 3333, 4040, 7099, 8800, 8801, 1234]

# Low-risk handshake guesses from prior reversing and wifi-uav behavior.
PROBE_PAYLOADS = [
    b"\x00\x00\x00\x00",
    b"\x01\x00\x00\x00",
    b"\x01\x01",
    b"\x08\x01",
    b"\xef\x00\x04\x00",  # START_STREAM in WiFi-UAV family
    b"\xef\x20\x02\x00\x01\x65",  # Common lxPro-adjacent frame seen in apps
]

BOOTSTRAP_PORTS = [2020, 2021, 6220, 6221, 3333, 4040, 7099, 8080, 8800]

BOOTSTRAP_STAGES = [
    {
        "name": "connect-seed",
        "payloads": [b"\x00\x00\x00\x00", b"\x01\x00\x00\x00", b"\x08\x01"],
        "wait": 0.30,
    },
    {
        "name": "cek-pulse",
        "payloads": [b"\x01\x01", b"\x01\x00\x00\x00", b"\x00\x01"],
        "wait": 0.35,
    },
    {
        "name": "cmd-seed",
        "payloads": [b"\xef\x20\x02\x00\x01\x65", b"\xef\x20\x03\x00\x01\x65\x01"],
        "wait": 0.35,
    },
    {
        "name": "stream-kick",
        "payloads": [b"\xef\x00\x04\x00", b"\xef\x00\x02\x00\x06\x01", b"\xef\x00\x02\x00\x06\x02"],
        "wait": 0.45,
    },
]

CADENCE_PAYLOADS = [
    b"\x08\x01",
    b"\x01\x01",
    b"\xef\x20\x02\x00\x01\x65",
    b"\xef\x00\x04\x00",
    b"\xef\x00\x02\x00\x06\x01",
    b"\xef\x00\x02\x00\x06\x02",
]


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def find_drone_interface() -> Optional[str]:
    try:
        result = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=6)
    except Exception:
        return None
    for line in result.stdout.splitlines():
        m = re.search(r"192\.168\.169\.(\d+)", line)
        if m:
            return "192.168.169." + m.group(1)
    return None


def get_interface_index_for_ip(bind_ip: str) -> Optional[int]:
    if sys.platform != "win32" or not bind_ip:
        return None
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-NetIPAddress -AddressFamily IPv4 "
                f"-IPAddress '{bind_ip}' | Select-Object -First 1 "
                "-ExpandProperty InterfaceIndex"
            ),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        value = result.stdout.strip()
        return int(value) if value.isdigit() else None
    except Exception:
        return None


def route_exists() -> bool:
    lines = route_lines()
    if not lines:
        return False
    for line in lines:
        if CAMERA_SUBNET in line and (DRONE_GATEWAY in line or "On-link" in line):
            return True
    return False


def route_lines() -> List[str]:
    try:
        result = subprocess.run(["route", "print", "-4"], capture_output=True, text=True, timeout=8)
    except Exception:
        return []
    out = []
    for line in result.stdout.splitlines():
        if "192.168.100." in line:
            out.append(line.strip())
    return out


def add_route(if_index: Optional[int]) -> bool:
    cmd = ["route", "add", CAMERA_SUBNET, "mask", CAMERA_MASK, DRONE_GATEWAY]
    if if_index is not None:
        cmd.extend(["if", str(if_index)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    if result.returncode == 0:
        return True
    combined = f"{result.stdout}\n{result.stderr}".lower()
    return "object already exists" in combined


def make_udp_socket(bind_ip: str, timeout: float = 0.2) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if sys.platform == "win32":
        sio_udp_connreset = 0x9800000C
        ret = ctypes.c_ulong(0)
        false = b"\x00\x00\x00\x00"
        ctypes.windll.ws2_32.WSAIoctl(
            sock.fileno(),
            sio_udp_connreset,
            false,
            len(false),
            None,
            0,
            ctypes.byref(ret),
            None,
            None,
        )
    sock.bind((bind_ip, 0))
    sock.settimeout(timeout)
    return sock


def make_listeners(bind_ip: str, ports: List[int]) -> Dict[int, socket.socket]:
    listeners: Dict[int, socket.socket] = {}
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((bind_ip, port))
            s.settimeout(0.05)
            listeners[port] = s
        except OSError:
            continue
    return listeners


def send_udp_probes(sock: socket.socket, ip: str, ports: List[int]) -> None:
    for port in ports:
        for payload in PROBE_PAYLOADS:
            try:
                sock.sendto(payload, (ip, port))
            except OSError:
                continue


def send_payload_set(sock: socket.socket, ip: str, ports: List[int], payloads: List[bytes]) -> int:
    sent = 0
    for port in ports:
        for payload in payloads:
            try:
                sock.sendto(payload, (ip, port))
                sent += 1
            except OSError:
                continue
    return sent


def tcp_probe(bind_ip: str, ip: str, ports: List[int]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            s.bind((bind_ip, 0))
        except OSError:
            pass
        try:
            rc = s.connect_ex((ip, port))
            out.append((port, rc))
        except OSError:
            out.append((port, -1))
        finally:
            s.close()
    return out


def recv_window(sender: socket.socket, listeners: Dict[int, socket.socket], seconds: float) -> List[Tuple[str, int, bytes]]:
    rows: List[Tuple[str, int, bytes]] = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for lsock in [sender] + list(listeners.values()):
            try:
                data, addr = lsock.recvfrom(65535)
                rows.append((addr[0], addr[1], data))
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
    return rows


def summarize(rows: List[Tuple[str, int, bytes]]) -> None:
    if not rows:
        print("  No UDP responses captured")
        return
    counts: Dict[Tuple[str, int], int] = {}
    for ip, port, _ in rows:
        counts[(ip, port)] = counts.get((ip, port), 0) + 1
    print(f"  UDP responses captured: {len(rows)}")
    for (ip, port), cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))[:20]:
        print(f"    {ip}:{port} -> {cnt} pkt")
    first = rows[0][2]
    print(f"  First payload head: {first[:32].hex(' ')}")


def analyze_9301(rows: List[Tuple[str, int, bytes]]) -> None:
    packets = [data for _, _, data in rows if len(data) >= 56 and data[:2] == b"\x93\x01"]
    if not packets:
        print("  93 01 analysis: no matching packets")
        return

    lens = [int.from_bytes(p[2:4], "little") for p in packets]
    fids = [int.from_bytes(p[16:18], "little") for p in packets]
    frag_ids = [int.from_bytes(p[32:34], "little") for p in packets]
    frag_totals = [int.from_bytes(p[36:38], "little") for p in packets]

    print("  93 01 analysis:")
    print(f"    count={len(packets)}")
    print(f"    pkt_len unique={sorted(set(lens))[:8]}")
    print(f"    frame_id unique count={len(set(fids))} sample={sorted(set(fids))[:8]}")
    print(f"    frag_id unique count={len(set(frag_ids))} sample={sorted(set(frag_ids))[:8]}")
    print(f"    frag_total unique={sorted(set(frag_totals))[:8]}")
    if len(fids) >= 2:
        advancing = sum(1 for i in range(1, len(fids)) if fids[i] != fids[i - 1])
        print(f"    frame_id transitions={advancing}/{len(fids)-1}")


def summarize_stage(name: str, rows: List[Tuple[str, int, bytes]]) -> None:
    counts: Dict[Tuple[str, int], int] = {}
    for ip, port, _ in rows:
        counts[(ip, port)] = counts.get((ip, port), 0) + 1
    print(f"    Stage {name}: rx={len(rows)}")
    for (ip, port), cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))[:5]:
        print(f"      {ip}:{port} -> {cnt}")
    if rows:
        print(f"      head={rows[0][2][:20].hex(' ')}")


def send_frame_request(sock: socket.socket, target_ip: str, target_port: int, frame_id: int) -> None:
    lo, hi = frame_id & 0xFF, (frame_id >> 8) & 0xFF
    rqst_a = bytearray(REQUEST_A)
    rqst_a[12], rqst_a[13] = lo, hi
    rqst_b = bytearray(REQUEST_B)
    for base in (12, 88, 107):
        rqst_b[base], rqst_b[base + 1] = lo, hi
    sock.sendto(rqst_a, (target_ip, target_port))
    sock.sendto(rqst_b, (target_ip, target_port))


def run_request_pump(
    sender: socket.socket,
    listeners: Dict[int, socket.socket],
    bind_ip: str,
    seconds: float,
    frame_timeout: float,
    max_retries: int,
    prime_seconds: float,
) -> None:
    """Pump START_STREAM + REQUEST_A/B with WiFi-UAV-like frame state machine."""
    print(f"\nREQUEST pump ({seconds:.1f}s):")
    print("  Mode: single duplex socket + watchdog retries (turbodrone-style)")

    _ = listeners
    _ = bind_ip
    sender.settimeout(0.05)

    total = 0
    unique_fids = set()
    frames_ok = 0
    frames_dropped = 0
    current_fid = 1
    last_completed_fid: Optional[int] = None
    sync_locked = False
    first_frame_done = False
    fragments = set()
    retry_cnt = 0

    last_req = time.monotonic()
    last_keepalive = 0.0
    last_warmup_nudge = 0.0
    end = time.monotonic() + seconds

    try:
        sender.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
        send_frame_request(sender, DRONE_GATEWAY, 8800, 0)
        last_req = time.monotonic()

        # Optional prime phase: replay stream-kick cadence briefly before watchdog loop.
        if prime_seconds > 0:
            prime_end = time.monotonic() + prime_seconds
            while time.monotonic() < prime_end:
                sender.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
                for p in [b"\xef\x00\x02\x00\x06\x01", b"\xef\x00\x02\x00\x06\x02", b"\xef\x20\x02\x00\x01\x65"]:
                    sender.sendto(p, (DRONE_GATEWAY, 8800))
                time.sleep(0.06)

        while time.monotonic() < end:
            now = time.monotonic()
            if now - last_keepalive > 0.25:
                sender.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
                last_keepalive = now

            try:
                data, addr = sender.recvfrom(65535)
            except socket.timeout:
                data = b""
                addr = ("", 0)
            except ConnectionResetError:
                data = b""
                addr = ("", 0)

            if data:
                if len(data) >= 56 and data[:2] == b"\x93\x01" and data[1] == 0x01:
                    total += 1
                    frame_id = int.from_bytes(data[16:18], "little")
                    frag_id = int.from_bytes(data[32:34], "little")
                    if addr[0]:
                        _ = addr

                    # First valid packet establishes sync target without counting a drop.
                    if not sync_locked:
                        current_fid = frame_id
                        sync_locked = True
                        retry_cnt = 0
                    elif frame_id != current_fid:
                        # Ignore stale/duplicate packets from an already completed frame.
                        if last_completed_fid is not None and frame_id == last_completed_fid:
                            continue

                        # If we had no partial data for current fid, treat this as benign resync.
                        if not fragments:
                            current_fid = frame_id
                            retry_cnt = 0
                            fragments.clear()
                        else:
                            # We were actively assembling a frame and jumped away -> real drop.
                            frames_dropped += 1
                            fragments.clear()
                            current_fid = frame_id
                            retry_cnt = 0

                    fragments.add(frag_id)
                    unique_fids.add(frame_id)
                    retry_cnt = 0

                    # Last fragment marker: byte2 != 0x38
                    if data[2] != 0x38:
                        frames_ok += 1
                        first_frame_done = True
                        last_completed_fid = frame_id
                        fragments.clear()
                        send_frame_request(sender, DRONE_GATEWAY, 8800, frame_id)
                        current_fid = (frame_id + 1) & 0xFFFF
                        last_req = time.monotonic()

            # Watchdog retry model from turbodrone:
            # request (current_fid - 1) when waiting too long.
            now = time.monotonic()
            if not first_frame_done and now - last_warmup_nudge >= 0.20:
                sender.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
                send_frame_request(sender, DRONE_GATEWAY, 8800, (current_fid - 1) & 0xFFFF)
                last_warmup_nudge = now
                last_req = now

            if now - last_req >= frame_timeout:
                if retry_cnt < max_retries:
                    send_frame_request(sender, DRONE_GATEWAY, 8800, (current_fid - 1) & 0xFFFF)
                    retry_cnt += 1
                else:
                    frames_dropped += 1
                    fragments.clear()
                    retry_cnt = 0
                    current_fid = (current_fid + 1) & 0xFFFF
                    send_frame_request(sender, DRONE_GATEWAY, 8800, (current_fid - 1) & 0xFFFF)
                last_req = now

        print(f"  RX packets: {total}")
        print(f"  Frames completed: {frames_ok}")
        print(f"  Frames dropped: {frames_dropped}")
        print(f"  Unique frame IDs: {len(unique_fids)}")
        if unique_fids:
            fid_min = min(unique_fids)
            fid_max = max(unique_fids)
            print(f"  Frame ID range: 0x{fid_min:04x} .. 0x{fid_max:04x}")
    finally:
        sender.settimeout(0.2)


def parse_intervals(spec: str) -> List[float]:
    out: List[float] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            v = float(token)
        except ValueError:
            continue
        if v > 0:
            out.append(v)
    return out or [0.06, 0.1, 0.14, 0.2]


def run_cadence_replay(
    sender: socket.socket,
    listeners: Dict[int, socket.socket],
    total_seconds: float,
    intervals: List[float],
) -> List[Tuple[str, int, bytes]]:
    print(f"\nCADENCE replay ({total_seconds:.1f}s):")
    print(f"  Intervals: {', '.join(f'{x:.3f}' for x in intervals)}")

    all_rows: List[Tuple[str, int, bytes]] = []
    if total_seconds <= 0:
        return all_rows

    slice_seconds = max(0.5, total_seconds / max(1, len(intervals)))
    best = (0, 0, 0.0)  # transitions, unique_fid, interval

    for interval in intervals:
        phase_end = time.monotonic() + slice_seconds
        phase_rows: List[Tuple[str, int, bytes]] = []
        phase_fids: List[int] = []

        while time.monotonic() < phase_end:
            sender.sendto(START_STREAM, (DRONE_GATEWAY, 8800))
            for payload in CADENCE_PAYLOADS:
                sender.sendto(payload, (DRONE_GATEWAY, 8800))
            rows = recv_window(sender, listeners, min(0.10, interval))
            phase_rows.extend(rows)
            for _, _, data in rows:
                if len(data) >= 56 and data[:2] == b"\x93\x01":
                    phase_fids.append(int.from_bytes(data[16:18], "little"))
            all_rows.extend(rows)
            time.sleep(interval)

        transitions = sum(1 for i in range(1, len(phase_fids)) if phase_fids[i] != phase_fids[i - 1])
        unique_fid = len(set(phase_fids))
        count_9301 = sum(1 for _, _, d in phase_rows if len(d) >= 56 and d[:2] == b"\x93\x01")
        print(
            f"  interval={interval:.3f}s: rx={len(phase_rows)} 93pkt={count_9301} "
            f"fid_unique={unique_fid} transitions={transitions}"
        )
        if (transitions, unique_fid) > (best[0], best[1]):
            best = (transitions, unique_fid, interval)

    print(f"  Best interval: {best[2]:.3f}s (fid_transitions={best[0]}, fid_unique={best[1]})")
    return all_rows


def run_connect_bootstrap(
    sender: socket.socket,
    listeners: Dict[int, socket.socket],
    cycles: int,
    stage_delay: float,
) -> List[Tuple[str, int, bytes]]:
    rows_all: List[Tuple[str, int, bytes]] = []
    for i in range(cycles):
        print(f"  Bootstrap cycle {i + 1}/{cycles}")
        for stage in BOOTSTRAP_STAGES:
            name = str(stage["name"])
            payloads = list(stage["payloads"])
            wait_time = float(stage["wait"]) + stage_delay
            sent = 0
            sent += send_payload_set(sender, DRONE_GATEWAY, BOOTSTRAP_PORTS, payloads)
            sent += send_payload_set(sender, CAMERA_IP, BOOTSTRAP_PORTS, payloads)
            rows = recv_window(sender, listeners, wait_time)
            rows_all.extend(rows)
            print(f"    Stage {name}: sent={sent}")
            summarize_stage(name, rows)
            time.sleep(max(0.01, stage_delay))
    return rows_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe lxPro handshake path")
    parser.add_argument("--bind-ip", default="", help="Local bind IP on Drone-XXXXXX network")
    parser.add_argument("--add-route", action="store_true", help="Add 192.168.100.0/24 route via 192.168.169.1")
    parser.add_argument("--cycles", type=int, default=8, help="Probe send/receive cycles")
    parser.add_argument("--cycle-wait", type=float, default=0.35, help="Seconds to receive after each cycle")
    parser.add_argument(
        "--connect-bootstrap",
        action="store_true",
        help="Run staged Connect(0)-style bootstrap sequence before summaries",
    )
    parser.add_argument(
        "--stage-delay",
        type=float,
        default=0.06,
        help="Inter-stage delay (seconds) for bootstrap mode",
    )
    parser.add_argument("--no-tcp", action="store_true", help="Skip TCP connect_ex probes")
    parser.add_argument(
        "--request-pump-seconds",
        type=float,
        default=0.0,
        help="After probing, run REQUEST_A/B pump for N seconds (0=disabled)",
    )
    parser.add_argument(
        "--request-frame-timeout",
        type=float,
        default=0.08,
        help="Watchdog timeout seconds before resending frame request",
    )
    parser.add_argument(
        "--request-max-retries",
        type=int,
        default=5,
        help="Max retries per frame before drop/advance",
    )
    parser.add_argument(
        "--request-prime-seconds",
        type=float,
        default=0.6,
        help="Prime stream-kick seconds before request watchdog loop",
    )
    parser.add_argument(
        "--cadence-replay",
        action="store_true",
        help="Sweep control cadence intervals and measure frame_id progression",
    )
    parser.add_argument(
        "--cadence-seconds",
        type=float,
        default=8.0,
        help="Total seconds for cadence replay sweep",
    )
    parser.add_argument(
        "--cadence-intervals",
        default="0.06,0.10,0.14,0.20",
        help="Comma-separated cadence intervals in seconds",
    )
    args = parser.parse_args()

    bind_ip = args.bind_ip or find_drone_interface()
    if not bind_ip:
        print("No 192.168.169.x interface found. Connect to drone WiFi first.")
        return

    print("=" * 68)
    print("lxPro Handshake Probe")
    print("=" * 68)
    print(f"  Local drone interface IP: {bind_ip}")

    if_index = get_interface_index_for_ip(bind_ip)
    if if_index is not None:
        print(f"  Interface index: {if_index}")

    if route_exists():
        print(f"  Route OK: {CAMERA_SUBNET}/24 via {DRONE_GATEWAY}")
    elif args.add_route:
        if not is_admin():
            print("  Cannot add route: run elevated for --add-route")
        else:
            ok = add_route(if_index)
            print(f"  Route add attempt: {'OK' if ok else 'FAILED'}")
            print(f"  Route verify: {'OK' if route_exists() else 'MISSING'}")
    else:
        print("  Route missing. Use --add-route for direct camera probing.")

    rlines = route_lines()
    if rlines:
        print("  Route table matches for 192.168.100.*:")
        for line in rlines:
            print(f"    {line}")

    sender = make_udp_socket(bind_ip)
    listeners = make_listeners(bind_ip, DEFAULT_PORTS)
    print(f"  Sender socket: {sender.getsockname()}")
    print(f"  UDP listeners opened: {len(listeners)} ports")

    all_rows: List[Tuple[str, int, bytes]] = []
    if args.connect_bootstrap:
        all_rows.extend(run_connect_bootstrap(sender, listeners, args.cycles, args.stage_delay))
    else:
        for i in range(args.cycles):
            send_udp_probes(sender, DRONE_GATEWAY, DEFAULT_PORTS)
            send_udp_probes(sender, CAMERA_IP, DEFAULT_PORTS)
            rows = recv_window(sender, listeners, args.cycle_wait)
            all_rows.extend(rows)
            print(f"  Cycle {i + 1}/{args.cycles}: rx={len(rows)}")

    print("\nUDP summary:")
    summarize(all_rows)
    analyze_9301(all_rows)

    if args.cadence_replay:
        cadence_rows = run_cadence_replay(
            sender,
            listeners,
            args.cadence_seconds,
            parse_intervals(args.cadence_intervals),
        )
        print("\nCADENCE summary:")
        summarize(cadence_rows)
        analyze_9301(cadence_rows)

    if args.request_pump_seconds > 0:
        run_request_pump(
            sender,
            listeners,
            bind_ip,
            args.request_pump_seconds,
            args.request_frame_timeout,
            max(1, args.request_max_retries),
            max(0.0, args.request_prime_seconds),
        )

    if not args.no_tcp:
        print("\nTCP summary:")
        cam = tcp_probe(bind_ip, CAMERA_IP, DEFAULT_PORTS)
        gw = tcp_probe(bind_ip, DRONE_GATEWAY, DEFAULT_PORTS)
        interesting = {0, 10061}
        cam_hit = [(p, rc) for p, rc in cam if rc in interesting]
        gw_hit = [(p, rc) for p, rc in gw if rc in interesting]
        print(f"  Camera interesting TCP results (0=open,10061=refused): {cam_hit or 'none'}")
        print(f"  Gateway interesting TCP results (0=open,10061=refused): {gw_hit or 'none'}")

    sender.close()
    for lsock in listeners.values():
        lsock.close()


if __name__ == "__main__":
    main()
