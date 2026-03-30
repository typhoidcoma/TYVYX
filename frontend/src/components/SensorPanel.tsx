import { useState, useEffect } from 'react'
import { rssiApi, slamApi, positionApi, API_BASE_URL, type RssiData, type SlamData } from '../services/api'
import { Position3DBox } from './Position3DBox'

interface PositionData {
  position: { x: number; y: number; z: number }
  velocity: { vx: number; vy: number; vz: number }
  altitude: number
  enabled: boolean
  feature_count: number
  camera_mode: 'bottom' | 'front'
}

interface PipelineData {
  position_enabled: boolean
  camera_mode: string
  altitude: number
  fps: number
  frame_count: number
  rssi_enabled: boolean
  optical_flow_features: number
  ekf: {
    updates: { velocity: number; altitude: number; rssi: number; predictions: number }
    anchor: { x: number; y: number; z: number }
  } | null
}

interface EkfStateData {
  state: { x: number; y: number; z: number; vx: number; vy: number; vz: number }
  covariance_diag: number[]
  uncertainty: { sigma_x: number; sigma_y: number; sigma_z: number }
  anchor: { x: number; y: number; z: number }
  updates: { predictions: number; velocity: number; altitude: number; rssi: number }
}

interface OpticalFlowData {
  initialized: boolean
  feature_count: number
  using_gpu: boolean
  last_pixel_velocity: number[] | null
}

const POLL_MS = 500

export function SensorPanel() {
  const [rssi, setRssi] = useState<RssiData | null>(null)
  const [slamData, setSlamData] = useState<SlamData | null>(null)
  const [position, setPosition] = useState<PositionData | null>(null)
  const [rssiLoading, setRssiLoading] = useState(false)
  const [calDist, setCalDist] = useState('')
  const [calLoading, setCalLoading] = useState(false)
  const [calResult, setCalResult] = useState<string | null>(null)
  const [gzLoading, setGzLoading] = useState(false)
  const [gzResult, setGzResult] = useState<string | null>(null)
  const [showDebug, setShowDebug] = useState(false)
  const [pipeline, setPipeline] = useState<PipelineData | null>(null)
  const [ekfState, setEkfState] = useState<EkfStateData | null>(null)
  const [optFlow, setOptFlow] = useState<OpticalFlowData | null>(null)
  const [debugLog, setDebugLog] = useState<string | null>(null)

  // Poll all sensor data
  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const [r, s, p] = await Promise.allSettled([
          rssiApi.getData(),
          slamApi.getStatus(),
          fetch(`http://localhost:${import.meta.env.VITE_API_PORT || '8000'}/api/position/current`)
            .then(res => res.json()),
        ])
        if (!active) return
        if (r.status === 'fulfilled') setRssi(r.value)
        if (s.status === 'fulfilled') setSlamData(s.value)
        if (p.status === 'fulfilled') setPosition(p.value)
      } catch {
        // ignore
      }
    }
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => { active = false; clearInterval(id) }
  }, [])

  // Poll debug data when debug panel is open
  useEffect(() => {
    if (!showDebug) return
    let active = true
    const poll = async () => {
      try {
        const [p, e, o] = await Promise.allSettled([
          fetch(`${API_BASE_URL}/api/debug/pipeline`).then(r => r.json()),
          fetch(`${API_BASE_URL}/api/debug/ekf/state`).then(r => r.json()),
          fetch(`${API_BASE_URL}/api/debug/optical_flow`).then(r => r.json()),
        ])
        if (!active) return
        if (p.status === 'fulfilled') setPipeline(p.value)
        if (e.status === 'fulfilled') setEkfState(e.value)
        if (o.status === 'fulfilled') setOptFlow(o.value)
      } catch { /* ignore */ }
    }
    poll()
    const id = setInterval(poll, 1000)
    return () => { active = false; clearInterval(id) }
  }, [showDebug])

  const debugAction = async (url: string, body?: Record<string, unknown>) => {
    setDebugLog(null)
    try {
      const res = await fetch(`${API_BASE_URL}${url}`, {
        method: body ? 'POST' : 'GET',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : undefined,
      })
      const data = await res.json()
      setDebugLog(JSON.stringify(data, null, 2))
    } catch (error) {
      setDebugLog(`Error: ${String(error)}`)
    }
  }

  const handleRssiToggle = async () => {
    setRssiLoading(true)
    try {
      if (rssi?.enabled) {
        await rssiApi.stop()
      } else {
        await rssiApi.start()
      }
    } catch (error) {
      console.error(String(error))
    }
    setRssiLoading(false)
  }

  const handleCalibrate = async () => {
    const mm = parseFloat(calDist)
    if (isNaN(mm) || mm <= 0) return
    setCalLoading(true)
    setCalResult(null)
    try {
      const result = await rssiApi.calibrate(mm / 1000) // mm → meters for API
      setCalResult(`${result.total_points} pts | n=${result.model.n.toFixed(2)} | ref=${result.model.rssi_ref.toFixed(0)} dBm`)
      setCalDist('')
    } catch (error) {
      setCalResult(`Error: ${String(error)}`)
    }
    setCalLoading(false)
  }

  const handleGroundZero = async () => {
    setGzLoading(true)
    setGzResult(null)
    try {
      const result = await positionApi.groundZero()
      const dist = result.rssi_distance?.toFixed(2) ?? '?'
      setGzResult(`Zero set | RSSI anchor: ${dist}m`)
    } catch (error) {
      setGzResult(`Error: ${String(error)}`)
    }
    setGzLoading(false)
  }

  // Signal strength bar color
  const signalColor = (pct: number) => {
    if (pct >= 70) return 'bg-green-500'
    if (pct >= 40) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  const Metric = ({ label, value, color = 'text-heading' }: { label: string; value: string; color?: string }) => (
    <div className="bg-panel/50 rounded px-2 py-1.5 min-w-0">
      <div className="text-dim text-[9px] uppercase tracking-wider leading-none mb-1">{label}</div>
      <div className={`font-mono text-sm leading-none ${color}`}>{value}</div>
    </div>
  )

  return (
    <div className="bg-card border border-border rounded-lg p-3 h-full flex flex-col">

      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-heading text-xs">Sensor Fusion</span>
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
            position?.enabled
              ? 'bg-emerald-900/40 text-emerald-400'
              : 'bg-panel text-dim'
          }`}>
            {position?.enabled ? 'EKF ACTIVE' : 'EKF IDLE'}
          </span>
          <button
            onClick={() => {
              const newMode = position?.camera_mode === 'bottom' ? 'front' : 'bottom'
              positionApi.setCameraMode(newMode).catch(console.error)
            }}
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded transition-colors ${
              position?.camera_mode === 'bottom'
                ? 'bg-cyan-900/40 text-cyan-400 hover:bg-cyan-800/50'
                : 'bg-panel text-dim hover:bg-panel/80'
            }`}
          >
            CAM: {position?.camera_mode === 'bottom' ? 'BTM' : 'FWD'}
          </button>
        </div>
        <div className="flex items-center gap-2">
          {gzResult && (
            <span className="text-[10px] font-mono text-emerald-400">{gzResult}</span>
          )}
          <button
            onClick={handleGroundZero}
            disabled={gzLoading}
            className="px-2.5 py-1 rounded text-[10px] font-medium bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 transition-colors"
          >
            {gzLoading ? '...' : 'Ground Zero'}
          </button>
          <button
            onClick={() => setShowDebug(v => !v)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors ${
              showDebug ? 'bg-amber-700 hover:bg-amber-600' : 'bg-gray-600 hover:bg-gray-500'
            }`}
          >
            Debug
          </button>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-8 gap-1.5 mb-2">
        <Metric label="X" value={position?.position.x.toFixed(3) ?? '—'} />
        <Metric label="Y" value={position?.position.y.toFixed(3) ?? '—'} />
        <Metric label="Z" value={position?.position.z.toFixed(3) ?? '—'} color="text-cyan-400" />
        <Metric label="Vx" value={position?.velocity.vx.toFixed(3) ?? '—'} />
        <Metric label="Vy" value={position?.velocity.vy.toFixed(3) ?? '—'} />
        <Metric label="Vz" value={position?.velocity.vz.toFixed(3) ?? '—'} color="text-cyan-400" />
        <Metric label="Features" value={String(position?.feature_count ?? '—')} />
        <Metric label="Alt (m)" value={position?.altitude.toFixed(2) ?? '—'} color="text-cyan-400" />
      </div>

      {/* 3D Position Box — fills available space */}
      <div className="flex-1 min-h-0 border-t border-border pt-2">
        <Position3DBox
          x={position?.position.x ?? 0}
          y={position?.position.y ?? 0}
          z={position?.position.z ?? 0}
          boundsX={[-1, 1]}
          boundsY={[-1, 1]}
          boundsZ={[0, 1.5]}
        />
      </div>

      {/* Sensor cards */}
      <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-border">

        {/* SLAM / VO Card */}
        <div className="bg-panel/30 rounded-lg p-2.5">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${
                !slamData?.enabled ? 'bg-gray-600'
                  : (slamData.inlier_ratio > 0.3 ? 'bg-emerald-400'
                    : slamData.inlier_ratio > 0.1 ? 'bg-yellow-400'
                    : 'bg-red-400')
              }`} />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">SLAM</span>
              <span className="text-[9px] text-dim">
                {slamData?.slam_type === 'visual_odometry' ? 'VO' : 'OF'}
              </span>
            </div>
            <button
              onClick={() => slamApi.reset().catch(console.error)}
              className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-600 hover:bg-gray-500 transition-colors"
            >
              Reset
            </button>
          </div>
          {slamData?.enabled ? (
            <div className="text-[11px] font-mono space-y-1">
              <div className="flex justify-between">
                <span className="text-dim">Keyframes</span>
                <span className="text-cyan-400">{slamData.keyframe_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-dim">Map Pts</span>
                <span className="text-heading">{slamData.map_points_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-dim">Matches</span>
                <span className="text-heading">{slamData.avg_matches.toFixed(0)}</span>
              </div>
              <div className="flex justify-between text-[10px] text-dim">
                <span>Inlier: {(slamData.inlier_ratio * 100).toFixed(0)}%</span>
                <span>Lost: {slamData.lost_count}</span>
                <span>{slamData.frame_count} frm</span>
              </div>
            </div>
          ) : (
            <div className="text-[11px] text-dim font-mono">Offline</div>
          )}
        </div>

        {/* RSSI Card */}
        <div className="bg-panel/30 rounded-lg p-2.5">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${rssi?.enabled ? 'bg-green-400' : 'bg-gray-600'}`} />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">WiFi RSSI</span>
              {rssi?.enabled && rssi.ssid && (
                <span className="text-[9px] text-dim">{rssi.ssid.slice(0, 10)}</span>
              )}
            </div>
            <button
              onClick={handleRssiToggle}
              disabled={rssiLoading}
              className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors disabled:opacity-50 ${
                rssi?.enabled ? 'bg-orange-700 hover:bg-orange-600' : 'bg-blue-700 hover:bg-blue-600'
              }`}
            >
              {rssiLoading ? '...' : rssi?.enabled ? 'Stop' : 'Start'}
            </button>
          </div>
          {rssi?.enabled ? (
            <div className="text-[11px] font-mono space-y-1">
              <div className="flex justify-between">
                <span className="text-dim">Distance</span>
                <span className="text-cyan-400 text-sm font-semibold">{rssi.distance.toFixed(2)}m</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-dim">Signal</span>
                <span className="text-heading">{rssi.signal_pct}% <span className="text-dim">({rssi.rssi_dbm.toFixed(0)} dBm)</span></span>
              </div>
              {/* Signal bar */}
              <div className="flex items-center gap-1.5">
                <div className="flex-1 h-1.5 bg-black/30 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${signalColor(rssi.signal_pct)}`}
                    style={{ width: `${rssi.signal_pct}%` }}
                  />
                </div>
              </div>
              {/* Model & calibration */}
              <div className="flex items-center gap-1.5 pt-1 border-t border-border/50">
                <span className="text-[9px] text-dim">n={rssi.model?.n.toFixed(1)}</span>
                <div className="flex-1" />
                <input
                  type="number"
                  value={calDist}
                  onChange={(e) => setCalDist(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCalibrate() }}
                  placeholder="mm"
                  step="10"
                  min="10"
                  className="w-14 px-1 py-0.5 rounded bg-panel border border-border text-heading text-[10px] font-mono focus:outline-none focus:border-accent"
                />
                <button
                  onClick={handleCalibrate}
                  disabled={calLoading || !calDist}
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-700 hover:bg-green-600 disabled:opacity-50 transition-colors"
                >
                  {calLoading ? '...' : 'Cal'}
                </button>
              </div>
              {calResult && (
                <div className="text-[9px] text-dim">{calResult}</div>
              )}
            </div>
          ) : (
            <div className="text-[11px] text-dim font-mono">Offline</div>
          )}
        </div>
      </div>

      {/* Debug Panel */}
      {showDebug && (
        <div className="mt-2 pt-2 border-t border-border space-y-2">
          {/* Pipeline overview */}
          <div className="bg-panel/30 rounded-lg p-2 text-[10px] font-mono">
            <div className="text-dim text-[9px] uppercase tracking-wider mb-1">Pipeline</div>
            <div className="grid grid-cols-4 gap-x-3 gap-y-0.5">
              <span className="text-dim">Frames</span>
              <span className="text-heading">{pipeline?.frame_count ?? '—'}</span>
              <span className="text-dim">FPS</span>
              <span className="text-heading">{pipeline?.fps ?? '—'}</span>
              <span className="text-dim">OF Features</span>
              <span className="text-heading">{optFlow?.feature_count ?? '—'}</span>
              <span className="text-dim">GPU</span>
              <span className={optFlow?.using_gpu ? 'text-emerald-400' : 'text-dim'}>{optFlow?.using_gpu ? 'Yes' : 'No'}</span>
              <span className="text-dim">Px Vel</span>
              <span className="text-heading">{optFlow?.last_pixel_velocity
                ? `[${optFlow.last_pixel_velocity.map(v => v.toFixed(2)).join(', ')}]`
                : '—'}</span>
            </div>
          </div>

          {/* EKF state */}
          {ekfState && (
            <div className="bg-panel/30 rounded-lg p-2 text-[10px] font-mono">
              <div className="text-dim text-[9px] uppercase tracking-wider mb-1">EKF State</div>
              <div className="grid grid-cols-6 gap-x-2 gap-y-0.5">
                <span className="text-dim">x</span>
                <span className="text-heading">{ekfState.state.x.toFixed(3)}</span>
                <span className="text-dim">y</span>
                <span className="text-heading">{ekfState.state.y.toFixed(3)}</span>
                <span className="text-dim">z</span>
                <span className="text-cyan-400">{ekfState.state.z.toFixed(3)}</span>
                <span className="text-dim">vx</span>
                <span className="text-heading">{ekfState.state.vx.toFixed(3)}</span>
                <span className="text-dim">vy</span>
                <span className="text-heading">{ekfState.state.vy.toFixed(3)}</span>
                <span className="text-dim">vz</span>
                <span className="text-cyan-400">{ekfState.state.vz.toFixed(3)}</span>
              </div>
              <div className="grid grid-cols-6 gap-x-2 mt-1">
                <span className="text-dim col-span-6">Covariance diag: [{ekfState.covariance_diag.map(v => v.toFixed(3)).join(', ')}]</span>
              </div>
              <div className="flex gap-3 mt-1 text-dim">
                <span>Predict: {ekfState.updates.predictions}</span>
                <span>Vel: {ekfState.updates.velocity}</span>
                <span>Alt: {ekfState.updates.altitude}</span>
                <span>RSSI: {ekfState.updates.rssi}</span>
              </div>
              <div className="text-dim mt-0.5">
                Anchor: ({ekfState.anchor.x.toFixed(2)}, {ekfState.anchor.y.toFixed(2)}, {ekfState.anchor.z.toFixed(2)})
              </div>
            </div>
          )}

          {/* Test actions */}
          <div className="bg-panel/30 rounded-lg p-2">
            <div className="text-dim text-[9px] uppercase tracking-wider font-mono mb-1">Test Actions</div>
            <div className="flex flex-wrap gap-1">
              <button onClick={() => debugAction('/api/slam/statistics')}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-600 hover:bg-gray-500 transition-colors">
                VO Stats
              </button>
              <button onClick={() => debugAction('/api/debug/transform/camera')}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-600 hover:bg-gray-500 transition-colors">
                Camera Intrinsics
              </button>
              <button onClick={() => debugAction('/api/debug/transform/pixel_to_world', { vx_px: 5, vy_px: 5 })}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-600 hover:bg-gray-500 transition-colors">
                Test Transform (5px)
              </button>
              <button onClick={() => debugAction('/api/debug/ekf/inject_velocity', { vx: 0.1, vy: 0 })}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-700 hover:bg-indigo-600 transition-colors">
                Inject Vel 0.1m/s
              </button>
              <button onClick={() => debugAction('/api/debug/ekf/inject_altitude', { altitude: 0.5 })}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-700 hover:bg-indigo-600 transition-colors">
                Inject Alt 0.5m
              </button>
              <button onClick={() => debugAction('/api/debug/ekf/inject_rssi', { distance: 1.0 })}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-700 hover:bg-indigo-600 transition-colors">
                Inject RSSI 1.0m
              </button>
              <button onClick={() => debugAction('/api/debug/rssi/reset_calibration', {})}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-700 hover:bg-red-600 transition-colors">
                Reset RSSI Cal
              </button>
            </div>
            {debugLog && (
              <pre className="mt-1.5 p-1.5 rounded bg-black/30 text-[9px] text-dim font-mono overflow-x-auto max-h-24 whitespace-pre-wrap">
                {debugLog}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
