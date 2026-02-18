/**
 * Position API Client
 *
 * Axios-based client for position tracking REST endpoints.
 */

import axios from 'axios';
import type {
  PositionState,
  TrajectoryData,
  PositionStatistics,
  StatusResponse,
  AltitudeRequest,
  ResetRequest,
} from '../types/position';

import { API_BASE_URL } from './api';

/**
 * Position API client
 */
class PositionApiClient {
  private baseURL: string;

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = `${baseURL}/api/position`;
  }

  /**
   * Get current position state
   */
  async getCurrentPosition(): Promise<PositionState> {
    const response = await axios.get<PositionState>(`${this.baseURL}/current`);
    return response.data;
  }

  /**
   * Get trajectory history
   *
   * @param maxPoints - Optional limit on number of points (most recent)
   */
  async getTrajectory(maxPoints?: number): Promise<TrajectoryData> {
    const params = maxPoints ? { max_points: maxPoints } : {};
    const response = await axios.get<TrajectoryData>(`${this.baseURL}/trajectory`, {
      params,
    });
    return response.data;
  }

  /**
   * Get detailed statistics
   */
  async getStatistics(): Promise<PositionStatistics> {
    const response = await axios.get<PositionStatistics>(`${this.baseURL}/statistics`);
    return response.data;
  }

  /**
   * Start position tracking
   */
  async startTracking(): Promise<StatusResponse> {
    const response = await axios.post<StatusResponse>(`${this.baseURL}/start`);
    return response.data;
  }

  /**
   * Stop position tracking
   */
  async stopTracking(): Promise<StatusResponse> {
    const response = await axios.post<StatusResponse>(`${this.baseURL}/stop`);
    return response.data;
  }

  /**
   * Reset position to origin or specified coordinates
   *
   * @param x - Initial X position (default 0)
   * @param y - Initial Y position (default 0)
   */
  async resetPosition(x: number = 0, y: number = 0): Promise<StatusResponse> {
    const request: ResetRequest = { x, y };
    const response = await axios.post<StatusResponse>(`${this.baseURL}/reset`, request);
    return response.data;
  }

  /**
   * Set altitude for velocity scaling
   *
   * @param altitude - Altitude in meters (0.1-100)
   */
  async setAltitude(altitude: number): Promise<StatusResponse> {
    const request: AltitudeRequest = { altitude };
    const response = await axios.post<StatusResponse>(`${this.baseURL}/altitude`, request);
    return response.data;
  }

  /**
   * Clear trajectory history
   */
  async clearTrajectory(): Promise<StatusResponse> {
    const response = await axios.post<StatusResponse>(`${this.baseURL}/clear_trajectory`);
    return response.data;
  }
}

// Export singleton instance
export const positionApi = new PositionApiClient();

// Export class for custom instances if needed
export default PositionApiClient;
