import { useState, useEffect } from 'react'
import { droneApi, DroneStatus, createWebSocket } from './services/api'
import { usePositionStore } from './stores/positionStore'
import { PositionMap } from './components/PositionMap'
import { PositionIndicator } from './components/PositionIndicator'
import { TrajectoryControls } from './components/TrajectoryControls'
import './App.css'

function App() {
  const [status, setStatus] = useState<DroneStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [videoStarted, setVideoStarted] = useState(false)

  // Position store (Phase 3)
  const { updatePosition } = usePositionStore()

  // Poll status
  useEffect(() => {
    const pollStatus = async () => {
      try {
        const statusData = await droneApi.getStatus()
        setStatus(statusData)
      } catch (error) {
        console.error('Error polling status:', error)
      }
    }

    // Poll every 2 seconds
    const interval = setInterval(pollStatus, 2000)
    pollStatus() // Initial poll

    return () => clearInterval(interval)
  }, [])

  // WebSocket for telemetry
  useEffect(() => {
    let ws: WebSocket | null = null

    if (status?.connected) {
      ws = createWebSocket((data) => {
        console.log('Telemetry:', data)

        // Update position store if position data is present (Phase 3)
        // WebSocket message structure: { type: "telemetry", data: { ..., position: ... } }
        if (data?.data?.position) {
          updatePosition(data.data.position)
        }
      })
    }

    return () => {
      if (ws) {
        ws.close()
      }
    }
  }, [status?.connected, updatePosition])

  const handleConnect = async () => {
    setLoading(true)
    setMessage('')
    try {
      const result = await droneApi.connect()
      setMessage(result.message)
    } catch (error: any) {
      setMessage(`Error: ${error.message}`)
    }
    setLoading(false)
  }

  const handleDisconnect = async () => {
    setLoading(true)
    setMessage('')
    try {
      const result = await droneApi.disconnect()
      setMessage(result.message)
      setVideoStarted(false)
    } catch (error: any) {
      setMessage(`Error: ${error.message}`)
    }
    setLoading(false)
  }

  const handleStartVideo = async () => {
    setLoading(true)
    setMessage('')
    try {
      const result = await droneApi.startVideo()
      setMessage(result.message)
      if (result.success) {
        setVideoStarted(true)
      }
    } catch (error: any) {
      setMessage(`Error: ${error.message}`)
    }
    setLoading(false)
  }

  const handleStopVideo = async () => {
    setLoading(true)
    setMessage('')
    try {
      const result = await droneApi.stopVideo()
      setMessage(result.message)
      setVideoStarted(false)
    } catch (error: any) {
      setMessage(`Error: ${error.message}`)
    }
    setLoading(false)
  }

  const handleSwitchCamera = async (camera: number) => {
    setLoading(true)
    setMessage('')
    try {
      const result = await droneApi.switchCamera(camera)
      setMessage(result.message)
    } catch (error: any) {
      setMessage(`Error: ${error.message}`)
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-4xl font-bold mb-2">🚁 TEKY Drone Control</h1>
          <p className="text-gray-400">Phase 3: Position Tracking with Optical Flow</p>
        </header>

        {/* Status Bar */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-gray-400 mr-2">Status:</span>
              <span className={`font-semibold ${status?.connected ? 'text-green-400' : 'text-red-400'}`}>
                {status?.connected ? '● Connected' : '○ Disconnected'}
              </span>
            </div>
            <div>
              <span className="text-gray-400 mr-2">Video:</span>
              <span className={`font-semibold ${status?.video_streaming ? 'text-green-400' : 'text-gray-500'}`}>
                {status?.video_streaming ? '● Streaming' : '○ Stopped'}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Video Feed */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-2xl font-bold mb-4">Video Feed</h2>
            <div className="bg-black rounded-lg aspect-video flex items-center justify-center">
              {videoStarted && status?.video_streaming ? (
                <img
                  src="http://localhost:8000/api/video/feed"
                  alt="Drone video feed"
                  className="w-full h-full object-contain rounded-lg"
                />
              ) : (
                <div className="text-gray-500 text-center">
                  <div className="text-6xl mb-4">📹</div>
                  <p>Video feed not available</p>
                  <p className="text-sm mt-2">Connect and start video</p>
                </div>
              )}
            </div>
          </div>

          {/* Controls */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-2xl font-bold mb-4">Controls</h2>

            {/* Connection Controls */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3 text-gray-300">Connection</h3>
              <div className="flex gap-3">
                <button
                  onClick={handleConnect}
                  disabled={loading || status?.connected}
                  className="flex-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-semibold transition-colors"
                >
                  Connect
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={loading || !status?.connected}
                  className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-semibold transition-colors"
                >
                  Disconnect
                </button>
              </div>
            </div>

            {/* Video Controls */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3 text-gray-300">Video</h3>
              <div className="flex gap-3">
                <button
                  onClick={handleStartVideo}
                  disabled={loading || !status?.connected || status?.video_streaming}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-semibold transition-colors"
                >
                  Start Video
                </button>
                <button
                  onClick={handleStopVideo}
                  disabled={loading || !status?.video_streaming}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-semibold transition-colors"
                >
                  Stop Video
                </button>
              </div>
            </div>

            {/* Camera Controls */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3 text-gray-300">Camera</h3>
              <div className="flex gap-3">
                <button
                  onClick={() => handleSwitchCamera(1)}
                  disabled={loading || !status?.connected}
                  className="flex-1 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-semibold transition-colors"
                >
                  Camera 1
                </button>
                <button
                  onClick={() => handleSwitchCamera(2)}
                  disabled={loading || !status?.connected}
                  className="flex-1 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded-lg font-semibold transition-colors"
                >
                  Camera 2
                </button>
              </div>
            </div>

            {/* Status Message */}
            {message && (
              <div className="mt-6 p-4 bg-gray-700 rounded-lg">
                <p className="text-sm">{message}</p>
              </div>
            )}
          </div>
        </div>

        {/* Position Tracking (Phase 3) */}
        <div className="mt-8">
          <h2 className="text-3xl font-bold mb-6 text-white">Position Tracking</h2>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            {/* Position Map */}
            <div className="xl:col-span-2">
              <PositionMap width={800} height={600} />
            </div>

            {/* Position Info and Controls */}
            <div className="space-y-6">
              <PositionIndicator />
              <TrajectoryControls />
            </div>
          </div>
        </div>

        {/* Info Footer */}
        <footer className="mt-8 text-center text-gray-500 text-sm">
          <p>Phase 3: Position Tracking • Optical Flow + Kalman Filter</p>
          <p className="mt-1">Next: Phase 4 - SLAM Integration</p>
        </footer>
      </div>
    </div>
  )
}

export default App
