import { useEffect, useRef, useState, useCallback } from 'react'

interface Position3DBoxProps {
  x: number
  y: number
  z: number
  boundsX?: [number, number]
  boundsY?: [number, number]
  boundsZ?: [number, number]
}

interface TrailPoint { x: number; y: number; z: number }

const MAX_TRAIL = 500
const MIN_MOVE = 0.002 // 2mm

// Sensitivity constants
const ORBIT_SPEED = 0.005    // rad/px
const PAN_SPEED = 1.0        // px/px
const ZOOM_FACTOR = 0.0008   // per scroll delta unit

// Default camera
const DEFAULT_AZIMUTH = 0.6    // ~34deg right
const DEFAULT_ELEVATION = -0.5 // ~29deg looking down
const DEFAULT_ZOOM = 1.0

/**
 * Turntable rotation: Z-up convention.
 * 1. Azimuth: rotate around world Z axis (spin the scene)
 * 2. Elevation: tilt around the camera-local X axis (look up/down)
 *
 * This keeps the Z axis (up) always projecting vertically on screen,
 * so the ground floor stays level no matter how you orbit.
 */
function rotate(
  px: number, py: number, pz: number,
  elevation: number, azimuth: number
): [number, number, number] {
  // 1. Azimuth — rotate XY around Z
  const cosA = Math.cos(azimuth), sinA = Math.sin(azimuth)
  const x1 = px * cosA - py * sinA
  const y1 = px * sinA + py * cosA
  // z1 = pz (Z unchanged by azimuth)

  // 2. Elevation — tilt YZ around X
  const cosE = Math.cos(elevation), sinE = Math.sin(elevation)
  const y2 = y1 * cosE - pz * sinE
  const z2 = y1 * sinE + pz * cosE
  // x2 = x1 (X unchanged by elevation)

  return [x1, y2, z2]
}

/** Project rotated 3D point to 2D (orthographic).
 *  Screen X = rotated X, Screen Y = -rotated Z (Z-up → screen-up) */
function project(
  x: number, y: number, z: number,
  cx: number, cy: number, scale: number,
  elevation: number, azimuth: number
): [number, number] {
  const [rx, , rz] = rotate(x, y, z, elevation, azimuth)
  return [cx + rx * scale, cy - rz * scale]
}

export function Position3DBox({
  x, y, z,
  boundsX = [-1, 1],
  boundsY = [-1, 1],
  boundsZ = [0, 1.5],
}: Position3DBoxProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const trailRef = useRef<TrailPoint[]>([])

  // Measured size from container
  const [size, setSize] = useState({ width: 480, height: 300 })

  // Camera state (turntable)
  const [azimuth, setAzimuth] = useState(DEFAULT_AZIMUTH)
  const [elevation, setElevation] = useState(DEFAULT_ELEVATION)
  const [zoom, setZoom] = useState(DEFAULT_ZOOM)
  const [panX, setPanX] = useState(0)
  const [panY, setPanY] = useState(0)

  // Interaction refs
  const dragMode = useRef<'none' | 'orbit' | 'pan'>('none')
  const lastMouse = useRef({ x: 0, y: 0 })

  // Auto-size to container
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const w = entry.contentRect.width
        if (w > 0) setSize({ width: w, height: Math.round(w * 0.6) })
      }
    })
    ro.observe(container)
    const w = container.clientWidth
    if (w > 0) setSize({ width: w, height: Math.round(w * 0.6) })
    return () => ro.disconnect()
  }, [])

  const { width, height } = size

  // Accumulate trail points
  useEffect(() => {
    const trail = trailRef.current
    const last = trail.length > 0 ? trail[trail.length - 1] : null
    if (!last || Math.hypot(x - last.x, y - last.y, z - last.z) >= MIN_MOVE) {
      trail.push({ x, y, z })
      if (trail.length > MAX_TRAIL) trail.shift()
    }
  }, [x, y, z])

  // Mouse down: determine orbit vs pan
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    lastMouse.current = { x: e.clientX, y: e.clientY }
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      dragMode.current = 'pan'
    } else if (e.button === 0) {
      dragMode.current = 'orbit'
    }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (dragMode.current === 'none') return
    const dx = e.clientX - lastMouse.current.x
    const dy = e.clientY - lastMouse.current.y
    lastMouse.current = { x: e.clientX, y: e.clientY }

    if (dragMode.current === 'orbit') {
      setAzimuth(a => a + dx * ORBIT_SPEED)
      // Clamp elevation: -85deg to -5deg (always looking down)
      setElevation(e => Math.max(-Math.PI * 0.47, Math.min(-0.05, e + dy * ORBIT_SPEED)))
    } else if (dragMode.current === 'pan') {
      setPanX(p => p + dx * PAN_SPEED)
      setPanY(p => p + dy * PAN_SPEED)
    }
  }, [])

  const handleMouseUp = useCallback(() => {
    dragMode.current = 'none'
  }, [])

  // Double-click: reset view
  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setAzimuth(DEFAULT_AZIMUTH)
    setElevation(DEFAULT_ELEVATION)
    setZoom(DEFAULT_ZOOM)
    setPanX(0)
    setPanY(0)
  }, [])

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
  }, [])

  // Native wheel listener with { passive: false }
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const factor = 1 - e.deltaY * ZOOM_FACTOR
      setZoom(z => Math.max(0.3, Math.min(5.0, z * factor)))
    }
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [])

  // Draw
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)

    const cx = width * 0.5 + panX
    const cy = height * 0.5 + panY
    const rangeX = boundsX[1] - boundsX[0]
    const rangeY = boundsY[1] - boundsY[0]
    const rangeZ = boundsZ[1] - boundsZ[0]
    const maxRange = Math.max(rangeX, rangeY, rangeZ * 1.5)
    const baseScale = Math.min(width, height) * 0.32 / Math.max(maxRange * 0.5, 1)
    const scale = baseScale * zoom

    // Pivot = 3D center of bounding box
    const midX = (boundsX[0] + boundsX[1]) / 2
    const midY = (boundsY[0] + boundsY[1]) / 2
    const midZ = (boundsZ[0] + boundsZ[1]) / 2

    const p = (bx: number, by: number, bz: number) =>
      project(bx - midX, by - midY, bz - midZ, cx, cy, scale, elevation, azimuth)

    const [x0, x1] = boundsX
    const [y0, y1] = boundsY
    const [z0, z1] = boundsZ

    const drawLine = (a: [number, number], b: [number, number]) => {
      ctx.beginPath()
      ctx.moveTo(a[0], a[1])
      ctx.lineTo(b[0], b[1])
      ctx.stroke()
    }

    // Box edges with depth-based opacity
    const corners: [number, number, number][] = [
      [x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
      [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1],
    ]
    const edges: [number,number][] = [
      [0,1],[1,2],[2,3],[3,0],
      [4,5],[5,6],[6,7],[7,4],
      [0,4],[1,5],[2,6],[3,7],
    ]

    ctx.lineWidth = 1
    for (const [ai, bi] of edges) {
      const ac = corners[ai], bc = corners[bi]
      const mx = (ac[0]+bc[0])/2-midX, my = (ac[1]+bc[1])/2-midY, mz = (ac[2]+bc[2])/2-midZ
      const [,ry] = rotate(mx, my, mz, elevation, azimuth)
      // ry = depth into screen: more negative = further away
      const depthNorm = (ry + maxRange) / (2 * maxRange)
      const alpha = 0.15 + 0.35 * Math.max(0, Math.min(1, depthNorm))
      ctx.strokeStyle = `rgba(100, 180, 220, ${alpha.toFixed(2)})`
      drawLine(p(ac[0],ac[1],ac[2]), p(bc[0],bc[1],bc[2]))
    }

    // Ground grid — 10cm
    ctx.strokeStyle = 'rgba(100, 120, 140, 0.10)'
    ctx.setLineDash([2, 4])
    const gridStep = 0.1
    for (let gx = x0 + gridStep; gx < x1 - 0.001; gx += gridStep) {
      drawLine(p(gx, y0, z0), p(gx, y1, z0))
    }
    for (let gy = y0 + gridStep; gy < y1 - 0.001; gy += gridStep) {
      drawLine(p(x0, gy, z0), p(x1, gy, z0))
    }
    ctx.setLineDash([])

    // 50cm grid (bolder)
    ctx.strokeStyle = 'rgba(100, 120, 140, 0.20)'
    const gridStep50 = 0.5
    for (let gx = x0 + gridStep50; gx < x1 - 0.001; gx += gridStep50) {
      drawLine(p(gx, y0, z0), p(gx, y1, z0))
    }
    for (let gy = y0 + gridStep50; gy < y1 - 0.001; gy += gridStep50) {
      drawLine(p(x0, gy, z0), p(x1, gy, z0))
    }

    // Origin crosshair on ground
    ctx.strokeStyle = 'rgba(16, 185, 129, 0.5)'
    ctx.lineWidth = 1.5
    const cs = 0.05
    drawLine(p(-cs, 0, z0), p(cs, 0, z0))
    drawLine(p(0, -cs, z0), p(0, cs, z0))
    ctx.lineWidth = 1

    // Trail
    const trail = trailRef.current
    if (trail.length >= 2) {
      for (let i = 1; i < trail.length; i++) {
        const alpha = (i / trail.length) * 0.8
        const tp = trail[i - 1], tc = trail[i]
        ctx.strokeStyle = `rgba(6, 182, 212, ${alpha.toFixed(2)})`
        ctx.lineWidth = 1.5
        drawLine(p(tp.x, tp.y, tp.z), p(tc.x, tc.y, tc.z))
      }
      // Ground shadow trail
      for (let i = 1; i < trail.length; i++) {
        const alpha = (i / trail.length) * 0.12
        const tp = trail[i - 1], tc = trail[i]
        ctx.strokeStyle = `rgba(6, 182, 212, ${alpha.toFixed(2)})`
        ctx.lineWidth = 1
        drawLine(p(tp.x, tp.y, z0), p(tc.x, tc.y, z0))
      }
    }

    // Drop line
    const droneX = Math.max(x0, Math.min(x1, x))
    const droneY = Math.max(y0, Math.min(y1, y))
    const droneZ = Math.max(z0, Math.min(z1, z))

    ctx.strokeStyle = 'rgba(6, 182, 212, 0.25)'
    ctx.setLineDash([2, 3])
    drawLine(p(droneX, droneY, z0), p(droneX, droneY, droneZ))
    ctx.setLineDash([])

    // Ground shadow dot
    const [gsx, gsy] = p(droneX, droneY, z0)
    ctx.fillStyle = 'rgba(6, 182, 212, 0.2)'
    ctx.beginPath()
    ctx.arc(gsx, gsy, 3, 0, Math.PI * 2)
    ctx.fill()

    // Drone dot
    const [dx, dy] = p(droneX, droneY, droneZ)
    ctx.fillStyle = 'rgba(6, 182, 212, 0.3)'
    ctx.beginPath()
    ctx.arc(dx, dy, 10, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#06b6d4'
    ctx.beginPath()
    ctx.arc(dx, dy, 5, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#fff'
    ctx.beginPath()
    ctx.arc(dx, dy, 2, 0, Math.PI * 2)
    ctx.fill()

    // Axis arrows & labels at origin (ground level)
    const arrowLen = 0.15
    ctx.font = '10px monospace'
    ctx.lineWidth = 1.5

    ctx.strokeStyle = 'rgba(239, 68, 68, 0.6)'
    ctx.fillStyle = 'rgba(239, 68, 68, 0.7)'
    drawLine(p(0, 0, z0), p(arrowLen, 0, z0))
    const [xlx, xly] = p(arrowLen + 0.03, 0, z0)
    ctx.fillText('X', xlx, xly)

    ctx.strokeStyle = 'rgba(34, 197, 94, 0.6)'
    ctx.fillStyle = 'rgba(34, 197, 94, 0.7)'
    drawLine(p(0, 0, z0), p(0, arrowLen, z0))
    const [ylx, yly] = p(0, arrowLen + 0.03, z0)
    ctx.fillText('Y', ylx, yly)

    ctx.strokeStyle = 'rgba(59, 130, 246, 0.6)'
    ctx.fillStyle = 'rgba(59, 130, 246, 0.7)'
    drawLine(p(0, 0, z0), p(0, 0, z0 + arrowLen))
    const [zlx, zly] = p(0, 0, z0 + arrowLen + 0.03)
    ctx.fillText('Z', zlx, zly)

    ctx.lineWidth = 1

    // Position label (cm)
    ctx.font = '11px monospace'
    ctx.fillStyle = 'rgba(6, 182, 212, 0.9)'
    ctx.fillText(
      `(${(x*100).toFixed(1)}, ${(y*100).toFixed(1)}, ${(z*100).toFixed(1)}) cm`,
      dx + 12, dy - 6
    )

    // Controls hint
    ctx.font = '9px monospace'
    ctx.fillStyle = 'rgba(148, 163, 184, 0.35)'
    ctx.fillText(`${zoom.toFixed(1)}x`, 6, height - 18)
    ctx.fillText('drag:orbit  shift:pan  scroll:zoom  dbl:reset', 6, height - 6)

  }, [x, y, z, boundsX, boundsY, boundsZ, width, height, elevation, azimuth, zoom, panX, panY])

  const getCursor = () => {
    if (dragMode.current === 'orbit') return 'grabbing'
    if (dragMode.current === 'pan') return 'move'
    return 'grab'
  }

  return (
    <div ref={containerRef} className="w-full">
      <canvas
        ref={canvasRef}
        style={{ width, height, cursor: getCursor() }}
        className="block w-full"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onDoubleClick={handleDoubleClick}
        onContextMenu={handleContextMenu}
      />
    </div>
  )
}
