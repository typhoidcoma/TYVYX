"""
FastAPI Backend for TYVYX Autonomous Drone System

Main application entry point for Phase 2+.
Wraps existing TYVYXDroneControllerAdvanced with modern async API.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from autonomous.api.routes import drone, video, position, network
from autonomous.api.websocket import websocket_router
from autonomous.services.drone_service import drone_service
from autonomous.services.position_service import position_service
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown of services.
    """
    # Startup
    logger.info("🚀 Starting TYVYX Autonomous Drone System...")

    try:
        # Initialize drone service (but don't connect yet)
        await drone_service.initialize()
        logger.info("✅ Drone service initialized")

        # Load configuration and initialize position service (Phase 3)
        config_path = Path(__file__).parent.parent.parent / "config" / "drone_config.yaml"
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            position_service.initialize(config)
            logger.info("✅ Position service initialized")
        else:
            logger.warning(f"⚠️ Config file not found: {config_path} - position service not initialized")

    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")

    yield

    # Shutdown
    logger.info("🛑 Shutting down TYVYX Autonomous Drone System...")
    try:
        await drone_service.shutdown()
        logger.info("✅ Drone service shut down cleanly")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


# Create FastAPI app
app = FastAPI(
    title="TYVYX Autonomous Drone API",
    description="Backend API for TYVYX autonomous drone control system (Phase 3: Position Tracking)",
    version="0.3.0",
    lifespan=lifespan
)

# CORS middleware (allow frontend to connect)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(drone.router, prefix="/api/drone", tags=["drone"])
app.include_router(video.router, prefix="/api/video", tags=["video"])
app.include_router(position.router, prefix="/api/position", tags=["position"])  # Phase 3
app.include_router(websocket_router, prefix="/ws", tags=["websocket"])
app.include_router(network.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "TYVYX Autonomous Drone API",
        "version": "0.3.0",
        "status": "running",
        "docs": "/docs",
        "drone_connected": drone_service.is_connected(),
        "position_tracking": position_service.is_enabled()  # Phase 3
    }


@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "drone_connected": drone_service.is_connected(),
        "video_streaming": drone_service.is_video_streaming()
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI server on http://0.0.0.0:8000")
    logger.info("API documentation: http://localhost:8000/docs")
    logger.info("Frontend should connect to: http://localhost:8000")

    uvicorn.run(
        "autonomous.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )
