import { useState, useEffect } from 'react'
import { droneApi, type DroneStatus, createWebSocket } from './services/api'
import { usePositionStore } from './stores/positionStore'
import { PositionMap } from './components/PositionMap'
import { PositionIndicator } from './components/PositionIndicator'
import { TrajectoryControls } from './components/TrajectoryControls'
import { WifiScanner } from './components/WifiScanner'
import './App.css'

function App() {
  const [status, setStatus] = useState<DroneStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [videoActive, setVideoActive] = useState(false)

  const { updatePosition } = usePositionStore()

  // Poll drone status every 2 s
  useEffect(() => {
    const poll = async () => {
      try {
        setStatus(await droneApi.getStatus())
      } catch {
        // backend unreachable — leave last status
      }
    }
    const id = setInterval(poll, 2000)
    poll()
    return () => clearInterval(id)
  }, [])

  // WebSocket telemetry when connected
  useEffect(() => {
    if (!status?.connected) return
    const ws = createWebSocket((data) => {
      if (data?.data?.position) updatePosition(data.data.position)
    })
    return () => ws.close()
  }, [status?.connected, updatePosition])

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
    const r = await droneApi.connect()
    return r
  })

  const handleDisconnect = () => withLoading(async () => {
    const r = await droneApi.disconnect()
    setVideoActive(false)
    return r
  })

  const handleVideoToggle = () => withLoading(async () => {
    if (videoActive || status?.video_streaming) {
      await droneApi.stopVideo()
      setVideoActive(false)
      return { message: 'Video stopped' }
    } else {
      const r = await droneApi.startVideo()
      if (r.success) setVideoActive(true)
      return r
    }
  })

  const handleSwitchCamera = (cam: number) => withLoading(() => droneApi.switchCamera(cam))

  const isStreaming = videoActive && status?.video_streaming

  return (
    <div className="min-h-screen bg-base text-heading p-6">
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <header className="mb-6 flex items-center gap-5">
          <img src="/tyvyx_logo.svg" alt="TYVYX" className="h-14 w-auto" />
          <div>
            <h1 className="text-3xl font-bold">Drone Control</h1>
            <p className="text-muted text-sm">Phase 3: Position Tracking</p>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ── Video Feed ─────────────────────────────────────────── */}
          <div className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-heading">Video Feed</h2>
              <div className="flex items-center gap-2 text-sm">
                <span className={`font-mono ${status?.connected ? 'text-green-400' : 'text-red-400'}`}>
                  {status?.connected ? '● Connected' : '○ Disconnected'}
                </span>
                <span className="text-border">|</span>
                <span className={`font-mono ${isStreaming ? 'text-green-400' : 'text-dim'}`}>
                  {isStreaming ? '● Streaming' : '○ No feed'}
                </span>
              </div>
            </div>

            <div className="bg-black aspect-video flex items-center justify-center relative">
              {isStreaming ? (
                <img
                  src="http://localhost:8000/api/video/feed"
                  alt="Drone video feed"
                  className="w-full h-full object-contain"
                  onError={() => setVideoActive(false)}
                />
              ) : (
                <div className="text-dim text-center select-none">
                  <div className="text-5xl mb-3 opacity-30">⬛</div>
                  <p className="text-sm">
                    {!status?.connected
                      ? 'Connect to drone to enable video'
                      : 'Click Start Video in controls'}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* ── Controls ───────────────────────────────────────────── */}
          <div className="bg-card border border-border rounded-lg p-5 space-y-5">
            <h2 className="font-semibold text-heading">Controls</h2>

            {/* WiFi status */}
            <section>
              <p className="text-xs text-dim uppercase tracking-wide mb-2">WiFi</p>
              <WifiScanner />
            </section>

            {/* Connection */}
            <section>
              <p className="text-xs text-dim uppercase tracking-wide mb-2">Connection</p>
              <div className="flex gap-2">
                <button
                  onClick={handleConnect}
                  disabled={loading || !!status?.connected}
                  className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
                    bg-green-700 hover:bg-green-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
                >
                  Connect
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={loading || !status?.connected}
                  className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
                    bg-red-700 hover:bg-red-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
                >
                  Disconnect
                </button>
              </div>
            </section>

            {/* Video */}
            <section>
              <p className="text-xs text-dim uppercase tracking-wide mb-2">Video</p>
              <div className="flex gap-2">
                <button
                  onClick={handleVideoToggle}
                  disabled={loading || !status?.connected}
                  className={`flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
                    disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed ${
                    isStreaming
                      ? 'bg-orange-700 hover:bg-orange-600'
                      : 'bg-blue-700 hover:bg-blue-600'
                  }`}
                >
                  {isStreaming ? 'Stop Video' : 'Start Video'}
                </button>
              </div>
            </section>

            {/* Camera */}
            <section>
              <p className="text-xs text-dim uppercase tracking-wide mb-2">Camera</p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleSwitchCamera(1)}
                  disabled={loading || !status?.connected}
                  className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
                    bg-purple-700 hover:bg-purple-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
                >
                  Cam 1
                </button>
                <button
                  onClick={() => handleSwitchCamera(2)}
                  disabled={loading || !status?.connected}
                  className="flex-1 px-4 py-2 rounded font-medium text-sm transition-colors
                    bg-purple-700 hover:bg-purple-600 disabled:bg-panel disabled:text-dim disabled:cursor-not-allowed"
                >
                  Cam 2
                </button>
              </div>
            </section>

            {/* Status message */}
            {message && (
              <div className="px-3 py-2 rounded bg-panel border border-border text-sm text-muted">
                {message}
              </div>
            )}
          </div>
        </div>

        {/* Position Tracking */}
        <div className="mt-8">
          <h2 className="text-2xl font-bold mb-5 text-heading">Position Tracking</h2>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <div className="xl:col-span-2">
              <PositionMap width={800} height={600} />
            </div>
            <div className="space-y-6">
              <PositionIndicator />
              <TrajectoryControls />
            </div>
          </div>
        </div>

        <footer className="mt-8 text-center text-dim text-xs">
          Phase 3: Optical Flow + Kalman Filter &nbsp;·&nbsp; Next: Phase 4 SLAM
        </footer>
      </div>
    </div>
  )
}

export default App
