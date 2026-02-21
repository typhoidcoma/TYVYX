/**
 * WiFi Scanner - Compact Status
 *
 * Shows whether the host is currently connected to a drone WiFi hotspot.
 * Scan-only; the user connects via Windows WiFi settings.
 */

import React, { useState } from 'react';
import { networkApi, type ScanResult } from '../services/api';

interface Props {
  onDroneDetected?: (ip: string) => void;
}

export const WifiScanner: React.FC<Props> = ({ onDroneDetected }) => {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState('');

  const handleScan = async () => {
    setScanning(true);
    setError('');
    try {
      const r = await networkApi.scan();
      setResult(r);
      if (r.connected_to_drone && r.drone_ip && onDroneDetected) {
        onDroneDetected(r.drone_ip);
      }
    } catch {
      setError('Scan failed');
    } finally {
      setScanning(false);
    }
  };

  let pill = 'border-border bg-panel text-dim';
  let dot = '○';
  let label = 'Not scanned';

  if (error) {
    pill = 'border-red-700 bg-red-900/20 text-red-300';
    dot = '✕';
    label = error;
  } else if (result) {
    if (result.connected_to_drone) {
      pill = 'border-green-700 bg-green-900/20 text-green-300';
      dot = '●';
      label = result.drone_ip
        ? `${result.current_ssid} → ${result.drone_ip}`
        : `${result.current_ssid}`;
    } else if (result.current_ssid) {
      pill = 'border-orange-700 bg-orange-900/15 text-orange-300';
      dot = '◐';
      label = `${result.current_ssid} — not drone`;
    } else {
      pill = 'border-border bg-panel text-dim';
      dot = '○';
      label = 'No WiFi detected';
    }
  }

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 flex items-center gap-2 px-3 py-2 rounded border text-sm font-mono ${pill}`}>
        <span className="shrink-0">{dot}</span>
        <span className="truncate">{scanning ? 'Scanning…' : label}</span>
      </div>
      <button
        onClick={handleScan}
        disabled={scanning}
        className={`px-3 py-2 rounded text-sm font-medium shrink-0 transition-colors ${
          scanning
            ? 'bg-panel text-dim cursor-not-allowed'
            : 'bg-blue-600 text-white hover:bg-blue-500'
        }`}
      >
        {scanning ? '…' : 'Scan'}
      </button>
    </div>
  );
};
