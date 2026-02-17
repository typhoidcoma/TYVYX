# Development Environment Setup

This guide covers setting up your development environment for contributing to the TYVYX drone controller project.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Python Backend Setup](#python-backend-setup)
- [Frontend Setup](#frontend-setup)
- [Running the Application](#running-the-application)
- [Development Tools](#development-tools)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Minimum Version | Purpose | Download |
|----------|----------------|---------|----------|
| **Python** | 3.8+ | Backend language | https://www.python.org/downloads/ |
| **Node.js** | 16+ | Frontend build tool | https://nodejs.org/ |
| **FFmpeg** | 4.0+ | Video processing | https://ffmpeg.org/download.html |
| **Git** | 2.0+ | Version control | https://git-scm.com/ |

### Hardware Requirements

- **Computer**: WiFi-capable laptop or desktop
- **Drone**: TYVYX WiFi drone (HD-720P-*, HD-FPV-*, HD720-*, or FHD-* models)
- **Minimum RAM**: 4GB (8GB recommended for frontend development)
- **Storage**: 2GB free space (mostly for node_modules)

---

## Python Backend Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/TYVYX.git
cd TYVYX
```

### 2. Create Virtual Environment

**Windows**:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS**:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` in your terminal prompt.

### 3. Install Python Dependencies

```bash
# Core dependencies
pip install -r requirements.txt

# Development dependencies (linters, test tools)
pip install -r requirements-dev.txt
```

### 4. Verify Installation

```bash
# Check Python version
python --version  # Should be 3.8+

# Check key packages
python -c "import cv2; print(f'OpenCV: {cv2.__version__}')"
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import flask; print(f'Flask: {flask.__version__}')"

# Check FFmpeg
ffmpeg -version
```

### 5. Configure IDE (Optional)

#### VS Code

Create `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

#### PyCharm

1. Open project in PyCharm
2. File → Settings → Project → Python Interpreter
3. Add interpreter → Existing environment
4. Select `.venv/Scripts/python.exe`

---

## Frontend Setup

### 1. Navigate to Frontend Directory

```bash
cd frontend
```

### 2. Install Node Dependencies

```bash
npm install
```

This will install:
- React and React DOM
- TypeScript
- Vite (build tool)
- Tailwind CSS
- ESLint and Prettier

### 3. Verify Installation

```bash
# Check Node version
node --version  # Should be 16+

# Check npm version
npm --version

# Verify dependencies
npm list --depth=0
```

### 4. Configure IDE (Optional)

#### VS Code

Install extensions:
- **ESLint** - Microsoft
- **Prettier** - Prettier
- **Tailwind CSS IntelliSense** - Tailwind Labs

Create/update `.vscode/settings.json` in frontend:
```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  }
}
```

---

## Running the Application

### Option 1: Development Mode (Recommended)

Run backend and frontend separately in two terminals:

#### Terminal 1: Backend

```bash
# From project root
cd i:/Projects/Drones/TYVYX
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

python -m autonomous.api.main
```

Backend runs at: **http://localhost:8000**
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

#### Terminal 2: Frontend

```bash
# From project root
cd frontend

npm run dev
```

Frontend runs at: **http://localhost:5173**

### Option 2: Legacy Flask App

```bash
cd i:/Projects/Drones/TYVYX
source .venv/bin/activate

python -m tyvyx.app
```

Flask runs at: **http://localhost:5000**

### Option 3: Basic Controller (No Web UI)

```bash
python -m tyvyx.drone_controller
```

Displays video window with keyboard controls.

---

## Development Tools

### Python Tools

#### Ruff (Linter)

Fast Python linter:

```bash
# Check all files
ruff check .

# Auto-fix issues
ruff check --fix .

# Check specific file
ruff check tyvyx/drone_controller.py
```

Configuration in `pyproject.toml` or `ruff.toml`.

#### Black (Formatter)

Code formatter:

```bash
# Format all files
black .

# Check formatting without changes
black --check .

# Format specific file
black tyvyx/drone_controller.py
```

#### MyPy (Type Checker)

Optional type checking:

```bash
mypy tyvyx/
```

### Frontend Tools

#### ESLint (Linter)

```bash
cd frontend

# Check for issues
npm run lint

# Auto-fix issues
npm run lint -- --fix
```

#### Prettier (Formatter)

Usually integrated with ESLint, but can run standalone:

```bash
npx prettier --write src/
```

#### Type Checking

```bash
npm run type-check  # If configured in package.json
```

---

## Testing

### Python Unit Tests

We use **pytest** for testing:

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_drone_controller.py

# Run tests matching pattern
pytest -k "test_heartbeat"

# Run with coverage report
pytest --cov=tyvyx --cov=autonomous

# Generate HTML coverage report
pytest --cov=tyvyx --cov-report=html
# Open htmlcov/index.html in browser
```

### Integration Tests

Some tests require a physical drone:

```bash
# Run only unit tests (no hardware)
pytest -m "not integration"

# Run only integration tests (requires drone)
pytest -m integration
```

### Frontend Tests

```bash
cd frontend

# Run tests (if configured)
npm test
```

---

## Code Quality

### Pre-commit Checks

Before committing, run:

```bash
# Python checks
ruff check .
black .
pytest

# Frontend checks
cd frontend
npm run lint
npm run build  # Verify builds successfully
```

### Recommended Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

# Run Python linter
echo "Running ruff..."
ruff check .
if [ $? -ne 0 ]; then
    echo "Ruff check failed. Please fix errors."
    exit 1
fi

# Run Python formatter check
echo "Checking black formatting..."
black --check .
if [ $? -ne 0 ]; then
    echo "Code not formatted with black. Run: black ."
    exit 1
fi

# Run Python tests
echo "Running pytest..."
pytest
if [ $? -ne 0 ]; then
    echo "Tests failed. Please fix."
    exit 1
fi

echo "All checks passed!"
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Troubleshooting

### Python Issues

#### Virtual Environment Not Activating

**Windows PowerShell Execution Policy**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Verify activation**:
```bash
which python  # Linux/macOS
where python  # Windows
```

Should point to `.venv/Scripts/python` or `.venv/bin/python`.

#### Import Errors

```bash
# Ensure virtual environment is activated
# Then reinstall dependencies
pip install -r requirements.txt
```

#### FFmpeg Not Found

**Windows**:
1. Download FFmpeg from https://ffmpeg.org/download.html
2. Extract and add `bin/` folder to PATH
3. Restart terminal and verify: `ffmpeg -version`

**Linux (Ubuntu/Debian)**:
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**macOS**:
```bash
brew install ffmpeg
```

### Frontend Issues

#### npm install Fails

```bash
# Clear cache
npm cache clean --force

# Delete node_modules and package-lock.json
rm -rf node_modules package-lock.json

# Reinstall
npm install
```

#### Port 5173 Already in Use

```bash
# Find process using port
lsof -i :5173  # Linux/macOS
netstat -ano | findstr :5173  # Windows

# Kill process or use different port
npm run dev -- --port 5174
```

#### Build Fails

```bash
# Check for TypeScript errors
npm run type-check

# Try clean build
rm -rf dist/
npm run build
```

### Drone Connection Issues

#### Can't Connect to Drone

1. Verify WiFi connection: `ping 192.168.1.1`
2. Check firewall isn't blocking Python
3. Run network diagnostics:
   ```bash
   python -m tyvyx.network_diagnostics
   ```

#### Video Stream Not Working

1. Verify FFmpeg: `ffmpeg -version`
2. Test RTSP manually:
   ```bash
   ffplay rtsp://192.168.1.1:7070/webcam
   ```
3. Check drone is powered on and video is streaming

---

## Development Workflow

### Typical Development Session

1. **Activate environment**:
   ```bash
   source .venv/bin/activate
   ```

2. **Update dependencies** (if changed):
   ```bash
   pip install -r requirements.txt
   cd frontend && npm install
   ```

3. **Create feature branch**:
   ```bash
   git checkout -b feature/my-new-feature
   ```

4. **Start development servers**:
   - Terminal 1: `python -m autonomous.api.main`
   - Terminal 2: `cd frontend && npm run dev`

5. **Make changes and test**:
   - Write code
   - Add tests
   - Run linters
   - Test with drone

6. **Commit changes**:
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   ```

7. **Push and create PR**:
   ```bash
   git push origin feature/my-new-feature
   ```

---

## Useful Commands Reference

### Python

| Command | Purpose |
|---------|---------|
| `python -m tyvyx.app` | Run Flask web interface |
| `python -m autonomous.api.main` | Run FastAPI backend |
| `python -m tyvyx.drone_controller` | Run basic controller |
| `python -m tyvyx.network_diagnostics` | Test drone connection |
| `pytest` | Run unit tests |
| `ruff check .` | Lint Python code |
| `black .` | Format Python code |

### Frontend

| Command | Purpose |
|---------|---------|
| `npm install` | Install dependencies |
| `npm run dev` | Start dev server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run lint` | Lint TypeScript/React |

### Git

| Command | Purpose |
|---------|---------|
| `git status` | Check file changes |
| `git checkout -b <branch>` | Create new branch |
| `git add <file>` | Stage file |
| `git commit -m "message"` | Commit changes |
| `git push origin <branch>` | Push to remote |

---

## Additional Resources

- **Getting Started Guide**: [docs/getting-started/README.md](../getting-started/README.md)
- **API Reference**: [docs/API_REFERENCE.md](../API_REFERENCE.md)
- **Contributing Guidelines**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Troubleshooting**: [docs/getting-started/TROUBLESHOOTING.md](../getting-started/TROUBLESHOOTING.md)

---

## IDE-Specific Tips

### VS Code

**Recommended Extensions**:
- Python (Microsoft)
- Pylance (Microsoft)
- Ruff (Astral)
- ESLint (Microsoft)
- Prettier (Prettier)
- Tailwind CSS IntelliSense (Tailwind Labs)
- GitLens (GitKraken)

**Keyboard Shortcuts**:
- `Ctrl+Shift+P` - Command palette
- `Ctrl+` - Toggle terminal
- `F5` - Start debugging
- `Ctrl+Shift+F` - Search in files

### PyCharm

**Run Configurations**:
1. Run → Edit Configurations
2. Add Python configuration
3. Script path: `autonomous/api/main.py`
4. Working directory: Project root

---

## Getting Help

If you encounter issues not covered here:

1. Check [Troubleshooting Guide](../getting-started/TROUBLESHOOTING.md)
2. Search existing GitHub issues
3. Ask in GitHub Discussions
4. Create a new issue with details

**Happy coding!** 🚁💻
