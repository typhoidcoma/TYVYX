# TYVYX Drone Documentation

Welcome to the TYVYX Drone project documentation. This index provides navigation to all available documentation organized by purpose and audience.

## Getting Started

New to TYVYX? Start here:

- **[Quick Reference](getting-started/QUICK_REFERENCE.md)** - Command cheat sheet and shortcuts
- **[Troubleshooting](getting-started/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Main README](../README.md)** - Project overview and quick start

## Implementation Guides

Detailed guides for each development phase and feature:

- **[Phase 1: Flight Control Calibration](guides/phase1-calibration.md)** - Calibrate flight controls and test basic functionality
- **[Phase 2: React + FastAPI Web App](guides/phase2-webapp.md)** - Modern web interface setup and usage
- **[Turbodrone Architecture Integration](guides/turbodrone-architecture.md)** - Autonomous navigation architecture patterns

## Technical Reference

Deep technical documentation:

- **[API Reference](API_REFERENCE.md)** - Module, class, and function documentation
- **[Reverse Engineering Notes](technical/reverse-engineering.md)** - UDP protocol analysis and findings
- **[Protocol Specification](technical/protocol-specification.md)** - Formal packet format and command reference
- **[System Architecture](technical/architecture.md)** - Component relationships and data flow

## Contributing

Want to contribute to TYVYX?

- **[Contributing Guidelines](contributing/CONTRIBUTING.md)** - How to contribute code and documentation
- **[Development Setup](contributing/DEVELOPMENT.md)** - Setting up your development environment

## Project Status

### Completed Phases
- ✅ Phase 1: Flight control calibration tools
- ✅ Phase 2: React + FastAPI web interface (21fps live video via K417 protocol engine)

### In Progress
- 🚧 Phase 3: Optical flow position estimation

> **Note**: Some docs in `guides/` and `technical/` reference earlier architecture (E88Pro-first, Flask app). The protocol-specification.md has been updated with K417 details. Other docs may lag behind.

### Planned
- 📋 Phase 4: SLAM integration
- 📋 Phase 5: Waypoint navigation
- 📋 Phase 6: Autonomous mapping
- 📋 Phase 7: Advanced SLAM (ORB-SLAM3, RTAB-Map)

## Quick Links

- **[Main Project README](../README.md)** - Project overview and quick start
- **[Configuration](../config/drone_config.yaml)** - Drone configuration file
- **[Frontend README](../frontend/README.md)** - React UI documentation

## Documentation Organization

This documentation is organized by purpose:

- **getting-started/** - Onboarding materials for new users
- **guides/** - Step-by-step implementation guides organized by phase
- **technical/** - Deep technical references and specifications
- **contributing/** - Information for contributors and developers

## Need Help?

- Check the [Troubleshooting Guide](getting-started/TROUBLESHOOTING.md) for common issues
- Review the [Quick Reference](getting-started/QUICK_REFERENCE.md) for command syntax
- Read the relevant phase guide for detailed instructions

## Safety Warning

⚠️ **Always fly responsibly:**
- Test in open, safe areas away from people and obstacles
- Keep drone in visual line of sight at all times
- Be prepared for unexpected behavior during development
- Follow all local regulations and laws
- Never fly near airports, crowds, or restricted areas

---

*Documentation last reorganized: February 2026*
