"""
Video Streaming REST API Routes

Endpoints for video feed access via FrameHub (UDP pipeline)
and WebRTC signaling (go2rtc proxy).
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
import logging

from autonomous.services.drone_service import drone_service
from autonomous.services.go2rtc_service import go2rtc_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/feed")
async def video_feed():
    """
    MJPEG video stream using FrameHub.

    Raw JPEG bytes flow directly from the UDP receiver — no decode/re-encode.
    Each client gets its own asyncio.Queue so multiple viewers work independently.
    """
    if not drone_service.is_video_streaming():
        raise HTTPException(
            status_code=503,
            detail="Video stream not available. Start video first.",
        )

    async def frame_generator():
        q = await drone_service.frame_hub.register()
        try:
            while True:
                frame_bytes = await q.get()
                if frame_bytes is None:
                    break
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
        finally:
            await drone_service.frame_hub.unregister(q)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
async def video_status():
    """Get video stream status."""
    return {
        "streaming": drone_service.is_video_streaming(),
        "protocol": getattr(drone_service, "_video_protocol", None),
        "source": "udp",
    }


# ── WebRTC signaling (proxied to go2rtc) ──────────────────────


@router.post("/webrtc/offer")
async def webrtc_offer(request: Request):
    """
    WebRTC SDP offer/answer exchange.

    Browser sends SDP offer, this endpoint proxies it to go2rtc
    and returns the SDP answer. Single HTTP round-trip.
    """
    if not go2rtc_service.is_running():
        raise HTTPException(status_code=503, detail="go2rtc is not running")

    sdp_offer = (await request.body()).decode("utf-8")
    if not sdp_offer:
        raise HTTPException(status_code=400, detail="Empty SDP offer")

    sdp_answer = await go2rtc_service.webrtc_offer("drone", sdp_offer)
    if sdp_answer is None:
        raise HTTPException(status_code=502, detail="Failed to get SDP answer from go2rtc")

    return Response(content=sdp_answer, media_type="application/sdp")


@router.get("/capabilities")
async def video_capabilities():
    """
    Available video transport methods.

    Frontend uses this to choose WebRTC or fall back to MJPEG.
    """
    return {
        "webrtc": go2rtc_service.is_running(),
        "mjpeg": True,
        "streaming": drone_service.is_video_streaming(),
    }
