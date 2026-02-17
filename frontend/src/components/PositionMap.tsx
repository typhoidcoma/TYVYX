/**
 * Position Map Component
 *
 * Canvas-based 2D map visualization showing drone position and trajectory.
 */

import React, { useRef, useEffect } from 'react';
import { usePositionStore } from '../stores/positionStore';

interface PositionMapProps {
  width?: number;       // Canvas width in pixels
  height?: number;      // Canvas height in pixels
  scale?: number;       // Pixels per meter (zoom)
  gridSize?: number;    // Grid spacing in meters
  showGrid?: boolean;   // Show grid
  showTrajectory?: boolean;  // Show trajectory trail
}

export const PositionMap: React.FC<PositionMapProps> = ({
  width = 600,
  height = 600,
  scale = 50,  // 50 pixels per meter
  gridSize = 1.0,  // 1 meter grid
  showGrid = true,
  showTrajectory = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { position, velocity, trajectory, enabled } = usePositionStore();

  /**
   * Render the map
   */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Read theme colors from CSS variables (single source of truth)
    const root = document.documentElement;
    const style = getComputedStyle(root);
    const c = {
      base:    style.getPropertyValue('--color-base').trim(),
      panel:   style.getPropertyValue('--color-panel').trim(),
      dim:     style.getPropertyValue('--color-dim').trim(),
      muted:   style.getPropertyValue('--color-muted').trim(),
      heading: style.getPropertyValue('--color-heading').trim(),
    };

    // Clear canvas with theme background
    ctx.fillStyle = c.base;
    ctx.fillRect(0, 0, width, height);

    // Calculate center (origin)
    const centerX = width / 2;
    const centerY = height / 2;

    // Transform: world coordinates to canvas coordinates
    // World: X=forward, Y=right
    // Canvas: X=right, Y=down
    const worldToCanvas = (worldX: number, worldY: number): [number, number] => {
      const canvasX = centerX + worldY * scale;  // Y maps to horizontal
      const canvasY = centerY - worldX * scale;  // X maps to vertical (inverted)
      return [canvasX, canvasY];
    };

    // Draw grid
    if (showGrid) {
      ctx.strokeStyle = c.panel;
      ctx.lineWidth = 1;

      // Vertical grid lines (X axis in world)
      const gridPixels = gridSize * scale;
      for (let x = centerX % gridPixels; x < width; x += gridPixels) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }

      // Horizontal grid lines (Y axis in world)
      for (let y = centerY % gridPixels; y < height; y += gridPixels) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Draw axes (thicker)
      ctx.strokeStyle = c.dim;
      ctx.lineWidth = 2;

      // Y axis (vertical through center)
      ctx.beginPath();
      ctx.moveTo(centerX, 0);
      ctx.lineTo(centerX, height);
      ctx.stroke();

      // X axis (horizontal through center)
      ctx.beginPath();
      ctx.moveTo(0, centerY);
      ctx.lineTo(width, centerY);
      ctx.stroke();

      // Origin marker
      ctx.fillStyle = c.dim;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 4, 0, 2 * Math.PI);
      ctx.fill();

      // Axis labels
      ctx.fillStyle = c.muted;
      ctx.font = '12px sans-serif';
      ctx.fillText('Y+', centerX + 5, 15);
      ctx.fillText('X+', width - 25, centerY - 5);
    }

    // Draw trajectory trail
    if (showTrajectory && trajectory.length > 1) {
      ctx.strokeStyle = '#3b82f6';  // Blue
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      ctx.beginPath();
      const [startX, startY] = worldToCanvas(trajectory[0].x, trajectory[0].y);
      ctx.moveTo(startX, startY);

      for (let i = 1; i < trajectory.length; i++) {
        const [x, y] = worldToCanvas(trajectory[i].x, trajectory[i].y);
        ctx.lineTo(x, y);
      }

      ctx.stroke();

      // Draw trajectory points as dots
      ctx.fillStyle = '#3b82f6';
      for (const point of trajectory) {
        const [x, y] = worldToCanvas(point.x, point.y);
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, 2 * Math.PI);
        ctx.fill();
      }
    }

    // Draw current position
    const [droneX, droneY] = worldToCanvas(position.x, position.y);

    // Drone circle
    ctx.fillStyle = enabled ? '#10b981' : c.dim;
    ctx.beginPath();
    ctx.arc(droneX, droneY, 12, 0, 2 * Math.PI);
    ctx.fill();

    // Drone border
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Velocity vector (heading indicator)
    if (enabled) {
      const speed = Math.sqrt(velocity.vx ** 2 + velocity.vy ** 2);

      if (speed > 0.05) {  // Only show if moving
        // Calculate heading angle
        const heading = Math.atan2(velocity.vy, velocity.vx);

        // Draw arrow
        const arrowLength = Math.min(speed * scale * 2, 50);  // Scale with speed, max 50px
        const arrowEndX = droneX + Math.cos(heading) * arrowLength;
        const arrowEndY = droneY - Math.sin(heading) * arrowLength;  // Canvas Y is inverted

        ctx.strokeStyle = '#10b981';
        ctx.fillStyle = '#10b981';
        ctx.lineWidth = 2;

        // Arrow line
        ctx.beginPath();
        ctx.moveTo(droneX, droneY);
        ctx.lineTo(arrowEndX, arrowEndY);
        ctx.stroke();

        // Arrow head
        const headLength = 8;
        const headAngle = Math.PI / 6;

        ctx.beginPath();
        ctx.moveTo(arrowEndX, arrowEndY);
        ctx.lineTo(
          arrowEndX - headLength * Math.cos(heading - headAngle),
          arrowEndY + headLength * Math.sin(heading - headAngle)
        );
        ctx.lineTo(
          arrowEndX - headLength * Math.cos(heading + headAngle),
          arrowEndY + headLength * Math.sin(heading + headAngle)
        );
        ctx.closePath();
        ctx.fill();
      }
    }

    // Draw position coordinates
    ctx.fillStyle = c.heading;
    ctx.font = '14px monospace';
    ctx.fillText(
      `Position: (${position.x.toFixed(2)}, ${position.y.toFixed(2)}) m`,
      10,
      height - 10
    );

  }, [position, velocity, trajectory, enabled, width, height, scale, gridSize, showGrid, showTrajectory]);

  return (
    <div className="border-2 border-border rounded-lg overflow-hidden shadow-lg">
      <div className="bg-card px-4 py-2 border-b border-divider">
        <h3 className="text-lg font-semibold text-heading">Position Map</h3>
        <p className="text-sm text-muted">
          {enabled ? '🟢 Tracking Active' : '⚪ Tracking Inactive'}
        </p>
      </div>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="bg-base"
      />
    </div>
  );
};
