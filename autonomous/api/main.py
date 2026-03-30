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

from autonomous.api.routes import drone, video, position, network, rc, autopilot, rssi, slam, debug
from autonomous.api.websocket import websocket_router
from autonomous.services.drone_service import drone_service
from autonomous.services.position_service import position_service
from autonomous.services.wifi_rssi_service import wifi_rssi_service
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

        # Load configuration and initialize services
        config_path = Path(__file__).parent.parent.parent / "config" / "drone_config.yaml"
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Position service (Phase 3 — optical flow + EKF)
            position_service.initialize(config)
            logger.info("Position service initialized (3D EKF)")

            # WiFi RSSI distance service
            wifi_rssi_service.initialize(config)
            logger.info("WiFi RSSI service initialized")

            # Wire cross-service callbacks:

            # RSSI distance → position EKF
            def _rssi_to_position():
                distance = wifi_rssi_service.get_distance()
                if distance > 0.1:
                    position_service.update_rssi_distance(distance)

            wifi_rssi_service.on_update(_rssi_to_position)

            logger.info("Sensor fusion callbacks wired")
        else:
            logger.warning(f"Config file not found: {config_path} - services not initialized")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")

    yield

    # Shutdown
    logger.info("Shutting down TYVYX Autonomous Drone System...")
    try:
        wifi_rssi_service.stop()
        await drone_service.shutdown()
        logger.info("All services shut down cleanly")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")



# Create FastAPI app
app = FastAPI(
    title="TYVYX Autonomous Drone API",
    description="Backend API for TYVYX autonomous drone control system (Phase 4: Visual Odometry + EKF + RSSI)",
    version="0.5.0",
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
app.include_router(rc.router, prefix="/api/rc", tags=["rc"])
app.include_router(autopilot.router, prefix="/api/autopilot", tags=["autopilot"])
app.include_router(rssi.router, prefix="/api/rssi", tags=["rssi"])
app.include_router(slam.router, prefix="/api/slam", tags=["slam"])
app.include_router(network.router)
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "TYVYX Autonomous Drone API",
        "version": "0.5.0",
        "status": "running",
        "docs": "/docs",
        "drone_connected": drone_service.is_connected(),
        "position_tracking": position_service.is_enabled(),
        "rssi_tracking": wifi_rssi_service.is_enabled()
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
        reload=False,
        log_level="warning",
        access_log=False,
    )
