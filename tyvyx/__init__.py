"""TYVYX package wrappers for backward-compatible imports.

This package re-exports the top-level modules so consumers can import
using `import tyvyx.drone_controller` without moving legacy files.
"""

from .drone_controller import TYVYXDroneController
from .drone_controller_advanced import TYVYXDroneControllerAdvanced, FlightController
from .drone_controller_yolo import TYVYXDroneYOLO, DroneVideoProcessor

__all__ = [
    "TYVYXDroneController",
    "TYVYXDroneControllerAdvanced",
    "FlightController",
    "TYVYXDroneYOLO",
    "DroneVideoProcessor",
]
"""TYVYX package - compatibility wrappers for the repository.

This package provides clean import paths (e.g. `import tyvyx.drone_controller`)
while leaving the original top-level modules in place for backwards
compatibility with scripts and tests that import them directly.
"""

from importlib import metadata

try:
    __version__ = metadata.version("TYVYX")
except Exception:
    __version__ = "0.0.0"

__all__ = [
    "drone_controller",
    "drone_controller_advanced",
    "drone_controller_yolo",
    "network_diagnostics",
    "video_stream",
    "app",
]
