# Phase 1: Flight Control Testing

Tools for testing and calibrating reverse-engineered drone flight controls.

**Safety**: Clear area, low altitude, emergency stop ready, fully charged battery.

## Quick Start

```bash
# Connect to drone WiFi (Drone-xxxxxx, FLOW_xxxxxx, K417-*)
ping 192.168.169.1

# Install dependencies
pip install -r requirements.txt

# Interactive testing
python -m autonomous.testing.flight_control_test --mode interactive
```

## Test Modes

| Mode | Command | Purpose |
|------|---------|---------|
| Interactive | `--mode interactive` | Manual exploration, log observations |
| Full calibration | `--mode calibrate` | Guided sequence for all axes |
| Throttle only | `--mode test_throttle` | Find hover value |
| Pitch only | `--mode test_pitch` | Forward/backward response |
| Roll only | `--mode test_roll` | Left/right response |
| Yaw only | `--mode test_yaw` | Rotation response |

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

- 0-127: Below neutral (descend, backward, left, counter-clockwise)
- 128: Neutral
- 129-255: Above neutral (ascend, forward, right, clockwise)

## Output

Test data saved to `logs/flight_tests/` as JSON. After testing, update `config/drone_config.yaml` with your calibration values. See [Phase 1 Guide](../../docs/guides/phase1-calibration.md) for details.
