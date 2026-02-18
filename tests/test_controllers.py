from tyvyx.drone_controller_advanced import TYVYXDroneControllerAdvanced


def test_controller_start_video_fallback():
    ca = TYVYXDroneControllerAdvanced()
    started = ca.start_video_stream()
    assert started is False
    ok, frame = ca.get_frame()
    assert ok is False
