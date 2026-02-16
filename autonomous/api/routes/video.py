"""
Video Streaming REST API Routes

Endpoints for video feed access.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import cv2
import logging

from autonomous.services.drone_service import drone_service

logger = logging.getLogger(__name__)

router = APIRouter()


def generate_mjpeg():
    """
    Generate MJPEG stream from video frames

    Yields MJPEG frames in multipart format
    """
    while True:
        try:
            # Get frame from drone service
            success, frame = drone_service.get_frame()

            if success and frame is not None:
                # Encode frame as JPEG
                ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

                if ret:
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' +
                        jpeg.tobytes() +
                        b'\r\n'
                    )
            else:
                # No frame available, brief pause
                import time
                time.sleep(0.01)

        except Exception as e:
            logger.error(f"Error generating MJPEG frame: {e}")
            break


@router.get("/feed")
async def video_feed():
    """
    Video feed endpoint (MJPEG stream)

    Returns:
        MJPEG video stream
    """
    if not drone_service.is_video_streaming():
        raise HTTPException(
            status_code=503,
            detail="Video stream not available. Call /api/drone/command with action='start_video' first."
        )

    return StreamingResponse(
        generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/status")
async def video_status():
    """
    Get video stream status

    Returns:
        Video status
    """
    return {
        "streaming": drone_service.is_video_streaming(),
        "source": "rtsp://192.168.1.1:7070/webcam" if drone_service.is_video_streaming() else None
    }
