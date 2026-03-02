# TYVYX Drone Documentation

## Getting Started

- [Quick Reference](getting-started/QUICK_REFERENCE.md) - Command cheat sheet
- [Troubleshooting](getting-started/TROUBLESHOOTING.md) - Common issues and solutions
- [Main README](../README.md) - Project overview and quick start

## Implementation Guides

- [Phase 1: Flight Control Calibration](guides/phase1-calibration.md) - Calibrate flight controls
- [Phase 2: React + FastAPI Web App](guides/phase2-webapp.md) - Web interface
- [Turbodrone Architecture Integration](guides/turbodrone-architecture.md) - Architecture patterns

## Technical Reference

- [API Reference](API_REFERENCE.md) - All endpoints and modules
- [Protocol Specification](technical/protocol-specification.md) - K417 and E88Pro packet formats
- [System Architecture](technical/architecture.md) - Component relationships and data flow
- [Reverse Engineering Notes](technical/reverse-engineering.md) - E88Pro protocol analysis

## Contributing

- [Contributing Guidelines](contributing/CONTRIBUTING.md) - How to contribute
- [Development Setup](contributing/DEVELOPMENT.md) - Environment setup

## Project Status

- Phase 1: Flight control calibration (complete)
- Phase 2: React + FastAPI web interface, 21fps video (complete)
- Phase 3: Sensor fusion position tracking - optical flow, depth, RSSI, EKF (in progress)
- Phase 4-7: SLAM, waypoint navigation, mapping (planned)

> Some docs in `guides/` reference earlier architecture. The protocol-specification.md and API_REFERENCE.md are current.

## Quick Links

- [Configuration](../config/drone_config.yaml) - Drone configuration
- [Frontend README](../frontend/README.md) - React UI docs
