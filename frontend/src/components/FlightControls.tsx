import { useState, useEffect, useCallback, useRef } from 'react'
import { droneApi, WS_BASE_URL } from '../services/api'

interface FlightControlsProps {
  connected: boolean
  armed: boolean
  onArmedChange: (armed: boolean) => void
}

const NEUTRAL = 127
const STICK_VALUE = 200  // axis value when key held (max deflection)
const SEND_INTERVAL = 30 // ms between periodic axis updates (~33 Hz)

// Key-to-axis mapping
const KEY_AXES: Record<string, { axis: string; value: number }> = {
  w: { axis: 'throttle', value: STICK_VALUE },
  s: { axis: 'throttle', value: NEUTRAL - (STICK_VALUE - NEUTRAL) },
  a: { axis: 'yaw', value: NEUTRAL - (STICK_VALUE - NEUTRAL) },
  d: { axis: 'yaw', value: STICK_VALUE },
  ArrowUp: { axis: 'pitch', value: STICK_VALUE },
  ArrowDown: { axis: 'pitch', value: NEUTRAL - (STICK_VALUE - NEUTRAL) },
  ArrowLeft: { axis: 'roll', value: NEUTRAL - (STICK_VALUE - NEUTRAL) },
  ArrowRight: { axis: 'roll', value: STICK_VALUE },
}

export function FlightControls({ connected, armed, onArmedChange }: FlightControlsProps) {
  const [loading, setLoading] = useState(false)
  const heldKeys = useRef<Set<string>>(new Set())
  const sendTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const rcWsRef = useRef<WebSocket | null>(null)

  const handleArm = async () => {
    setLoading(true)
    try {
      if (armed) {
        await droneApi.disarm()
        onArmedChange(false)
      } else {
        await droneApi.arm()
        onArmedChange(true)
      }
    } catch (error) {
      console.error('Arm/disarm error:', String(error))
    }
    setLoading(false)
  }

  const handleTakeoff = async () => {
    if (!armed) return
    try { await droneApi.takeoff() } catch (error) { console.error(String(error)) }
  }

  const handleLand = async () => {
    if (!armed) return
    try { await droneApi.land() } catch (error) { console.error(String(error)) }
  }

  const handleCalibrate = async () => {
    if (!armed) return
    try { await droneApi.calibrate() } catch (error) { console.error(String(error)) }
  }

  // Build axes from currently held keys
  const buildAxes = useCallback(() => {
    const axes: Record<string, number> = {
      throttle: NEUTRAL,
      yaw: NEUTRAL,
      pitch: NEUTRAL,
      roll: NEUTRAL,
    }
    heldKeys.current.forEach(key => {
      const mapping = KEY_AXES[key]
      if (mapping) {
        axes[mapping.axis] = mapping.value
      }
    })
    return axes
  }, [])

  // Send stick state via WebSocket (fast) or HTTP fallback
  const sendStickState = useCallback(() => {
    const axes = buildAxes()
    let hasInput = false
    if (axes.throttle !== NEUTRAL || axes.yaw !== NEUTRAL ||
        axes.pitch !== NEUTRAL || axes.roll !== NEUTRAL) {
      hasInput = true
    }

    if (!hasInput) return

    // Try WebSocket first (lowest latency)
    const ws = rcWsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        t: axes.throttle,
        y: axes.yaw,
        p: axes.pitch,
        r: axes.roll,
      }))
      return
    }

    // HTTP fallback
    droneApi.setAxes(axes).catch(() => {})
  }, [buildAxes])

  // RC WebSocket lifecycle: open when armed, close when not
  useEffect(() => {
    if (!armed || !connected) {
      if (rcWsRef.current) {
        rcWsRef.current.onclose = null
        rcWsRef.current.close()
        rcWsRef.current = null
      }
      return
    }

    const ws = new WebSocket(`${WS_BASE_URL}/api/rc/ws`)
    rcWsRef.current = ws

    ws.onopen = () => {
      console.log('[RC] WebSocket connected')
    }

    ws.onclose = () => {
      console.log('[RC] WebSocket closed')
      if (rcWsRef.current === ws) {
        rcWsRef.current = null
      }
    }

    ws.onerror = () => {
      console.warn('[RC] WebSocket error, will use HTTP fallback')
    }

    return () => {
      ws.onclose = null
      ws.close()
      if (rcWsRef.current === ws) {
        rcWsRef.current = null
      }
    }
  }, [armed, connected])

  // Periodic axis sender while armed
  useEffect(() => {
    if (!armed) {
      if (sendTimer.current) {
        clearInterval(sendTimer.current)
        sendTimer.current = null
      }
      return
    }

    sendTimer.current = setInterval(sendStickState, SEND_INTERVAL)
    return () => {
      if (sendTimer.current) {
        clearInterval(sendTimer.current)
        sendTimer.current = null
      }
    }
  }, [armed, sendStickState])

  // Keyboard handlers
  useEffect(() => {
    if (!armed) {
      heldKeys.current.clear()
      return
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      if (e.key in KEY_AXES) {
        e.preventDefault()
        const wasEmpty = heldKeys.current.size === 0
        heldKeys.current.add(e.key)
        // Immediate send on first key press (don't wait for interval)
        if (wasEmpty || !e.repeat) {
          sendStickState()
        }
      }

      // One-shot commands (ignore repeats)
      if (!e.repeat) {
        if (e.key === ' ') { e.preventDefault(); handleTakeoff() }
        if (e.key === 'x') { e.preventDefault(); handleLand() }
        if (e.key === 'c') { e.preventDefault(); handleCalibrate() }
      }
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key in KEY_AXES) {
        heldKeys.current.delete(e.key)
        // Immediate send on key release (responsive stick centering)
        sendStickState()
      }
    }

    // Clear keys on window blur (prevent stuck keys)
    const handleBlur = () => { heldKeys.current.clear() }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    window.addEventListener('blur', handleBlur)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
      window.removeEventListener('blur', handleBlur)
      heldKeys.current.clear()
    }
  }, [armed, sendStickState])

  // Disarm on disconnect
  useEffect(() => {
    if (!connected && armed) {
      onArmedChange(false)
    }
  }, [connected, armed, onArmedChange])

  return (
    <section>
      <p className="text-xs text-dim uppercase tracking-wide mb-2">Flight</p>

      <div className="flex gap-2 mb-3">
        <button
          onClick={handleArm}
          disabled={loading || !connected}
          className={`flex-1 px-4 py-2 rounded font-bold text-sm transition-colors
            disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed ${
            armed
              ? 'bg-red-600 hover:bg-red-500'
              : 'bg-yellow-700 hover:bg-yellow-600'
          }`}
        >
          {armed ? 'DISARM' : 'ARM'}
        </button>
      </div>

      <div className="flex gap-2 mb-3">
        <button
          onClick={handleTakeoff}
          disabled={!armed}
          className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
            bg-green-700 hover:bg-green-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
        >
          Takeoff
        </button>
        <button
          onClick={handleLand}
          disabled={!armed}
          className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
            bg-orange-700 hover:bg-orange-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
        >
          Land
        </button>
        <button
          onClick={handleCalibrate}
          disabled={!armed}
          className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
            bg-blue-700 hover:bg-blue-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
        >
          Calibrate
        </button>
      </div>

      {armed && (
        <div className="text-xs text-dim bg-panel rounded p-2 font-mono">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <span>W/S &mdash; Throttle</span>
            <span>&uarr;/&darr; &mdash; Pitch</span>
            <span>A/D &mdash; Yaw</span>
            <span>&larr;/&rarr; &mdash; Roll</span>
            <span>Space &mdash; Takeoff</span>
            <span>X &mdash; Land</span>
          </div>
          <div className="mt-1 text-[10px] text-dim/60">
            {rcWsRef.current?.readyState === WebSocket.OPEN ? '● WS RC' : '○ HTTP RC'}
          </div>
        </div>
      )}
    </section>
  )
}
