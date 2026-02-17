import time


def test_flight_controller_sends_commands():
    from tyvyx.drone_controller_advanced import FlightController

    sent = []

    def sender(cmd: bytes):
        sent.append(cmd)

    fc = FlightController(sender)
    fc.DECEL_STEP = 0  # disable auto-decel for test predictability
    fc.command_interval = 0.02
    fc.start()
    fc.increase_throttle()
    fc.yaw_right()
    time.sleep(0.12)
    fc.stop()

    # At least one command should have been sent
    assert len(sent) >= 1
    assert isinstance(sent[0], (bytes, bytearray))

    # Validate E88Pro packet format (9 bytes)
    packet = sent[0]
    assert len(packet) == 9, f"Expected 9-byte packet, got {len(packet)}"
    assert packet[0] == 0x03, f"First byte should be 0x03 command prefix, got {packet[0]:#x}"
    assert packet[1] == 0x66, f"Second byte should be 0x66 protocol marker, got {packet[1]:#x}"
    assert packet[8] == 0x99, f"Last byte should be 0x99 end marker, got {packet[8]:#x}"

    # Verify XOR checksum (bytes 2-6: roll, pitch, throttle, yaw, flags)
    expected_xor = packet[2] ^ packet[3] ^ packet[4] ^ packet[5] ^ packet[6]
    assert packet[7] == expected_xor, f"XOR checksum mismatch: {packet[7]:#x} != {expected_xor:#x}"


def test_flight_controller_takeoff_flag():
    from tyvyx.drone_controller_advanced import FlightController

    sent = []

    def sender(cmd: bytes):
        sent.append(cmd)

    fc = FlightController(sender)
    fc.DECEL_STEP = 0
    fc.command_interval = 0.02
    fc.start()
    fc.takeoff()
    time.sleep(0.08)
    fc.stop()

    # Find the packet with takeoff flag set
    takeoff_packets = [p for p in sent if len(p) == 9 and (p[6] & 0x01)]
    assert len(takeoff_packets) >= 1, "Expected at least one packet with takeoff flag"

    # Flag should be cleared on subsequent packets
    non_takeoff = [p for p in sent if len(p) == 9 and not (p[6] & 0x01)]
    assert len(non_takeoff) >= 1, "Takeoff flag should be cleared after first send"


def test_flight_controller_headless_toggle():
    from tyvyx.drone_controller_advanced import FlightController

    fc = FlightController(lambda cmd: None)
    assert not fc._headless_mode

    fc.toggle_headless()
    assert fc._headless_mode

    fc.toggle_headless()
    assert not fc._headless_mode
