/**
 * Position Store (Zustand)
 *
 * Global state management for position tracking data.
 * Updates via WebSocket telemetry and provides reactive state for components.
 */

import { create } from 'zustand';
import type { PositionStore, PositionState, TrajectoryPoint } from '../types/position';

/**
 * Position store hook
 *
 * Usage:
 *   const { position, velocity, updatePosition } = usePositionStore();
 */
export const usePositionStore = create<PositionStore>((set, get) => ({
  // Initial state
  position: { x: 0, y: 0 },
  velocity: { vx: 0, vy: 0 },
  altitude: 1.0,
  enabled: false,
  feature_count: 0,
  timestamp: Date.now() / 1000,
  trajectory: [],

  // Update position from telemetry or API
  updatePosition: (state: PositionState) => {
    set({
      position: state.position,
      velocity: state.velocity,
      altitude: state.altitude,
      enabled: state.enabled,
      feature_count: state.feature_count,
      timestamp: state.timestamp,
    });

    // Automatically add to trajectory if tracking is enabled
    if (state.enabled) {
      get().addTrajectoryPoint({
        x: state.position.x,
        y: state.position.y,
        timestamp: state.timestamp,
      });
    }
  },

  // Add single trajectory point
  addTrajectoryPoint: (point: TrajectoryPoint) => {
    set((state) => {
      // Limit trajectory to 1000 points
      const maxPoints = 1000;
      const newTrajectory = [...state.trajectory, point];

      if (newTrajectory.length > maxPoints) {
        newTrajectory.shift(); // Remove oldest point
      }

      return { trajectory: newTrajectory };
    });
  },

  // Set full trajectory (from API fetch)
  setTrajectory: (points: TrajectoryPoint[]) => {
    set({ trajectory: points });
  },

  // Clear trajectory history
  clearTrajectory: () => {
    set({ trajectory: [] });
  },

  // Reset to initial state
  reset: () => {
    set({
      position: { x: 0, y: 0 },
      velocity: { vx: 0, vy: 0 },
      altitude: 1.0,
      enabled: false,
      feature_count: 0,
      timestamp: Date.now() / 1000,
      trajectory: [],
    });
  },
}));
