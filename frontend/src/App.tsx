import { useState, useEffect, useRef } from 'react'
import { droneApi, type DroneStatus } from './services/api'
import { DroneVideo } from './components/DroneVideo'
import { FlightControls } from './components/FlightControls'
import { AutopilotPanel } from './components/AutopilotPanel'
import { SensorPanel } from './components/SensorPanel'

function App() {
  const [droneIp, setDroneIp] = useState('192.168.169.1')
  const [status, setStatus] = useState<DroneStatus | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [message, setMessage] = useState('')
  const [flightArmed, setFlightArmed] = useState(false)
  const [rawHex, setRawHex] = useState('')
  const videoAutoStarted = useRef(false)

  // Poll drone status every 2s
  useEffect(() => {
    const poll = async () => {
      try {
        setStatus(await droneApi.getStatus())
      } catch {
        // backend unreachable
      }
    }
    const id = setInterval(poll, 2000)
    poll()
    return () => clearInterval(id)
  }, [])

  const isStreaming = !!status?.video_streaming
  const isConnected = !!status?.connected

  // Auto-start video when connected but not streaming
  useEffect(() => {
    if (isConnected && !isStreaming && !videoAutoStarted.current) {
      videoAutoStarted.current = true
      droneApi.startVideo()
        .then(() => droneApi.getStatus())
        .then(s => setStatus(s))
        .catch(() => { videoAutoStarted.current = false })
    }
    if (!isConnected) {
      videoAutoStarted.current = false
    }
  }, [isConnected, isStreaming])

  const handleConnect = async () => {
    setConnecting(true)
    setMessage('')
    try {
      const result = await droneApi.connect(droneIp)
      if (result.message) setMessage(result.message)
      // Set status immediately from connect response (triggers auto-video)
      if (result.status) setStatus(result.status)
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : String(err)}`)
    }
    setConnecting(false)
  }

  const handleDisconnect = () => {
    // Optimistic: update UI immediately, don't wait for backend
    setStatus(prev => prev ? { ...prev, connected: false, video_streaming: false } : null)
    setFlightArmed(false)
    setMessage('')
    droneApi.disconnect().catch(() => {})
  }

  const handleVideoToggle = async () => {
    try {
      if (isStreaming) {
        await droneApi.stopVideo()
        videoAutoStarted.current = true // prevent auto-restart after manual stop
      } else {
        videoAutoStarted.current = false
        await droneApi.startVideo()
      }
      setStatus(await droneApi.getStatus())
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const handleSwitchCamera = async (cam: number) => {
    try { await droneApi.switchCamera(cam) } catch (error) { console.error(String(error)) }
  }

  const handleHeadless = async () => {
    try { await droneApi.headless() } catch (error) { console.error(String(error)) }
  }

  const handleSendRaw = () => {
    const hex = rawHex.replace(/\s/g, '')
    if (!hex) return
    droneApi.sendRaw(hex).catch(() => {})
  }

  return (
    <div className="min-h-screen bg-base text-heading flex flex-col">

      {/* Top Bar: connection + status */}
      <header className="px-4 py-2 border-b border-border flex items-center gap-3">
        <img src="/tyvyx_logo_1.svg" alt="TYVYX" className="h-5 w-auto opacity-70" />
        <div className="flex items-center gap-2 ml-2">
          <input
            type="text"
            value={droneIp}
            onChange={(e) => setDroneIp(e.target.value)}
            className="w-36 px-2 py-1 rounded bg-panel border border-border text-heading text-xs font-mono focus:outline-none focus:border-accent"
            placeholder="192.168.169.1"
          />
          {!isConnected ? (
            <button
              onClick={handleConnect}
              disabled={connecting}
              className="px-3 py-1 rounded font-medium text-xs transition-colors
                bg-green-700 hover:bg-green-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
            >
              {connecting ? '...' : 'Connect'}
            </button>
          ) : (
            <button
              onClick={handleDisconnect}
              className="px-3 py-1 rounded font-medium text-xs transition-colors
                bg-red-700 hover:bg-red-600"
            >
              Disconnect
            </button>
          )}
        </div>
        {message && (
          <span className="text-xs text-dim truncate max-w-[300px]">{message}</span>
        )}
        <div className="ml-auto flex items-center gap-3">
          <span className={`font-mono text-xs ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
            {isConnected ? '● Connected' : '○ Disconnected'}
          </span>
          {isStreaming && (
            <span className="font-mono text-xs text-green-400">● Video</span>
          )}
        </div>
      </header>

      <main className="flex-1 flex gap-3 p-3 min-h-0">

        {/* Left Column: Video + Controls (compact) */}
        <div className="w-80 shrink-0 flex flex-col gap-3">

          {/* Video Feed (compact) */}
          <div className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="px-3 py-1.5 border-b border-border flex items-center justify-between">
              <span className="font-semibold text-heading text-xs">Camera</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleVideoToggle}
                  disabled={!isConnected}
                  className={`px-2 py-0.5 rounded font-medium text-[10px] transition-colors
                    disabled:opacity-40 ${
                    isStreaming
                      ? 'bg-orange-700 hover:bg-orange-600'
                      : 'bg-blue-700 hover:bg-blue-600'
                  }`}
                >
                  {isStreaming ? 'Stop' : 'Start'}
                </button>
                <button
                  onClick={() => handleSwitchCamera(1)}
                  disabled={!isConnected}
                  className="px-1.5 py-0.5 rounded font-medium text-[10px] transition-colors
                    bg-purple-700 hover:bg-purple-600 disabled:opacity-40"
                >
                  1
                </button>
                <button
                  onClick={() => handleSwitchCamera(2)}
                  disabled={!isConnected}
                  className="px-1.5 py-0.5 rounded font-medium text-[10px] transition-colors
                    bg-purple-700 hover:bg-purple-600 disabled:opacity-40"
                >
                  2
                </button>
              </div>
            </div>
            <div className="aspect-video bg-black flex items-center justify-center">
              {isStreaming ? (
                <DroneVideo streaming={true} className="w-full h-full" />
              ) : (
                <div className="text-dim text-center select-none p-4">
                  <p className="text-xs">
                    {!isConnected ? 'No connection' : 'Starting...'}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Flight Controls */}
          <div className="bg-card border border-border rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-heading text-xs">Flight Controls</span>
              <button
                onClick={handleHeadless}
                disabled={!isConnected}
                className="px-2 py-0.5 rounded font-medium text-[10px] transition-colors
                  bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40"
              >
                Headless
              </button>
            </div>
            <FlightControls
              connected={isConnected}
              armed={flightArmed}
              onArmedChange={setFlightArmed}
            />
          </div>

          {/* Autopilot Panel (self-hiding when disabled) */}
          <AutopilotPanel />

          {/* Raw Command */}
          <div className="bg-card border border-border rounded-lg p-2">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={rawHex}
                onChange={(e) => setRawHex(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSendRaw() }}
                className="flex-1 px-2 py-1 rounded bg-panel border border-border text-heading text-xs font-mono focus:outline-none focus:border-accent"
                placeholder="ef 00 04 00"
              />
              <button
                onClick={handleSendRaw}
                disabled={!isConnected || !rawHex.replace(/\s/g, '')}
                className="px-3 py-1 rounded font-medium text-xs transition-colors
                  bg-gray-600 hover:bg-gray-500 disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Sensor Fusion (main content, fills remaining space) */}
        <div className="flex-1 min-w-0">
          <SensorPanel />
        </div>

      </main>
    </div>
  )
}

export default App



