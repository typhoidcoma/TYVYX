"""Probe the JieLi camera module at 192.168.100.1.

The K417 drone has a dual-module architecture:
  - BL608 Flight Controller: 192.168.169.1 (WiFi AP, MJPEG video, RC control)
  - JieLi Camera Module:     192.168.100.1 (H.264 video, lxPro SDK)

The BL608 acts as a gateway/router between the WiFi subnet (192.168.169.x)
and the internal camera subnet (192.168.100.x).  The liblxPro.so native
library connects directly to 192.168.100.1.

This script:
  1. Verifies drone WiFi connectivity
  2. Ensures Windows has a route to 192.168.100.0/24 via the BL608 gateway
  3. Probes the camera module on common JieLi ports (UDP + TCP)
  4. Attempts a basic lxPro Cek (heartbeat) handshake
  5. Captures any responses for protocol analysis

Usage:
  python scripts/probe_camera.py [--bind-ip IP] [--add-route]
"""

import argparse
import ctypes
import re
import socket
import subprocess
import sys
import time
from typing import List, Optional, Tuple

# Network constants
DRONE_GATEWAY = "192.168.169.1"
CAMERA_IP = "192.168.100.1"
CAMERA_SUBNET = "192.168.100.0"
CAMERA_MASK = "255.255.255.0"

# Common JieLi camera ports (from reverse engineering various drone apps)
JIELI_UDP_PORTS = [
    2020,   # Common JieLi data port
    2021,   # Common JieLi stream port
    6220,   # FHD camera drones
    6221,   # FHD camera drones alt
    8080,   # HTTP
    8090,   # alt HTTP
    8800,   # match BL608 video port
    8801,   # match BL608 control port
    9090,   # common IoT
    4040,   # common camera
    3333,   # common
    5555,   # common ADB
    7060,   # common camera
    7070,   # common camera
    49152,  # IANA dynamic range start
]

JIELI_TCP_PORTS = [
    80,     # HTTP
    554,    # RTSP
    2020,   # JieLi data
    8080,   # HTTP alt
    8554,   # RTSP alt
]


def find_drone_interface():
    # type: () -> Optional[str]
    """Find the local IP of the network adapter connected to the drone."""
    try:
        result = subprocess.run(
            ["ipconfig", "/all"], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return None

    lines = result.stdout.split("\n")
    for line in lines:
        # Look for IPv4 address lines
        if "IPv4" in line and "192.168.169" in line:
            # Extract IP
            parts = line.split(":")
            if len(parts) >= 2:
                ip = parts[-1].strip().rstrip("(Preferred)")
                ip = ip.replace("(Preferred)", "").strip()
                return ip

        # Also check for any 192.168.169.x in the line
        match = re.search(r"192\.168\.169\.(\d+)", line)
        if match:
            return "192.168.169." + match.group(1)

    return None


def check_route_exists():
    # type: () -> bool
    """Check if a route to 192.168.100.0/24 exists via the drone gateway."""
    try:
        result = subprocess.run(
            ["route", "print", CAMERA_IP],
            capture_output=True, text=True, timeout=5
        )
        return "192.168.100" in result.stdout and "192.168.169.1" in result.stdout
    except Exception:
        return False


def is_admin():
    # type: () -> bool
    """Return True if running with Administrator privileges."""
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_interface_index_for_ip(bind_ip):
    # type: (str) -> Optional[int]
    """Return Windows interface index that owns bind_ip."""
    if sys.platform != "win32" or not bind_ip:
        return None
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-NetIPAddress -AddressFamily IPv4 "
                f"-IPAddress '{bind_ip}' | "
                "Select-Object -First 1 -ExpandProperty InterfaceIndex"
            ),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        value = result.stdout.strip()
        return int(value) if value.isdigit() else None
    except Exception:
        return None


def add_route(if_index=None):
    # type: (Optional[int]) -> bool
    """Add a route for 192.168.100.0/24 via the drone gateway.

    Requires admin privileges on Windows.
    """
    extra = f" if {if_index}" if if_index else ""
    print(f"  Adding route: {CAMERA_SUBNET}/24 via {DRONE_GATEWAY}{extra}")
    try:
        cmd = ["route", "add", CAMERA_SUBNET, "mask", CAMERA_MASK, DRONE_GATEWAY]
        if if_index is not None:
            cmd.extend(["if", str(if_index)])
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print("  Route added successfully")
            return True
        combined_output = f"{result.stdout}\n{result.stderr}".lower()
        if "object already exists" in combined_output:
            print("  Route already exists")
            return True
        else:
            print(f"  Route add failed: {result.stderr.strip()}")
            print("  Try running as Administrator, or add manually:")
            print(f"    route add {CAMERA_SUBNET} mask {CAMERA_MASK} {DRONE_GATEWAY}")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def create_udp_socket(bind_ip=""):
    # type: (str) -> socket.socket
    """Create a UDP socket bound to the drone WiFi interface."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Disable Windows ICMP port-unreachable errors
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


def probe_udp(bind_ip, camera_ip, ports):
    # type: (str, str, List[int]) -> List[Tuple[int, bytes, tuple]]
    """Send UDP probes to camera_ip on given ports, collect responses."""
    print(f"\n  === UDP Probes to {camera_ip} ===")
    sock = create_udp_socket(bind_ip)
    local_addr = sock.getsockname()
    print(f"  Local socket: {local_addr}")

    # Various probe payloads
    probes = [
        b"\x00\x00\x00\x00",           # Null probe
        b"\x01\x00\x00\x00",           # Simple probe
        b"\xff\xff\xff\xff",           # Broadcast-style
        b"\x00\x01",                    # Minimal
        b"\x93\x01",                    # Our 0x93 magic (in case camera speaks it too)
        b"\xef\x00\x04\x00",           # START_STREAM (BL608 command, in case forwarded)
    ]

    responses = []  # type: List[Tuple[int, bytes, tuple]]

    for port in ports:
        for probe in probes:
            try:
                sock.sendto(probe, (camera_ip, port))
            except OSError as e:
                if "No route" in str(e) or "10065" in str(e):
                    print(f"  Port {port}: NO ROUTE TO HOST - need to add route")
                    sock.close()
                    return responses
                elif "unreachable" in str(e).lower():
                    print(f"  Port {port}: Network unreachable")
                    sock.close()
                    return responses

    print(f"  Sent {len(ports) * len(probes)} probes across {len(ports)} ports")
    print(f"  Listening for responses (3s)...")

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
            port = addr[1]
            responses.append((port, data, addr))
            print(f"  RESPONSE from {addr}: {len(data)} bytes")
            print(f"    hex: {data[:64].hex(' ')}")
        except socket.timeout:
            continue
        except ConnectionResetError:
            # ICMP port unreachable — host IS reachable, port closed
            print(f"  Got ICMP unreachable — {camera_ip} IS reachable (port closed)")
            continue

    sock.close()

    if not responses:
        print(f"  No UDP responses from {camera_ip}")
    return responses


def probe_tcp(bind_ip, camera_ip, ports):
    # type: (str, str, List[int]) -> List[Tuple[int, str]]
    """Try TCP connections to camera_ip on given ports."""
    print(f"\n  === TCP Probes to {camera_ip} ===")
    results = []  # type: List[Tuple[int, str]]

    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        if bind_ip:
            try:
                sock.bind((bind_ip, 0))
            except OSError:
                pass

        try:
            result = sock.connect_ex((camera_ip, port))
            if result == 0:
                status = "OPEN"
                # Try to read banner
                try:
                    sock.settimeout(1.0)
                    banner = sock.recv(1024)
                    status = f"OPEN - banner: {banner[:64].hex(' ')}"
                except Exception:
                    pass
            elif result == 10061:
                status = "REFUSED (host reachable, port closed)"
            elif result == 10060:
                status = "TIMEOUT"
            elif result == 10035:
                status = "WOULD BLOCK (likely filtered or no route)"
            elif result == 10065:
                status = "NO ROUTE"
            elif result == 10051:
                status = "NETWORK UNREACHABLE"
            else:
                status = f"ERROR ({result})"
        except Exception as e:
            status = f"EXCEPTION: {e}"
        finally:
            sock.close()

        results.append((port, status))
        indicator = "+" if "OPEN" in status or "REFUSED" in status else "-"
        print(f"  [{indicator}] TCP {camera_ip}:{port} — {status}")

    return results


def probe_ping(camera_ip):
    # type: (str) -> bool
    """Ping the camera IP to check basic reachability."""
    print(f"\n  === ICMP Ping to {camera_ip} ===")
    try:
        result = subprocess.run(
            ["ping", "-n", "3", "-w", "1000", camera_ip],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout
        print(f"  {output.strip().split(chr(10))[-1]}")

        if "TTL=" in output:
            print(f"  PING SUCCESS — {camera_ip} is reachable!")
            return True
        elif "unreachable" in output.lower():
            print(f"  Destination unreachable (but gateway forwarded the request)")
            return False
        else:
            print(f"  No response")
            return False
    except Exception as e:
        print(f"  Ping error: {e}")
        return False


def probe_gateway_forwarding(bind_ip):
    # type: (str) -> None
    """Test if the BL608 gateway forwards to the camera subnet.

    Send UDP to 192.168.169.1 on unusual ports that might be forwarded
    to the camera module internally.
    """
    print(f"\n  === Gateway Forwarding Test ===")
    print(f"  Testing if BL608 at {DRONE_GATEWAY} forwards to camera module")

    sock = create_udp_socket(bind_ip)

    # The lxPro library might connect to the gateway IP, not the camera IP directly
    # Test if the BL608 responds to lxPro-style commands on specific ports
    test_ports = [2020, 2021, 6220, 6221, 8080, 3333, 4040]

    for port in test_ports:
        try:
            # Simple probes
            sock.sendto(b"\x00\x00\x00\x00", (DRONE_GATEWAY, port))
            sock.sendto(b"\x01\x00\x00\x00", (DRONE_GATEWAY, port))
        except OSError:
            pass

    print(f"  Sent probes to {DRONE_GATEWAY} on ports {test_ports}")
    print(f"  Listening for responses (2s)...")

    deadline = time.monotonic() + 2.0
    got_response = False
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
            # Filter out known BL608 video stream packets
            if data[:2] == b"\x93\x01":
                continue
            print(f"  RESPONSE from {addr}: {len(data)} bytes")
            print(f"    hex: {data[:64].hex(' ')}")
            got_response = True
        except socket.timeout:
            continue
        except ConnectionResetError:
            continue

    sock.close()
    if not got_response:
        print(f"  No responses from gateway forwarding test")


def main():
    parser = argparse.ArgumentParser(description="Probe JieLi camera module at 192.168.100.1")
    parser.add_argument("--bind-ip", default="", help="Local IP to bind (auto-detect if empty)")
    parser.add_argument("--add-route", action="store_true", help="Add route for 192.168.100.0/24 via drone gateway")
    parser.add_argument("--gateway-only", action="store_true", help="Only probe via gateway (skip direct camera probe)")
    args = parser.parse_args()

    print("=" * 70)
    print("JieLi Camera Module Probe")
    print("=" * 70)

    # Step 1: Find drone WiFi interface
    bind_ip = args.bind_ip
    if not bind_ip:
        bind_ip = find_drone_interface()
        if bind_ip:
            print(f"\n  Auto-detected drone WiFi adapter: {bind_ip}")
        else:
            print("\n  WARNING: Not connected to drone WiFi (no 192.168.169.x interface found)")
            print("  Connect to the drone's WiFi first (SSID: Drone-XXXXXX)")
            return

    # Step 2: Check/add route
    print(f"\n{'=' * 70}")
    print("ROUTING CHECK")
    print("=" * 70)

    if_index = get_interface_index_for_ip(bind_ip)
    if if_index is not None:
        print(f"  Drone WiFi interface index: {if_index}")
    else:
        print("  Drone WiFi interface index: unknown (route add may use default interface)")

    if check_route_exists():
        print(f"  Route to {CAMERA_SUBNET}/24 via {DRONE_GATEWAY} already exists")
    elif args.add_route:
        if not is_admin():
            print("  Cannot add route: not running as Administrator")
            print(f"  Re-run elevated, or manually: route add {CAMERA_SUBNET} mask {CAMERA_MASK} {DRONE_GATEWAY}")
        else:
            add_route(if_index=if_index)

        if check_route_exists():
            print(f"  Route verification OK: {CAMERA_SUBNET}/24 via {DRONE_GATEWAY}")
        else:
            print(f"  Route verification failed: {CAMERA_SUBNET}/24 not found via {DRONE_GATEWAY}")
    else:
        print(f"  No route to {CAMERA_SUBNET}/24")
        print(f"  Run with --add-route to add, or manually:")
        print(f"    route add {CAMERA_SUBNET} mask {CAMERA_MASK} {DRONE_GATEWAY}")

    # Step 3: Test gateway forwarding first (always works, no routing needed)
    print(f"\n{'=' * 70}")
    print("GATEWAY FORWARDING TEST")
    print("=" * 70)
    probe_gateway_forwarding(bind_ip)

    if args.gateway_only:
        print(f"\n{'=' * 70}")
        print("DONE (gateway-only mode)")
        print("=" * 70)
        return

    # Step 4: Ping camera
    print(f"\n{'=' * 70}")
    print("DIRECT CAMERA PROBE")
    print("=" * 70)
    ping_ok = probe_ping(CAMERA_IP)

    # Step 5: UDP probes
    udp_responses = probe_udp(bind_ip, CAMERA_IP, JIELI_UDP_PORTS)

    # Step 6: TCP probes
    tcp_results = probe_tcp(bind_ip, CAMERA_IP, JIELI_TCP_PORTS)

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"  Ping reachable:  {'YES' if ping_ok else 'NO'}")
    print(f"  UDP responses:   {len(udp_responses)}")
    tcp_open = [p for p, s in tcp_results if "OPEN" in s]
    tcp_refused = [p for p, s in tcp_results if "REFUSED" in s]
    print(f"  TCP ports open:  {tcp_open if tcp_open else 'none'}")
    print(f"  TCP ports refused (host reachable): {tcp_refused if tcp_refused else 'none'}")

    if ping_ok or udp_responses or tcp_open or tcp_refused:
        print(f"\n  CAMERA MODULE IS REACHABLE!")
        print(f"  Next step: reverse-engineer the lxPro Cek handshake protocol")
    else:
        print(f"\n  Camera module NOT directly reachable.")
        print(f"  Possible causes:")
        print(f"    1. No route to 192.168.100.0/24 (run with --add-route)")
        print(f"    2. BL608 doesn't route between subnets")
        print(f"    3. Camera module only accessible via BL608 forwarding")
        print(f"    4. lxPro protocol requires specific handshake before routing is enabled")


if __name__ == "__main__":
    main()
