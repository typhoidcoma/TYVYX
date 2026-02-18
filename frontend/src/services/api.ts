/**
 * API Client for TYVYX Drone Backend
 */

import axios from 'axios';
import type { PositionState } from '../types/position';

export const API_PORT = import.meta.env.VITE_API_PORT || '8000';
export const API_BASE_URL = `http://localhost:${API_PORT}`;
export const WS_BASE_URL = `ws://localhost:${API_PORT}`;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

export interface DroneStatus {
  connected: boolean;
  video_streaming: boolean;
  is_running?: boolean;
  device_type?: number;
  timestamp: number;
  bind_ip?: string | null;
  drone_protocol?: string | null;
  position?: PositionState;  // Phase 3: Present when position tracking is enabled
}

export interface CommandRequest {
  action: string;
  params?: Record<string, any>;
}

export interface CommandResponse {
  success: boolean;
  message: string;
}

// Drone Control APIs
export const droneApi = {
  connect: async (droneIp?: string) => {
    const response = await api.post('/api/drone/connect', {
      drone_ip: droneIp || '',  // empty = auto-detect from WiFi adapter
    });
    return response.data;
  },

  disconnect: async () => {
    const response = await api.post('/api/drone/disconnect');
    return response.data;
  },

  getStatus: async (): Promise<DroneStatus> => {
    const response = await api.get<DroneStatus>('/api/drone/status');
    return response.data;
  },

  sendCommand: async (command: CommandRequest): Promise<CommandResponse> => {
    const response = await api.post<CommandResponse>('/api/drone/command', command);
    return response.data;
  },

  startVideo: async () => {
    return droneApi.sendCommand({ action: 'start_video' });
  },

  stopVideo: async () => {
    return droneApi.sendCommand({ action: 'stop_video' });
  },

  switchCamera: async (camera: number) => {
    return droneApi.sendCommand({ action: 'switch_camera', params: { camera } });
  },

  switchScreen: async (mode: number) => {
    return droneApi.sendCommand({ action: 'switch_screen', params: { mode } });
  },
};

// Network / WiFi Scanner APIs
export interface WifiNetwork {
  ssid: string;
  signal: number;       // 0–100
  security: string;
  bssid: string;
  is_drone: boolean;
}

export interface ScanResult {
  networks: WifiNetwork[];
  current_ssid: string | null;
  connected_to_drone: boolean;
  drone_adapter_ip: string | null;
  drone_adapter_name: string | null;
  drone_ip: string | null;
}

export const networkApi = {
  scan: async (): Promise<ScanResult> => {
    const response = await api.get<ScanResult>('/api/network/scan');
    return response.data;
  },
};

// Video APIs
export const videoApi = {
  getFeedUrl: () => `${API_BASE_URL}/api/video/feed`,

  getStatus: async () => {
    const response = await api.get('/api/video/status');
    return response.data;
  },

  getCapabilities: async (): Promise<{ websocket: boolean; mjpeg: boolean; streaming: boolean }> => {
    const response = await api.get('/api/video/capabilities');
    return response.data;
  },
};

// WebSocket connection for telemetry
export const createWebSocket = (onMessage: (data: any) => void): WebSocket => {
  const ws = new WebSocket(`${WS_BASE_URL}/ws/telemetry`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  ws.onclose = () => {
    console.log('WebSocket closed');
  };

  return ws;
};

export default api;
