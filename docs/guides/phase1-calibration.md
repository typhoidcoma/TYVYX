# Phase 1: Flight Control Calibration

Test and calibrate reverse-engineered flight controls. Map desired velocities to drone control values (0-255).

**Safety**: Clear area, low altitude (0.5-1m), emergency stop ready, drone fully charged.

## Quick Start

```bash
# Connect to drone WiFi (Drone-xxxxxx, FLOW_xxxxxx, K417-*)
ping 192.168.169.1

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

## Interactive Commands

| Command | Description |
|---------|-------------|
| `t <value>` | Set throttle (0-255) |
| `y <value>` | Set yaw (0-255) |
| `p <value>` | Set pitch (0-255) |
| `r <value>` | Set roll (0-255) |
| `reset` | Reset all to neutral (128) |
| `status` | Show current values |
| `log <msg>` | Log observation |
| `quit` | Exit |

## Control Values

- **0-127**: Below neutral (descend, backward, left, counter-clockwise)
- **128**: Neutral (no movement)
- **129-255**: Above neutral (ascend, forward, right, clockwise)

## What to Measure

- **Hover throttle**: Value where drone maintains altitude (usually 140-160)
- **Movement thresholds**: Minimum pitch/roll for gentle movement
- **Safe ranges**: Maximum values before too aggressive
- **Dead zones**: Values that produce no response

## Output

Test data saved to `logs/flight_tests/` as JSON files.

## Update Config

After testing, update `config/drone_config.yaml`:

```yaml
flight_controls:
  throttle:
    hover_value: 150
    velocity_map:
      -1.0: 110
      0.0: 150
      0.5: 165
      1.0: 180

  pitch:
    velocity_map:
      -0.5: 115
      0.0: 128
      0.5: 140

  roll:
    velocity_map:
      -0.5: 115
      0.0: 128
      0.5: 140

  yaw:
    velocity_map:
      -45: 115
      0: 128
      45: 140
```

This calibration data feeds into PID controllers for autonomous navigation.
