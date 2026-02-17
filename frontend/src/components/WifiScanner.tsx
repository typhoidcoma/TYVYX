/**
 * WiFi Scanner Component
 *
 * Scans for nearby WiFi networks and highlights likely drone hotspots.
 * Helps the user identify and connect to the drone's WiFi before launching.
 */

import React, { useState } from 'react';
import { networkApi, type WifiNetwork } from '../services/api';

function SignalBar({ signal }: { signal: number }) {
  const bars = 4;
  const filled = Math.ceil((signal / 100) * bars);
  const color = signal >= 70 ? 'bg-green-400' : signal >= 40 ? 'bg-yellow-400' : 'bg-red-400';

  return (
    <div className="flex items-end gap-0.5 h-4">
      {Array.from({ length: bars }, (_, i) => (
        <div
          key={i}
          className={`w-1.5 rounded-sm ${i < filled ? color : 'bg-panel'}`}
          style={{ height: `${((i + 1) / bars) * 100}%` }}
        />
      ))}
    </div>
  );
}

function NetworkRow({ network, isCurrent }: { network: WifiNetwork; isCurrent: boolean }) {
  const borderColor = isCurrent
    ? 'border-green-600'
    : network.is_drone
    ? 'border-orange-600'
    : 'border-border';

  const bgColor = isCurrent
    ? 'bg-green-900/20'
    : network.is_drone
    ? 'bg-orange-900/15'
    : 'bg-panel';

  return (
    <div className={`flex items-center justify-between px-3 py-2 rounded border ${borderColor} ${bgColor}`}>
      <div className="flex items-center gap-2 min-w-0">
        <SignalBar signal={network.signal} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-heading truncate">{network.ssid}</span>
            {network.is_drone && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-orange-800 text-orange-200 shrink-0">
                drone
              </span>
            )}
            {isCurrent && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-green-800 text-green-200 shrink-0">
                connected
              </span>
            )}
          </div>
          <div className="text-xs text-dim">{network.security}</div>
        </div>
      </div>
      <div className="text-xs text-muted shrink-0 ml-2">{network.signal}%</div>
    </div>
  );
}

export const WifiScanner: React.FC = () => {
  const [scanning, setScanning] = useState(false);
  const [networks, setNetworks] = useState<WifiNetwork[]>([]);
  const [currentSsid, setCurrentSsid] = useState<string | null>(null);
  const [connectedToDrone, setConnectedToDrone] = useState(false);
  const [error, setError] = useState<string>('');
  const [hasScanned, setHasScanned] = useState(false);

  const handleScan = async () => {
    setScanning(true);
    setError('');
    try {
      const result = await networkApi.scan();
      setNetworks(result.networks);
      setCurrentSsid(result.current_ssid);
      setConnectedToDrone(result.connected_to_drone);
      setHasScanned(true);
    } catch (err) {
      setError('Scan failed — is the backend running?');
    } finally {
      setScanning(false);
    }
  };

  const droneNetworks = networks.filter(n => n.is_drone);
  const otherNetworks = networks.filter(n => !n.is_drone);

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-heading">WiFi Scanner</h3>
        <button
          onClick={handleScan}
          disabled={scanning}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            scanning
              ? 'bg-panel text-dim cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-500'
          }`}
        >
          {scanning ? 'Scanning…' : 'Scan'}
        </button>
      </div>

      {/* Current connection */}
      {hasScanned && (
        <div className={`mb-3 px-3 py-2 rounded text-sm border ${
          connectedToDrone
            ? 'bg-green-900/20 border-green-700 text-green-300'
            : currentSsid
            ? 'bg-panel border-border text-muted'
            : 'bg-panel border-border text-dim'
        }`}>
          {connectedToDrone
            ? `Connected to drone: ${currentSsid}`
            : currentSsid
            ? `Connected to: ${currentSsid} (not a drone network)`
            : 'Not connected to any WiFi'}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-3 px-3 py-2 rounded text-sm bg-red-900/30 border border-red-700 text-red-300">
          {error}
        </div>
      )}

      {/* Results */}
      {hasScanned && networks.length === 0 && !error && (
        <p className="text-sm text-dim text-center py-4">No networks found</p>
      )}

      {droneNetworks.length > 0 && (
        <div className="mb-3">
          <div className="text-xs font-medium text-orange-400 uppercase tracking-wide mb-1.5">
            Drone Networks ({droneNetworks.length})
          </div>
          <div className="space-y-1.5">
            {droneNetworks.map(n => (
              <NetworkRow key={n.bssid || n.ssid} network={n} isCurrent={n.ssid === currentSsid} />
            ))}
          </div>
        </div>
      )}

      {otherNetworks.length > 0 && (
        <div>
          <div className="text-xs font-medium text-dim uppercase tracking-wide mb-1.5">
            Other Networks ({otherNetworks.length})
          </div>
          <div className="space-y-1.5">
            {otherNetworks.map(n => (
              <NetworkRow key={n.bssid || n.ssid} network={n} isCurrent={n.ssid === currentSsid} />
            ))}
          </div>
        </div>
      )}

      {!hasScanned && (
        <p className="text-sm text-dim text-center py-4">
          Click Scan to find nearby drone networks
        </p>
      )}

      <div className="mt-3 pt-3 border-t border-divider">
        <p className="text-xs text-dim">
          <strong className="text-muted">Tip:</strong> Connect to the drone's WiFi hotspot in Windows
          settings first, then click Scan to confirm.
        </p>
      </div>
    </div>
  );
};
