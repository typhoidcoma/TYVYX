/**
 * Position Types for Phase 3 Optical Flow Position Estimation
 *
 * TypeScript interfaces for position tracking data from backend.
 */

/**
 * 2D position coordinates
 */
export interface Position {
  x: number;  // Position in meters (forward/backward from origin)
  y: number;  // Position in meters (left/right from origin)
}

/**
 * 2D velocity
 */
export interface Velocity {
  vx: number;  // Velocity in m/s (X direction)
  vy: number;  // Velocity in m/s (Y direction)
}

/**
 * Position uncertainty (standard deviation)
 */
export interface Uncertainty {
  sigma_x: number;  // X position uncertainty (meters)
  sigma_y: number;  // Y position uncertainty (meters)
}

/**
 * Last velocity measurement from optical flow
 */
export interface Measurement {
  vx: number;  // Measured velocity X (m/s)
  vy: number;  // Measured velocity Y (m/s)
}

/**
 * Complete position state from backend
 */
export interface PositionState {
  position: Position;
  velocity: Velocity;
  altitude: number;          // Current altitude in meters
  enabled: boolean;          // Whether tracking is active
  feature_count: number;     // Number of tracked features
  timestamp: number;         // Unix timestamp of last update
}

/**
 * Single trajectory point
 */
export interface TrajectoryPoint {
  x: number;       // Position X in meters
  y: number;       // Position Y in meters
  timestamp: number;  // Unix timestamp
}

/**
 * Trajectory history response
 */
export interface TrajectoryData {
  points: TrajectoryPoint[];
  count: number;
}

/**
 * Detailed position statistics
 */
export interface PositionStatistics {
  enabled: boolean;
  position: Position;
  velocity: Velocity;
  altitude: number;
  frame_count: number;
  trajectory_points: number;
  timestamp: number;
  feature_count?: number;
  uncertainty?: Uncertainty;
  last_measurement?: Measurement;
}

/**
 * API response status
 */
export interface StatusResponse {
  success: boolean;
  message: string;
}

/**
 * Request to set altitude
 */
export interface AltitudeRequest {
  altitude: number;  // Height in meters (0.1-100)
}

/**
 * Request to reset position
 */
export interface ResetRequest {
  x?: number;  // Initial X position (default 0)
  y?: number;  // Initial Y position (default 0)
}

/**
 * Position store state (Zustand)
 */
export interface PositionStore {
  // State
  position: Position;
  velocity: Velocity;
  altitude: number;
  enabled: boolean;
  feature_count: number;
  timestamp: number;
  trajectory: TrajectoryPoint[];

  // Actions
  updatePosition: (state: PositionState) => void;
  addTrajectoryPoint: (point: TrajectoryPoint) => void;
  setTrajectory: (points: TrajectoryPoint[]) => void;
  clearTrajectory: () => void;
  reset: () => void;
}

/**
 * Map visualization settings
 */
export interface MapSettings {
  width: number;      // Canvas width in pixels
  height: number;     // Canvas height in pixels
  scale: number;      // Pixels per meter
  gridSize: number;   // Grid spacing in meters
  showGrid: boolean;  // Show grid
  showTrajectory: boolean;  // Show trajectory trail
  maxTrajectoryPoints: number;  // Max points to render
}

/**
 * Map render state
 */
export interface MapRenderState {
  offsetX: number;    // Pan offset X
  offsetY: number;    // Pan offset Y
  scale: number;      // Zoom scale
  rotation: number;   // Map rotation in radians
}
