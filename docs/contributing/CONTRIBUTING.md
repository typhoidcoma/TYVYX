# Contributing to TEKY Drone

Thank you for your interest in contributing to the TEKY drone controller project! This document provides guidelines for contributing code, documentation, and discoveries.

## Table of Contents

- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Workflow](#development-workflow)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing Requirements](#testing-requirements)
- [Documentation Standards](#documentation-standards)
- [Community Guidelines](#community-guidelines)

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:
- Python 3.8 or higher installed
- Node.js 16+ (for frontend contributions)
- FFmpeg installed for video streaming
- A TEKY WiFi drone for testing (recommended)
- Git for version control

### Initial Setup

1. **Fork the repository** on GitHub

2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/TEKY.git
   cd TEKY
   ```

3. **Set up Python environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Set up frontend** (if contributing to React UI):
   ```bash
   cd frontend
   npm install
   cd ..
   ```

5. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## How to Contribute

### Types of Contributions

We welcome several types of contributions:

#### 1. Code Contributions
- Bug fixes
- New features (navigation, UI improvements, etc.)
- Performance optimizations
- Test coverage improvements

#### 2. Protocol Discoveries
- New UDP command findings
- Flight control command patterns
- Telemetry data parsing
- Video stream improvements

#### 3. Documentation
- Tutorial improvements
- API documentation
- Troubleshooting guides
- Architecture clarifications

#### 4. Testing
- Flight test results
- Calibration data for different models
- Bug reports with reproducible steps
- Performance benchmarks

---

## Development Workflow

### 1. Create an Issue (Optional but Recommended)

Before starting significant work:
- Check existing issues to avoid duplication
- Create a new issue describing your proposed change
- Discuss the approach with maintainers
- Get feedback before investing time

### 2. Make Your Changes

Follow these guidelines:
- **Keep changes focused**: One feature/fix per pull request
- **Write tests**: Add unit tests for new functionality
- **Update documentation**: Keep docs in sync with code changes
- **Follow code style**: Use provided linters (ruff, ESLint)

### 3. Test Your Changes

#### Backend Testing
```bash
# Run unit tests
pytest tests/

# Run linter
ruff check .

# Format code
black .
```

#### Frontend Testing
```bash
cd frontend

# Run linter
npm run lint

# Build to verify
npm run build
```

#### Integration Testing
- Test with actual drone if possible
- Document behavior changes
- Test all affected features

### 4. Commit Your Changes

Use clear, descriptive commit messages:

**Good commit messages**:
```
feat: Add PID controller for altitude hold

Implements a PID controller that maintains target altitude using
throttle commands. Tested with hover value of 150.

Closes #42
```

```
fix: Resolve video stream reconnection issue

The video stream would not reconnect after stopping. Added proper
cleanup of cv2.VideoCapture resources.

Fixes #38
```

```
docs: Update troubleshooting guide with FFmpeg issues

Added section on common FFmpeg installation and configuration
problems based on user feedback.
```

**Commit message format**:
```
<type>: <short summary>

<detailed description>

<issue references>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks

### 5. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 6. Create a Pull Request

1. Go to the original repository on GitHub
2. Click "New Pull Request"
3. Select your fork and branch
4. Fill out the PR template with:
   - **Description** of changes
   - **Testing** performed
   - **Related issues** (if any)
   - **Screenshots/videos** (for UI changes)

---

## Code Style Guidelines

### Python Code Style

We follow **PEP 8** with some project-specific conventions:

#### Use Ruff for Linting
```bash
ruff check .
ruff check --fix .  # Auto-fix issues
```

#### Use Black for Formatting
```bash
black .
```

#### Code Conventions
- **Line length**: 100 characters (not 79)
- **Imports**: Group stdlib, third-party, local imports
- **Type hints**: Use for function signatures
- **Docstrings**: Use for public functions and classes

**Example**:
```python
from typing import Optional
import socket
import time

from teky.video_stream import VideoStream


class DroneController:
    """
    Controls TEKY drone via UDP commands.

    Args:
        drone_ip: IP address of drone (default: 192.168.1.1)
        port: UDP port for commands (default: 7099)
    """

    def __init__(self, drone_ip: str = "192.168.1.1", port: int = 7099):
        self.drone_ip = drone_ip
        self.port = port
        self._socket: Optional[socket.socket] = None

    def connect(self) -> bool:
        """
        Establish UDP connection to drone.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
```

### TypeScript/React Code Style

We use **ESLint** and **Prettier** for consistency:

#### Run Linter
```bash
cd frontend
npm run lint
```

#### Code Conventions
- **Functional components**: Use function components with hooks
- **Type safety**: Define interfaces for props and state
- **Naming**: PascalCase for components, camelCase for functions/variables

**Example**:
```typescript
interface DroneStatus {
  connected: boolean;
  videoStreaming: boolean;
  batteryLevel?: number;
}

interface DroneControlsProps {
  onConnect: () => void;
  onDisconnect: () => void;
  status: DroneStatus;
}

export function DroneControls({ onConnect, onDisconnect, status }: DroneControlsProps) {
  return (
    <div className="drone-controls">
      <button
        onClick={status.connected ? onDisconnect : onConnect}
        className="btn"
      >
        {status.connected ? 'Disconnect' : 'Connect'}
      </button>
    </div>
  );
}
```

---

## Testing Requirements

### Unit Tests (Python)

Use **pytest** for testing:

```python
# tests/test_drone_controller.py
import pytest
from teky.drone_controller import DroneController


def test_drone_controller_initialization():
    """Test that controller initializes with correct defaults."""
    controller = DroneController()
    assert controller.drone_ip == "192.168.1.1"
    assert controller.port == 7099


def test_heartbeat_command():
    """Test that heartbeat command generates correct bytes."""
    controller = DroneController()
    heartbeat = controller._create_heartbeat()
    assert heartbeat == bytes([0x01, 0x01])
```

Run tests:
```bash
pytest tests/
pytest tests/test_drone_controller.py  # Specific file
pytest -v  # Verbose output
pytest --cov=teky  # With coverage
```

### Integration Tests

For features requiring drone hardware:

1. **Document test procedure** in comments
2. **Log test results** to `logs/flight_tests/`
3. **Include findings** in PR description
4. **Add to manual test checklist**

Example test documentation:
```python
# Flight Test: Throttle Response
# Date: 2024-02-16
# Drone Model: HD-720P-XXX
#
# Test Procedure:
# 1. Set throttle to 128 (neutral) - Drone remains on ground
# 2. Increment throttle by 5 until lift-off
# 3. Record hover value
#
# Results:
# - Lift-off at throttle 140
# - Stable hover at throttle 150
# - Max tested: throttle 180
```

---

## Documentation Standards

### Code Documentation

- **Docstrings**: Use for all public functions, classes, and modules
- **Inline comments**: Explain "why", not "what"
- **Type hints**: Provide type information for clarity

### File Documentation

When creating new files, include a module docstring:

```python
"""
Module for PID controller implementation.

This module provides PID (Proportional-Integral-Derivative) controllers
for position and velocity control of the TEKY drone.

Example:
    >>> controller = PIDController(kp=1.0, ki=0.1, kd=0.05)
    >>> output = controller.update(setpoint=10.0, measurement=8.5, dt=0.1)
"""
```

### Markdown Documentation

- Use clear headers (# ## ###)
- Include code examples with syntax highlighting
- Add tables for structured information
- Link to related documentation
- Include "last updated" dates

---

## Community Guidelines

### Be Respectful

- Treat all contributors with respect
- Welcome newcomers and help them get started
- Provide constructive feedback on PRs
- Acknowledge good work and contributions

### Be Collaborative

- Share your discoveries with the community
- Help others troubleshoot issues
- Review pull requests when possible
- Participate in discussions

### Be Safe

- **Never** encourage dangerous flying
- Emphasize safety in all contributions
- Test in safe, open areas
- Follow local drone regulations

### Reporting Issues

When reporting bugs or issues:

1. **Search existing issues** first
2. **Use issue templates** (bug report, feature request)
3. **Provide details**:
   - Python/Node version
   - Operating system
   - Drone model
   - Steps to reproduce
   - Expected vs. actual behavior
   - Error messages and logs
4. **Be responsive** to questions from maintainers

---

## Reverse Engineering Contributions

### Protocol Discoveries

If you discover new UDP commands or behaviors:

1. **Document your findings** in [docs/technical/reverse-engineering.md](../technical/reverse-engineering.md)
2. **Include**:
   - Command bytes (in hex and decimal)
   - Purpose/behavior observed
   - Test conditions
   - Packet captures (if available)
   - Screenshots or videos

3. **Format**:
   ```markdown
   ### New Command: Set LED Color

   **Discovery Date**: 2024-02-16
   **Discovered By**: @username

   **Command**:
   [0x0A, red, green, blue]

   **Behavior**:
   Changes drone LED to specified RGB color.

   **Testing**:
   Tested on HD-720P-XXX. Red=255, Green=0, Blue=0 turns LED red.
   ```

### Packet Captures

When sharing packet captures:

1. Use the packet sniffer tool:
   ```bash
   python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 60
   ```

2. Save to `sniffs/` directory (gitignored)
3. Document what actions were performed during capture
4. Share interesting findings in issues/PRs

---

## Pull Request Process

### PR Checklist

Before submitting, ensure:

- [ ] Code follows style guidelines (ruff/black/ESLint)
- [ ] Tests pass (`pytest`, `npm run build`)
- [ ] Documentation updated (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] Branch is up to date with main
- [ ] No merge conflicts
- [ ] Changes are focused (one feature/fix)

### Review Process

1. **Maintainer review**: A project maintainer will review your PR
2. **Feedback**: Address any requested changes
3. **Approval**: Once approved, PR will be merged
4. **Recognition**: You'll be credited in release notes!

### After Merge

- Delete your feature branch (locally and on fork)
- Pull latest main: `git pull upstream main`
- Start your next contribution!

---

## Questions or Need Help?

- **Documentation**: Check [docs/](../INDEX.md) first
- **Issues**: Search or create GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Email**: Contact maintainers (if available)

---

## Recognition

All contributors will be:
- Listed in release notes
- Credited in documentation they create
- Thanked in commit messages
- Celebrated for protocol discoveries

**Thank you for contributing to TEKY!** 🚁✨

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see main README.md).

---

*For development environment setup details, see [DEVELOPMENT.md](DEVELOPMENT.md).*
