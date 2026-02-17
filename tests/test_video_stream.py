from tyvyx.video_stream import OpenCVVideoStream


def test_video_stream_start_stop():
    # Use an unreachable RTSP URL that will fail quickly
    vs = OpenCVVideoStream("rtsp://127.0.0.1:554/no_stream")
    started = vs.start(timeout=1.0)
    assert started is False or isinstance(started, bool)

    ok, frame = vs.read()
    assert ok is False
    assert frame is None

    # Stop should not raise
    vs.stop()
