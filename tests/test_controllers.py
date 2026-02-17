from tyvyx.drone_controller import TYVYXDroneController
from tyvyx.drone_controller_advanced import TYVYXDroneControllerAdvanced
from tyvyx.drone_controller_yolo import TYVYXDroneYOLO


def test_controllers_start_video_fallback():
    # Controllers should be importable and their start_video_stream
    # should return False in an environment without the drone RTSP.
    c = TYVYXDroneController()
    assert c.DRONE_IP == "192.168.1.1"
    started = c.start_video_stream()
    assert started is False
    ok, frame = c.get_frame()
    assert ok is False

    ca = TYVYXDroneControllerAdvanced()
    started = ca.start_video_stream()
    assert started is False
    ok, frame = ca.get_frame()
    assert ok is False

    cy = TYVYXDroneYOLO()
    started = cy.start_video_stream()
    assert started is False
    ok, frame = cy.get_frame()
    assert ok is False
