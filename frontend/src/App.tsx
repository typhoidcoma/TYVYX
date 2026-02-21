import { useState, useEffect } from 'react'
import { droneApi, type DroneStatus } from './services/api'
import { WifiScanner } from './components/WifiScanner'
import { DroneVideo } from './components/DroneVideo'
import { FlightControls } from './components/FlightControls'

function App() {
  const [droneIp, setDroneIp] = useState('192.168.169.1')
  const [status, setStatus] = useState<DroneStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [flightArmed, setFlightArmed] = useState(false)
  const [rawHex, setRawHex] = useState('')

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

  const withLoading = async (fn: () => Promise<{ message?: string } | void>) => {
    setLoading(true)
    setMessage('')
    try {
      const result = await fn()
      if (result && 'message' in result && result.message) setMessage(result.message)
    } catch (err) {
      setMessage(`Error: ${err instanceof Error ? err.message : String(err)}`)
    }
    setLoading(false)
  }

  const handleConnect = () => withLoading(async () => {
    return await droneApi.connect(droneIp)
  })

  const handleDisconnect = () => withLoading(async () => {
    return await droneApi.disconnect()
  })

  const handleVideoToggle = () => withLoading(async () => {
    if (status?.video_streaming) {
      await droneApi.stopVideo()
      return { message: 'Video stopped' }
    } else {
      return await droneApi.startVideo()
    }
  })

  const handleSwitchCamera = (cam: number) => withLoading(() => droneApi.switchCamera(cam))

  const handleHeadless = () => withLoading(() => droneApi.headless())

  const handleSendRaw = () => {
    const hex = rawHex.replace(/\s/g, '')
    if (!hex) return
    withLoading(() => droneApi.sendRaw(hex))
  }

  const isStreaming = !!status?.video_streaming
  const isConnected = !!status?.connected

  return (
    <div className="min-h-screen bg-base text-heading">

      {/* Header */}
      <header className="px-4 py-3 border-b border-border flex items-center gap-4">
        <img src="/tyvyx_logo_1.svg" alt="TYVYX" className="h-10 w-auto" />
        <h1 className="text-xl font-bold">Drone Controller</h1>
        <span className={`ml-auto font-mono text-sm ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
          {isConnected ? '● Connected' : '○ Disconnected'}
        </span>
        {isStreaming && (
          <span className="font-mono text-sm text-green-400">● Video</span>
        )}
      </header>

      <main className="max-w-5xl mx-auto px-4 py-4 space-y-4">

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
              disabled={loading || isConnected}
              className="px-4 py-1.5 rounded font-medium text-sm transition-colors
                bg-green-700 hover:bg-green-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
            >
              Connect
            </button>
            <button
              onClick={handleDisconnect}
              disabled={loading || !isConnected}
              className="px-4 py-1.5 rounded font-medium text-sm transition-colors
                bg-red-700 hover:bg-red-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
            >
              Disconnect
            </button>
            <div className="border-l border-border pl-3 flex-1 min-w-0">
              <WifiScanner onDroneDetected={(ip) => setDroneIp(ip)} />
            </div>
          </div>
        </div>

        {/* Video Feed */}
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-border flex items-center justify-between">
            <span className="font-semibold text-heading text-sm">Video Feed</span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleVideoToggle}
                disabled={loading || !isConnected}
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
                disabled={loading || !isConnected}
                className="px-3 py-1 rounded font-medium text-xs transition-colors
                  bg-purple-700 hover:bg-purple-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
              >
                Cam 1
              </button>
              <button
                onClick={() => handleSwitchCamera(2)}
                disabled={loading || !isConnected}
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
                    : 'Click Start Video above'}
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
              disabled={loading || !isConnected}
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
              disabled={loading || !isConnected || !rawHex.replace(/\s/g, '')}
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
    </div>
  )
}

export default App
