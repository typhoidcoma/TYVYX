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
    <div className="bg-card border border-panel rounded-lg shadow-lg p-4">
      <h3 className="text-lg font-semibold text-heading mb-4">Position Tracking Controls</h3>

      {/* Message Display */}
      {message && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-sm font-medium ${
          messageType === 'success'
            ? 'bg-green-900/50 text-green-300 border border-green-700'
            : 'bg-red-900/50 text-red-300 border border-red-700'
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
              ? 'bg-panel text-dim cursor-not-allowed'
              : 'bg-green-600 text-heading hover:bg-green-500'
          }`}
        >
          {loading ? '...' : '▶️ Start Tracking'}
        </button>

        <button
          onClick={handleStop}
          disabled={!enabled || loading}
          className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
            !enabled || loading
              ? 'bg-panel text-dim cursor-not-allowed'
              : 'bg-red-600 text-heading hover:bg-red-500'
          }`}
        >
          {loading ? '...' : '⏹️ Stop Tracking'}
        </button>
      </div>

      {/* Altitude Control */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-muted mb-2">
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
            className="flex-1 px-3 py-2 bg-panel border border-panel text-heading rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-dim"
            placeholder="1.0"
          />
          <button
            onClick={handleSetAltitude}
            disabled={loading}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              loading
                ? 'bg-panel text-dim cursor-not-allowed'
                : 'bg-blue-600 text-heading hover:bg-blue-500'
            }`}
          >
            Set
          </button>
        </div>
        <div className="mt-1 text-xs text-dim">
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
              ? 'bg-panel text-dim cursor-not-allowed'
              : 'bg-orange-600 text-heading hover:bg-orange-500'
          }`}
        >
          🔄 Reset Position
        </button>

        <button
          onClick={handleClearTrajectory}
          disabled={loading}
          className={`w-full px-4 py-2 rounded-lg font-medium transition-colors ${
            loading
              ? 'bg-panel text-dim cursor-not-allowed'
              : 'bg-dim text-heading hover:bg-muted'
          }`}
        >
          🗑️ Clear Trajectory
        </button>
      </div>

      {/* Help Text */}
      <div className="mt-4 pt-4 border-t border-panel">
        <p className="text-xs text-dim">
          <strong className="text-muted">Note:</strong> Start tracking after video is running. Altitude affects
          velocity scaling - set to actual height above ground for accurate position estimates.
        </p>
      </div>
    </div>
  );
};
