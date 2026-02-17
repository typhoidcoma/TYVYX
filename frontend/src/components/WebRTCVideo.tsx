import { useState, useRef, useEffect, useCallback } from 'react'

const API_BASE = 'http://localhost:8000'

type Transport = 'connecting' | 'webrtc' | 'mjpeg'

interface Props {
  streaming: boolean
  className?: string
}

export function WebRTCVideo({ streaming, className = '' }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const [transport, setTransport] = useState<Transport>('connecting')

  const cleanup = useCallback(() => {
    if (pcRef.current) {
      pcRef.current.close()
      pcRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }, [])

  const startWebRTC = useCallback(async () => {
    cleanup()
    setTransport('connecting')

    try {
      // Check if go2rtc is available
      const caps = await fetch(`${API_BASE}/api/video/capabilities`).then(r => r.json())

      if (!caps.webrtc || !caps.streaming) {
        setTransport(caps.streaming ? 'mjpeg' : 'connecting')
        return
      }

      // Create peer connection (LAN only — no STUN needed, go2rtc uses ICE-lite)
      const pc = new RTCPeerConnection({ iceServers: [] })
      pcRef.current = pc

      // Receive-only video
      pc.addTransceiver('video', { direction: 'recvonly' })

      // Attach incoming stream to <video>
      pc.ontrack = (e) => {
        if (videoRef.current && e.streams[0]) {
          videoRef.current.srcObject = e.streams[0]
        }
      }

      // Fall back to MJPEG if WebRTC connection fails
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
          cleanup()
          setTransport('mjpeg')
        }
      }

      // Create offer and wait for ICE gathering (trickle-less)
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)

      await new Promise<void>((resolve) => {
        if (pc.iceGatheringState === 'complete') return resolve()
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === 'complete') resolve()
        }
        setTimeout(resolve, 3000) // LAN gathering is near-instant
      })

      // Send offer to backend → go2rtc → get answer
      const resp = await fetch(`${API_BASE}/api/video/webrtc/offer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: pc.localDescription!.sdp,
      })

      if (!resp.ok) throw new Error(`Signaling failed: ${resp.status}`)

      const sdpAnswer = await resp.text()
      await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: sdpAnswer }))

      setTransport('webrtc')
    } catch (err) {
      console.warn('WebRTC failed, falling back to MJPEG:', err)
      cleanup()
      setTransport('mjpeg')
    }
  }, [cleanup])

  useEffect(() => {
    if (streaming) {
      startWebRTC()
    } else {
      cleanup()
      setTransport('connecting')
    }
    return cleanup
  }, [streaming, startWebRTC, cleanup])

  if (!streaming) return null

  return (
    <div className={`relative ${className}`}>
      {/* WebRTC: native <video> with H.264 passthrough */}
      {transport === 'webrtc' && (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full h-full object-contain"
        />
      )}

      {/* MJPEG fallback */}
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
        {transport === 'webrtc' && <span className="text-green-400">WebRTC</span>}
        {transport === 'mjpeg' && <span className="text-orange-400">MJPEG</span>}
      </span>
    </div>
  )
}
