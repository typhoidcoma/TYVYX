# Development Environment Setup

## Prerequisites

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.8+ | Backend |
| Node.js | 18+ | Frontend |
| Git | 2.0+ | Version control |

Hardware: WiFi-capable computer, K417 drone (recommended).

## Python Backend

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify
python --version
python -c "import cv2; print(f'OpenCV: {cv2.__version__}')"
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
```

## Frontend

```bash
cd frontend
npm install

# Verify
node --version
npm list --depth=0
```

## Running

### Development (two terminals)

```bash
# Terminal 1: Backend
python -m autonomous.api.main
# http://localhost:8000, API docs at /docs

# Terminal 2: Frontend
cd frontend && npm run dev
# http://localhost:5173
```

### Direct controller (no web UI)

```bash
python -m tyvyx.drone_controller
```

## Testing

```bash
# Python
pytest                              # All tests
pytest -v                           # Verbose
pytest -k "test_heartbeat"         # Pattern match
pytest --cov=tyvyx --cov=autonomous # Coverage

# Frontend
cd frontend
npm run lint
npm run build
```

## Code Quality

```bash
# Python
ruff check .          # Lint
ruff check --fix .    # Auto-fix
black .               # Format

# Frontend
cd frontend
npm run lint
```

## Troubleshooting

**Virtual env not activating (Windows PowerShell)**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**npm install fails**:
```bash
rm -rf node_modules package-lock.json && npm install
```

**Port in use**:
```bash
# Check port 5173 or 8000
netstat -ano | findstr :5173
```
