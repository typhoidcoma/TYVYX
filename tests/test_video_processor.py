import numpy as np

from teky.drone_controller_yolo import DroneVideoProcessor


def test_process_frame_no_yolo():
    vp = DroneVideoProcessor()
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    processed, detections = vp.process_frame(frame)
    assert processed.shape == frame.shape
    assert isinstance(detections, list)
