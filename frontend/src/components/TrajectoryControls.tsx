/**
 * Trajectory Controls Component
 *
 * Control panel for position tracking operations.
 */

import React, { useState } from 'react';
import { usePositionStore } from '../stores/positionStore';
import { positionApi } from '../services/positionApi';

export const TrajectoryControls: React.FC = () => {
  const { enabled, altitude, clearTrajectory } = usePositionStore();

  const [altitudeInput, setAltitudeInput] = useState<string>(altitude.toFixed(1));
  const [loading, setLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<string>('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');

  /**
   * Show temporary message
   */
  const showMessage = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage(text);
    setMessageType(type);
    setTimeout(() => setMessage(''), 3000);
  };

  /**
   * Start position tracking
   */
  const handleStart = async () => {
    setLoading(true);
    try {
      const response = await positionApi.startTracking();
      showMessage(response.message, 'success');
    } catch (error) {
      console.error('Failed to start tracking:', error);
      showMessage('Failed to start tracking', 'error');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Stop position tracking
   */
  const handleStop = async () => {
    setLoading(true);
    try {
      const response = await positionApi.stopTracking();
      showMessage(response.message, 'success');
    } catch (error) {
      console.error('Failed to stop tracking:', error);
      showMessage('Failed to stop tracking', 'error');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Reset position to origin
   */
  const handleReset = async () => {
    if (!confirm('Reset position to origin (0, 0)?')) return;

    setLoading(true);
    try {
      const response = await positionApi.resetPosition(0, 0);
      showMessage(response.message, 'success');
    } catch (error) {
      console.error('Failed to reset position:', error);
      showMessage('Failed to reset position', 'error');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Set altitude
   */
  const handleSetAltitude = async () => {
    const altValue = parseFloat(altitudeInput);

    if (isNaN(altValue) || altValue < 0.1 || altValue > 100) {
      showMessage('Altitude must be between 0.1 and 100 meters', 'error');
      return;
    }

    setLoading(true);
    try {
      const response = await positionApi.setAltitude(altValue);
      showMessage(response.message, 'success');
    } catch (error) {
      console.error('Failed to set altitude:', error);
      showMessage('Failed to set altitude', 'error');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Clear trajectory history
   */
  const handleClearTrajectory = async () => {
    setLoading(true);
    try {
      const response = await positionApi.clearTrajectory();
      clearTrajectory();  // Also clear in Zustand store
      showMessage(response.message, 'success');
    } catch (error) {
      console.error('Failed to clear trajectory:', error);
      showMessage('Failed to clear trajectory', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border-2 border-gray-300 rounded-lg shadow-lg p-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">Position Tracking Controls</h3>

      {/* Message Display */}
      {message && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-sm font-medium ${
          messageType === 'success'
            ? 'bg-green-50 text-green-800 border border-green-200'
            : 'bg-red-50 text-red-800 border border-red-200'
        }`}>
          {message}
        </div>
      )}

      {/* Start/Stop Buttons */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={handleStart}
          disabled={enabled || loading}
          className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
            enabled || loading
              ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
              : 'bg-green-500 text-white hover:bg-green-600'
          }`}
        >
          {loading ? '...' : '▶️ Start Tracking'}
        </button>

        <button
          onClick={handleStop}
          disabled={!enabled || loading}
          className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
            !enabled || loading
              ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
              : 'bg-red-500 text-white hover:bg-red-600'
          }`}
        >
          {loading ? '...' : '⏹️ Stop Tracking'}
        </button>
      </div>

      {/* Altitude Control */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Altitude (meters)
        </label>
        <div className="flex gap-2">
          <input
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            value={altitudeInput}
            onChange={(e) => setAltitudeInput(e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="1.0"
          />
          <button
            onClick={handleSetAltitude}
            disabled={loading}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              loading
                ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                : 'bg-blue-500 text-white hover:bg-blue-600'
            }`}
          >
            Set
          </button>
        </div>
        <div className="mt-1 text-xs text-gray-500">
          Current: {altitude.toFixed(2)} m
        </div>
      </div>

      {/* Action Buttons */}
      <div className="space-y-2">
        <button
          onClick={handleReset}
          disabled={loading}
          className={`w-full px-4 py-2 rounded-lg font-medium transition-colors ${
            loading
              ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
              : 'bg-orange-500 text-white hover:bg-orange-600'
          }`}
        >
          🔄 Reset Position
        </button>

        <button
          onClick={handleClearTrajectory}
          disabled={loading}
          className={`w-full px-4 py-2 rounded-lg font-medium transition-colors ${
            loading
              ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
              : 'bg-gray-500 text-white hover:bg-gray-600'
          }`}
        >
          🗑️ Clear Trajectory
        </button>
      </div>

      {/* Help Text */}
      <div className="mt-4 pt-4 border-t border-gray-200">
        <p className="text-xs text-gray-600">
          <strong>Note:</strong> Start tracking after video is running. Altitude affects
          velocity scaling - set to actual height above ground for accurate position estimates.
        </p>
      </div>
    </div>
  );
};
