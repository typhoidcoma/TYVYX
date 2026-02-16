# Phase 1: Flight Control Calibration

## Overview

Phase 1 is the **critical foundation** for the autonomous drone system. Before building autonomous navigation, we must verify that experimental flight control commands work and calibrate them properly.

**The Challenge**: The experimental flight controls use a reverse-engineered command format:
```
[CMD_ID, throttle, yaw, pitch, roll, checksum]
```

Where CMD_ID = 0x50 and each value is 0-255 (128 = neutral).

**Your Mission**: Test these controls systematically and document what works!

---

## Table of Contents

- [Quick Start](#quick-start)
- [What We've Built](#what-weve-built)
- [Detailed Calibration Guide](#detailed-calibration-guide)
- [Understanding the System](#understanding-the-system)
- [Troubleshooting](#troubleshooting)
- [What Success Looks Like](#what-success-looks-like)
- [Next Steps](#next-steps)

---

## Quick Start

### Prerequisites

- Python 3.8+ installed
- TEKY WiFi drone powered on
- Computer connected to drone WiFi
- Open testing area (safety first!)

### 5-Minute Quick Start

#### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

#### Step 2: Connect to Drone WiFi

Connect your computer to the drone's WiFi network:
- Look for networks starting with: `HD-720P-*`, `HD-FPV-*`, `HD720-*`, or `FHD-*`
- Drone IP should be: `192.168.1.1`
- Verify: `ping 192.168.1.1`

#### Step 3: Run Interactive Test Mode

```bash
python -m autonomous.testing.flight_control_test --mode interactive
```

This gives you manual control to experiment safely:

```
Control> status               # Show current values
Control> t 150                # Set throttle to 150
Control> log Drone lifts off slowly
Control> t 128                # Back to neutral
Control> reset                # Reset everything
Control> quit                 # Exit
```

### Available Test Commands

| Command | Description | Example |
|---------|-------------|---------|
| `t <value>` | Set throttle (0-255) | `t 150` |
| `y <value>` | Set yaw (0-255) | `y 140` |
| `p <value>` | Set pitch (0-255) | `p 135` |
| `r <value>` | Set roll (0-255) | `r 120` |
| `reset` | Reset all to neutral (128) | `reset` |
| `status` | Show current values | `status` |
| `log <msg>` | Log observation | `log Drone hovering steadily` |
| `quit` | Exit | `quit` |

### Control Values Guide

- **0-127**: Below neutral (descend, backward, left, counter-clockwise)
- **128**: Neutral (should be no movement)
- **129-255**: Above neutral (ascend, forward, right, clockwise)

---

## What We've Built

Phase 1 setup provides the foundation for flight control testing and calibration.

### Project Structure

```
TEKY/
├── autonomous/                    # Autonomous system package
│   ├── api/                      # FastAPI backend (Phase 2)
│   ├── localization/             # Position estimation (Phase 3)
│   ├── navigation/               # Path planning & control
│   │   └── pid_controller.py    # PID implementation ready
│   ├── perception/               # SLAM & vision (Phase 3+)
│   ├── services/                 # High-level services (Phase 2)
│   ├── slam/                     # SLAM engines (Phase 7)
│   └── testing/
│       ├── flight_control_test.py  # Main calibration tool
│       └── README.md                # Complete testing guide
│
├── config/
│   └── drone_config.yaml         # Configuration template
│
├── logs/
│   └── flight_tests/             # Test data saved here
│
├── maps/                          # Map files (Phase 4)
│
└── docs/                          # Documentation
```

### Key Components

#### 1. Flight Control Test Harness

**File**: [autonomous/testing/flight_control_test.py](../../autonomous/testing/flight_control_test.py)

A comprehensive tool for testing and calibrating drone flight controls.

**Features**:
- **Interactive Mode**: Manual control testing with real-time logging
- **Full Calibration**: Guided test sequence for all axes
- **Individual Axis Tests**: Focus on throttle, pitch, roll, or yaw
- **Data Logging**: All observations saved to JSON
- **Safety Features**: Emergency stop, reset commands

**Usage**:
```bash
# Interactive testing (recommended first)
python -m autonomous.testing.flight_control_test --mode interactive

# Full calibration sequence
python -m autonomous.testing.flight_control_test --mode calibrate

# Test specific axis
python -m autonomous.testing.flight_control_test --mode test_throttle
python -m autonomous.testing.flight_control_test --mode test_pitch
python -m autonomous.testing.flight_control_test --mode test_roll
python -m autonomous.testing.flight_control_test --mode test_yaw
```

#### 2. PID Controller

**File**: [autonomous/navigation/pid_controller.py](../../autonomous/navigation/pid_controller.py)

Production-ready PID controller implementation for autonomous navigation.

**Features**:
- Generic `PIDController` class (single axis)
- `DronePositionController` class (manages X, Y, Z, Yaw)
- Anti-windup protection
- Output clamping
- Live gain tuning
- State monitoring for debugging

**Will be used for**:
- Position hold (hover at fixed coordinates)
- Waypoint tracking (fly to target positions)
- Velocity control

#### 3. Configuration System

**File**: [config/drone_config.yaml](../../config/drone_config.yaml)

Centralized configuration file with sections for:

- `drone`: Network settings (IP, ports)
- `flight_controls`: Calibration data (you'll fill this!)
- `navigation`: PID gains and speed limits
- `safety`: Geofencing, emergency behaviors
- `camera`: Intrinsic parameters for SLAM
- `slam`: SLAM configuration
- `map`: Map file settings
- `api`: FastAPI server settings

#### 4. Test Logs

**Location**: `logs/flight_tests/`

All test sessions are logged to JSON files:
```
logs/flight_tests/
├── flight_test_20240216_143022.json
├── calibration_interrupted.json
└── ...
```

---

## Detailed Calibration Guide

### Full Calibration Process (1-2 Hours)

When ready for systematic testing:

```bash
python -m autonomous.testing.flight_control_test --mode calibrate
```

This guided calibration will test:
1. **Throttle** - Find hover value
2. **Pitch** - Forward/backward movement
3. **Roll** - Left/right movement
4. **Yaw** - Rotation

### What You'll Discover

#### 1. Hover Throttle Value (Most Important!)

- At what throttle value (0-255) does the drone maintain altitude?
- Usually around 140-160
- This is the foundation for all altitude control

#### 2. Movement Response

- How much pitch/roll causes gentle movement?
- What values are too aggressive?
- Is the response linear or non-linear?

#### 3. Safe Operating Ranges

- Maximum safe values for each control
- Dead zones (values that don't respond)
- Minimum values for movement

### Example Calibration Session

#### Finding Hover Value

```bash
python -m autonomous.testing.flight_control_test --mode test_throttle
```

Test sequence:
- Throttle 100: Stays on ground
- Throttle 128: Stays on ground
- Throttle 140: Gentle lift-off ✓
- Throttle 150: Steady hover ✓ **RECORD THIS**
- Throttle 160: Ascending
- Throttle 128: Descending

**Result**: Hover value = 150

#### Testing Forward Movement

```bash
python -m autonomous.testing.flight_control_test --mode test_pitch
```

With throttle at 150 (hovering):
- Pitch 128: No movement
- Pitch 135: Gentle forward ✓ **RECORD THIS**
- Pitch 145: Moderate forward ✓
- Pitch 165: Fast forward (too fast!) ⚠️

**Result**: Map gentle forward (0.5 m/s) → pitch 135

#### Testing Left/Right Movement

```bash
python -m autonomous.testing.flight_control_test --mode test_roll
```

Similar process for roll...

#### Testing Rotation

```bash
python -m autonomous.testing.flight_control_test --mode test_yaw
```

Similar process for yaw...

### Expected Timeline

- **Interactive exploration**: 30-60 minutes
  - Get familiar with controls
  - Test basic throttle, pitch, roll, yaw
  - Find approximate hover value

- **Full calibration**: 1-2 hours
  - Systematic testing of all axes
  - Document observations
  - Create velocity mapping

- **Configuration update**: 15-30 minutes
  - Update `config/drone_config.yaml` with findings
  - Create velocity → control value mappings

**Total: 2-4 hours** (can be split across multiple sessions)

---

## Understanding the System

### Why PID Controllers?

Your drone doesn't have position sensors - we'll estimate position using SLAM (Phase 3). The PID controllers convert position errors into velocity commands:

```
Target Position (x, y, z)
    ↓
Position Error = Target - Current
    ↓
PID Controller
    ↓
Velocity Command (vx, vy, vz)
    ↓
Calibration Mapping
    ↓
Control Values (throttle, pitch, roll)
    ↓
Drone Hardware
```

### The Calibration Flow

```
Phase 1 (NOW):
  Test controls → Document behavior → Create calibration map

Phase 2:
  Build UI → Display telemetry → Manual control with calibrated values

Phase 3:
  Add SLAM → Estimate position → Display on map

Phase 5:
  Use PID + calibration → Click map → Drone flies there!
```

### Why This Matters

The calibration data you create now will be the foundation for:
- Position hold
- Waypoint navigation
- Autonomous missions
- PID controller tuning

Without accurate calibration, autonomous navigation won't work properly!

---

## After Calibration

### Update Configuration File

Once you've completed testing, update [config/drone_config.yaml](../../config/drone_config.yaml):

```yaml
flight_controls:
  throttle:
    hover_value: 150  # YOUR MEASURED VALUE HERE
    velocity_map:
      -1.0: 110  # Descend 1.0 m/s
      -0.5: 130  # Descend 0.5 m/s
      0.0: 150   # HOVER VALUE
      0.5: 165   # Climb 0.5 m/s
      1.0: 180   # Climb 1.0 m/s

  pitch:
    velocity_map:
      -1.0: 100  # Backward 1.0 m/s
      -0.5: 115  # Backward 0.5 m/s
      0.0: 128   # Neutral
      0.5: 140   # Forward 0.5 m/s
      1.0: 155   # Forward 1.0 m/s

  roll:
    velocity_map:
      -1.0: 100  # Left 1.0 m/s
      -0.5: 115  # Left 0.5 m/s
      0.0: 128   # Neutral
      0.5: 140   # Right 0.5 m/s
      1.0: 155   # Right 1.0 m/s

  yaw:
    velocity_map:
      -90: 100   # Rotate left 90 deg/s
      -45: 115   # Rotate left 45 deg/s
      0: 128     # Neutral
      45: 140    # Rotate right 45 deg/s
      90: 155    # Rotate right 90 deg/s
```

---

## Troubleshooting

### Import Errors

```bash
# Verify dependencies installed
pip install -r requirements.txt

# Test import
python -c "from autonomous.navigation.pid_controller import PIDController; print('OK')"
```

### Can't Connect to Drone

```bash
# Test basic connectivity with existing system
python -m teky.app
# Visit http://localhost:5000 - does video work?

# Check WiFi connection
ping 192.168.1.1

# Run network diagnostics
python -m teky.network_diagnostics
```

### Drone Doesn't Respond to Commands

**Expected**: This is often normal! Flight controls are experimental.

**Solutions**:
1. **Test basic connectivity first**:
   ```bash
   python -m teky.app
   ```
   Visit http://localhost:5000 and test camera switching. If that works, UDP connection is good.

2. **Capture packets during real flight**:
   ```bash
   # Run packet sniffer while controlling from official Android app
   python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30
   ```
   Compare captured commands with our implementation.

3. **Verify command format**: Check that you're using the correct format:
   ```python
   [CMD_ID, throttle, yaw, pitch, roll, checksum]
   ```

### Drone Behaves Erratically

- Start with smaller value changes (±5 instead of ±10)
- Test in calm environment (no wind/drafts)
- Ensure battery is fully charged
- May need to adjust command format based on packet sniffing

### Need to See Actual Commands

```bash
# Use packet sniffer while controlling from Android app
python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30

# Compare with our commands
```

For more troubleshooting, see [Troubleshooting Guide](../getting-started/TROUBLESHOOTING.md).

---

## Safety Checklist

Before you start:

- [ ] Clear, open testing area (no obstacles, people, pets)
- [ ] Drone fully charged
- [ ] Consider tethering drone for first tests
- [ ] Emergency stop plan ready
- [ ] Low altitude testing (0.5-1.0m)
- [ ] Know how to manually power off drone
- [ ] Official Android app ready as backup
- [ ] Weather conditions suitable (no wind)

---

## What Success Looks Like

After completing Phase 1, you should have:

### ✅ Validated Flight Controls Work

- Drone responds to throttle commands (ascends/descends)
- Drone responds to pitch commands (forward/backward)
- Drone responds to roll commands (left/right)
- Drone responds to yaw commands (rotation)

### ✅ Calibration Data Collected

- Hover throttle value identified
- Velocity → control value mappings documented
- Safe operating ranges defined
- Test logs saved to `logs/flight_tests/`

### ✅ Configuration Updated

- `config/drone_config.yaml` populated with real values
- PID gains ready for tuning (can use defaults initially)

### ✅ Ready for Phase 2

- Foundation solid for building autonomous navigation
- Controls validated and documented
- Can proceed with confidence to React frontend + FastAPI backend

---

## Next Steps

### Coming in Phase 2: React + FastAPI Web Interface

Once Phase 1 is complete, we'll build:

1. **FastAPI Backend**
   - Wraps your existing `TEKYDroneControllerAdvanced`
   - REST API for drone control
   - WebSocket for real-time telemetry

2. **React Frontend**
   - Modern TypeScript UI
   - Live video feed display
   - Manual controls with calibrated values
   - Real-time status monitoring

3. **Testing Framework**
   - Verify PID controllers work with real calibration data
   - Live PID gain tuning UI
   - Position hold testing

**Estimated Phase 2 Duration**: 1-2 days of development + testing

See [Phase 2 Documentation](phase2-webapp.md) for details.

---

## Additional Resources

### Documentation

- **Getting Started**: [Getting Started Guide](../getting-started/README.md)
- **Quick Reference**: [Quick Reference](../getting-started/QUICK_REFERENCE.md)
- **Testing Guide**: [autonomous/testing/README.md](../../autonomous/testing/README.md)
- **Config Reference**: [config/drone_config.yaml](../../config/drone_config.yaml)

### Code References

- **PID Controller**: [autonomous/navigation/pid_controller.py](../../autonomous/navigation/pid_controller.py)
- **Test Harness**: [autonomous/testing/flight_control_test.py](../../autonomous/testing/flight_control_test.py)
- **Existing Controller**: [teky/drone_controller_advanced.py](../../teky/drone_controller_advanced.py)

### Existing Tools (Still Available)

- **Flask Web App**: `python -m teky.app` (http://localhost:5000)
- **Packet Sniffer**: `python -m teky.tools.packet_sniffer`
- **UDP Proxy**: `python -m teky.tools.udp_proxy`
- **Network Diagnostics**: `python -m teky.network_diagnostics`

---

## You're Ready!

Everything is set up for Phase 1 calibration. The tools are ready, documentation is complete, and you have a clear path forward.

**First command to run**:
```bash
python -m autonomous.testing.flight_control_test --mode interactive
```

Good luck with your calibration testing! Remember:
- **Safety first**: Clear area, low altitude, emergency stop ready
- **Start small**: Interactive mode before full calibration
- **Document everything**: The logs are valuable for later phases
- **Be patient**: This is experimental hardware - iteration is expected

**Ready to transform your drone into an autonomous navigator!** 🚁✨

---

*For detailed troubleshooting, see [Troubleshooting Guide](../getting-started/TROUBLESHOOTING.md).*
