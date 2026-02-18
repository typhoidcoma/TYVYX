import { useState, useRef, useEffect, useCallback } from 'react'
import { API_BASE_URL, WS_BASE_URL } from '../services/api'

type Transport = 'connecting' | 'websocket' | 'mjpeg'

interface Props {
  streaming: boolean
  testMode?: boolean
  className?: string
}

interface DebugStats {
  fps: number
  frameSize: number
  frameCount: number
}

const MAX_WS_RETRIES = 3
const WS_RETRY_DELAY = 2000 // ms between reconnect attempts

export function DroneVideo({ streaming, testMode = false, className = '' }: Props) {
  const imgRef = useRef<HTMLImageElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const prevUrlRef = useRef<string | null>(null)
  const [transport, setTransport] = useState<Transport>('connecting')
  const [debug, setDebug] = useState<DebugStats>({ fps: 0, frameSize: 0, frameCount: 0 })
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wsRetries = useRef(0)

  // FPS tracking refs (avoid re-renders per frame)
  const fpsCounter = useRef(0)
  const fpsInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const totalCount = useRef(0)
  const lastSize = useRef(0)

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
    if (fpsInterval.current) {
      clearInterval(fpsInterval.current)
      fpsInterval.current = null
    }
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.onmessage = null
      wsRef.current.close()
      wsRef.current = null
    }
    if (prevUrlRef.current) {
      URL.revokeObjectURL(prevUrlRef.current)
      prevUrlRef.current = null
    }
  }, [])

  const fallbackToMjpeg = useCallback(() => {
    cleanup()
    console.warn('[DroneVideo] Falling back to MJPEG')
    setTransport('mjpeg')
  }, [cleanup])

  const connectWs = useCallback(() => {
    cleanup()
    setTransport('connecting')

    // Test mode uses /api/video/test, live mode uses /api/video/ws
    const wsPath = testMode ? '/api/video/test' : '/api/video/ws'
    console.log(`[DroneVideo] Connecting WebSocket to ${wsPath} (attempt ${wsRetries.current + 1})...`)
    const ws = new WebSocket(`${WS_BASE_URL}${wsPath}`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    // FPS counter: sample every second, update debug overlay
    fpsInterval.current = setInterval(() => {
      setDebug({
        fps: fpsCounter.current,
        frameSize: lastSize.current,
        frameCount: totalCount.current,
      })
      fpsCounter.current = 0
    }, 1000)

    ws.onopen = () => {
      console.log('[DroneVideo] WebSocket connected')
      setTransport('websocket')
      wsRetries.current = 0 // reset retry count on successful connection
    }

    ws.onmessage = (e) => {
      if (!(e.data instanceof ArrayBuffer)) return

      fpsCounter.current++
      totalCount.current++
      lastSize.current = e.data.byteLength

      const blob = new Blob([e.data], { type: 'image/jpeg' })
      const url = URL.createObjectURL(blob)

      if (imgRef.current) {
        imgRef.current.src = url
      }

      // Revoke previous blob URL to avoid memory leak
      if (prevUrlRef.current) {
        URL.revokeObjectURL(prevUrlRef.current)
      }
      prevUrlRef.current = url
    }

    ws.onclose = (e) => {
      console.warn(`[DroneVideo] WebSocket closed: code=${e.code} reason=${e.reason}`)
      wsRef.current = null

      // Retry WS before falling back to MJPEG
      wsRetries.current++
      if (wsRetries.current <= MAX_WS_RETRIES) {
        console.log(`[DroneVideo] Reconnecting WS in ${WS_RETRY_DELAY}ms (retry ${wsRetries.current}/${MAX_WS_RETRIES})...`)
        reconnectTimer.current = setTimeout(() => {
          connectWs()
        }, WS_RETRY_DELAY)
      } else {
        console.warn(`[DroneVideo] Max WS retries reached, falling back to MJPEG`)
        fallbackToMjpeg()
      }
    }

    ws.onerror = () => {
      // onclose will fire after onerror, let it handle retry logic
      console.error('[DroneVideo] WebSocket error')
    }
  }, [cleanup, fallbackToMjpeg, testMode])

  useEffect(() => {
    if (streaming || testMode) {
      wsRetries.current = 0
      fpsCounter.current = 0
      totalCount.current = 0
      lastSize.current = 0
      setDebug({ fps: 0, frameSize: 0, frameCount: 0 })
      connectWs()
    } else {
      cleanup()
      setTransport('connecting')
    }
    return cleanup
  }, [streaming, testMode, connectWs, cleanup])

  if (!streaming && !testMode) return null

  // Choose MJPEG URL based on mode
  const mjpegUrl = testMode
    ? `${API_BASE_URL}/api/video/test`
    : `${API_BASE_URL}/api/video/feed`

  return (
    <div className={`relative ${className}`}>
      {/* WebSocket: JPEG frames rendered to <img> via blob URLs */}
      {transport === 'websocket' && (
        <img
          ref={imgRef}
          alt="Drone video feed"
          className="w-full h-full object-contain"
        />
      )}

      {/* MJPEG fallback: browser-native multipart streaming */}
      {transport === 'mjpeg' && (
        <img
          src={mjpegUrl}
          alt="Drone video feed"
          className="w-full h-full object-contain"
        />
      )}

      {/* Connecting state */}
      {transport === 'connecting' && (
        <div className="flex items-center justify-center h-full">
          <p className="text-dim text-sm animate-pulse">Connecting...</p>
        </div>
      )}

      {/* Debug overlay — top-left */}
      <div className="absolute top-2 left-2 px-2 py-1 rounded bg-black/70 text-[10px] font-mono leading-relaxed text-white/80">
        <div>{debug.fps} fps</div>
        <div>{(debug.frameSize / 1024).toFixed(1)} KB</div>
        <div>#{debug.frameCount}</div>
      </div>

      {/* Transport badge — top-right */}
      <span className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-mono bg-black/60">
        {transport === 'websocket' && <span className="text-green-400">WS</span>}
        {transport === 'mjpeg' && <span className="text-orange-400">MJPEG</span>}
        {testMode && <span className="text-yellow-400 ml-1">TEST</span>}
      </span>
    </div>
  )
}
