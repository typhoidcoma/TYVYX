# WiFi-Augmented Drone 3D Sensing System — Implementation Guide

> **Purpose**: This document is a technical reference for implementing a low-cost indoor 3D sensing and positioning system using a WiFi drone with a single camera, ESP32 ground anchors, and a gaming laptop as the compute platform. Feed this document to Claude when working in this repo so it has full architectural context.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GAMING LAPTOP (Ground Station)               │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ WiFi Position │  │ Visual SLAM  │  │  Monocular Depth          │ │
│  │ Engine        │  │ (ORB-SLAM3   │  │  (Depth Anything V2)      │ │
│  │ (CSI/RSSI     │  │  or DPVO)    │  │                           │ │
│  │  trilateration)│  │              │  │                           │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────────┘ │
│         │                 │                       │                 │
│         └────────┬────────┴───────────┬───────────┘                 │
│                  ▼                    ▼                              │
│         ┌──────────────┐    ┌──────────────────┐                    │
│         │ Sensor Fusion │    │ Dense 3D Recon   │                    │
│         │ (EKF / GTSAM) │    │ (Open3D / PCL)   │                    │
│         └──────┬───────┘    └────────┬─────────┘                    │
│                │                     │                              │
│                ▼                     ▼                              │
│         ┌──────────────────────────────────┐                        │
│         │ Unified 3D Map + Drone Pose      │                        │
│         │ (Optional: 3D Gaussian Splatting) │                        │
│         └──────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
         ▲              ▲                ▲
         │ CSI/RSSI     │ Video Stream   │ CSI between
         │ from drone   │ (H.264/MJPEG)  │ anchor pairs
         │              │                │
    ┌────┴────┐    ┌────┴────┐     ┌─────┴──────┐
    │ ESP32   │    │  DRONE  │     │ ESP32      │
    │ Anchors │    │ (WiFi + │     │ Anchor Mesh│
    │ (4-6x)  │    │ Camera) │     │ (inter-    │
    │         │    │         │     │  anchor    │
    │         │    │         │     │  sensing)  │
    └─────────┘    └─────────┘     └────────────┘
```

### Data Flow Summary

| Source | Data Type | Rate | Destination |
|--------|-----------|------|-------------|
| Drone camera | H.264/MJPEG video | 30 fps | Laptop: Visual SLAM + Depth |
| Drone WiFi radio | WiFi packets (probe/data) | Continuous | ESP32 anchors: CSI/RSSI capture |
| ESP32 anchors | CSI amplitude + phase per subcarrier | 10-100 Hz per anchor | Laptop: WiFi positioning engine |
| ESP32 anchor mesh | Inter-anchor CSI (environment sensing) | 10-50 Hz | Laptop: occupancy/obstacle map |
| Laptop fusion output | Drone 6DoF pose + 3D map | Real-time | Visualization / autonomy |

---

## 2. Hardware Setup

### 2.1 ESP32 Ground Anchors

**Recommended board**: ESP32-S3-DevKitC-1 (has WiFi + BLE, sufficient antenna, ~$8 each)

**Quantity**: 4 minimum, 6 recommended for good 3D coverage

**Placement strategy**:
- NOT all at the same height — vary Z positions for 3D resolution
- At least one anchor elevated (ceiling mount, high shelf) for vertical discrimination
- Space them to provide overlapping coverage of the flight volume
- Aim for the drone to always be in range of at least 3-4 anchors simultaneously
- Avoid co-planar placement (all anchors in a plane gives poor depth along the normal)

**Example layout for a 10m × 8m × 3m room**:
```
Anchor 0: (0, 0, 0.3)      — floor level, corner A
Anchor 1: (10, 0, 2.8)     — ceiling level, corner B
Anchor 2: (0, 8, 1.5)      — mid-height, corner C
Anchor 3: (10, 8, 0.3)     — floor level, corner D
Anchor 4: (5, 0, 2.8)      — ceiling, midpoint wall
Anchor 5: (5, 8, 1.5)      — mid-height, midpoint opposite wall
```

**Anchor coordinate system**: Define a world coordinate frame. Measure anchor positions in meters from an origin. Record these precisely — position accuracy of anchors directly limits tracking accuracy.

### 2.2 Drone

**Budget option**: DJI Tello EDU (~$130)
- 720p camera, 5MP photos
- WiFi 802.11n
- Python SDK available (`djitellopy`)
- SDK gives access to video stream, flight commands, IMU data
- Limitation: proprietary WiFi chip, CSI extraction not straightforward

**DIY option**: Custom build with flight controller + ESP32-CAM
- Full control over the WiFi radio (CSI extraction possible)
- ESP32-CAM provides both WiFi and camera in one board
- More work but more capability
- Consider Betaflight/iNav compatible FC + ESP32 as companion computer

**Key requirement**: The drone must transmit WiFi packets that the ground anchors can receive. Any WiFi drone does this inherently (video stream, telemetry, probe requests).

### 2.3 Gaming Laptop Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA RTX 3060 (6GB VRAM) | RTX 4070+ (8GB+ VRAM) |
| RAM | 16 GB | 32 GB |
| CPU | 6-core modern | 8-core+ |
| Storage | SSD, 50GB free | NVMe SSD |
| WiFi | Any (for ESP32 comms) | WiFi 6 for lower latency |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

**NVIDIA drivers + CUDA**: Required for GPU inference. Install CUDA 11.8 or 12.x with cuDNN.

---

## 3. Software Stack

### 3.1 Core Dependencies

```bash
# System packages
sudo apt update && sudo apt install -y \
    build-essential cmake git wget curl \
    python3-pip python3-venv \
    libopencv-dev libpcl-dev \
    libgtsam-dev \
    ffmpeg

# Python environment
python3 -m venv venv
source venv/bin/activate

# Core Python packages
pip install numpy scipy opencv-python-headless matplotlib
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install open3d
pip install pyserial  # ESP32 serial communication
pip install paho-mqtt  # MQTT for anchor data collection

# Drone SDK (if using Tello)
pip install djitellopy

# Optional but recommended
pip install rerun-sdk  # Excellent real-time 3D visualization
pip install gtsam      # Factor graph fusion (Python bindings)
```

### 3.2 Recommended Project Structure

```
wifi-drone-3d/
├── README.md
├── ARCHITECTURE.md          ← (this document)
├── requirements.txt
├── config/
│   ├── anchors.yaml         # Anchor positions and IDs
│   ├── camera.yaml          # Camera intrinsics
│   └── system.yaml          # System-wide parameters
├── firmware/
│   ├── esp32_anchor/        # ESP32 anchor firmware (ESP-IDF or Arduino)
│   │   ├── main/
│   │   │   └── csi_anchor.c
│   │   └── CMakeLists.txt
│   └── README.md
├── src/
│   ├── __init__.py
│   ├── wifi_positioning/
│   │   ├── __init__.py
│   │   ├── csi_collector.py     # Collects CSI from ESP32 anchors
│   │   ├── rssi_collector.py    # Fallback RSSI collection
│   │   ├── trilateration.py     # 3D position from ranges
│   │   ├── csi_processor.py     # CSI → AoA/ToF extraction
│   │   └── wifi_localizer.py    # Main WiFi positioning class
│   ├── visual_slam/
│   │   ├── __init__.py
│   │   ├── video_capture.py     # Drone video stream capture
│   │   ├── orb_slam_wrapper.py  # ORB-SLAM3 Python wrapper
│   │   ├── dpvo_wrapper.py      # DPVO alternative
│   │   └── visual_odometry.py   # Lightweight VO fallback
│   ├── depth_estimation/
│   │   ├── __init__.py
│   │   ├── depth_anything.py    # Depth Anything V2 inference
│   │   └── depth_to_pointcloud.py  # Depth map → 3D points
│   ├── fusion/
│   │   ├── __init__.py
│   │   ├── ekf_fusion.py        # Extended Kalman Filter
│   │   ├── gtsam_fusion.py      # Factor graph fusion
│   │   └── pose_graph.py        # Pose graph optimization
│   ├── reconstruction/
│   │   ├── __init__.py
│   │   ├── pointcloud_accumulator.py  # Incremental 3D map
│   │   ├── tsdf_volume.py       # TSDF-based reconstruction
│   │   └── gaussian_splatting.py # Post-flight 3DGS
│   ├── wifi_sensing/
│   │   ├── __init__.py
│   │   ├── environment_map.py   # WiFi occupancy sensing
│   │   └── csi_anomaly.py       # Detect obstacles via CSI changes
│   ├── drone_interface/
│   │   ├── __init__.py
│   │   ├── tello_driver.py      # Tello-specific driver
│   │   └── generic_driver.py    # Generic drone interface
│   └── visualization/
│       ├── __init__.py
│       ├── rerun_viz.py         # Rerun-based 3D visualization
│       └── opencv_viz.py        # Simple 2D overlay visualization
├── scripts/
│   ├── calibrate_anchors.py     # Anchor position calibration
│   ├── calibrate_camera.py      # Camera intrinsic calibration
│   ├── run_system.py            # Main entry point
│   ├── record_flight.py         # Record all data for offline processing
│   └── replay_flight.py         # Replay recorded data
└── tests/
    ├── test_trilateration.py
    ├── test_csi_processor.py
    └── test_fusion.py
```

---

## 4. ESP32 Anchor Firmware

### 4.1 CSI Extraction (Preferred — Higher Accuracy)

Uses Espressif's official `esp-csi` component. Each anchor listens for WiFi packets from the drone and extracts per-subcarrier CSI data.

**Setup**:
```bash
# Install ESP-IDF v5.x
# https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/

# Clone ESP-CSI component
git clone https://github.com/espressif/esp-csi.git
```

**Anchor firmware concept** (ESP-IDF, C):

```c
// firmware/esp32_anchor/main/csi_anchor.c
// 
// Each anchor:
// 1. Connects to the same WiFi network as the drone (or runs in promiscuous mode)
// 2. Captures CSI from packets transmitted by the drone
// 3. Sends CSI data + metadata to laptop via UDP or serial

#include <stdio.h>
#include <string.h>
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "lwip/sockets.h"

#define ANCHOR_ID           0          // Unique per anchor (0-5)
#define LAPTOP_IP           "192.168.4.100"
#define LAPTOP_PORT         5000
#define DRONE_MAC           {0xXX, 0xXX, 0xXX, 0xXX, 0xXX, 0xXX}  // Set to drone's MAC

static const char *TAG = "csi_anchor";
static int udp_sock = -1;

// CSI callback — fired for every received WiFi frame with CSI
static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) return;
    
    // Optional: filter to only process packets from the drone's MAC
    // Compare info->mac with DRONE_MAC
    
    // Build packet: [anchor_id(1) | timestamp(8) | rssi(1) | len(2) | csi_data(N)]
    uint8_t packet[1500];
    int offset = 0;
    
    packet[offset++] = ANCHOR_ID;
    
    int64_t timestamp = esp_timer_get_time();  // microseconds
    memcpy(&packet[offset], &timestamp, 8);
    offset += 8;
    
    packet[offset++] = info->rx_ctrl.rssi;
    
    uint16_t csi_len = info->len;
    memcpy(&packet[offset], &csi_len, 2);
    offset += 2;
    
    // CSI data: array of int8 pairs [real, imag] for each subcarrier
    // For 802.11n HT20: 56 subcarriers × 2 (I/Q) = 112 bytes
    // For 802.11n HT40: 114 subcarriers × 2 (I/Q) = 228 bytes
    memcpy(&packet[offset], info->buf, csi_len);
    offset += csi_len;
    
    // Send to laptop via UDP
    struct sockaddr_in dest;
    dest.sin_family = AF_INET;
    dest.sin_port = htons(LAPTOP_PORT);
    inet_pton(AF_INET, LAPTOP_IP, &dest.sin_addr);
    
    sendto(udp_sock, packet, offset, 0,
           (struct sockaddr *)&dest, sizeof(dest));
}

void app_main(void) {
    // Initialize NVS, WiFi, network
    nvs_flash_init();
    esp_netif_init();
    esp_event_loop_create_default();
    
    // Configure WiFi in station mode and connect to network
    // ... (standard ESP-IDF WiFi init) ...
    
    // Enable CSI collection
    wifi_csi_config_t csi_config = {
        .lltf_en = true,           // Enable L-LTF (Legacy Long Training Field)
        .htltf_en = true,          // Enable HT-LTF
        .stbc_htltf2_en = true,    // Enable STBC HT-LTF2
        .ltf_merge_en = true,      // Merge LTF
        .channel_filter_en = false,
        .manu_scale = false,
        .shift = false,
    };
    
    esp_wifi_set_csi_config(&csi_config);
    esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL);
    esp_wifi_set_csi(true);
    
    // Create UDP socket for sending data to laptop
    udp_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    
    ESP_LOGI(TAG, "Anchor %d ready, sending CSI to %s:%d",
             ANCHOR_ID, LAPTOP_IP, LAPTOP_PORT);
}
```

### 4.2 RSSI-Only Fallback (Simpler Setup)

If CSI extraction is problematic, RSSI alone still works for positioning (lower accuracy, ~2-5m):

```c
// Simpler approach: just report RSSI values per received packet
// Can use Arduino framework instead of ESP-IDF for faster prototyping

// In promiscuous mode, capture all packets and report RSSI
void promiscuous_rx_cb(void *buf, wifi_promiscuous_pkt_type_t type) {
    wifi_promiscuous_pkt_t *pkt = (wifi_promiscuous_pkt_t *)buf;
    int8_t rssi = pkt->rx_ctrl.rssi;
    uint8_t *mac = pkt->payload + 10;  // Source MAC offset
    
    // Filter for drone's MAC and send RSSI to laptop
}
```

### 4.3 Inter-Anchor Sensing

For environment/obstacle sensing, anchors can also monitor CSI between each other:

```
Anchor 0 ←→ Anchor 1: CSI link 01
Anchor 0 ←→ Anchor 2: CSI link 02
Anchor 1 ←→ Anchor 2: CSI link 12
... etc.
```

When the drone (or any object) passes through these links, the CSI changes. This gives you a coarse "WiFi motion grid" covering the space. Implement by having anchors take turns transmitting a known packet while others listen.

---

## 5. WiFi Positioning Engine

### 5.1 CSI Data Collection (Laptop Side)

```python
# src/wifi_positioning/csi_collector.py

import socket
import struct
import numpy as np
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class CSIFrame:
    """Single CSI measurement from one anchor."""
    anchor_id: int
    timestamp_us: int      # ESP32 microsecond timestamp
    rssi: int              # dBm
    csi_raw: np.ndarray    # Complex CSI values per subcarrier
    receive_time: float    # Laptop receive time (time.monotonic())

@dataclass
class AnchorConfig:
    """Known anchor position and metadata."""
    anchor_id: int
    position: np.ndarray   # [x, y, z] in meters, world frame
    mac_address: str
    channel: int = 6

class CSICollector:
    """
    Collects CSI data from all ESP32 anchors via UDP.
    Runs a background thread to continuously receive packets.
    """
    
    def __init__(self, port: int = 5000, anchors: Dict[int, AnchorConfig] = None):
        self.port = port
        self.anchors = anchors or {}
        self.latest_csi: Dict[int, CSIFrame] = {}
        self.csi_buffer: Dict[int, List[CSIFrame]] = defaultdict(list)
        self.buffer_max_size = 100  # Keep last N frames per anchor
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
    
    def start(self):
        """Start background collection thread."""
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def _receive_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self.port))
        sock.settimeout(0.1)
        
        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                frame = self._parse_packet(data)
                if frame is not None:
                    with self._lock:
                        self.latest_csi[frame.anchor_id] = frame
                        buf = self.csi_buffer[frame.anchor_id]
                        buf.append(frame)
                        if len(buf) > self.buffer_max_size:
                            buf.pop(0)
            except socket.timeout:
                continue
        sock.close()
    
    def _parse_packet(self, data: bytes) -> Optional[CSIFrame]:
        """Parse UDP packet from ESP32 anchor."""
        if len(data) < 12:
            return None
        
        offset = 0
        anchor_id = data[offset]; offset += 1
        timestamp_us = struct.unpack('<q', data[offset:offset+8])[0]; offset += 8
        rssi = struct.unpack('<b', data[offset:offset+1])[0]; offset += 1
        csi_len = struct.unpack('<H', data[offset:offset+2])[0]; offset += 2
        
        if len(data) < offset + csi_len:
            return None
        
        # Parse CSI: pairs of int8 [I, Q] for each subcarrier
        csi_bytes = np.frombuffer(data[offset:offset+csi_len], dtype=np.int8)
        csi_complex = csi_bytes[0::2] + 1j * csi_bytes[1::2]  # I + jQ
        
        return CSIFrame(
            anchor_id=anchor_id,
            timestamp_us=timestamp_us,
            rssi=rssi,
            csi_raw=csi_complex,
            receive_time=time.monotonic()
        )
    
    def get_latest_all(self) -> Dict[int, CSIFrame]:
        """Get most recent CSI frame from each anchor."""
        with self._lock:
            return dict(self.latest_csi)
    
    def get_synchronized_frames(self, max_age_ms: float = 50) -> Dict[int, CSIFrame]:
        """
        Get frames from all anchors within a time window.
        Returns empty dict if not all anchors have recent data.
        """
        now = time.monotonic()
        with self._lock:
            synced = {}
            for aid, frame in self.latest_csi.items():
                age_ms = (now - frame.receive_time) * 1000
                if age_ms <= max_age_ms:
                    synced[aid] = frame
            return synced
```

### 5.2 3D Trilateration

```python
# src/wifi_positioning/trilateration.py

import numpy as np
from scipy.optimize import least_squares
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class PositionEstimate:
    """3D position estimate with uncertainty."""
    position: np.ndarray    # [x, y, z] meters
    covariance: np.ndarray  # 3x3 covariance matrix
    num_anchors: int        # How many anchors contributed
    residual: float         # Optimization residual
    timestamp: float        # When this estimate was computed

class WiFiTrilateration:
    """
    Estimate 3D position from range measurements to known anchors.
    
    Supports both RSSI-derived ranges and CSI-derived ranges.
    Uses nonlinear least squares with robust loss for outlier rejection.
    """
    
    def __init__(self, anchor_positions: Dict[int, np.ndarray]):
        """
        Args:
            anchor_positions: {anchor_id: np.array([x, y, z])} in meters
        """
        self.anchor_positions = anchor_positions
        
        # RSSI → distance model parameters (log-distance path loss)
        # d = 10^((RSSI_0 - RSSI) / (10 * n))
        self.rssi_d0 = 1.0       # Reference distance (meters)
        self.rssi_at_d0 = -40    # RSSI at reference distance (dBm) — CALIBRATE THIS
        self.path_loss_exp = 2.5  # Path loss exponent — CALIBRATE THIS (2.0=free space, 3-4=indoors)
        
        self._last_position = None  # For warm-starting optimizer
    
    def rssi_to_distance(self, rssi: float) -> float:
        """Convert RSSI (dBm) to estimated distance (meters)."""
        return self.rssi_d0 * 10 ** ((self.rssi_at_d0 - rssi) / (10 * self.path_loss_exp))
    
    def estimate_position(
        self,
        ranges: Dict[int, float],  # {anchor_id: estimated_distance_meters}
        weights: Optional[Dict[int, float]] = None,
    ) -> Optional[PositionEstimate]:
        """
        Estimate 3D position from range measurements.
        
        Args:
            ranges: Distance estimate to each anchor
            weights: Optional confidence weight per anchor (higher = more trusted)
        
        Returns:
            PositionEstimate or None if insufficient data
        """
        # Need at least 3 anchors for 3D (4 is better)
        valid_ids = [aid for aid in ranges if aid in self.anchor_positions]
        if len(valid_ids) < 3:
            return None
        
        anchor_pos = np.array([self.anchor_positions[aid] for aid in valid_ids])
        measured_ranges = np.array([ranges[aid] for aid in valid_ids])
        
        if weights:
            w = np.array([weights.get(aid, 1.0) for aid in valid_ids])
        else:
            w = np.ones(len(valid_ids))
        
        # Initial guess: weighted centroid or last known position
        if self._last_position is not None:
            x0 = self._last_position.copy()
        else:
            x0 = np.average(anchor_pos, axis=0, weights=1.0/measured_ranges)
        
        def residuals(pos):
            predicted_ranges = np.linalg.norm(anchor_pos - pos, axis=1)
            return w * (predicted_ranges - measured_ranges)
        
        result = least_squares(
            residuals, x0,
            loss='huber',     # Robust to outliers
            f_scale=1.0,      # Expected noise level (meters)
            max_nfev=100
        )
        
        position = result.x
        self._last_position = position.copy()
        
        # Estimate covariance from Jacobian
        J = result.jac
        try:
            residual_var = np.sum(result.fun**2) / max(1, len(valid_ids) - 3)
            cov = residual_var * np.linalg.inv(J.T @ J)
        except np.linalg.LinAlgError:
            cov = np.eye(3) * 10.0  # Large uncertainty fallback
        
        return PositionEstimate(
            position=position,
            covariance=cov,
            num_anchors=len(valid_ids),
            residual=np.sqrt(np.mean(result.fun**2)),
            timestamp=0  # Caller should set this
        )
    
    def estimate_from_rssi(
        self,
        rssi_readings: Dict[int, float]  # {anchor_id: rssi_dBm}
    ) -> Optional[PositionEstimate]:
        """Convenience: RSSI readings → position estimate."""
        ranges = {aid: self.rssi_to_distance(rssi) for aid, rssi in rssi_readings.items()}
        # Weight inversely by distance (closer anchors are more reliable)
        weights = {aid: 1.0 / max(d, 0.5) for aid, d in ranges.items()}
        return self.estimate_position(ranges, weights)
    
    def calibrate_rssi_model(
        self,
        known_positions: List[Tuple[np.ndarray, Dict[int, float]]]
    ):
        """
        Calibrate RSSI path-loss model from known position + RSSI pairs.
        
        Args:
            known_positions: List of (position_xyz, {anchor_id: rssi}) tuples
                             collected at known locations
        """
        # Collect (true_distance, rssi) pairs
        distances = []
        rssis = []
        for pos, readings in known_positions:
            for aid, rssi in readings.items():
                if aid in self.anchor_positions:
                    true_dist = np.linalg.norm(pos - self.anchor_positions[aid])
                    if true_dist > 0.1:  # Skip if too close
                        distances.append(true_dist)
                        rssis.append(rssi)
        
        distances = np.array(distances)
        rssis = np.array(rssis)
        
        # Fit log-distance model: RSSI = RSSI_0 - 10*n*log10(d/d0)
        log_d = np.log10(distances / self.rssi_d0)
        # Linear regression: RSSI = A + B * log10(d)
        A = np.column_stack([np.ones_like(log_d), log_d])
        result = np.linalg.lstsq(A, rssis, rcond=None)
        self.rssi_at_d0 = result[0][0]
        self.path_loss_exp = -result[0][1] / 10.0
        
        print(f"Calibrated: RSSI_0={self.rssi_at_d0:.1f} dBm, n={self.path_loss_exp:.2f}")
```

### 5.3 CSI-Based Range Estimation (Advanced)

```python
# src/wifi_positioning/csi_processor.py

import numpy as np
from typing import Optional, Tuple

class CSIProcessor:
    """
    Extract range and angle-of-arrival information from CSI data.
    
    CSI provides per-subcarrier amplitude and phase, which encodes
    multipath propagation information. Key techniques:
    
    1. Phase-based ranging: Phase slope across subcarriers → ToF → distance
    2. MUSIC/ESPRIT: Super-resolution algorithms for AoA estimation
    3. SpotFi: Joint AoA + ToF estimation from CSI
    
    This implementation focuses on phase-based ranging as the most
    practical approach for ESP32 hardware.
    """
    
    def __init__(self, bandwidth_hz: float = 20e6, num_subcarriers: int = 56,
                 center_freq_hz: float = 5.18e9):
        self.bandwidth = bandwidth_hz
        self.num_subcarriers = num_subcarriers
        self.center_freq = center_freq_hz
        self.subcarrier_spacing = bandwidth_hz / num_subcarriers
        self.speed_of_light = 3e8
        
        # Subcarrier frequency offsets from center
        self.subcarrier_freqs = np.arange(num_subcarriers) * self.subcarrier_spacing \
                                - bandwidth_hz / 2 + self.subcarrier_spacing / 2
    
    def estimate_distance_from_csi(self, csi: np.ndarray) -> Optional[float]:
        """
        Estimate distance from CSI phase slope.
        
        The phase of CSI across subcarriers has a linear component
        proportional to the time-of-flight:
            phase(f) = -2π * f * ToF + offset
        
        Args:
            csi: Complex CSI array, shape (num_subcarriers,)
        
        Returns:
            Estimated distance in meters, or None if unreliable
        """
        if len(csi) < 10:
            return None
        
        # Extract and unwrap phase
        phase = np.angle(csi)
        phase_unwrapped = np.unwrap(phase)
        
        # Remove phase offset and slope (sanitize)
        # Linear fit: phase = slope * freq + offset
        # slope = -2π * ToF
        freqs = self.subcarrier_freqs[:len(csi)]
        
        # Robust linear fit
        coeffs = np.polyfit(freqs, phase_unwrapped, 1)
        slope = coeffs[0]
        
        tof = -slope / (2 * np.pi)
        distance = tof * self.speed_of_light
        
        # Sanity check
        if distance < 0 or distance > 100:
            return None
        
        return distance
    
    def estimate_aoa_from_csi(
        self,
        csi_ant1: np.ndarray,
        csi_ant2: np.ndarray,
        antenna_spacing_m: float = 0.025  # Half wavelength at 5GHz ≈ 2.5cm
    ) -> Optional[float]:
        """
        Estimate angle of arrival from CSI phase difference between two antennas.
        
        Requires dual-antenna ESP32 setup (ESP32-S3 has 2 antenna ports).
        
        Args:
            csi_ant1: CSI from antenna 1
            csi_ant2: CSI from antenna 2
            antenna_spacing_m: Physical distance between antennas
        
        Returns:
            Angle of arrival in radians (-π/2 to π/2), or None
        """
        if len(csi_ant1) != len(csi_ant2):
            return None
        
        # Phase difference between antennas
        phase_diff = np.angle(csi_ant2 * np.conj(csi_ant1))
        
        # Average across subcarriers (reduces noise)
        avg_phase_diff = np.mean(phase_diff)
        
        # AoA from phase difference:
        # phase_diff = 2π * d * sin(θ) / λ
        wavelength = self.speed_of_light / self.center_freq
        sin_theta = avg_phase_diff * wavelength / (2 * np.pi * antenna_spacing_m)
        
        if abs(sin_theta) > 1.0:
            return None  # Invalid
        
        return np.arcsin(sin_theta)
    
    def compute_csi_amplitude_features(self, csi: np.ndarray) -> dict:
        """
        Extract amplitude features useful for fingerprinting and environment sensing.
        """
        amplitude = np.abs(csi)
        return {
            'mean_amplitude': np.mean(amplitude),
            'std_amplitude': np.std(amplitude),
            'max_amplitude': np.max(amplitude),
            'amplitude_spread': np.max(amplitude) - np.min(amplitude),
            'subcarrier_correlation': np.corrcoef(amplitude[:-1], amplitude[1:])[0, 1],
        }
```

---

## 6. Visual Pipeline (Laptop GPU)

### 6.1 Video Capture from Drone

```python
# src/visual_slam/video_capture.py

import cv2
import threading
import numpy as np
import time
from typing import Optional, Tuple, Callable
from dataclasses import dataclass

@dataclass
class VideoFrame:
    """Single captured video frame with metadata."""
    image: np.ndarray       # BGR image
    timestamp: float        # time.monotonic()
    frame_id: int
    width: int
    height: int

class DroneVideoCapture:
    """
    Capture video stream from WiFi drone.
    
    Supports:
    - Tello: UDP stream on port 11111 (H.264)
    - Generic: RTSP or HTTP MJPEG streams
    - Direct OpenCV VideoCapture for any source
    
    Runs capture in a background thread to avoid blocking.
    """
    
    def __init__(self, source: str = "udp://0.0.0.0:11111",
                 target_fps: int = 30,
                 resolution: Tuple[int, int] = (960, 720)):
        self.source = source
        self.target_fps = target_fps
        self.resolution = resolution
        self._latest_frame: Optional[VideoFrame] = None
        self._frame_id = 0
        self._running = False
        self._lock = threading.Lock()
        self._callbacks: list = []
    
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._running = False
    
    def on_frame(self, callback: Callable[[VideoFrame], None]):
        """Register callback for each new frame."""
        self._callbacks.append(callback)
    
    def _capture_loop(self):
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        
        # Reduce latency for UDP streams
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # Resize if needed
            if frame.shape[:2][::-1] != self.resolution:
                frame = cv2.resize(frame, self.resolution)
            
            vf = VideoFrame(
                image=frame,
                timestamp=time.monotonic(),
                frame_id=self._frame_id,
                width=frame.shape[1],
                height=frame.shape[0]
            )
            self._frame_id += 1
            
            with self._lock:
                self._latest_frame = vf
            
            for cb in self._callbacks:
                cb(vf)
        
        cap.release()
    
    def get_latest(self) -> Optional[VideoFrame]:
        with self._lock:
            return self._latest_frame
```

### 6.2 Depth Anything V2 Integration

```python
# src/depth_estimation/depth_anything.py

import torch
import torch.nn.functional as F
import numpy as np
import cv2
from typing import Optional

class DepthAnythingV2:
    """
    Monocular depth estimation using Depth Anything V2.
    
    Turns a single camera image into a per-pixel depth map.
    Combined with known camera pose, this gives dense 3D reconstruction.
    
    Models (VRAM usage at 518×518 input):
    - depth-anything-v2-vits: ~1GB VRAM, fastest, ~60fps on RTX 3060
    - depth-anything-v2-vitb: ~2GB VRAM, balanced, ~30fps
    - depth-anything-v2-vitl: ~4GB VRAM, best quality, ~15fps
    
    For real-time drone operation, use 'vits' or 'vitb'.
    
    IMPORTANT: Depth Anything V2 produces *relative* (affine-invariant) depth.
    You need scale calibration to get metric depth. Options:
    1. Use the 'metric' variants (depth-anything-v2-metric-*) — trained for metric output
    2. Calibrate scale using known distances from WiFi positioning
    3. Use visual SLAM scale + WiFi anchoring to resolve
    """
    
    def __init__(self, model_size: str = 'vitb', device: str = 'cuda',
                 input_size: int = 518, use_metric: bool = True):
        self.device = device
        self.input_size = input_size
        
        # Load model
        # Option A: Use the metric depth variant (recommended)
        if use_metric:
            # pip install huggingface_hub
            # Model: depth-anything/Depth-Anything-V2-Metric-Indoor-Base
            from transformers import pipeline
            model_id = f"depth-anything/Depth-Anything-V2-Metric-Indoor-{'Small' if model_size == 'vits' else 'Base' if model_size == 'vitb' else 'Large'}"
            self.pipe = pipeline("depth-estimation", model=model_id, device=device)
            self._use_pipeline = True
        else:
            # Option B: Use transformers depth estimation pipeline
            from transformers import pipeline
            model_id = f"depth-anything/Depth-Anything-V2-{'Small' if model_size == 'vits' else 'Base' if model_size == 'vitb' else 'Large'}"
            self.pipe = pipeline("depth-estimation", model=model_id, device=device)
            self._use_pipeline = True
        
        # Scale factor for converting relative depth to meters
        # This should be calibrated using WiFi-derived distances
        self.depth_scale = 1.0
        self.depth_offset = 0.0
    
    @torch.no_grad()
    def estimate_depth(self, image_bgr: np.ndarray) -> np.ndarray:
        """
        Estimate depth from a BGR image.
        
        Args:
            image_bgr: Input BGR image (H, W, 3), uint8
        
        Returns:
            Depth map (H, W), float32, in meters (if metric model)
            or relative depth (if non-metric model, needs scaling)
        """
        from PIL import Image
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(image_rgb)
        
        result = self.pipe(pil_image)
        depth = np.array(result['depth'], dtype=np.float32)
        
        # Resize to match input image
        if depth.shape != image_bgr.shape[:2]:
            depth = cv2.resize(depth, (image_bgr.shape[1], image_bgr.shape[0]))
        
        # Apply calibration
        depth = depth * self.depth_scale + self.depth_offset
        
        return depth
    
    def calibrate_scale(self, depth_map: np.ndarray, 
                        known_distance: float, 
                        pixel_coords: tuple):
        """
        Calibrate depth scale using a known real-world distance.
        
        For example, use WiFi-derived distance to an anchor visible in frame,
        or a known object size.
        
        Args:
            depth_map: Raw depth output
            known_distance: True distance in meters
            pixel_coords: (x, y) pixel location of the reference point
        """
        raw_depth = depth_map[pixel_coords[1], pixel_coords[0]]
        if raw_depth > 0:
            self.depth_scale = known_distance / raw_depth
```

### 6.3 Depth Map → 3D Point Cloud

```python
# src/depth_estimation/depth_to_pointcloud.py

import numpy as np
import open3d as o3d
from typing import Optional, Tuple

class DepthToPointCloud:
    """
    Convert depth maps + camera pose into 3D point clouds in world coordinates.
    
    Requires camera intrinsics (focal length, principal point).
    """
    
    def __init__(self, fx: float, fy: float, cx: float, cy: float,
                 width: int, height: int,
                 max_depth: float = 10.0,
                 min_depth: float = 0.1,
                 downsample_factor: int = 4):
        """
        Args:
            fx, fy: Focal lengths in pixels
            cx, cy: Principal point in pixels
            width, height: Image dimensions
            max_depth: Ignore points beyond this distance (meters)
            min_depth: Ignore points closer than this (meters)
            downsample_factor: Spatial downsampling (4 = every 4th pixel)
        """
        self.fx = fx
        self.fy = fy
        self.cx = cx
        self.cy = cy
        self.width = width
        self.height = height
        self.max_depth = max_depth
        self.min_depth = min_depth
        self.ds = downsample_factor
        
        # Pre-compute pixel coordinate grid (downsampled)
        u = np.arange(0, width, self.ds)
        v = np.arange(0, height, self.ds)
        self.u_grid, self.v_grid = np.meshgrid(u, v)
    
    def deproject(self, depth_map: np.ndarray,
                  color_image: Optional[np.ndarray] = None,
                  camera_pose: Optional[np.ndarray] = None) -> o3d.geometry.PointCloud:
        """
        Convert depth map to 3D point cloud.
        
        Args:
            depth_map: (H, W) depth in meters
            color_image: Optional (H, W, 3) BGR image for coloring points
            camera_pose: Optional 4x4 world-from-camera transform matrix.
                         If provided, points are in world coordinates.
                         If None, points are in camera coordinates.
        
        Returns:
            Open3D point cloud
        """
        # Downsample depth map
        depth = depth_map[::self.ds, ::self.ds]
        
        # Valid depth mask
        valid = (depth > self.min_depth) & (depth < self.max_depth)
        
        # Back-project to 3D (camera coordinates)
        z = depth[valid]
        x = (self.u_grid[valid] - self.cx) * z / self.fx
        y = (self.v_grid[valid] - self.cy) * z / self.fy
        
        points_camera = np.stack([x, y, z], axis=-1)  # (N, 3)
        
        # Transform to world coordinates
        if camera_pose is not None:
            R = camera_pose[:3, :3]
            t = camera_pose[:3, 3]
            points_world = (R @ points_camera.T).T + t
        else:
            points_world = points_camera
        
        # Create Open3D point cloud
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points_world)
        
        # Add colors if available
        if color_image is not None:
            colors = color_image[::self.ds, ::self.ds][valid]
            colors_rgb = colors[:, ::-1].astype(np.float64) / 255.0  # BGR→RGB, normalize
            pcd.colors = o3d.utility.Vector3dVector(colors_rgb)
        
        return pcd
```

---

## 7. Sensor Fusion

### 7.1 Extended Kalman Filter (WiFi + Visual Odometry)

```python
# src/fusion/ekf_fusion.py

import numpy as np
from typing import Optional
from dataclasses import dataclass

@dataclass
class FusedState:
    """Fused drone state estimate."""
    position: np.ndarray     # [x, y, z] meters, world frame
    velocity: np.ndarray     # [vx, vy, vz] m/s
    orientation: np.ndarray  # Quaternion [w, x, y, z] or rotation matrix
    covariance: np.ndarray   # 9x9 (pos + vel + orientation)
    timestamp: float

class WiFiVisualEKF:
    """
    Extended Kalman Filter fusing:
    1. WiFi position estimates (absolute, low rate ~10Hz, noisy ~1m)
    2. Visual odometry increments (relative, high rate ~30Hz, drifts)
    3. Optional: IMU data if available from drone
    
    State vector: [x, y, z, vx, vy, vz] (6-DOF simplified)
    For full 6-DOF, extend to include orientation.
    """
    
    def __init__(self):
        # State: [x, y, z, vx, vy, vz]
        self.state = np.zeros(6)
        self.P = np.eye(6) * 10.0  # Initial covariance (high uncertainty)
        
        # Process noise (how much we expect state to change per second)
        self.Q_per_sec = np.diag([
            0.01, 0.01, 0.01,   # Position process noise (m²/s)
            0.5, 0.5, 0.5       # Velocity process noise (m²/s³)
        ])
        
        # Measurement noise: WiFi positioning
        self.R_wifi = np.diag([1.0, 1.0, 1.5]) ** 2  # meters² (z is less certain)
        
        # Measurement noise: Visual odometry (per-step)
        # This scales with the magnitude of the VO displacement
        self.R_vo_scale = 0.05  # 5% of displacement as noise
        
        self.last_timestamp = None
        self.initialized = False
    
    def predict(self, timestamp: float):
        """
        Predict state forward to given timestamp using constant-velocity model.
        """
        if self.last_timestamp is None:
            self.last_timestamp = timestamp
            return
        
        dt = timestamp - self.last_timestamp
        if dt <= 0 or dt > 1.0:  # Skip if dt is unreasonable
            self.last_timestamp = timestamp
            return
        
        # State transition matrix (constant velocity)
        F = np.eye(6)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt
        
        # Predict
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + self.Q_per_sec * dt
        
        self.last_timestamp = timestamp
    
    def update_wifi(self, position: np.ndarray, covariance: Optional[np.ndarray] = None,
                    timestamp: Optional[float] = None):
        """
        Update with WiFi position measurement.
        
        Args:
            position: [x, y, z] measured position (meters)
            covariance: Optional 3x3 measurement covariance
            timestamp: Measurement timestamp
        """
        if timestamp is not None:
            self.predict(timestamp)
        
        if not self.initialized:
            self.state[:3] = position
            self.initialized = True
            return
        
        R = covariance if covariance is not None else self.R_wifi
        
        # Observation matrix: we observe [x, y, z]
        H = np.zeros((3, 6))
        H[0, 0] = 1  # x
        H[1, 1] = 1  # y
        H[2, 2] = 1  # z
        
        # Kalman update
        y = position - H @ self.state          # Innovation
        S = H @ self.P @ H.T + R              # Innovation covariance
        K = self.P @ H.T @ np.linalg.inv(S)   # Kalman gain
        
        self.state = self.state + K @ y
        self.P = (np.eye(6) - K @ H) @ self.P
    
    def update_visual_odometry(self, delta_position: np.ndarray,
                                timestamp: Optional[float] = None):
        """
        Update with visual odometry displacement (relative motion).
        
        Args:
            delta_position: [dx, dy, dz] displacement since last VO update
                           In world frame (caller should rotate from camera frame)
            timestamp: Measurement timestamp
        """
        if timestamp is not None:
            self.predict(timestamp)
        
        if not self.initialized:
            return  # Need at least one absolute measurement first
        
        # VO gives relative displacement, so measurement = current_pos + delta
        # This is equivalent to measuring position with higher noise
        displacement_norm = np.linalg.norm(delta_position)
        noise_std = max(0.01, displacement_norm * self.R_vo_scale)
        R = np.eye(3) * noise_std**2
        
        # Predicted position after applying VO delta
        predicted_pos = self.state[:3] + delta_position
        
        H = np.zeros((3, 6))
        H[0, 0] = 1
        H[1, 1] = 1
        H[2, 2] = 1
        
        y = predicted_pos - H @ self.state
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        
        self.state = self.state + K @ y
        self.P = (np.eye(6) - K @ H) @ self.P
    
    def get_state(self) -> FusedState:
        return FusedState(
            position=self.state[:3].copy(),
            velocity=self.state[3:6].copy(),
            orientation=np.array([1, 0, 0, 0]),  # Placeholder
            covariance=self.P.copy(),
            timestamp=self.last_timestamp or 0
        )
```

---

## 8. Main System Runner

```python
# scripts/run_system.py

"""
Main entry point for the WiFi-augmented drone 3D sensing system.

Usage:
    python scripts/run_system.py --config config/system.yaml

This script:
1. Starts CSI/RSSI collection from ESP32 anchors
2. Connects to drone video stream
3. Runs visual SLAM + depth estimation on GPU
4. Fuses WiFi position with visual odometry
5. Accumulates dense 3D point cloud
6. Visualizes everything in real-time
"""

import yaml
import time
import numpy as np
import threading
import argparse
import open3d as o3d

# Import our modules
from src.wifi_positioning.csi_collector import CSICollector, AnchorConfig
from src.wifi_positioning.trilateration import WiFiTrilateration
from src.visual_slam.video_capture import DroneVideoCapture
from src.depth_estimation.depth_anything import DepthAnythingV2
from src.depth_estimation.depth_to_pointcloud import DepthToPointCloud
from src.fusion.ekf_fusion import WiFiVisualEKF


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/system.yaml')
    parser.add_argument('--no-depth', action='store_true', help='Disable depth estimation')
    parser.add_argument('--record', action='store_true', help='Record all data for replay')
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    # ── 1. Setup anchor positions ──
    anchors = {}
    anchor_positions = {}
    for a in config['anchors']:
        pos = np.array(a['position'])
        anchors[a['id']] = AnchorConfig(
            anchor_id=a['id'],
            position=pos,
            mac_address=a.get('mac', ''),
            channel=a.get('channel', 6)
        )
        anchor_positions[a['id']] = pos
    
    # ── 2. Start CSI collection ──
    csi_collector = CSICollector(port=config.get('csi_port', 5000), anchors=anchors)
    csi_collector.start()
    print(f"[WiFi] Listening for CSI on port {config.get('csi_port', 5000)}")
    
    # ── 3. WiFi positioning engine ──
    trilat = WiFiTrilateration(anchor_positions)
    
    # ── 4. Start video capture ──
    video_source = config.get('video_source', 'udp://0.0.0.0:11111')
    video = DroneVideoCapture(source=video_source)
    video.start()
    print(f"[Video] Capturing from {video_source}")
    
    # ── 5. Depth estimation (GPU) ──
    depth_model = None
    depth_projector = None
    if not args.no_depth:
        print("[Depth] Loading Depth Anything V2...")
        depth_model = DepthAnythingV2(
            model_size=config.get('depth_model', 'vitb'),
            use_metric=True
        )
        
        cam = config.get('camera', {})
        depth_projector = DepthToPointCloud(
            fx=cam.get('fx', 500), fy=cam.get('fy', 500),
            cx=cam.get('cx', 480), cy=cam.get('cy', 360),
            width=cam.get('width', 960), height=cam.get('height', 720),
            downsample_factor=config.get('pointcloud_downsample', 4)
        )
        print("[Depth] Model loaded")
    
    # ── 6. Sensor fusion ──
    ekf = WiFiVisualEKF()
    
    # ── 7. Point cloud accumulator ──
    global_pcd = o3d.geometry.PointCloud()
    max_points = config.get('max_global_points', 500000)
    
    # ── 8. Main loop ──
    print("\n[System] Running. Press Ctrl+C to stop.\n")
    
    wifi_hz = config.get('wifi_update_hz', 10)
    wifi_interval = 1.0 / wifi_hz
    last_wifi_time = 0
    frame_count = 0
    
    try:
        while True:
            now = time.monotonic()
            
            # ── WiFi position update ──
            if now - last_wifi_time >= wifi_interval:
                csi_frames = csi_collector.get_synchronized_frames(max_age_ms=100)
                if len(csi_frames) >= 3:
                    # Extract RSSI for trilateration
                    rssi_readings = {aid: f.rssi for aid, f in csi_frames.items()}
                    wifi_pos = trilat.estimate_from_rssi(rssi_readings)
                    
                    if wifi_pos is not None:
                        wifi_pos.timestamp = now
                        ekf.update_wifi(wifi_pos.position, wifi_pos.covariance, now)
                        
                        if frame_count % 30 == 0:  # Print every ~1 second
                            p = wifi_pos.position
                            print(f"[WiFi] pos=({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}) "
                                  f"anchors={wifi_pos.num_anchors} "
                                  f"residual={wifi_pos.residual:.2f}m")
                
                last_wifi_time = now
            
            # ── Video frame processing ──
            frame = video.get_latest()
            if frame is None:
                time.sleep(0.001)
                continue
            
            # TODO: Run visual odometry here
            # vo_delta = visual_slam.process_frame(frame.image)
            # if vo_delta is not None:
            #     ekf.update_visual_odometry(vo_delta, frame.timestamp)
            
            # ── Depth estimation + point cloud ──
            if depth_model is not None and frame_count % 3 == 0:  # Every 3rd frame
                depth_map = depth_model.estimate_depth(frame.image)
                
                # Get current fused pose
                fused = ekf.get_state()
                
                if fused.position is not None:
                    # Build camera pose matrix (simplified: translation only)
                    # TODO: Include orientation from visual SLAM
                    camera_pose = np.eye(4)
                    camera_pose[:3, 3] = fused.position
                    
                    # Generate colored point cloud
                    pcd = depth_projector.deproject(
                        depth_map, frame.image, camera_pose
                    )
                    
                    # Accumulate
                    global_pcd += pcd
                    
                    # Downsample if too many points
                    if len(global_pcd.points) > max_points:
                        global_pcd = global_pcd.voxel_down_sample(0.05)
            
            frame_count += 1
            
            # Status print
            if frame_count % 100 == 0:
                state = ekf.get_state()
                p = state.position
                n_pts = len(global_pcd.points)
                print(f"[Fused] pos=({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}) "
                      f"points={n_pts}")
    
    except KeyboardInterrupt:
        print("\n[System] Shutting down...")
    
    finally:
        csi_collector.stop()
        video.stop()
        
        # Save accumulated point cloud
        if len(global_pcd.points) > 0:
            output_path = "output/scan.ply"
            o3d.io.write_point_cloud(output_path, global_pcd)
            print(f"[System] Saved {len(global_pcd.points)} points to {output_path}")


if __name__ == '__main__':
    main()
```

---

## 9. Configuration Files

### 9.1 System Configuration

```yaml
# config/system.yaml

# ── ESP32 Anchor Configuration ──
anchors:
  - id: 0
    position: [0.0, 0.0, 0.3]       # x, y, z in meters
    mac: "AA:BB:CC:DD:EE:00"
    channel: 6
  - id: 1
    position: [10.0, 0.0, 2.8]
    mac: "AA:BB:CC:DD:EE:01"
    channel: 6
  - id: 2
    position: [0.0, 8.0, 1.5]
    mac: "AA:BB:CC:DD:EE:02"
    channel: 6
  - id: 3
    position: [10.0, 8.0, 0.3]
    mac: "AA:BB:CC:DD:EE:03"
    channel: 6
  - id: 4
    position: [5.0, 0.0, 2.8]
    mac: "AA:BB:CC:DD:EE:04"
    channel: 6
  - id: 5
    position: [5.0, 8.0, 1.5]
    mac: "AA:BB:CC:DD:EE:05"
    channel: 6

csi_port: 5000

# ── Drone / Video ──
video_source: "udp://0.0.0.0:11111"   # Tello default
# video_source: "rtsp://192.168.1.1:554/stream"  # Generic RTSP

# ── Camera Intrinsics ──
# Calibrate these! Use scripts/calibrate_camera.py with a checkerboard.
# These are rough defaults for Tello at 960×720.
camera:
  fx: 500
  fy: 500
  cx: 480
  cy: 360
  width: 960
  height: 720

# ── Depth Estimation ──
depth_model: "vitb"              # vits (fast), vitb (balanced), vitl (best)
pointcloud_downsample: 4         # Process every Nth pixel

# ── Fusion ──
wifi_update_hz: 10               # WiFi position update rate
max_global_points: 500000        # Max accumulated point cloud size

# ── RSSI Model (calibrate with scripts/calibrate_anchors.py) ──
rssi_model:
  rssi_at_d0: -40                # RSSI at 1m reference distance
  path_loss_exponent: 2.5        # Typically 2.0-4.0 indoors
```

---

## 10. Calibration Procedures

### 10.1 Camera Intrinsic Calibration

Before any visual processing, calibrate the drone's camera:

```python
# scripts/calibrate_camera.py
# Print a checkerboard, record video of it from the drone, extract intrinsics

import cv2
import numpy as np
import glob
import yaml

# Checkerboard parameters
BOARD_SIZE = (9, 6)  # Inner corners
SQUARE_SIZE = 0.025  # 25mm squares

# Prepare object points
objp = np.zeros((BOARD_SIZE[0] * BOARD_SIZE[1], 3), np.float32)
objp[:, :2] = np.mgrid[0:BOARD_SIZE[0], 0:BOARD_SIZE[1]].T.reshape(-1, 2)
objp *= SQUARE_SIZE

obj_points = []
img_points = []

images = glob.glob('calibration_images/*.jpg')
for fname in images:
    img = cv2.imread(fname)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(gray, BOARD_SIZE, None)
    if ret:
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        obj_points.append(objp)
        img_points.append(corners)

ret, K, dist, rvecs, tvecs = cv2.calibrateCamera(
    obj_points, img_points, gray.shape[::-1], None, None
)

print(f"Camera matrix:\n{K}")
print(f"Distortion coefficients: {dist.ravel()}")

# Save
calib = {
    'fx': float(K[0, 0]),
    'fy': float(K[1, 1]),
    'cx': float(K[0, 2]),
    'cy': float(K[1, 2]),
    'width': int(gray.shape[1]),
    'height': int(gray.shape[0]),
    'dist_coeffs': dist.ravel().tolist()
}
with open('config/camera.yaml', 'w') as f:
    yaml.dump(calib, f)
```

### 10.2 RSSI Path-Loss Calibration

```python
# scripts/calibrate_anchors.py
# Walk the drone to known positions and record RSSI from all anchors

# Procedure:
# 1. Place drone at 5-10 known positions in the space
# 2. At each position, collect RSSI from all visible anchors for 10 seconds
# 3. Record true position (measure with tape measure) and average RSSI
# 4. Run this script to fit the path-loss model

# Example calibration data format:
# calibration_data = [
#     {"position": [2.0, 3.0, 1.0], "rssi": {0: -45, 1: -52, 2: -48, 3: -60}},
#     {"position": [5.0, 1.0, 1.5], "rssi": {0: -55, 1: -43, 2: -58, 3: -50}},
#     ...
# ]
```

---

## 11. Post-Flight Dense Reconstruction

After a flight, you can run offline reconstruction for higher quality:

### 11.1 3D Gaussian Splatting

```bash
# Record a flight with all camera frames + poses saved
python scripts/record_flight.py --output data/flight_001/

# After flight, run 3D Gaussian Splatting
# Requires: https://github.com/graphdeco-inria/gaussian-splatting

# 1. Prepare COLMAP-format input from saved frames + WiFi-calibrated poses
python scripts/prepare_colmap_from_flight.py data/flight_001/

# 2. Train Gaussian Splatting model
python train.py -s data/flight_001/colmap/ -m output/gs_model/

# 3. View result
# The output is a photorealistic, navigable 3D scene
```

### 11.2 TSDF Volume Reconstruction

```python
# For a cleaner mesh reconstruction using depth maps:

import open3d as o3d

volume = o3d.pipelines.integration.ScalableTSDFVolume(
    voxel_length=0.02,       # 2cm voxels
    sdf_trunc=0.08,
    color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8
)

# For each saved frame:
for frame_data in flight_recording:
    depth = frame_data['depth']     # Depth map
    color = frame_data['color']     # Color image
    pose = frame_data['pose']       # 4×4 camera-to-world transform
    
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(color),
        o3d.geometry.Image((depth * 1000).astype(np.uint16)),  # mm
        depth_scale=1000.0,
        depth_trunc=8.0,
        convert_rgb_to_intensity=False
    )
    
    intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, fx, fy, cx, cy)
    volume.integrate(rgbd, intrinsic, np.linalg.inv(pose))

# Extract mesh
mesh = volume.extract_triangle_mesh()
mesh.compute_vertex_normals()
o3d.io.write_triangle_mesh("output/mesh.ply", mesh)
```

---

## 12. Key Implementation Notes

### Things That Will Bite You

1. **WiFi channel hopping**: Make sure ALL anchors and the drone are on the SAME WiFi channel. CSI is only captured when the receiver is listening on the channel the transmitter is using.

2. **ESP32 CSI format varies by chip revision**: ESP32 (original), ESP32-S2, ESP32-S3, and ESP32-C3 all have slightly different CSI formats. Check Espressif docs for your specific chip.

3. **Clock synchronization**: ESP32 anchors have independent clocks. For CSI-based techniques that require timing, you need to either synchronize clocks (NTP, or use the laptop as time server) or use relative timing within each anchor.

4. **Drone video latency**: WiFi camera drones typically have 100-300ms video latency. Your visual SLAM timestamps will lag real-time. The EKF handles this if you timestamp correctly, but be aware of it.

5. **RSSI is noisy**: Individual RSSI readings fluctuate ±5-10 dBm. Always average over multiple packets (10-50) before using for positioning. The EKF naturally handles this, but raw readings will jump around.

6. **Depth Anything scale ambiguity**: Even the "metric" models can have systematic scale errors in novel environments. Use WiFi distances as ground truth to calibrate the depth scale factor.

7. **ESP32 promiscuous mode + STA mode**: On ESP32, you can run in station mode (connected to a network) and enable CSI capture simultaneously. You don't need promiscuous mode for CSI if the drone is on the same network.

8. **Point cloud memory**: Dense point clouds eat RAM fast. At 960×720 with downsample=4, each frame produces ~43K points (× 12 bytes = ~500KB). At 10 fps, that's 5MB/s. Use voxel downsampling aggressively.

### Performance Budgets (RTX 3060, 960×720 input)

| Component | Latency | GPU Memory | Notes |
|-----------|---------|------------|-------|
| Depth Anything V2 (vitb) | ~33ms | ~2GB | Can run on every frame |
| Depth Anything V2 (vits) | ~17ms | ~1GB | Faster, slightly less accurate |
| ORB-SLAM3 | ~20ms | ~500MB | CPU-heavy, some GPU for features |
| DPVO | ~30ms | ~2GB | Fully GPU, more robust |
| Point cloud projection | ~5ms | CPU | Numpy vectorized |
| EKF fusion | <1ms | CPU | Negligible |
| WiFi trilateration | <1ms | CPU | Negligible |
| **Total pipeline** | **~60-80ms** | **~3-4GB** | **Leaves headroom on 6GB GPU** |

---

## 13. Testing Without a Drone

You can develop and test most of the system without flying:

1. **WiFi positioning**: Walk around with a phone/laptop as the "drone" — the ESP32 anchors track any WiFi device
2. **Visual pipeline**: Use a recorded video dataset (TUM RGB-D, ScanNet, etc.) to test SLAM + depth
3. **Fusion**: Generate synthetic WiFi + visual data to test the EKF
4. **Simulate**: Record a real flight's data once, then replay it indefinitely with `scripts/replay_flight.py`

---

## 14. References and Resources

### Open Source Tools
- **Espressif ESP-CSI**: https://github.com/espressif/esp-csi
- **Depth Anything V2**: https://github.com/DepthAnything/Depth-Anything-V2
- **ORB-SLAM3**: https://github.com/UZ-SLAMLab/ORB_SLAM3
- **DPVO**: https://github.com/princeton-vl/DPVO
- **Open3D**: https://github.com/isl-org/Open3D
- **GTSAM**: https://github.com/borglab/gtsam
- **3D Gaussian Splatting**: https://github.com/graphdeco-inria/gaussian-splatting
- **Rerun (visualization)**: https://github.com/rerun-io/rerun
- **DJITelloPy**: https://github.com/damiafuentes/DJITelloPy

### Key Papers
- "Spatio-Temporal 3D Point Clouds from WiFi-CSI Data via Transformer Networks" (Määttä et al., 2025)
- "SpotFi: Decimeter Level Localization Using WiFi" (Kotaru et al., SIGCOMM 2015)
- "IndoTrack: Device-Free Indoor Human Tracking with Commodity WiFi" (Li et al., 2017)
- "Depth Anything V2" (Yang et al., 2024)
- "IEEE 802.11bf: WLAN Sensing" (published September 2025)

### WiFi CSI Datasets
- **MM-Fi Dataset**: Multi-modal (WiFi + LiDAR + mmWave + RGB-D)
- **Awesome WiFi CSI Sensing**: https://github.com/NTUMARS/Awesome-WiFi-CSI-Sensing
- **ESP32 CSI Dataset Collection Tools**: Built into esp-csi repo
