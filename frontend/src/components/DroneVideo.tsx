import { useState, useRef, useEffect, useCallback } from 'react'

const API_BASE = 'http://localhost:8000'
const WS_BASE = 'ws://localhost:8000'

type Transport = 'connecting' | 'websocket' | 'mjpeg'

interface Props {
  streaming: boolean
  className?: string
}

export function DroneVideo({ streaming, className = '' }: Props) {
  const imgRef = useRef<HTMLImageElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const prevUrlRef = useRef<string | null>(null)
  const [transport, setTransport] = useState<Transport>('connecting')
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
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
    setTransport('mjpeg')
  }, [cleanup])

  const connectWs = useCallback(() => {
    cleanup()
    setTransport('connecting')

    const ws = new WebSocket(`${WS_BASE}/api/video/ws`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      setTransport('websocket')
    }

    ws.onmessage = (e) => {
      if (!(e.data instanceof ArrayBuffer)) return
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

    ws.onclose = () => {
      // Auto-reconnect after 1s, fall back to MJPEG after 3 failed attempts
      wsRef.current = null
      reconnectTimer.current = setTimeout(() => {
        fallbackToMjpeg()
      }, 1000)
    }

    ws.onerror = () => {
      fallbackToMjpeg()
    }
  }, [cleanup, fallbackToMjpeg])

  useEffect(() => {
    if (streaming) {
      connectWs()
    } else {
      cleanup()
      setTransport('connecting')
    }
    return cleanup
  }, [streaming, connectWs, cleanup])

  if (!streaming) return null

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
          src={`${API_BASE}/api/video/feed`}
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

      {/* Transport badge */}
      <span className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-mono bg-black/60">
        {transport === 'websocket' && <span className="text-green-400">WS</span>}
        {transport === 'mjpeg' && <span className="text-orange-400">MJPEG</span>}
      </span>
    </div>
  )
}
