import { useState, useEffect, useRef } from 'react'
import { autopilotApi } from '../services/api'

interface AutopilotOutput {
  roll: number
  pitch: number
  error_x: number
  error_y: number
  pid_x: number
  pid_y: number
  safe_mode: boolean
  feature_count: number
}

interface AutopilotState {
  enabled: boolean
  target: { x: number; y: number }
  output: AutopilotOutput
  pid_x: { kp: number; ki: number; kd: number; integral: number; last_error: number }
  pid_y: { kp: number; ki: number; kd: number; integral: number; last_error: number }
  config: {
    loop_hz: number
    stick_scale: number
    min_features: number
    stale_timeout: number
  }
  altitude?: number
}

const SIZE = 180
const CENTER = SIZE / 2
const SCALE = 40 // pixels per meter
const TRAIL_MAX = 60

export function AutopilotPanel() {
  const [state, setState] = useState<AutopilotState | null>(null)
  const trail = useRef<{ x: number; y: number }[]>([])

  // Poll autopilot state at 5Hz
  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const s = await autopilotApi.getState()
        if (active) setState(s)
      } catch {
        if (active) setState(null)
      }
    }
    poll()
    const id = setInterval(poll, 200)
    return () => { active = false; clearInterval(id) }
  }, [])

  if (!state?.enabled) return null

  const { output, target } = state
  const ex = output.error_x
  const ey = output.error_y

  // Current position = target - error (error = target - current → current = target - error)
  // For the crosshair we show offset from target, so dot = -error
  const dotX = CENTER + (-ex) * SCALE
  const dotY = CENTER + (ey) * SCALE // Y inverted: positive Y = right on screen

  // Update trail
  trail.current.push({ x: dotX, y: dotY })
  if (trail.current.length > TRAIL_MAX) trail.current.shift()

  const safeMode = output.safe_mode
  const features = output.feature_count
  const minFeatures = state.config.min_features

  // Feature health: green > 2x min, yellow > min, red < min
  const featureColor = features >= minFeatures * 2
    ? 'text-green-400'
    : features >= minFeatures
      ? 'text-yellow-400'
      : 'text-red-400'

  const dotColor = safeMode ? '#ef4444' : '#22d3ee' // red if safe mode, cyan if tracking

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-heading text-sm">Position Hold</span>
        <span className={`text-xs font-mono ${safeMode ? 'text-red-400 animate-pulse' : 'text-cyan-400'}`}>
          {safeMode ? 'SAFE MODE' : 'TRACKING'}
        </span>
      </div>

      <div className="flex gap-4 items-start">
        {/* Crosshair SVG */}
        <svg
          width={SIZE}
          height={SIZE}
          className="bg-black/40 rounded border border-border shrink-0"
          viewBox={`0 0 ${SIZE} ${SIZE}`}
        >
          {/* Grid */}
          {[-2, -1, 1, 2].map(i => (
            <g key={i}>
              <line
                x1={CENTER + i * SCALE} y1={0}
                x2={CENTER + i * SCALE} y2={SIZE}
                stroke="white" strokeOpacity={0.06}
              />
              <line
                x1={0} y1={CENTER + i * SCALE}
                x2={SIZE} y2={CENTER + i * SCALE}
                stroke="white" strokeOpacity={0.06}
              />
            </g>
          ))}

          {/* Center crosshair (target) */}
          <line x1={CENTER} y1={0} x2={CENTER} y2={SIZE} stroke="white" strokeOpacity={0.15} />
          <line x1={0} y1={CENTER} x2={SIZE} y2={CENTER} stroke="white" strokeOpacity={0.15} />
          <circle cx={CENTER} cy={CENTER} r={3} fill="none" stroke="white" strokeOpacity={0.3} />

          {/* Scale label */}
          <text x={CENTER + SCALE} y={SIZE - 4} fill="white" fillOpacity={0.2} fontSize={8} textAnchor="middle">
            1m
          </text>

          {/* Trail */}
          {trail.current.length > 1 && (
            <polyline
              points={trail.current.map(p => `${p.x},${p.y}`).join(' ')}
              fill="none"
              stroke={dotColor}
              strokeOpacity={0.25}
              strokeWidth={1}
            />
          )}

          {/* Current position dot */}
          <circle
            cx={Math.max(4, Math.min(SIZE - 4, dotX))}
            cy={Math.max(4, Math.min(SIZE - 4, dotY))}
            r={5}
            fill={dotColor}
            fillOpacity={0.9}
          />
          <circle
            cx={Math.max(4, Math.min(SIZE - 4, dotX))}
            cy={Math.max(4, Math.min(SIZE - 4, dotY))}
            r={8}
            fill="none"
            stroke={dotColor}
            strokeOpacity={0.4}
          />
        </svg>

        {/* Telemetry readout */}
        <div className="flex-1 text-xs font-mono space-y-2">
          {/* Position error */}
          <div>
            <span className="text-dim uppercase text-[10px]">Error (m)</span>
            <div className="grid grid-cols-2 gap-x-3">
              <span>X: <span className="text-heading">{ex.toFixed(3)}</span></span>
              <span>Y: <span className="text-heading">{ey.toFixed(3)}</span></span>
            </div>
          </div>

          {/* PID output */}
          <div>
            <span className="text-dim uppercase text-[10px]">PID Output</span>
            <div className="grid grid-cols-2 gap-x-3">
              <span>X: <span className="text-heading">{output.pid_x.toFixed(3)}</span></span>
              <span>Y: <span className="text-heading">{output.pid_y.toFixed(3)}</span></span>
            </div>
          </div>

          {/* Stick output */}
          <div>
            <span className="text-dim uppercase text-[10px]">Sticks</span>
            <div className="grid grid-cols-2 gap-x-3">
              <span>Pitch: <span className="text-heading">{output.pitch}</span></span>
              <span>Roll: <span className="text-heading">{output.roll}</span></span>
            </div>
          </div>

          {/* Features + altitude + target */}
          <div className="flex justify-between">
            <span>
              Features: <span className={featureColor}>{features}</span>
              <span className="text-dim">/{minFeatures}</span>
            </span>
            {state.altitude != null && (
              <span className="text-cyan-400">{state.altitude.toFixed(2)}m</span>
            )}
            <span className="text-dim">
              Tgt ({target.x.toFixed(1)}, {target.y.toFixed(1)})
            </span>
          </div>

          {/* Stick bars */}
          <div className="space-y-1">
            <StickBar label="P" value={output.pitch} />
            <StickBar label="R" value={output.roll} />
          </div>
        </div>
      </div>
    </div>
  )
}

function StickBar({ label, value }: { label: string; value: number }) {
  const offset = value - 128
  const pct = (offset / 92) * 50 // 92 = max deflection (220-128)
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-dim w-3 text-right">{label}</span>
      <div className="flex-1 h-2 bg-black/30 rounded-full relative overflow-hidden">
        {/* Center mark */}
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-white/20" />
        {/* Bar */}
        <div
          className="absolute top-0 bottom-0 rounded-full"
          style={{
            left: pct >= 0 ? '50%' : `${50 + pct}%`,
            width: `${Math.abs(pct)}%`,
            backgroundColor: Math.abs(offset) > 60 ? '#f59e0b' : '#22d3ee',
          }}
        />
      </div>
      <span className="text-dim w-6 text-right text-[10px]">{offset > 0 ? '+' : ''}{offset}</span>
    </div>
  )
}
