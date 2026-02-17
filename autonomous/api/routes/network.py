"""
Network API Routes

Endpoints for scanning WiFi networks and identifying drone hotspots.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from autonomous.services.network_service import scan_wifi_networks, get_current_ssid

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

    current_network = next((n for n in networks if n.ssid == current_ssid), None)
    connected_to_drone = bool(current_network and current_network.is_drone)

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
    )
