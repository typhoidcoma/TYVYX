import time


def test_flight_controller_sends_commands():
    from drone_controller_advanced import FlightController

    sent = []

    def sender(cmd: bytes):
        sent.append(cmd)

    fc = FlightController(sender)
    # Make interval small for test
    fc.command_interval = 0.02
    fc.start()
    # change some controls
    fc.increase_throttle()
    fc.yaw_right()
    time.sleep(0.12)
    fc.stop()

    # At least one command should have been sent
    assert len(sent) >= 1
    assert isinstance(sent[0], (bytes, bytearray))
