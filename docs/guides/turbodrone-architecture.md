# Turbodrone Architecture Integration

Turbodrone (`I:\Projects\turbodrone`) is a reverse-engineered control system for budget toy drones (S20, S29, V88, D16, E58). While it controls different drones, its architecture patterns were adapted for TYVYX.

## What Was Integrated

### Control Profile System (`autonomous/models/control_profile.py`)
- Defines control behavior: acceleration, deceleration, exponential curves
- Predefined profiles: normal (0.5 expo), precise (0.3), aggressive (1.5), autonomous (0.0 linear)
- Maps stick ranges (0-255) to normalized values (-1.0 to +1.0)

### BaseRCModel (`autonomous/models/base_rc.py`)
- Abstract base for drone control models
- Manages throttle/yaw/pitch/roll with smooth acceleration/deceleration
- Profile-based behavior, command flags (takeoff, land, stop)

### TYVYX RC Model (`autonomous/models/tyvyx_rc.py`)
- Implements BaseRCModel for TYVYX drones
- Builds flight control packets per drone protocol

### Flight Controller Service (`autonomous/services/flight_controller.py`)
- 80 Hz control loop (12.5ms update interval)
- Async and sync versions
- UDP packet sending with statistics

## Architecture

```
FlightController (80 Hz loop)       <- Service layer
  -> TYVYXRCModel (protocol-specific) <- Model layer
    -> BaseRCModel (abstract)          <- Abstract base
      -> ControlProfile + StickRange   <- Configuration
```

## Integration with Current System

The turbodrone patterns complement the existing `tyvyx/` codebase:

- `tyvyx/wifi_uav_controller.py` - K417 controller (primary, handles protocol engine)
- `tyvyx/drone_controller_advanced.py` - E88Pro controller (legacy)
- `autonomous/models/` - Control models and profiles (from turbodrone)
- `autonomous/services/` - High-level services wrapping controllers
