"""
Video Streaming API Routes

Endpoints for video feed access via FrameHub (UDP pipeline).
Provides WebSocket binary (primary) and MJPEG (fallback) transports.
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import logging

from autonomous.services.drone_service import drone_service

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


@router.websocket("/ws")
async def video_ws(websocket: WebSocket):
    """
    WebSocket binary video stream.

    Sends raw JPEG frames as binary messages — lower latency than MJPEG
    multipart, instant stall detection via WebSocket close.
    """
    await websocket.accept()

    if not drone_service.is_video_streaming():
        await websocket.close(code=1013, reason="Video not streaming")
        return

    q = await drone_service.frame_hub.register()
    try:
        while True:
            frame_bytes = await q.get()
            if frame_bytes is None:
                # Stream stall — close cleanly so frontend can reconnect
                await websocket.close(code=1001, reason="Stream stalled")
                break
            await websocket.send_bytes(frame_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("Video WS closed: %s", e)
    finally:
        await drone_service.frame_hub.unregister(q)


@router.get("/status")
async def video_status():
    """Get video stream status."""
    return {
        "streaming": drone_service.is_video_streaming(),
        "protocol": getattr(drone_service, "_video_protocol", None),
        "source": "udp",
    }


@router.get("/capabilities")
async def video_capabilities():
    """
    Available video transport methods.

    Frontend uses this to choose WebSocket or fall back to MJPEG.
    """
    return {
        "websocket": True,
        "mjpeg": True,
        "streaming": drone_service.is_video_streaming(),
    }
