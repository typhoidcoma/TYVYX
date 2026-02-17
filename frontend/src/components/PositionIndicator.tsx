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
    <div className="bg-white border-2 border-gray-300 rounded-lg shadow-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">Position Data</h3>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${
          enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
        }`}>
          {enabled ? '🟢 Tracking' : '⚪ Inactive'}
        </div>
      </div>

      <div className="space-y-3">
        {/* Position */}
        <div>
          <div className="text-sm font-medium text-gray-600 mb-1">Position</div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-50 px-3 py-2 rounded">
              <div className="text-xs text-gray-500">X (Forward)</div>
              <div className="text-lg font-mono font-semibold text-gray-800">
                {position.x.toFixed(2)} m
              </div>
            </div>
            <div className="bg-gray-50 px-3 py-2 rounded">
              <div className="text-xs text-gray-500">Y (Right)</div>
              <div className="text-lg font-mono font-semibold text-gray-800">
                {position.y.toFixed(2)} m
              </div>
            </div>
          </div>
        </div>

        {/* Velocity */}
        <div>
          <div className="text-sm font-medium text-gray-600 mb-1">Velocity</div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-50 px-3 py-2 rounded">
              <div className="text-xs text-gray-500">VX</div>
              <div className="text-lg font-mono font-semibold text-gray-800">
                {velocity.vx.toFixed(2)} m/s
              </div>
            </div>
            <div className="bg-gray-50 px-3 py-2 rounded">
              <div className="text-xs text-gray-500">VY</div>
              <div className="text-lg font-mono font-semibold text-gray-800">
                {velocity.vy.toFixed(2)} m/s
              </div>
            </div>
          </div>
        </div>

        {/* Speed and Heading */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-blue-50 px-3 py-2 rounded">
            <div className="text-xs text-blue-600 font-medium">Speed</div>
            <div className="text-lg font-mono font-semibold text-blue-800">
              {speed.toFixed(2)} m/s
            </div>
          </div>
          <div className="bg-purple-50 px-3 py-2 rounded">
            <div className="text-xs text-purple-600 font-medium">Heading</div>
            <div className="text-lg font-mono font-semibold text-purple-800">
              {heading.toFixed(1)}°
            </div>
          </div>
        </div>

        {/* Altitude */}
        <div className="bg-gray-50 px-3 py-2 rounded">
          <div className="text-xs text-gray-500">Altitude</div>
          <div className="text-lg font-mono font-semibold text-gray-800">
            {altitude.toFixed(2)} m
          </div>
        </div>

        {/* Tracking Stats */}
        {enabled && (
          <div className="pt-2 border-t border-gray-200">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-gray-600">Features:</span>
                <span className="ml-1 font-mono font-semibold text-gray-800">
                  {feature_count}
                </span>
              </div>
              <div>
                <span className="text-gray-600">Trail Points:</span>
                <span className="ml-1 font-mono font-semibold text-gray-800">
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
