#!/bin/bash
# Start Phase 2: Backend and Frontend

echo "🚀 Starting TYVYX Phase 2..."
echo ""
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""

# Check if in correct directory
if [ ! -f "autonomous/api/main.py" ]; then
    echo "❌ Error: Run this script from TYVYX project root"
    exit 1
fi

# Start backend in background
echo "📡 Starting FastAPI backend..."
python -m autonomous.api.main &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 3

# Start frontend
echo "🎨 Starting React frontend..."
cd frontend
npm run dev

# Cleanup on exit
trap "kill $BACKEND_PID" EXIT
