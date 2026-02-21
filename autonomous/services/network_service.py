"""
WiFi Network Scanner Service

Scans for nearby WiFi networks and identifies likely drone hotspots
based on known SSID naming patterns.

Windows only — uses `netsh wlan` which is available on all modern Windows installs
without any additional packages.
"""

import re
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# SSIDs matching these prefixes are flagged as likely drone networks
DRONE_SSID_PATTERNS = ["HD-", "FHD-", "HD720", "K417", "HD-FPV", "TYVYX", "drone", "Drone-", "UFO", "FLOW"]


@dataclass
class WifiNetwork:
    ssid: str
    signal: int       # 0-100 percent
    security: str     # e.g. "WPA2-Personal", "Open"
    bssid: str = ""
    is_drone: bool = field(init=False)

    def __post_init__(self):
        ssid_upper = self.ssid.upper()
        self.is_drone = any(p.upper() in ssid_upper for p in DRONE_SSID_PATTERNS)


@dataclass
class DroneAdapter:
    """Represents a network adapter connected (or likely connected) to the drone."""
    name: str
    ssid: Optional[str]       # WiFi SSID if detected via WiFi, else None
    state: str                # e.g. "connected", "disconnected"
    local_ip: Optional[str] = None
    gateway_ip: Optional[str] = None  # Default gateway = drone IP
    probe_port: Optional[int] = None  # Port that responded to probe (7099=E88Pro, 8800=WiFi UAV)
    is_drone: bool = field(init=False)

    def __post_init__(self):
        if self.ssid:
            ssid_upper = self.ssid.upper()
            self.is_drone = any(p.upper() in ssid_upper for p in DRONE_SSID_PATTERNS)
        else:
            self.is_drone = False


def _netsh_available() -> bool:
    return shutil.which("netsh") is not None


def scan_wifi_networks() -> List[WifiNetwork]:
    """
    Scan available WiFi networks using netsh (Windows).

    Returns a list of WifiNetwork objects sorted by signal strength (strongest first),
    with drone-likely SSIDs first within that ordering.
    """
    if not _netsh_available():
        logger.warning("netsh not available — WiFi scanning only supported on Windows")
        return []

    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        logger.error("netsh wlan scan timed out")
        return []
    except Exception as e:
        logger.error(f"Failed to run netsh: {e}")
        return []

    return _parse_netsh_networks(output)


def _parse_netsh_networks(output: str) -> List[WifiNetwork]:
    """Parse `netsh wlan show networks mode=bssid` output into WifiNetwork list."""
    networks: List[WifiNetwork] = []
    current: dict = {}

    for line in output.splitlines():
        line = line.strip()

        # New network block: "SSID 1 : MyNetwork"
        m = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line)
        if m:
            if current.get("ssid"):
                networks.append(_make_network(current))
            current = {"ssid": m.group(1).strip(), "signal": 0, "security": "Unknown", "bssid": ""}
            continue

        if not current:
            continue

        # Signal: "Signal : 78%"
        m = re.match(r"^Signal\s*:\s*(\d+)%", line)
        if m:
            current["signal"] = int(m.group(1))
            continue

        # Authentication / security: "Authentication : WPA2-Personal"
        m = re.match(r"^Authentication\s*:\s*(.+)$", line)
        if m:
            current["security"] = m.group(1).strip()
            continue

        # BSSID: "BSSID 1 : aa:bb:cc:dd:ee:ff"
        m = re.match(r"^BSSID\s+\d+\s*:\s*(.+)$", line)
        if m and not current.get("bssid"):
            current["bssid"] = m.group(1).strip()
            continue

    # Flush last block
    if current.get("ssid"):
        networks.append(_make_network(current))

    # Sort: drone networks first, then by signal descending
    networks.sort(key=lambda n: (not n.is_drone, -n.signal))
    return networks


def _make_network(d: dict) -> WifiNetwork:
    return WifiNetwork(
        ssid=d.get("ssid", ""),
        signal=d.get("signal", 0),
        security=d.get("security", "Unknown"),
        bssid=d.get("bssid", ""),
    )


def get_all_wifi_interfaces() -> List[DroneAdapter]:
    """Enumerate all WiFi adapters and their connection state via netsh."""
    if not _netsh_available():
        return []

    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        logger.error(f"Failed to enumerate WiFi interfaces: {e}")
        return []

    return _parse_wlan_interfaces(result.stdout)


def _parse_wlan_interfaces(output: str) -> List[DroneAdapter]:
    """Parse `netsh wlan show interfaces` into per-adapter DroneAdapter list.

    The output contains one block per adapter, separated by blank lines.
    Each block has fields like:
        Name                   : Wi-Fi
        State                  : connected
        SSID                   : K417-ABCDEF
    """
    interfaces: List[DroneAdapter] = []
    current: dict = {}

    for line in output.splitlines():
        stripped = line.strip()

        # Blank line or end-of-block — flush current adapter
        if not stripped:
            if current.get("name"):
                interfaces.append(_make_interface(current))
                current = {}
            continue

        # "Key : Value" format
        m = re.match(r"^(.+?)\s*:\s*(.*)$", stripped)
        if not m:
            continue

        key = m.group(1).strip().lower()
        val = m.group(2).strip()

        if key == "name":
            current["name"] = val
        elif key == "state":
            current["state"] = val.lower()
        elif key == "ssid" and "ssid" not in current:
            # Take first SSID field only (avoid BSSID overwriting)
            current["ssid"] = val

    # Flush last block
    if current.get("name"):
        interfaces.append(_make_interface(current))

    return interfaces


def _make_interface(d: dict) -> DroneAdapter:
    return DroneAdapter(
        name=d.get("name", ""),
        ssid=d.get("ssid") if d.get("state") == "connected" else None,
        state=d.get("state", "disconnected"),
    )


def _get_adapter_info(adapter_name: str) -> tuple:
    """Get the IPv4 address and default gateway of a named network adapter.

    Returns (local_ip, gateway_ip) — either may be None.
    """
    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return (None, None)

    local_ip = None
    gateway_ip = None
    lines = result.stdout.splitlines()
    in_section = False
    for line in lines:
        # Adapter sections start with non-indented text containing the adapter name
        if line and not line.startswith(" ") and adapter_name.lower() in line.lower():
            in_section = True
            local_ip = None
            gateway_ip = None
            continue
        if in_section:
            # New section starts (non-indented, non-empty line)
            if line and not line.startswith(" "):
                if local_ip or gateway_ip:
                    break  # found our section, stop
                in_section = False
                continue
            # Match IPv4 address
            m = re.match(r"^\s+IPv4 Address.*?:\s*([\d.]+)", line)
            if m:
                local_ip = m.group(1)
                continue
            # Fallback: match "IP Address" for older Windows
            m = re.match(r"^\s+IP Address.*?:\s*([\d.]+)", line)
            if m:
                local_ip = m.group(1)
                continue
            # Match Default Gateway
            m = re.match(r"^\s+Default Gateway.*?:\s*([\d.]+)", line)
            if m:
                gateway_ip = m.group(1)
                continue

    return (local_ip, gateway_ip)


def _get_subnet_hosts(local_ip, gateway_ip):
    # type: (str, Optional[str]) -> List[str]
    """Get candidate drone IPs from ARP table on the same /24 subnet.

    On a drone WiFi network the only other device is the drone itself.
    Returns gateway first (most common case), then other ARP entries.
    """
    subnet = ".".join(local_ip.split(".")[:3]) + "."

    candidates = []  # type: List[str]
    if gateway_ip and gateway_ip.startswith(subnet):
        candidates.append(gateway_ip)

    try:
        result = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ip = m.group(1)
                if (ip.startswith(subnet) and ip != local_ip
                        and ip not in candidates and not ip.endswith(".255")):
                    candidates.append(ip)
    except Exception:
        pass

    return candidates


def _probe_drone_udp(drone_ip: str, bind_ip: str,
                     ports: Optional[List[int]] = None,
                     timeout: float = 1.0) -> Optional[int]:
    """Send protocol probes to the drone and check if it responds.

    Sends both E88Pro heartbeat and WiFi UAV START_STREAM on each port.
    Probes ports in order (default: [8800, 7099] — WiFi UAV first).
    Returns the port that responded, or None if no response.
    """
    import sys
    if ports is None:
        ports = [8800, 7099]

    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            if sys.platform == "win32":
                import ctypes
                SIO_UDP_CONNRESET = 0x9800000C
                ret = ctypes.c_ulong(0)
                false = b"\x00\x00\x00\x00"
                ctypes.windll.ws2_32.WSAIoctl(
                    sock.fileno(), SIO_UDP_CONNRESET,
                    false, len(false), None, 0,
                    ctypes.byref(ret), None, None,
                )
            sock.bind((bind_ip, 0))
            sock.sendto(bytes([0x01, 0x01]), (drone_ip, port))  # E88Pro heartbeat
            sock.sendto(bytes([0xef, 0x00, 0x04, 0x00]), (drone_ip, port))  # WiFi UAV START_STREAM
            data, _ = sock.recvfrom(2048)
            if len(data) > 0:
                return port
        except (socket.timeout, ConnectionResetError, OSError):
            continue
        finally:
            sock.close()

    return None


def _find_adapter_by_gateway_probe() -> Optional[DroneAdapter]:
    """Fallback: find any adapter whose gateway responds as a drone.

    Iterates all network adapters, extracts their gateway IPs, and
    probes each on known drone ports (7099, 8800).  Returns the first
    adapter whose gateway responds.

    Catches cases where the drone is connected via Ethernet, USB WiFi
    adapter showing as Ethernet, or other non-WiFi interfaces.
    """
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None

    # Parse ipconfig: collect (adapter_name, local_ip, gateway_ip) tuples
    candidates: list = []
    lines = result.stdout.splitlines()
    current_adapter = ""
    current_ip = ""
    current_gw = ""

    for line in lines:
        # Adapter header: non-indented line with ":"
        if line and not line.startswith(" ") and ":" in line:
            # Flush previous adapter
            if current_adapter and current_ip and current_gw:
                candidates.append((current_adapter, current_ip, current_gw))
            m = re.match(r"^.*?adapter\s+(.+?)\s*:$", line)
            current_adapter = m.group(1) if m else line.strip().rstrip(":")
            current_ip = ""
            current_gw = ""
            continue

        if not current_adapter:
            continue

        m = re.match(r"^\s+IPv4 Address.*?:\s*([\d.]+)", line)
        if m:
            current_ip = m.group(1)
            continue
        m = re.match(r"^\s+Default Gateway.*?:\s*([\d.]+)", line)
        if m:
            current_gw = m.group(1)

    # Flush last adapter
    if current_adapter and current_ip and current_gw:
        candidates.append((current_adapter, current_ip, current_gw))

    # Probe each gateway for a drone response
    for adapter_name, adapter_ip, gateway_ip in candidates:
        logger.debug(f"Probing gateway {gateway_ip} from {adapter_name} ({adapter_ip})...")
        port = _probe_drone_udp(gateway_ip, bind_ip=adapter_ip, timeout=0.5)
        if port is not None:
            logger.info(
                f"Drone verified at gateway {gateway_ip}:{port} via "
                f"{adapter_name} ({adapter_ip})"
            )
            adapter = DroneAdapter(
                name=adapter_name, ssid=None, state="connected",
            )
            adapter.is_drone = True
            adapter.local_ip = adapter_ip
            adapter.gateway_ip = gateway_ip
            adapter.probe_port = port
            return adapter
        else:
            logger.debug(
                f"No drone response at gateway {gateway_ip} via "
                f"{adapter_name} ({adapter_ip}) — skipping"
            )

    return None


def find_bind_ip_fast(drone_ip):
    # type: (str) -> str
    """Find local IP on the same /24 subnet as drone_ip.

    Fast path: single ``ipconfig`` call (~200ms), no UDP probes or ARP.
    Returns empty string if no match found.
    """
    subnet = ".".join(drone_ip.split(".")[:3]) + "."

    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return ""

    for line in result.stdout.splitlines():
        m = re.match(r"^\s+IPv4 Address.*?:\s*([\d.]+)", line)
        if m and m.group(1).startswith(subnet):
            return m.group(1)
    return ""


def find_drone_interface() -> Optional[DroneAdapter]:
    """Find the network adapter connected to the drone.

    Strategy:
    1. Check WiFi interfaces for a drone SSID — probe gateway + ARP
       candidates to find the actual drone IP (some drones serve on a
       different IP than the gateway).
    2. Fallback: probe the gateway of every adapter for a drone response
       on known ports (8800, 7099).

    Returns None if no adapter is connected to a drone network.
    """
    # Strategy 1: WiFi adapter connected to a drone SSID
    interfaces = get_all_wifi_interfaces()
    for iface in interfaces:
        if iface.is_drone and iface.ssid:
            local_ip, gateway_ip = _get_adapter_info(iface.name)
            iface.local_ip = local_ip
            if iface.local_ip:
                # Probe candidate IPs to find where drone services live.
                # Usually the gateway, but some drones (e.g. Mten) serve
                # on a different IP on the same subnet.
                # Limit to gateway + first 2 ARP entries to keep scan fast
                # (each probe takes ~2s on timeout, full ARP can be 10+ hosts).
                candidates = _get_subnet_hosts(local_ip, gateway_ip)[:3]
                drone_ip = gateway_ip  # default fallback
                probe_port = None
                for cip in candidates:
                    port = _probe_drone_udp(cip, bind_ip=local_ip,
                                            timeout=0.5)
                    if port is not None:
                        drone_ip = cip
                        probe_port = port
                        if cip != gateway_ip:
                            logger.info(
                                f"Drone services at {cip} (gateway is {gateway_ip})"
                            )
                        break

                iface.gateway_ip = drone_ip
                iface.probe_port = probe_port
                logger.info(
                    f"Drone WiFi adapter found: {iface.name} -> "
                    f"SSID={iface.ssid}, IP={iface.local_ip}, "
                    f"Drone={iface.gateway_ip}"
                )
                return iface
            else:
                logger.warning(
                    f"Adapter {iface.name} is on drone SSID "
                    f"{iface.ssid} but has no IPv4 address"
                )

    # Strategy 2: Probe gateways on ALL adapters for a drone response
    gateway_adapter = _find_adapter_by_gateway_probe()
    if gateway_adapter:
        return gateway_adapter

    return None


def get_current_ssid() -> Optional[str]:
    """
    Return the SSID of the currently connected WiFi network (Windows).

    Returns None if not connected or netsh is unavailable.
    """
    interfaces = get_all_wifi_interfaces()
    for iface in interfaces:
        if iface.ssid:
            return iface.ssid
    return None
