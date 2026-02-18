"""
Video Streaming API Routes

Endpoints for video feed access via FrameHub (UDP pipeline).
Provides WebSocket binary (primary) and MJPEG (fallback) transports.
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
import logging
import time

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
        count = 0
        t0 = time.monotonic()
        logger.info("[mjpeg] Client connected")
        try:
            while True:
                try:
                    frame_bytes = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if not drone_service.is_video_streaming():
                        logger.info("[mjpeg] Video stopped")
                        break
                    continue
                if frame_bytes is None:
                    logger.info("[mjpeg] Shutdown signal")
                    break
                count += 1
                if count == 1:
                    logger.info("[mjpeg] First frame sent (%d bytes)", len(frame_bytes))
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
        finally:
            elapsed = time.monotonic() - t0
            logger.info("[mjpeg] Client disconnected (%d frames in %.1fs)", count, elapsed)
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
    multipart.  Survives temporary stalls (adapter reconnect) — only
    closes on explicit shutdown (None from stop_video) or if video is
    stopped externally.
    """
    await websocket.accept()
    logger.info("[ws] Video WebSocket client connected")

    if not drone_service.is_video_streaming():
        logger.warning("[ws] Rejected — video not streaming")
        await websocket.close(code=1013, reason="Video not streaming")
        return

    q = await drone_service.frame_hub.register()
    count = 0
    t0 = time.monotonic()
    try:
        while True:
            try:
                frame_bytes = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No frame yet — check if video was explicitly stopped
                if not drone_service.is_video_streaming():
                    logger.info("[ws] Video stopped — closing")
                    await websocket.close(code=1001, reason="Video stopped")
                    break
                continue
            if frame_bytes is None:
                # Explicit shutdown signal from stop_video()
                logger.info("[ws] Shutdown signal — closing")
                await websocket.close(code=1001, reason="Video stopped")
                break
            count += 1
            if count == 1:
                logger.info("[ws] First frame sent (%d bytes)", len(frame_bytes))
            await websocket.send_bytes(frame_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("[ws] Closed: %s", e)
    finally:
        elapsed = time.monotonic() - t0
        logger.info("[ws] Client disconnected (%d frames in %.1fs)", count, elapsed)
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


# ── Test endpoints (synthetic frames, no drone needed) ────────


def _generate_test_jpeg(frame_num: int) -> bytes:
    """Generate a simple test-pattern JPEG using OpenCV."""
    import cv2
    import numpy as np

    img = np.zeros((480, 640, 3), dtype=np.uint8)

    # Alternating color bars
    colors = [
        (0, 0, 255), (0, 255, 0), (255, 0, 0),
        (0, 255, 255), (255, 0, 255), (255, 255, 0),
        (255, 255, 255), (128, 128, 128),
    ]
    bar_w = 640 // len(colors)
    for i, color in enumerate(colors):
        x = i * bar_w
        img[:, x:x + bar_w] = color

    # Moving indicator (horizontal bar that scrolls down)
    y = (frame_num * 4) % 480
    cv2.rectangle(img, (0, y), (640, y + 8), (0, 0, 0), -1)

    # Frame counter + timestamp
    text = f"#{frame_num}  {time.strftime('%H:%M:%S')}"
    cv2.putText(img, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
    cv2.putText(img, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    cv2.putText(img, "TEST PATTERN", (180, 260), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 4)
    cv2.putText(img, "TEST PATTERN", (180, 260), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


@router.websocket("/test")
async def video_test_ws(websocket: WebSocket):
    """
    Test WebSocket: sends synthetic JPEG frames at ~25 fps.
    No drone connection needed — verifies the full frontend pipeline.
    """
    await websocket.accept()
    logger.info("[test-ws] Test video client connected")
    frame_num = 0
    try:
        while True:
            jpeg = _generate_test_jpeg(frame_num)
            await websocket.send_bytes(jpeg)
            frame_num += 1
            await asyncio.sleep(0.04)  # ~25 fps
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("[test-ws] Closed: %s", e)
    finally:
        logger.info("[test-ws] Disconnected after %d frames", frame_num)


@router.get("/test")
async def video_test_mjpeg():
    """
    Test MJPEG: sends synthetic JPEG frames at ~25 fps.
    No drone connection needed — verifies the full frontend pipeline.
    Open http://localhost:8000/api/video/test in a browser to view.
    """
    logger.info("[test-mjpeg] Test video client connected")

    async def gen():
        frame_num = 0
        try:
            while True:
                jpeg = _generate_test_jpeg(frame_num)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
                frame_num += 1
                await asyncio.sleep(0.04)
        except asyncio.CancelledError:
            logger.info("[test-mjpeg] Disconnected after %d frames", frame_num)

    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame"
    )
