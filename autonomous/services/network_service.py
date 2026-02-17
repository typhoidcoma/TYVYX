"""
WiFi Network Scanner Service

Scans for nearby WiFi networks and identifies likely drone hotspots
based on known SSID naming patterns.

Windows only — uses `netsh wlan` which is available on all modern Windows installs
without any additional packages.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# SSIDs matching these prefixes are flagged as likely drone networks
DRONE_SSID_PATTERNS = ["HD-", "FHD-", "HD720", "K417", "HD-FPV", "TYVYX", "drone"]


@dataclass
class WifiNetwork:
    ssid: str
    signal: int       # 0–100 percent
    security: str     # e.g. "WPA2-Personal", "Open"
    bssid: str = ""
    is_drone: bool = field(init=False)

    def __post_init__(self):
        ssid_upper = self.ssid.upper()
        self.is_drone = any(p.upper() in ssid_upper for p in DRONE_SSID_PATTERNS)


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


def get_current_ssid() -> Optional[str]:
    """
    Return the SSID of the currently connected WiFi network (Windows).

    Returns None if not connected or netsh is unavailable.
    """
    if not _netsh_available():
        return None

    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout
    except Exception as e:
        logger.error(f"Failed to get current SSID: {e}")
        return None

    for line in output.splitlines():
        m = re.match(r"^\s*SSID\s*:\s*(.+)$", line)
        if m:
            ssid = m.group(1).strip()
            if ssid:
                return ssid

    return None
