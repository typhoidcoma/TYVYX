import { useState, useEffect, useRef } from 'react'
import { droneApi, type DroneStatus } from './services/api'
import { DroneVideo } from './components/DroneVideo'
import { FlightControls } from './components/FlightControls'

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

      {/* Header */}
      <header className="px-4 py-3 border-b border-border flex items-center gap-4">
        <span className={`ml-auto font-mono text-sm ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
          {isConnected ? '● Connected' : '○ Disconnected'}
        </span>
        {isStreaming && (
          <span className="font-mono text-sm text-green-400">● Video</span>
        )}
      </header>

      <main className="max-w-5xl w-full mx-auto px-4 py-4 space-y-4 flex-1">

        {/* Connection Bar */}
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-dim uppercase tracking-wide shrink-0">Drone IP</label>
            <input
              type="text"
              value={droneIp}
              onChange={(e) => setDroneIp(e.target.value)}
              className="flex-1 max-w-[200px] px-3 py-1.5 rounded bg-panel border border-border text-heading text-sm font-mono focus:outline-none focus:border-accent"
              placeholder="192.168.169.1"
            />
            <button
              onClick={handleConnect}
              disabled={connecting || isConnected}
              className="px-4 py-1.5 rounded font-medium text-sm transition-colors
                bg-green-700 hover:bg-green-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
            >
              {connecting ? 'Connecting...' : 'Connect'}
            </button>
            <button
              onClick={handleDisconnect}
              disabled={!isConnected}
              className="px-4 py-1.5 rounded font-medium text-sm transition-colors
                bg-red-700 hover:bg-red-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
            >
              Disconnect
            </button>
          </div>
        </div>

        {/* Video Feed */}
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-border flex items-center justify-between">
            <span className="font-semibold text-heading text-sm">Video Feed</span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleVideoToggle}
                disabled={!isConnected}
                className={`px-3 py-1 rounded font-medium text-xs transition-colors
                  disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed ${
                  isStreaming
                    ? 'bg-orange-700 hover:bg-orange-600'
                    : 'bg-blue-700 hover:bg-blue-600'
                }`}
              >
                {isStreaming ? 'Stop Video' : 'Start Video'}
              </button>
              <button
                onClick={() => handleSwitchCamera(1)}
                disabled={!isConnected}
                className="px-3 py-1 rounded font-medium text-xs transition-colors
                  bg-purple-700 hover:bg-purple-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
              >
                Cam 1
              </button>
              <button
                onClick={() => handleSwitchCamera(2)}
                disabled={!isConnected}
                className="px-3 py-1 rounded font-medium text-xs transition-colors
                  bg-purple-700 hover:bg-purple-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
              >
                Cam 2
              </button>
            </div>
          </div>
          <div className="aspect-video bg-black flex items-center justify-center">
            {isStreaming ? (
              <DroneVideo streaming={true} className="w-full h-full" />
            ) : (
              <div className="text-dim text-center select-none">
                <div className="text-5xl mb-3 opacity-30">&#x2B1B;</div>
                <p className="text-sm">
                  {!isConnected
                    ? 'Connect to drone to enable video'
                    : 'Starting video...'}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Flight Controls */}
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold text-heading text-sm">Flight Controls</span>
            <button
              onClick={handleHeadless}
              disabled={!isConnected}
              className="px-3 py-1 rounded font-medium text-xs transition-colors
                bg-indigo-700 hover:bg-indigo-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
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

        {/* Raw Command */}
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-dim uppercase tracking-wide shrink-0">Raw Hex</label>
            <input
              type="text"
              value={rawHex}
              onChange={(e) => setRawHex(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSendRaw() }}
              className="flex-1 px-3 py-1.5 rounded bg-panel border border-border text-heading text-sm font-mono focus:outline-none focus:border-accent"
              placeholder="ef 00 04 00"
            />
            <button
              onClick={handleSendRaw}
              disabled={!isConnected || !rawHex.replace(/\s/g, '')}
              className="px-4 py-1.5 rounded font-medium text-sm transition-colors
                bg-gray-600 hover:bg-gray-500 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </div>

        {/* Status Message */}
        {message && (
          <div className="px-3 py-2 rounded bg-panel border border-border text-sm text-muted">
            {message}
          </div>
        )}
      </main>

      <footer className="px-10 pb-6 pt-2 flex flex-col items-center gap-32">

        <img src="/tyvyx_logo_1.svg" alt="TYVYX" className="h-8 md:h-10 w-auto opacity-100" />
      </footer>
    </div>
  )
}

export default App



