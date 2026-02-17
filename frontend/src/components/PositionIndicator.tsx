/**
 * Position Indicator Component
 *
 * Display widget showing current position, velocity, and tracking status.
 */

import React from 'react';
import { usePositionStore } from '../stores/positionStore';

export const PositionIndicator: React.FC = () => {
  const { position, velocity, altitude, enabled, feature_count, trajectory } = usePositionStore();

  // Calculate speed (magnitude of velocity)
  const speed = Math.sqrt(velocity.vx ** 2 + velocity.vy ** 2);

  // Calculate heading (direction of movement)
  const heading = Math.atan2(velocity.vy, velocity.vx) * (180 / Math.PI);

  return (
    <div className="bg-card border border-border rounded-lg shadow-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-heading">Position Data</h3>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${
          enabled ? 'bg-green-900 text-green-300' : 'bg-panel text-muted'
        }`}>
          {enabled ? '🟢 Tracking' : '⚪ Inactive'}
        </div>
      </div>

      <div className="space-y-3">
        {/* Position */}
        <div>
          <div className="text-sm font-medium text-muted mb-1">Position</div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-panel px-3 py-2 rounded">
              <div className="text-xs text-dim">X (Forward)</div>
              <div className="text-lg font-mono font-semibold text-heading">
                {position.x.toFixed(2)} m
              </div>
            </div>
            <div className="bg-panel px-3 py-2 rounded">
              <div className="text-xs text-dim">Y (Right)</div>
              <div className="text-lg font-mono font-semibold text-heading">
                {position.y.toFixed(2)} m
              </div>
            </div>
          </div>
        </div>

        {/* Velocity */}
        <div>
          <div className="text-sm font-medium text-muted mb-1">Velocity</div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-panel px-3 py-2 rounded">
              <div className="text-xs text-dim">VX</div>
              <div className="text-lg font-mono font-semibold text-heading">
                {velocity.vx.toFixed(2)} m/s
              </div>
            </div>
            <div className="bg-panel px-3 py-2 rounded">
              <div className="text-xs text-dim">VY</div>
              <div className="text-lg font-mono font-semibold text-heading">
                {velocity.vy.toFixed(2)} m/s
              </div>
            </div>
          </div>
        </div>

        {/* Speed and Heading */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-blue-900/40 px-3 py-2 rounded border border-blue-800">
            <div className="text-xs text-blue-400 font-medium">Speed</div>
            <div className="text-lg font-mono font-semibold text-blue-300">
              {speed.toFixed(2)} m/s
            </div>
          </div>
          <div className="bg-purple-900/40 px-3 py-2 rounded border border-purple-800">
            <div className="text-xs text-purple-400 font-medium">Heading</div>
            <div className="text-lg font-mono font-semibold text-purple-300">
              {heading.toFixed(1)}°
            </div>
          </div>
        </div>

        {/* Altitude */}
        <div className="bg-panel px-3 py-2 rounded">
          <div className="text-xs text-dim">Altitude</div>
          <div className="text-lg font-mono font-semibold text-heading">
            {altitude.toFixed(2)} m
          </div>
        </div>

        {/* Tracking Stats */}
        {enabled && (
          <div className="pt-2 border-t border-divider">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-dim">Features:</span>
                <span className="ml-1 font-mono font-semibold text-subheading">
                  {feature_count}
                </span>
              </div>
              <div>
                <span className="text-dim">Trail Points:</span>
                <span className="ml-1 font-mono font-semibold text-subheading">
                  {trajectory.length}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
