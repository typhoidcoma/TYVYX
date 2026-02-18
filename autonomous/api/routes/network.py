"""
Network API Routes

Endpoints for scanning WiFi networks and identifying drone hotspots.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from autonomous.services.network_service import scan_wifi_networks, get_current_ssid, find_drone_interface

router = APIRouter(prefix="/api/network", tags=["network"])


class WifiNetworkSchema(BaseModel):
    ssid: str
    signal: int
    security: str
    bssid: str
    is_drone: bool


class ScanResponse(BaseModel):
    networks: List[WifiNetworkSchema]
    current_ssid: Optional[str]
    connected_to_drone: bool
    drone_adapter_ip: Optional[str] = None
    drone_adapter_name: Optional[str] = None
    drone_ip: Optional[str] = None  # gateway IP = drone IP


@router.get("/scan", response_model=ScanResponse)
async def scan():
    """
    Scan for nearby WiFi networks.

    Returns all visible SSIDs with signal strength and security type.
    Drone-likely networks (matching known SSID patterns) are flagged with is_drone=true
    and sorted to the top. Also returns the currently connected SSID.
    """
    networks = scan_wifi_networks()
    current_ssid = get_current_ssid()

    drone_iface = find_drone_interface()  # no hardcoded IP — uses gateway detection
    connected_to_drone = drone_iface is not None

    # Use the drone adapter's SSID for consistency
    if drone_iface and drone_iface.ssid:
        current_ssid = drone_iface.ssid

    return ScanResponse(
        networks=[
            WifiNetworkSchema(
                ssid=n.ssid,
                signal=n.signal,
                security=n.security,
                bssid=n.bssid,
                is_drone=n.is_drone,
            )
            for n in networks
        ],
        current_ssid=current_ssid,
        connected_to_drone=connected_to_drone,
        drone_adapter_ip=drone_iface.local_ip if drone_iface else None,
        drone_adapter_name=drone_iface.name if drone_iface else None,
        drone_ip=drone_iface.gateway_ip if drone_iface else None,
    )
