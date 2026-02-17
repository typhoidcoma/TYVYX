# Phase 1: Flight Control Validation & Calibration

This directory contains tools for testing and calibrating the experimental flight controls of the TYVYX drone.

## 🎯 Goal

Validate that the reverse-engineered flight control commands work correctly and create calibration data that maps desired velocities to drone control values (0-255).

## ⚠️ Safety First!

**IMPORTANT:** Flight testing is inherently risky. Follow these safety guidelines:

1. **Clear Testing Area**: Test in an open space, free of obstacles, people, and pets
2. **Tethered Testing**: Consider tethering the drone during initial tests
3. **Low Altitude**: Start with low altitude flights (0.5-1.0m)
4. **Emergency Stop**: Keep the emergency stop button/command ready at all times
5. **Supervision**: Never leave the drone unattended during testing
6. **Battery**: Ensure drone is fully charged before testing
7. **Backup**: Have a way to catch/stop the drone if controls fail

## 📋 Prerequisites

1. **Drone Setup**:
   - TYVYX WiFi drone powered on
   - Connected to drone's WiFi network (HD-720P-*, HD-FPV-*, etc.)
   - Drone IP should be 192.168.1.1 (verify with `ping 192.168.1.1`)

2. **Environment**:
   - Python 3.8+
   - Dependencies installed: `pip install -r requirements.txt`
   - FFmpeg installed and in PATH (for video streaming)

3. **Existing System Working**:
   - Test that basic connection works:
     ```bash
     python -m tyvyx.app
     # Visit http://localhost:5000 and verify video feed + camera switching
     ```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Connect to Drone WiFi

Connect your computer to the drone's WiFi network. The network name typically starts with:
- `HD-720P-*`
- `HD-FPV-*`
- `HD720-*`
- `FHD-*`

### 3. Run Interactive Mode (Recommended First)

```bash
python -m autonomous.testing.flight_control_test --mode interactive
```

This launches an interactive control interface where you can manually test individual control values.

**Interactive Commands:**
```
t <value>  - Set throttle (0-255)
y <value>  - Set yaw (0-255)
p <value>  - Set pitch (0-255)
r <value>  - Set roll (0-255)
reset      - Reset all to neutral (128)
status     - Show current values
log <msg>  - Log observation
quit       - Exit interactive mode
```

**Example Session:**
```
Control> t 150
Throttle set to 150
Control> log Drone lifting off gently
Control> t 128
Throttle set to 128
Control> log Drone descending slowly
Control> quit
```

### 4. Run Full Calibration

Once you're comfortable with interactive mode, run the full calibration sequence:

```bash
python -m autonomous.testing.flight_control_test --mode calibrate
```

This will guide you through:
1. Throttle range testing (find hover value)
2. Pitch testing (forward/backward movement)
3. Roll testing (left/right movement)
4. Yaw testing (rotation)

**During calibration:**
- The script will prompt you before each test
- Describe what you observe after each control value is applied
- Be ready to manually stop the drone if needed
- All data is logged to `logs/flight_tests/`

## 📊 Test Modes

### Interactive Mode
```bash
python -m autonomous.testing.flight_control_test --mode interactive
```
- Manual control for exploration
- Best for initial testing and understanding drone behavior
- Log observations as you go

### Full Calibration
```bash
python -m autonomous.testing.flight_control_test --mode calibrate
```
- Runs all tests in sequence
- Guided process with prompts
- Creates comprehensive calibration data

### Individual Axis Tests
```bash
python -m autonomous.testing.flight_control_test --mode test_throttle
python -m autonomous.testing.flight_control_test --mode test_pitch
python -m autonomous.testing.flight_control_test --mode test_roll
python -m autonomous.testing.flight_control_test --mode test_yaw
```
- Test one axis at a time
- Useful for fine-tuning specific controls

## 📝 What to Look For During Testing

### Throttle Testing
- **Below neutral (< 128)**: Drone should descend or stay grounded
- **Neutral (128)**: Baseline (may not hover, depends on drone)
- **Hover value (~140-160)**: Find the value where drone maintains altitude
- **Above hover**: Drone should ascend

**Record:**
- Minimum lift-off value
- Hover value (most important!)
- Max safe climb value
- Descent values

### Pitch Testing (Forward/Backward)
- **< 128**: Backward movement
- **128**: No pitch movement
- **> 128**: Forward movement

**Record:**
- How much control input causes gentle forward movement?
- At what value does movement become too fast?
- Is backward movement symmetric to forward?

### Roll Testing (Left/Right)
- **< 128**: Left movement
- **128**: No roll movement
- **> 128**: Right movement

**Record:**
- Control values for gentle left/right movement
- Maximum safe roll values
- Symmetry between left and right

### Yaw Testing (Rotation)
- **< 128**: Counter-clockwise rotation
- **128**: No rotation
- **> 128**: Clockwise rotation

**Record:**
- Rotation speeds at different values
- Smoothness of rotation
- Any dead zones

## 📂 Output Files

All test data is saved to `logs/flight_tests/`:

```
logs/flight_tests/
├── flight_test_20240216_143022.json    # Timestamped test logs
├── calibration_interrupted.json        # If you stop mid-test
└── ...
```

**Log file format:**
```json
{
  "timestamp": "2024-02-16T14:30:22.123456",
  "test_name": "throttle_test_150",
  "control_values": {
    "throttle": 150,
    "yaw": 128,
    "pitch": 128,
    "roll": 128
  },
  "observations": "Drone lifting off smoothly at about 0.5m/s",
  "success": true
}
```

## 🔧 Creating Calibration Config

After completing tests, update `config/drone_config.yaml` with your findings:

```yaml
flight_controls:
  throttle:
    hover_value: 152  # YOUR MEASURED VALUE
    velocity_map:
      -1.0: 110  # Descend 1 m/s - YOUR MEASURED VALUE
      0.0: 152   # Hover - YOUR MEASURED VALUE
      0.5: 165   # Climb 0.5 m/s - YOUR MEASURED VALUE
      1.0: 180   # Climb 1 m/s - YOUR MEASURED VALUE

  pitch:
    velocity_map:
      -0.5: 110  # Backward 0.5 m/s
      0.0: 128   # No movement
      0.5: 145   # Forward 0.5 m/s
      # ... etc
```

**Tips for creating the velocity map:**
1. Start with the values you directly tested
2. Interpolate between tested points
3. Be conservative - it's better to move slowly than crash!
4. You can fine-tune these later during PID testing

## 🐛 Troubleshooting

### Drone not responding to controls
- Verify UDP connection: Check logs for "Connected to drone successfully"
- Check WiFi connection: `ping 192.168.1.1`
- Try basic controls first (camera switch) to verify communication
- Review reverse engineering notes: `REVERSE_ENGINEERING_NOTES.md`

### Controls work but drone behaves unexpectedly
- The experimental command format may need adjustment
- Use packet sniffer to capture Android app commands:
  ```bash
  python -m tyvyx.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30
  ```
- Compare captured packets with our commands

### Video stream not working
- Check that FFmpeg is installed: `ffmpeg -version`
- Try RTSP URL directly: `ffplay rtsp://192.168.1.1:7070/webcam`
- Video is non-critical for control testing (can continue without it)

### Drone drifts during hover test
- Indoor wind/air currents can affect stability
- This is normal - PID controllers will compensate later
- Try to find environment with minimal air movement

## 📚 Next Steps

After completing Phase 1 calibration:

1. **✅ You should have**:
   - Validated that flight controls work
   - Identified hover throttle value
   - Created velocity → control value mappings
   - Documented safe operating ranges
   - Updated `config/drone_config.yaml`

2. **📋 Ready for Phase 2**:
   - Build React frontend
   - Create FastAPI backend
   - Implement real-time telemetry
   - Begin PID controller tuning with your calibration data

3. **🔬 Optional Advanced Testing**:
   - Packet sniffing comparison with Android app
   - Fine-tune velocity mappings
   - Test emergency stop procedures
   - Measure actual velocities with video analysis

## 📖 Related Documentation

- Main plan: `~/.claude/plans/fluttering-soaring-horizon.md`
- Reverse engineering notes: `REVERSE_ENGINEERING_NOTES.md`
- Configuration reference: `config/drone_config.yaml`
- PID controller: `autonomous/navigation/pid_controller.py`

## 🆘 Getting Help

If you encounter issues:

1. Check the test logs in `logs/flight_tests/`
2. Review the reverse engineering notes
3. Try the original Flask app to verify basic functionality
4. Consider using UDP proxy to inspect traffic:
   ```bash
   python -m tyvyx.tools.udp_proxy --listen-port 17099 --drone-ip 192.168.1.1
   ```

## ⚡ Quick Reference

```bash
# Interactive testing
python -m autonomous.testing.flight_control_test --mode interactive

# Full calibration
python -m autonomous.testing.flight_control_test --mode calibrate

# Test specific axis
python -m autonomous.testing.flight_control_test --mode test_throttle

# Packet sniffing (for comparison)
python -m tyvyx.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30

# UDP proxy (for traffic analysis)
python -m tyvyx.tools.udp_proxy --listen-port 17099 --drone-ip 192.168.1.1
```

---

**Remember: Safety first! Start conservative, test incrementally, and always be ready for emergency stop.**

Good luck with calibration! 🚁✨
