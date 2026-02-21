/**
 * API Client for TYVYX Drone Backend
 */

import axios from 'axios';

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
  flight_armed?: boolean;
  is_running?: boolean;
  device_type?: number;
  timestamp: number;
  bind_ip?: string | null;
  drone_protocol?: string | null;
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

  // Flight control
  arm: async () => droneApi.sendCommand({ action: 'arm' }),
  disarm: async () => droneApi.sendCommand({ action: 'disarm' }),
  takeoff: async () => droneApi.sendCommand({ action: 'takeoff' }),
  land: async () => droneApi.sendCommand({ action: 'land' }),
  calibrate: async () => droneApi.sendCommand({ action: 'calibrate' }),
  headless: async () => droneApi.sendCommand({ action: 'headless' }),
  setAxes: async (axes: { throttle?: number; yaw?: number; pitch?: number; roll?: number }) => {
    return droneApi.sendCommand({ action: 'axes', params: axes });
  },

  // Send raw hex bytes to drone (for experimentation)
  sendRaw: async (hex: string) => {
    return droneApi.sendCommand({ action: 'raw', params: { data: hex } });
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

export default api;
