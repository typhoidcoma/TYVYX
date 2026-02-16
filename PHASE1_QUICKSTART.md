# Phase 1: Flight Control Calibration - Quick Start Guide

## 🎯 What is Phase 1?

Phase 1 is the **critical foundation** for the autonomous drone system. Before we can build autonomous navigation, we need to verify that the experimental flight control commands actually work and calibrate them.

**The experimental flight controls** use a reverse-engineered command format:
```
[CMD_ID, throttle, yaw, pitch, roll, checksum]
```

Where CMD_ID = 0x50 and each value is 0-255 (128 = neutral).

**Your mission**: Test these controls systematically and document what works!

## ⚡ Quick Start (5 minutes)

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Connect to Drone WiFi

Connect your computer to the drone's WiFi network:
- Look for networks starting with: `HD-720P-*`, `HD-FPV-*`, `HD720-*`, or `FHD-*`
- Drone IP should be: `192.168.1.1`
- Verify: `ping 192.168.1.1`

### Step 3: Run Interactive Test Mode

```bash
python -m autonomous.testing.flight_control_test --mode interactive
```

This gives you manual control to experiment safely:

```
Control> t 150        # Set throttle to 150
Control> log Drone lifts off slowly
Control> t 128        # Back to neutral
Control> reset        # Reset everything
Control> quit         # Exit
```

### Step 4: Run Full Calibration (When Ready)

```bash
python -m autonomous.testing.flight_control_test --mode calibrate
```

This will guide you through testing:
1. **Throttle** - Find hover value
2. **Pitch** - Forward/backward movement
3. **Roll** - Left/right movement
4. **Yaw** - Rotation

All data is logged to `logs/flight_tests/`

## 📊 What You'll Discover

### Critical Values to Find:

1. **Hover Throttle Value** (Most Important!)
   - At what throttle value (0-255) does the drone maintain altitude?
   - Usually around 140-160
   - This is the foundation for all altitude control

2. **Movement Response**
   - How much pitch/roll causes gentle movement?
   - What values are too aggressive?
   - Is the response linear or non-linear?

3. **Safe Operating Ranges**
   - Maximum safe values for each control
   - Dead zones (values that don't respond)
   - Minimum values for movement

## 📝 Expected Timeline

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

## ⚠️ Safety Checklist

Before you start:
- [ ] Clear, open testing area (no obstacles, people, pets)
- [ ] Drone fully charged
- [ ] Consider tethering drone for first tests
- [ ] Emergency stop plan ready
- [ ] Low altitude testing (0.5-1.0m)
- [ ] Know how to manually power off drone

## 🎮 Control Reference

### Control Values (0-255)
- **0-127**: Below neutral (descend, backward, left, counter-clockwise)
- **128**: Neutral (should be no movement)
- **129-255**: Above neutral (ascend, forward, right, clockwise)

### Interactive Mode Commands
```
t <value>     Set throttle (0-255)
y <value>     Set yaw (0-255)
p <value>     Set pitch (0-255)
r <value>     Set roll (0-255)
reset         Reset all to neutral (128)
status        Show current values
log <msg>     Log observation
quit          Exit
```

## 📂 Output Files

Test logs are saved to:
```
logs/flight_tests/
├── flight_test_20240216_143022.json
└── calibration_interrupted.json
```

Configuration to update:
```
config/drone_config.yaml
```

## 🔍 Example Calibration Flow

### 1. Find Hover Value

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

### 2. Test Forward Movement

```bash
python -m autonomous.testing.flight_control_test --mode test_pitch
```

With throttle at 150 (hovering):
- Pitch 128: No movement
- Pitch 135: Gentle forward ✓ **RECORD THIS**
- Pitch 145: Moderate forward ✓
- Pitch 165: Fast forward (too fast!) ⚠️

**Result**: Map gentle forward (0.5 m/s) → pitch 135

### 3. Test Left/Right Movement

Similar process for roll...

### 4. Test Rotation

Similar process for yaw...

## 📋 After Calibration

Once you've completed testing, you should have:

1. **Test Logs**: JSON files in `logs/flight_tests/` with all observations

2. **Updated Config**: Edit `config/drone_config.yaml`:
   ```yaml
   flight_controls:
     throttle:
       hover_value: 150  # YOUR VALUE HERE
       velocity_map:
         -1.0: 110  # YOUR VALUE
         0.0: 150   # HOVER VALUE
         0.5: 165   # YOUR VALUE
         1.0: 180   # YOUR VALUE
   ```

3. **Knowledge of Drone Behavior**: Understanding of how controls affect movement

## 🐛 Troubleshooting

### Drone doesn't respond
```bash
# Test basic connectivity first
python -m teky.app  # Visit http://localhost:5000

# Check video feed and camera switching
# If that works, UDP connection is good
```

### Need to see actual commands
```bash
# Use packet sniffer while controlling from Android app
python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30

# Compare with our commands
```

### Drone behaves erratically
- Start with smaller value changes (±5 instead of ±10)
- Test in calm environment (no wind/drafts)
- Ensure battery is fully charged
- May need to adjust command format based on packet sniffing

## 🚀 Next: Phase 2

After successful Phase 1 calibration, you'll be ready for:

**Phase 2: React Frontend + FastAPI Backend**
- Modern web UI
- Real-time telemetry via WebSocket
- Manual controls with your calibrated values
- Live video feed display

The calibration data you create now will be the foundation for PID control and autonomous navigation in later phases!

## 📚 Detailed Documentation

For comprehensive instructions, see:
- [autonomous/testing/README.md](autonomous/testing/README.md) - Full testing guide
- [config/drone_config.yaml](config/drone_config.yaml) - Configuration reference
- Plan file: `~/.claude/plans/fluttering-soaring-horizon.md`

---

**Ready to start? Run this command:**

```bash
python -m autonomous.testing.flight_control_test --mode interactive
```

**Safety first, have fun testing! 🚁✨**
