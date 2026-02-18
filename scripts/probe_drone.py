#!/usr/bin/env python3
"""
Drone Protocol Probe

Tests basic network connectivity, diagnoses Windows Firewall issues,
then sends various protocol packets to the drone and logs all responses.

Usage:
    python scripts/probe_drone.py [--drone-ip 192.168.169.1] [--bind-ip 192.168.169.5]
    python scripts/probe_drone.py --fix-firewall   # attempt to add firewall rule (needs admin)

If no IPs given, tries auto-detection from the network adapter.
"""

import argparse
import ctypes
import ipaddress
import os
import socket
import subprocess
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def is_admin() -> bool:
    """Check if the script is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def create_udp_socket(bind_ip: str = "", timeout: float = 2.0) -> socket.socket:
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
    sock.bind((bind_ip, 0))
    sock.settimeout(timeout)
    return sock


def recv_all(sock: socket.socket, duration: float = 2.0):
    """Receive all packets for the given duration."""
    packets = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
            packets.append((data, addr, time.monotonic()))
        except socket.timeout:
            continue
        except ConnectionResetError:
            continue
    return packets


def dump_packets(packets, label: str):
    if not packets:
        print(f"  {label}: NO RESPONSE")
        return
    print(f"  {label}: {len(packets)} packet(s)")
    for i, (data, addr, ts) in enumerate(packets[:10]):
        head = data[:32].hex(" ")
        print(f"    [{i}] {len(data)} bytes from {addr}  head={head}")
        if len(data) >= 2:
            if data[:2] == b"\x40\x40":
                print(f"         ^ S2x sync bytes detected!")
            if data[0] == 0xef:
                print(f"         ^ WiFi-UAV header (0xEF) detected!")
            if data[:2] == b"\xff\xd8":
                print(f"         ^ JPEG SOI marker detected!")
    if len(packets) > 10:
        print(f"    ... and {len(packets) - 10} more")


# ──────────────────────────────────────────────────────────
# Phase 0: Basic connectivity
# ──────────────────────────────────────────────────────────

def probe_connectivity(drone_ip: str, bind_ip: str):
    """Test basic network connectivity: ping, ARP, TCP scan."""
    print(f"\n{'='*60}")
    print(f"PHASE 0: BASIC CONNECTIVITY  ->  {drone_ip}")
    print(f"{'='*60}")

    # 1. Ping
    print(f"\n  [1] Ping {drone_ip} (4 packets)...")
    try:
        result = subprocess.run(
            ["ping", "-n", "4", "-w", "1000", drone_ip],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and ("received" in line.lower() or "lost" in line.lower()
                         or "average" in line.lower() or "packets" in line.lower()):
                print(f"    {line}")
        if result.returncode != 0:
            print(f"    PING FAILED (rc={result.returncode})")
        else:
            print(f"    PING OK")
    except Exception as e:
        print(f"    Ping error: {e}")

    # 2. ARP table check
    print(f"\n  [2] ARP table for {drone_ip}...")
    try:
        result = subprocess.run(
            ["arp", "-a", drone_ip],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if drone_ip in line or "dynamic" in line.lower() or "static" in line.lower():
                print(f"    {line}")
        if not result.stdout.strip():
            print(f"    No ARP entry for {drone_ip}")
    except Exception as e:
        print(f"    ARP check error: {e}")

    # 3. Quick TCP scan (reduced — just the most likely)
    print(f"\n  [3] TCP port scan (key ports)...")
    tcp_ports = [80, 554, 1234, 7070, 7099, 8080, 8800, 8888]
    open_ports = []
    for port in tcp_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if bind_ip:
                s.bind((bind_ip, 0))
            result = s.connect_ex((drone_ip, port))
            if result == 0:
                open_ports.append(port)
                print(f"    TCP {port}: OPEN")
            s.close()
        except Exception:
            pass
    if not open_ports:
        print(f"    No open TCP ports (tried {len(tcp_ports)} ports)")


# ──────────────────────────────────────────────────────────
# Phase 0.5: Firewall diagnostics & fix
# ──────────────────────────────────────────────────────────

def _get_python_exe() -> str:
    """Get the path to the Python executable."""
    return sys.executable


def diagnose_firewall(drone_ip: str, bind_ip: str, fix: bool = False):
    """Comprehensive Windows Firewall diagnostics."""
    print(f"\n{'='*60}")
    print(f"PHASE 0.5: WINDOWS FIREWALL DIAGNOSTICS")
    print(f"{'='*60}")

    python_exe = _get_python_exe()
    print(f"\n  Python executable: {python_exe}")
    print(f"  Running as admin: {is_admin()}")

    # 1. Show ALL profiles
    print(f"\n  [1] All firewall profiles:")
    for profile in ["domainprofile", "privateprofile", "publicprofile"]:
        try:
            result = subprocess.run(
                ["netsh", "advfirewall", "show", profile],
                capture_output=True, text=True, timeout=5,
            )
            name = profile.replace("profile", "").upper()
            for line in result.stdout.splitlines():
                line = line.strip()
                if "state" in line.lower() or "firewall policy" in line.lower():
                    print(f"    {name:10s}: {line}")
        except Exception:
            pass

    # 2. Which profile is the drone adapter using?
    print(f"\n  [2] Network category for drone adapter...")
    try:
        # Use PowerShell to get network profile for each connection
        ps_cmd = (
            "Get-NetConnectionProfile | "
            "Select-Object -Property Name, InterfaceAlias, NetworkCategory, "
            "IPv4Connectivity | Format-List"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        print(f"    Active network profiles:")
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                print(f"      {line}")
    except Exception as e:
        print(f"    Could not query network profiles: {e}")

    # 3. Check if Python has any firewall rules
    print(f"\n  [3] Firewall rules for Python...")
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=in", "verbose"],
            capture_output=True, text=True, timeout=15,
        )
        # Parse rules looking for python in the program path
        python_rules = []
        current_rule = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Rule Name:"):
                if current_rule:
                    prog = current_rule.get("program", "").lower()
                    if "python" in prog:
                        python_rules.append(current_rule)
                current_rule = {"name": line.split(":", 1)[1].strip()}
            elif ":" in line and current_rule:
                key, _, val = line.partition(":")
                current_rule[key.strip().lower()] = val.strip()
        # Check last rule
        if current_rule:
            prog = current_rule.get("program", "").lower()
            if "python" in prog:
                python_rules.append(current_rule)

        if python_rules:
            print(f"    Found {len(python_rules)} Python inbound rule(s):")
            for rule in python_rules:
                action = rule.get("action", "?")
                enabled = rule.get("enabled", "?")
                profiles = rule.get("profiles", "?")
                program = rule.get("program", "?")
                protocol = rule.get("protocol", "?")
                print(f"      '{rule['name']}'  action={action}  enabled={enabled}  "
                      f"profiles={profiles}  protocol={protocol}")
                print(f"        program={program}")
        else:
            print(f"    NO inbound firewall rules found for Python!")
            print(f"    This is likely WHY UDP responses are blocked.")
            print(f"    The firewall blocks all inbound UDP to python.exe")
    except Exception as e:
        print(f"    Could not check rules: {e}")

    # 4. Check for any BLOCK rules on python
    print(f"\n  [4] Checking for explicit BLOCK rules on Python...")
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=in", "action=block", "verbose"],
            capture_output=True, text=True, timeout=15,
        )
        block_rules = []
        current_rule = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Rule Name:"):
                if current_rule:
                    prog = current_rule.get("program", "").lower()
                    if "python" in prog:
                        block_rules.append(current_rule)
                current_rule = {"name": line.split(":", 1)[1].strip()}
            elif ":" in line and current_rule:
                key, _, val = line.partition(":")
                current_rule[key.strip().lower()] = val.strip()
        if current_rule:
            prog = current_rule.get("program", "").lower()
            if "python" in prog:
                block_rules.append(current_rule)

        if block_rules:
            print(f"    FOUND {len(block_rules)} BLOCK rule(s) for Python!")
            for rule in block_rules:
                print(f"      '{rule['name']}'  profiles={rule.get('profiles', '?')}  "
                      f"protocol={rule.get('protocol', '?')}")
            print(f"    ** These BLOCK rules prevent UDP responses from reaching Python **")
        else:
            print(f"    No explicit block rules for Python (good)")
    except Exception as e:
        print(f"    Could not check block rules: {e}")

    # 5. Attempt to add firewall rule
    if fix:
        print(f"\n  [5] Attempting to add firewall rule...")
        _add_firewall_rule(python_exe)
    else:
        print(f"\n  [5] Firewall fix: skipped (use --fix-firewall to attempt)")
        print(f"      Or manually run as Administrator:")
        print(f'      netsh advfirewall firewall add rule name="TYVYX Drone UDP" '
              f'dir=in action=allow protocol=UDP program="{python_exe}" enable=yes')

    # 6. Quick UDP test after potential fix
    print(f"\n  [6] Quick UDP echo test...")
    _quick_udp_test(drone_ip, bind_ip)


def _add_firewall_rule(python_exe: str):
    """Try to add a Windows Firewall rule allowing inbound UDP for Python."""
    if not is_admin():
        print(f"    NOT running as admin — cannot add firewall rule.")
        print(f"    Re-run this script as Administrator with --fix-firewall")
        print(f"    Or run this in an admin PowerShell:")
        print(f'      netsh advfirewall firewall add rule name="TYVYX Drone UDP" '
              f'dir=in action=allow protocol=UDP program="{python_exe}" enable=yes')
        return

    # Remove old rule if it exists (ignore errors)
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "delete", "rule",
         "name=TYVYX Drone UDP"],
        capture_output=True, timeout=5,
    )

    # Add new rule: allow inbound UDP to Python from any source
    # (drone could be on various subnets)
    result = subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=TYVYX Drone UDP",
         "dir=in", "action=allow", "protocol=UDP",
         f"program={python_exe}",
         "enable=yes", "profile=any"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        print(f"    SUCCESS: Added firewall rule 'TYVYX Drone UDP'")
        print(f"      Allows inbound UDP to {python_exe}")
    else:
        print(f"    FAILED to add rule: {result.stderr.strip()}")

    # Also try to change the drone network from Public to Private
    print(f"\n    Attempting to set drone network to Private...")
    ps_cmd = (
        "Get-NetConnectionProfile | Where-Object { "
        "$_.NetworkCategory -eq 'Public' -and "
        "$_.IPv4Connectivity -ne 'NoTraffic' } | "
        "Set-NetConnectionProfile -NetworkCategory Private"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        print(f"    Set Public network(s) to Private")
    else:
        err = result.stderr.strip()
        if err:
            print(f"    Could not change network profile: {err}")
        else:
            print(f"    No Public networks to change (or already Private)")


def _quick_udp_test(drone_ip: str, bind_ip: str):
    """Send a packet and see if we get ANY response now."""
    try:
        sock = create_udp_socket(bind_ip, timeout=1.0)
        local = sock.getsockname()
        print(f"    Socket: {local[0]}:{local[1]} -> {drone_ip}:8800")

        # Send START_STREAM
        from tyvyx.utils.wifi_uav_packets import START_STREAM
        sock.sendto(START_STREAM, (drone_ip, 8800))
        # Also try heartbeat
        sock.sendto(bytes([0x01, 0x01]), (drone_ip, 7099))

        pkts = recv_all(sock, 2.0)
        if pkts:
            print(f"    GOT {len(pkts)} RESPONSE(S)!")
            dump_packets(pkts, "UDP responses")
        else:
            print(f"    Still no UDP response. If firewall was just fixed,")
            print(f"    the drone may need a moment. Try again.")
        sock.close()
    except Exception as e:
        print(f"    UDP test error: {e}")


# ──────────────────────────────────────────────────────────
# Phase 1: E88Pro probing
# ──────────────────────────────────────────────────────────

def probe_e88pro(drone_ip: str, port: int, bind_ip: str):
    """Test E88Pro protocol commands."""
    print(f"\n{'='*60}")
    print(f"PHASE 1: E88Pro PROTOCOL  ->  {drone_ip}:{port}")
    print(f"{'='*60}")

    sock = create_udp_socket(bind_ip)
    local = sock.getsockname()
    print(f"  Local socket: {local[0]}:{local[1]}")

    # 1. Heartbeat
    print(f"\n  [1] Heartbeat [01 01]...")
    sock.sendto(bytes([0x01, 0x01]), (drone_ip, port))
    pkts = recv_all(sock, 1.0)
    dump_packets(pkts, "Heartbeat response")

    # 2. Init E88Pro
    print(f"\n  [2] Init E88Pro [08 01]...")
    sock.sendto(bytes([0x08, 0x01]), (drone_ip, port))
    pkts = recv_all(sock, 1.0)
    dump_packets(pkts, "Init response")

    # 3. FH-style init: 0x08 + client IP
    print(f"\n  [3] FH-style init [08 + client IP]...")
    client_ip = bind_ip or local[0]
    fh_payload = b"\x08" + ipaddress.IPv4Address(client_ip).packed
    print(f"       payload: {fh_payload.hex(' ')}")
    sock.sendto(fh_payload, (drone_ip, port))
    pkts = recv_all(sock, 1.0)
    dump_packets(pkts, "FH init response")

    # 4. Camera select (front)
    print(f"\n  [4] Camera select front [06 01]...")
    sock.sendto(bytes([0x06, 0x01]), (drone_ip, port))
    pkts = recv_all(sock, 1.0)
    dump_packets(pkts, "Camera select response")

    # 5. Start video variants
    for label, cmd in [
        ("[08 02 01 41 01]", bytes([0x08, 0x02, 0x01, 0x41, 0x01])),
        ("[08 02]", bytes([0x08, 0x02])),
    ]:
        print(f"\n  [5] Start video {label}...")
        sock.sendto(cmd, (drone_ip, port))
        pkts = recv_all(sock, 1.0)
        dump_packets(pkts, f"Start video response")

    sock.close()


# ──────────────────────────────────────────────────────────
# Phase 2: WiFi-UAV probing
# ──────────────────────────────────────────────────────────

def probe_wifi_uav(drone_ip: str, port: int, bind_ip: str):
    """Test WiFi-UAV protocol commands."""
    print(f"\n{'='*60}")
    print(f"PHASE 2: WiFi-UAV PROTOCOL  ->  {drone_ip}:{port}")
    print(f"{'='*60}")

    sock = create_udp_socket(bind_ip)
    local = sock.getsockname()
    print(f"  Local socket: {local[0]}:{local[1]}")

    from tyvyx.utils.wifi_uav_packets import START_STREAM, REQUEST_A, REQUEST_B

    # 1. START_STREAM
    print(f"\n  [1] START_STREAM [ef 00 04 00]...")
    sock.sendto(START_STREAM, (drone_ip, port))
    pkts = recv_all(sock, 1.5)
    dump_packets(pkts, "START_STREAM response")

    # 2. Frame request 0
    print(f"\n  [2] REQUEST_A + REQUEST_B (frame 0)...")
    rqst_a = bytearray(REQUEST_A)
    rqst_a[12], rqst_a[13] = 0, 0
    rqst_b = bytearray(REQUEST_B)
    for base in (12, 88, 107):
        rqst_b[base] = 0
        rqst_b[base + 1] = 0
    sock.sendto(rqst_a, (drone_ip, port))
    sock.sendto(rqst_b, (drone_ip, port))
    pkts = recv_all(sock, 2.0)
    dump_packets(pkts, "Frame request response")

    # 3. Warmup sequence
    print(f"\n  [3] Full warmup (5 cycles, 300ms each)...")
    all_pkts = []
    for i in range(5):
        sock.sendto(START_STREAM, (drone_ip, port))
        time.sleep(0.05)
        sock.sendto(rqst_a, (drone_ip, port))
        sock.sendto(rqst_b, (drone_ip, port))
        pkts = recv_all(sock, 0.3)
        all_pkts.extend(pkts)
    dump_packets(all_pkts, "Warmup sequence responses")

    sock.close()


# ──────────────────────────────────────────────────────────
# Phase 2.5: Send commands to 8800, listen for video on 1234
# ──────────────────────────────────────────────────────────

def probe_video_port_1234(drone_ip: str, bind_ip: str):
    """Send START_STREAM to port 8800, listen for video on port 1234."""
    print(f"\n{'='*60}")
    print(f"PHASE 2.5: VIDEO ON PORT 1234  (send to 8800, recv on 1234)")
    print(f"{'='*60}")

    from tyvyx.utils.wifi_uav_packets import START_STREAM, REQUEST_A, REQUEST_B

    # Open listener on port 1234 FIRST
    try:
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind((bind_ip, 1234))
        listen_sock.settimeout(0.5)
        print(f"  Listening on {listen_sock.getsockname()} for video...")
    except OSError as e:
        print(f"  Cannot bind to port 1234: {e}")
        return

    # Open sender socket to port 8800
    send_sock = create_udp_socket(bind_ip, timeout=1.0)
    print(f"  Sending from {send_sock.getsockname()} to {drone_ip}:8800")

    # Prepare frame request
    rqst_a = bytearray(REQUEST_A)
    rqst_a[12], rqst_a[13] = 0, 0
    rqst_b = bytearray(REQUEST_B)
    for base in (12, 88, 107):
        rqst_b[base] = 0
        rqst_b[base + 1] = 0

    # Send START_STREAM + frame requests, listen on 1234
    print(f"\n  [1] Sending START_STREAM + frame requests (5 cycles)...")
    all_pkts = []
    for i in range(5):
        send_sock.sendto(START_STREAM, (drone_ip, 8800))
        time.sleep(0.05)
        send_sock.sendto(rqst_a, (drone_ip, 8800))
        send_sock.sendto(rqst_b, (drone_ip, 8800))

        # Check both sockets for responses
        for _ in range(10):
            for label, sock in [("port-1234", listen_sock), ("send-sock", send_sock)]:
                try:
                    data, addr = sock.recvfrom(65535)
                    all_pkts.append((data, addr, time.monotonic()))
                    head = data[:32].hex(" ")
                    print(f"    >> {label}: {len(data)} bytes from {addr}  head={head}")
                except (socket.timeout, ConnectionResetError):
                    pass
        time.sleep(0.1)

    if all_pkts:
        dump_packets(all_pkts, "Video port 1234 responses")
    else:
        print(f"  No video data on port 1234 or send socket")

    # Also try just listening on 1234 for a few more seconds
    print(f"\n  [2] Passive listen on port 1234 (3s)...")
    pkts = recv_all(listen_sock, 3.0)
    dump_packets(pkts, "Passive port 1234")

    send_sock.close()
    listen_sock.close()


# ──────────────────────────────────────────────────────────
# Phase 3: Listen for spontaneous traffic
# ──────────────────────────────────────────────────────────

def probe_listen_all(drone_ip: str, bind_ip: str):
    """Listen for any spontaneous traffic from the drone."""
    print(f"\n{'='*60}")
    print(f"PHASE 3: LISTENING FOR SPONTANEOUS TRAFFIC (5s)")
    print(f"{'='*60}")

    ports = [1234, 7070, 7099, 8080, 8800, 8888, 40000, 6100, 4660]
    sockets = {}

    for p in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((bind_ip, p))
            s.settimeout(0.1)
            sockets[p] = s
        except OSError as e:
            print(f"  Port {p}: cannot bind ({e})")

    deadline = time.monotonic() + 5.0
    received = {p: [] for p in sockets}

    while time.monotonic() < deadline:
        for p, s in sockets.items():
            try:
                data, addr = s.recvfrom(65535)
                received[p].append((data, addr, time.monotonic()))
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue

    for p in sorted(sockets):
        pkts = received[p]
        if pkts:
            dump_packets(pkts, f"Port {p}")
        else:
            print(f"  Port {p}: nothing received")

    for s in sockets.values():
        s.close()


# ──────────────────────────────────────────────────────────
# Auto-detect & main
# ──────────────────────────────────────────────────────────

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


def main():
    parser = argparse.ArgumentParser(description="Probe drone video protocol")
    parser.add_argument("--drone-ip", default="", help="Drone IP (auto-detect if empty)")
    parser.add_argument("--bind-ip", default="", help="Local bind IP (auto-detect if empty)")
    parser.add_argument("--port", type=int, default=0, help="Drone port (try all if 0)")
    parser.add_argument("--fix-firewall", action="store_true",
                        help="Attempt to add firewall rule (needs admin)")
    parser.add_argument("--skip-probes", action="store_true",
                        help="Only run firewall diagnostics, skip protocol probes")
    args = parser.parse_args()

    drone_ip = args.drone_ip
    bind_ip = args.bind_ip

    if not drone_ip or not bind_ip:
        print("Auto-detecting drone adapter...")
        auto_ip, auto_bind = auto_detect()
        if auto_ip and not drone_ip:
            drone_ip = auto_ip
            print(f"  Drone IP (gateway): {drone_ip}")
        if auto_bind and not bind_ip:
            bind_ip = auto_bind
            print(f"  Bind IP (local):    {bind_ip}")

    if not drone_ip:
        print("ERROR: Could not detect drone IP. Provide --drone-ip.")
        sys.exit(1)

    print(f"\nDrone: {drone_ip}  Bind: {bind_ip or '(all interfaces)'}")
    print(f"Time: {time.strftime('%H:%M:%S')}")

    # Phase 0: Basic connectivity
    probe_connectivity(drone_ip, bind_ip)

    # Phase 0.5: Firewall diagnostics (always) + fix (if --fix-firewall)
    diagnose_firewall(drone_ip, bind_ip, fix=args.fix_firewall)

    if args.skip_probes:
        print(f"\n{'='*60}")
        print("SKIPPING PROTOCOL PROBES (--skip-probes)")
        print(f"{'='*60}")
        return

    # Determine which ports to probe
    ports = [args.port] if args.port else [8800, 7099]

    # Phase 1: E88Pro
    for port in ports:
        probe_e88pro(drone_ip, port, bind_ip)

    # Phase 2: WiFi-UAV
    for port in ports:
        probe_wifi_uav(drone_ip, port, bind_ip)

    # Phase 2.5: Send to 8800, listen on 1234
    probe_video_port_1234(drone_ip, bind_ip)

    # Phase 3: Listen for spontaneous traffic
    probe_listen_all(drone_ip, bind_ip)

    print(f"\n{'='*60}")
    print("PROBE COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
