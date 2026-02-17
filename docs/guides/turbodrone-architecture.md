# Turbodrone Architecture Integration

This document explains the integration of turbodrone's proven architecture into the TYVYX autonomous drone system.

## What is Turbodrone?

Turbodrone is a fully reverse-engineered control system for budget toy drones ($50 range) found at `I:\Projects\turbodrone`. It supports multiple drone families (S20, S29, V88, D16, E58) with:

✅ **Fully working flight control** (80 Hz update rate)
✅ **Clean protocol adapter pattern**
✅ **Control profiles** (normal, precise, aggressive)
✅ **Robust video reassembly**
✅ **Production-ready architecture**

## What We Integrated

While turbodrone controls **different drones** than TYVYX, its **architecture patterns** are excellent and have been adapted for our autonomous system.

### Core Components Integrated

#### 1. Control Profile System
**Files:**
- [`autonomous/models/control_profile.py`](autonomous/models/control_profile.py)

**What it does:**
- Defines control behavior (acceleration, deceleration, exponential curves)
- Maps stick ranges (min/mid/max) to normalized values (-1.0 to +1.0)
- Provides predefined profiles: normal, precise, aggressive, autonomous

**Usage:**
```python
from autonomous.models import ControlProfile, StickRange, get_profile

# Get a predefined profile
profile = get_profile("normal")  # or "precise", "aggressive", "autonomous"

# Apply expo curve to control input
normalized_value = 0.5  # 50% forward
expo_value = profile.apply_expo(normalized_value)

# Define custom stick range
stick_range = StickRange(min=0.0, mid=128.0, max=255.0)
```

**Profiles:**
```python
PROFILES = {
    "normal":      # Balanced response (expo=0.5)
    "precise":     # Gentle, gradual (expo=0.3)
    "aggressive":  # Fast, responsive (expo=1.5)
    "autonomous":  # Linear for PID (expo=0.0)
}
```

#### 2. BaseRCModel Abstraction
**Files:**
- [`autonomous/models/base_rc.py`](autonomous/models/base_rc.py)

**What it does:**
- Abstract base class for all drone control models
- Manages throttle, yaw, pitch, roll values with acceleration/deceleration
- Handles takeoff/land/stop commands
- Normalizes control values between stick range and protocol range

**Key Features:**
- **Smooth control transitions** - acceleration/deceleration curves
- **Normalized interface** - work with -1.0 to +1.0 values
- **Profile-based behavior** - swap profiles on the fly
- **Command flags** - takeoff, land, stop (cleared after packet sent)

**Interface:**
```python
class BaseRCModel(ABC):
    # Properties
    throttle, yaw, pitch, roll  # Stick range values

    # Methods
    def set_normalized_controls(throttle, yaw, pitch, roll)  # -1.0 to +1.0
    def get_normalized_controls() -> dict
    def update(dt) -> bool  # Apply accel/decel
    def takeoff(), land(), stop()
    def reset_controls()

    # Abstract
    def build_control_packet() -> bytes  # Implement per drone
```

#### 3. TYVYX RC Model
**Files:**
- [`autonomous/models/tyvyx_rc.py`](autonomous/models/tyvyx_rc.py)

**What it does:**
- Implements BaseRCModel specifically for TYVYX drone
- Builds experimental flight control packets: `[0x50, throttle, yaw, pitch, roll, checksum]`
- Also handles camera switch and screen mode commands

**Usage:**
```python
from autonomous.models import TYVYXRCModel, create_tyvyx_rc, create_autonomous_tyvyx_rc

# Create with default settings
rc_model = create_tyvyx_rc(profile="normal")

# Or create for autonomous control (linear response)
rc_model = create_autonomous_tyvyx_rc()

# Set controls (normalized -1.0 to +1.0)
rc_model.set_normalized_controls(
    throttle=0.5,   # 50% throttle
    pitch=0.3,      # 30% forward
    roll=0.0,       # No roll
    yaw=0.0         # No rotation
)

# Update (applies accel/decel)
rc_model.update(dt=0.0125)  # 80 Hz = 12.5ms

# Build packet
packet = rc_model.build_control_packet()  # Returns 6 bytes

# Commands
rc_model.takeoff()
rc_model.land()
rc_model.stop()  # Emergency stop + reset controls
```

**TYVYX Protocol (Experimental):**
```python
# Flight control packet (6 bytes)
[CMD_ID, throttle, yaw, pitch, roll, checksum]

CMD_ID = 0x50
throttle, yaw, pitch, roll = 0-255 (128 = neutral)
checksum = (sum of all bytes) & 0xFF

# Other commands
HEARTBEAT = [0x01, 0x01]
CAMERA_1 = [0x06, 0x01]
CAMERA_2 = [0x06, 0x02]
SCREEN_1 = [0x09, 0x01]
SCREEN_2 = [0x09, 0x02]
```

#### 4. Flight Controller Service
**Files:**
- [`autonomous/services/flight_controller.py`](autonomous/services/flight_controller.py)

**What it does:**
- 80 Hz control loop (12.5ms update interval)
- Sends UDP packets to drone
- Async (FlightController) and sync (FlightControllerSync) versions
- Packet statistics and callbacks

**Usage (Async):**
```python
from autonomous.models import create_tyvyx_rc
from autonomous.services import FlightController

# Create RC model
rc_model = create_tyvyx_rc(profile="normal")

# Create flight controller
controller = FlightController(
    rc_model=rc_model,
    drone_ip="192.168.1.1",
    control_port=7099,
    update_rate_hz=80.0
)

# Connect and start
controller.connect()
await controller.start()

# Control via RC model
rc_model.set_normalized_controls(throttle=0.5)

# Stop
await controller.stop()
controller.disconnect()
```

**Usage (Sync - for Phase 1 testing):**
```python
from autonomous.services import FlightControllerSync

controller = FlightControllerSync(rc_model, drone_ip="192.168.1.1")
controller.connect()
controller.start()  # Runs in background thread

# Control via RC model
rc_model.set_normalized_controls(throttle=0.5)

controller.stop()
controller.disconnect()
```

## Architecture Benefits

### Clean Separation of Concerns

```
┌─────────────────────────────────────┐
│   FlightController (80 Hz loop)    │  ← Service layer
│   - UDP socket management          │
│   - Packet sending                 │
│   - Statistics                     │
└─────────────┬───────────────────────┘
              │
              │ uses
              ▼
┌─────────────────────────────────────┐
│   TYVYXRCModel (protocol-specific)   │  ← Model layer
│   - Builds packets                  │
│   - Protocol constants              │
│   - Command flags                   │
└─────────────┬───────────────────────┘
              │
              │ extends
              ▼
┌─────────────────────────────────────┐
│   BaseRCModel (abstract)            │  ← Abstract base
│   - Control value management        │
│   - Accel/decel logic               │
│   - Normalization                   │
└─────────────┬───────────────────────┘
              │
              │ uses
              ▼
┌─────────────────────────────────────┐
│   ControlProfile + StickRange       │  ← Configuration
│   - Expo curves                     │
│   - Stick ranges                    │
│   - Profiles (normal/precise/etc)   │
└─────────────────────────────────────┘
```

### Key Advantages

1. **Testability** - Each layer can be tested independently
2. **Flexibility** - Swap profiles, change update rates, modify protocols
3. **Extensibility** - Add new drone types by subclassing BaseRCModel
4. **Proven** - Architecture based on working turbodrone implementation
5. **Autonomous-ready** - Linear profile for PID control

## Integration with Existing TYVYX Code

The new architecture **complements** rather than replaces existing code:

**Existing (Keep):**
- `tyvyx/drone_controller.py` - Original implementation (fallback)
- `tyvyx/drone_controller_advanced.py` - Flight controller class
- `tyvyx/video_stream.py` - RTSP video streaming
- `tyvyx/app.py` - Flask web interface

**New (Turbodrone-inspired):**
- `autonomous/models/` - Control models and profiles
- `autonomous/services/` - Flight controller service
- `autonomous/navigation/` - PID controllers
- `autonomous/testing/` - Calibration tools

**How they work together:**
```python
# Option 1: Use new architecture directly
from autonomous.models import create_tyvyx_rc
from autonomous.services import FlightControllerSync

rc_model = create_tyvyx_rc()
controller = FlightControllerSync(rc_model)
controller.start()

# Option 2: Wrap existing TYVYXDroneControllerAdvanced
from tyvyx.drone_controller_advanced import TYVYXDroneControllerAdvanced
existing_controller = TYVYXDroneControllerAdvanced()
# Use FlightController's methods but with existing controller
```

## Phase 1 Integration

The Phase 1 flight control test harness has been updated to leverage this architecture:

**Before (manual byte manipulation):**
```python
self.drone.flight_controller.throttle = 150  # Direct value
```

**After (profile-based control):**
```python
rc_model = create_tyvyx_rc(profile="normal")
rc_model.set_normalized_controls(throttle=0.4)  # 40% throttle
rc_model.update(dt=0.0125)  # Smooth transition
packet = rc_model.build_control_packet()
```

## Calibration Integration

The control profile system integrates with Phase 1 calibration:

**From calibration data:**
```yaml
# config/drone_config.yaml
flight_controls:
  throttle:
    hover_value: 150
    velocity_map:
      0.0: 150  # Hover
      0.5: 165  # Climb 0.5 m/s
```

**Load into RC model:**
```python
from autonomous.models import TYVYXRCModel

# Create from calibration
rc_model = TYVYXRCModel.from_calibration(
    calibration_data=config['flight_controls'],
    profile_name="normal"
)
```

## PID Integration (Phase 5)

The autonomous profile is designed for PID control:

**PID → Velocity → Control Values:**
```python
from autonomous.navigation import DronePositionController
from autonomous.models import create_autonomous_tyvyx_rc

# Create autonomous RC model (linear response)
rc_model = create_autonomous_tyvyx_rc()

# Create PID controller
pid = DronePositionController()
pid.set_target(x=5.0, y=3.0, z=1.5)

# Control loop
current_pos = get_current_position()  # From SLAM
velocity_cmd = pid.update(current_pos[0], current_pos[1], current_pos[2])

# Map velocity to control values
rc_model.set_normalized_controls(
    pitch=velocity_cmd['vx'] / MAX_VELOCITY,  # Normalize to -1.0 to +1.0
    roll=velocity_cmd['vy'] / MAX_VELOCITY,
    throttle=velocity_cmd['vz'] / MAX_VELOCITY
)

# Send to drone (80 Hz loop handles this)
```

## Comparison: Turbodrone vs TYVYX

| Aspect | Turbodrone (S20/V88/etc) | TYVYX | Integration |
|--------|--------------------------|------|-------------|
| **Protocol** | S2x, WiFi UAV (fully known) | Experimental (needs validation) | Architecture adapted |
| **Control Port** | 8080 (S2x), 8800 (WiFi UAV) | 7099 | Configurable |
| **Packet Format** | 20-byte (S2x), 85-byte (WiFi UAV) | 6-byte experimental | TYVYX-specific impl |
| **Update Rate** | 80 Hz | 80 Hz (adopted) | ✅ Same |
| **Profiles** | normal/precise/aggressive | Adopted | ✅ Integrated |
| **Video** | JPEG reassembly | RTSP streaming | Keep existing |
| **Architecture** | Protocol adapters | Adapted | ✅ Integrated |

## Files Created/Modified

### New Files
```
autonomous/
├── models/
│   ├── __init__.py          ✅ Created
│   ├── control_profile.py   ✅ Created - Profiles and stick ranges
│   ├── base_rc.py           ✅ Created - Abstract RC model
│   └── tyvyx_rc.py           ✅ Created - TYVYX-specific implementation
└── services/
    ├── __init__.py          ✅ Created
    └── flight_controller.py ✅ Created - 80 Hz control loop
```

### Existing Files (Unchanged)
```
tyvyx/
├── drone_controller.py              ← Keep as-is
├── drone_controller_advanced.py     ← Keep as-is
└── video_stream.py                  ← Keep as-is
```

## Next Steps

1. **Phase 1 Testing** - Use new architecture in flight control calibration
2. **Validate Protocol** - Confirm experimental TYVYX commands work
3. **Calibration Integration** - Load calibration data into profiles
4. **PID Integration** - Connect autonomous profile to position controller
5. **FastAPI Migration** - Use FlightController in new backend

## Quick Reference

**Create RC model:**
```python
from autonomous.models import create_tyvyx_rc, create_autonomous_tyvyx_rc

rc_model = create_tyvyx_rc("normal")         # Manual control
rc_model = create_autonomous_tyvyx_rc()      # PID control
```

**Control with normalized values:**
```python
rc_model.set_normalized_controls(
    throttle=0.5,   # -1.0 to +1.0
    pitch=0.3,
    roll=-0.2,
    yaw=0.0
)
```

**Use flight controller:**
```python
from autonomous.services import FlightControllerSync

controller = FlightControllerSync(rc_model)
controller.start()  # 80 Hz loop in background
# ...
controller.stop()
```

**Access profiles:**
```python
from autonomous.models import get_profile, PROFILES

profile = get_profile("precise")
print(profile.expo)  # 0.3
```

---

**The turbodrone architecture provides a solid, proven foundation for the TYVYX autonomous system while maintaining compatibility with existing code!** 🚁✨
