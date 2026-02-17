"""
go2rtc Process Manager & API Client

Manages go2rtc as a subprocess and provides methods to register streams
and proxy WebRTC signaling.
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent


class Go2RTCService:
    """Manages the go2rtc subprocess lifecycle and REST API interactions."""

    API_BASE = "http://127.0.0.1:1984"
    STARTUP_TIMEOUT = 10  # seconds

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._config_path = _PROJECT_ROOT / "config" / "go2rtc.yaml"

        # Resolve binary path based on platform
        if sys.platform == "win32":
            self._binary_path = _PROJECT_ROOT / "bin" / "go2rtc.exe"
        else:
            self._binary_path = _PROJECT_ROOT / "bin" / "go2rtc"

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> bool:
        """Launch go2rtc and wait for the API to become responsive."""
        if self._process and self._process.poll() is None:
            logger.info("go2rtc already running (PID %d)", self._process.pid)
            return True

        if not self._binary_path.exists():
            logger.warning(
                "go2rtc binary not found at %s — WebRTC unavailable (MJPEG fallback)",
                self._binary_path,
            )
            return False

        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                [str(self._binary_path), "-config", str(self._config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                **kwargs,
            )
            logger.info("go2rtc started (PID %d)", self._process.pid)
            return await self._wait_for_ready()

        except Exception as e:
            logger.error("Failed to start go2rtc: %s", e, exc_info=True)
            return False

    async def _wait_for_ready(self) -> bool:
        """Poll the go2rtc API until it responds or timeout."""
        async with httpx.AsyncClient() as client:
            for _ in range(self.STARTUP_TIMEOUT * 10):
                try:
                    resp = await client.get(f"{self.API_BASE}/api")
                    if resp.status_code == 200:
                        logger.info("go2rtc API ready")
                        return True
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)

        logger.error("go2rtc API did not become ready within %ds", self.STARTUP_TIMEOUT)
        return False

    async def stop(self):
        """Terminate the go2rtc process."""
        if not self._process:
            return
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            logger.info("go2rtc stopped")
        except Exception as e:
            logger.error("Error stopping go2rtc: %s", e)
        finally:
            self._process = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    # ── Stream Management ──────────────────────────────────────

    async def register_stream(self, name: str, rtsp_url: str) -> bool:
        """Register an RTSP source with go2rtc."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.put(
                    f"{self.API_BASE}/api/streams",
                    params={"src": name},
                    json={"url": rtsp_url},
                )
                if resp.status_code in (200, 201):
                    logger.info("Registered go2rtc stream '%s' -> %s", name, rtsp_url)
                    return True
                logger.error("go2rtc register failed: %d %s", resp.status_code, resp.text)
                return False
            except Exception as e:
                logger.error("Error registering stream with go2rtc: %s", e)
                return False

    async def remove_stream(self, name: str) -> bool:
        """Remove a stream from go2rtc."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.delete(
                    f"{self.API_BASE}/api/streams",
                    params={"src": name},
                )
                return resp.status_code in (200, 204)
            except Exception as e:
                logger.error("Error removing go2rtc stream: %s", e)
                return False

    # ── WebRTC Signaling ───────────────────────────────────────

    async def webrtc_offer(self, stream_name: str, sdp_offer: str) -> Optional[str]:
        """
        Forward an SDP offer to go2rtc and return the SDP answer.

        go2rtc uses ICE-lite so all candidates are embedded in the SDP —
        a single HTTP round-trip handles the entire negotiation.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{self.API_BASE}/api/webrtc",
                    params={"src": stream_name},
                    content=sdp_offer,
                    headers={"Content-Type": "application/sdp"},
                )
                if resp.status_code == 200:
                    return resp.text
                logger.error("go2rtc WebRTC offer failed: %d %s", resp.status_code, resp.text)
                return None
            except Exception as e:
                logger.error("Error in WebRTC offer: %s", e)
                return None

    # ── Helpers ────────────────────────────────────────────────

    def get_restream_url(self, stream_name: str) -> str:
        """RTSP re-stream URL for position tracking via OpenCV."""
        return f"rtsp://127.0.0.1:8554/{stream_name}"


# Singleton
go2rtc_service = Go2RTCService()
