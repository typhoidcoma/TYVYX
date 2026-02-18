"""RTSP/RTP MJPEG video protocol adapter for lxPro-family drones.

Some E88Pro-family drones (e.g. Mten/FLOW-UFO) serve video via RTSP on
TCP 7070 with RTP/MJPEG (PT 26, RFC 2435) over UDP.

The RTSP session flow:
  1. Send E88Pro init commands on UDP (port 7099) to wake up the camera
  2. DESCRIBE rtsp://<ip>:7070/webcam  -> SDP (m=video 0 RTP/AVP 26)
  3. SETUP .../webcam/track0  Transport: RTP/AVP;unicast;client_port=X-Y
  4. PLAY  -> drone starts sending RTP/MJPEG on negotiated UDP port

RTP/MJPEG reassembly (RFC 2435):
  - Each RTP packet carries an 8-byte JPEG header + optional restart
    marker header (4B, type >= 64) + optional quantization tables
    (4B header + Nx64B tables, Q >= 128 and frag_offset == 0)
  - JPEG scan data follows; client must build the full JPEG file:
    SOI + DQT(s) + SOF0 + DHT + SOS + scan_data + EOI

Duck-typed adapter — same interface as PushJpegVideoProtocolAdapter:
  start() / stop() / is_running() / get_frame(timeout) / get_packets()
  start_keepalive() / stop_keepalive()  (no-ops)
"""

import ctypes
import queue
import re
import socket
import struct
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

from tyvyx.models.video_frame import VideoFrame


# ── Standard JPEG / RFC 2435 constants ──────────────────────────────

# Default Huffman tables (JPEG baseline, from JFIF spec / RFC 2435 appendix)
# Luma DC
_DHT_LUM_DC = bytes([
    0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x0A, 0x0B,
])
# Luma AC
_DHT_LUM_AC = bytes([
    0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03,
    0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
    0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
    0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16,
    0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
    0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
    0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
    0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
    0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4,
    0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
    0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA,
])
# Chroma DC
_DHT_CHR_DC = bytes([
    0x00, 0x03, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x0A, 0x0B,
])
# Chroma AC
_DHT_CHR_AC = bytes([
    0x00, 0x02, 0x01, 0x02, 0x04, 0x04, 0x03, 0x04,
    0x07, 0x05, 0x04, 0x04, 0x00, 0x01, 0x02, 0x77,
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21,
    0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71,
    0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91,
    0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0,
    0x15, 0x62, 0x72, 0xD1, 0x0A, 0x16, 0x24, 0x34,
    0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26,
    0x27, 0x28, 0x29, 0x2A, 0x35, 0x36, 0x37, 0x38,
    0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48,
    0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58,
    0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68,
    0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78,
    0x79, 0x7A, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96,
    0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5,
    0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4,
    0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3,
    0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2,
    0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA,
    0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9,
    0xEA, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA,
])


def _build_jpeg(width, height, jpeg_type, qtables, dri, scan_data):
    # type: (int, int, int, bytes, int, bytes) -> bytes
    """Build a complete JPEG file from RFC 2435 RTP/MJPEG components.

    Args:
        width:     Image width in pixels
        height:    Image height in pixels
        jpeg_type: JPEG type from RTP header (0/1 = YUV 4:2:2, 64/65 = with restart)
        qtables:   Raw quantization table bytes (64 per table, typically 128 = luma+chroma)
        dri:       Restart interval (0 = none)
        scan_data: JPEG entropy-coded scan data
    """
    buf = bytearray()

    # SOI
    buf.extend(b"\xff\xd8")

    # APP0 (JFIF — optional but some decoders expect it)
    # Skipped — keeps frames small

    # DQT (one or two 64-byte tables)
    n_tables = len(qtables) // 64
    for i in range(n_tables):
        table = qtables[i * 64:(i + 1) * 64]
        # FF DB  00 43  (0x00 | table_id)  <64 bytes>
        buf.extend(b"\xff\xdb")
        buf.extend(struct.pack(">H", 2 + 1 + 64))  # length
        buf.append(i)  # precision=0 (8-bit) | table_id
        buf.extend(table)

    # SOF0 (baseline DCT)
    # Determine subsampling from jpeg_type (RFC 2435 §3.1.3)
    # type 0/64: YUV 4:2:2  type 1/65: YUV 4:2:0
    base_type = jpeg_type & 0x3F  # strip restart marker bit
    if base_type == 0:
        # 4:2:2 — H1=2,V1=1  H2=1,V2=1  H3=1,V3=1
        components = bytes([0x01, 0x21, 0x00,
                            0x02, 0x11, 0x01,
                            0x03, 0x11, 0x01])
    else:
        # 4:2:0 — H1=2,V1=2  H2=1,V2=1  H3=1,V3=1
        components = bytes([0x01, 0x22, 0x00,
                            0x02, 0x11, 0x01,
                            0x03, 0x11, 0x01])
    buf.extend(b"\xff\xc0")
    buf.extend(struct.pack(">H", 2 + 1 + 2 + 2 + 1 + len(components)))
    buf.append(8)  # precision = 8 bits
    buf.extend(struct.pack(">HH", height, width))
    buf.append(3)  # number of components
    buf.extend(components)

    # DHT (4 tables: luma DC, luma AC, chroma DC, chroma AC)
    for table_class, table_id, table_data in [
        (0, 0, _DHT_LUM_DC),
        (1, 0, _DHT_LUM_AC),
        (0, 1, _DHT_CHR_DC),
        (1, 1, _DHT_CHR_AC),
    ]:
        buf.extend(b"\xff\xc4")
        buf.extend(struct.pack(">H", 2 + 1 + len(table_data)))
        buf.append((table_class << 4) | table_id)
        buf.extend(table_data)

    # DRI (restart interval, if type >= 64)
    if dri > 0:
        buf.extend(b"\xff\xdd")
        buf.extend(struct.pack(">H", 4))  # length = 4
        buf.extend(struct.pack(">H", dri))

    # SOS (start of scan)
    sos_data = bytes([0x01, 0x00,   # Y  -> DC=0 AC=0
                      0x02, 0x11,   # Cb -> DC=1 AC=1
                      0x03, 0x11])  # Cr -> DC=1 AC=1
    buf.extend(b"\xff\xda")
    buf.extend(struct.pack(">H", 2 + 1 + len(sos_data) + 3))
    buf.append(3)  # number of components
    buf.extend(sos_data)
    buf.extend(bytes([0x00, 0x3F, 0x00]))  # Ss=0, Se=63, Ah=0/Al=0

    # Scan data
    buf.extend(scan_data)

    # EOI
    buf.extend(b"\xff\xd9")

    return bytes(buf)


class RtspVideoProtocolAdapter:
    """RTSP/RTP MJPEG video adapter for lxPro-family drones.

    Negotiates an RTSP session (DESCRIBE/SETUP/PLAY), receives RTP
    packets with RFC 2435 MJPEG payload, reassembles complete JPEG
    frames, and queues them as VideoFrame objects.
    """

    def __init__(
        self,
        drone_ip,           # type: str
        video_port=7070,    # type: int
        control_port=7099,  # type: int
        bind_ip="",         # type: str
        rtsp_path="/webcam",  # type: str
        debug=False,        # type: bool
        **kwargs
    ):
        self.drone_ip = drone_ip
        self.video_port = video_port
        self.control_port = control_port
        self.bind_ip = bind_ip
        self.rtsp_path = rtsp_path

        self._debug = debug
        self._dbg = (lambda *a, **k: print(*a, **k)) if debug else (lambda *a, **k: None)

        # Threading
        self._running = False
        self._rx_thread = None          # type: Optional[threading.Thread]
        self._frame_q = queue.Queue(maxsize=4)  # type: queue.Queue

        # Stats
        self._frame_count = 0
        self.frames_ok = 0
        self.frames_dropped = 0
        self.bytes_rx = 0
        self._last_frame_time = 0.0
        self._stall_timeout = 15.0
        self._stats_time = time.time()
        self._stats_frames = 0
        self._stats_bytes = 0

        self._dbg("[rtsp-video] Adapter created  drone=%s:%d  bind=%s  path=%s"
                  % (drone_ip, video_port, bind_ip or "*", rtsp_path))

    # ── lifecycle (called by VideoReceiverService) ──

    def start(self):
        # type: () -> None
        if self._running:
            return
        self._running = True
        self._rx_thread = threading.Thread(
            target=self._session_loop, daemon=True, name="RtspVideoRx",
        )
        self._rx_thread.start()
        print("[rtsp-video] Started (drone=%s:%d%s)" %
              (self.drone_ip, self.video_port, self.rtsp_path))

    def stop(self):
        # type: () -> None
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=3.0)
        print("[rtsp-video] Stopped  ok=%d  dropped=%d  bytes=%d" %
              (self.frames_ok, self.frames_dropped, self.bytes_rx))

    def is_running(self):
        # type: () -> bool
        if not self._running or self._rx_thread is None or not self._rx_thread.is_alive():
            return False
        if self._last_frame_time > 0 and (time.time() - self._last_frame_time) > self._stall_timeout:
            print("[rtsp-video] Stall detected (%.0fs), stopping for reconnect" % self._stall_timeout)
            self._running = False
            return False
        return True

    def get_frame(self, timeout=1.0):
        # type: (float) -> Optional[VideoFrame]
        try:
            return self._frame_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_packets(self):
        # type: () -> List[bytes]
        return []

    # ── keepalive stubs (RTSP session is kept alive via heartbeat) ──

    def start_keepalive(self, interval=1.0):
        # type: (float) -> None
        pass

    def stop_keepalive(self):
        # type: () -> None
        pass

    # ── internal: RTSP + RTP session ──

    def _send_camera_init(self):
        # type: () -> None
        """Send E88Pro init commands on UDP to wake up the camera hardware."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)
            if self.bind_ip:
                sock.bind((self.bind_ip, 0))
            for cmd in [bytes([0x01, 0x01]), bytes([0x08, 0x01]),
                        bytes([0x06, 0x01])]:
                sock.sendto(cmd, (self.drone_ip, self.control_port))
                time.sleep(0.1)
            sock.close()
            self._dbg("[rtsp-video] Sent camera init to %s:%d"
                      % (self.drone_ip, self.control_port))
        except OSError as e:
            print("[rtsp-video] Camera init error: %s" % e)

    def _rtsp_exchange(self, sock, request):
        # type: (socket.socket, str) -> str
        """Send an RTSP request and return the response text."""
        sock.send(request.encode("ascii"))
        time.sleep(0.2)
        try:
            data = sock.recv(4096)
            return data.decode("ascii", errors="replace")
        except socket.timeout:
            return ""

    def _session_loop(self):
        # type: () -> None
        """Main loop: init camera, establish RTSP session, receive RTP, reconnect."""
        while self._running:
            self._send_camera_init()
            time.sleep(0.3)

            try:
                self._run_rtsp_session()
            except Exception as e:
                if self._running:
                    print("[rtsp-video] Session error: %s" % e)

            if self._running:
                print("[rtsp-video] Session ended, reconnecting in 2s...")
                time.sleep(2.0)

        self._dbg("[rtsp-video] Session thread stopped")

    def _run_rtsp_session(self):
        # type: () -> None
        """Run one complete RTSP session: DESCRIBE, SETUP, PLAY, receive RTP."""
        rtsp_url = "rtsp://%s:%d%s" % (self.drone_ip, self.video_port,
                                        self.rtsp_path)

        # Create RTP UDP socket
        rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if sys.platform == "win32":
            SIO_UDP_CONNRESET = 0x9800000C
            ret = ctypes.c_ulong(0)
            ctypes.windll.ws2_32.WSAIoctl(
                rtp_sock.fileno(), SIO_UDP_CONNRESET,
                b"\x00\x00\x00\x00", 4, None, 0,
                ctypes.byref(ret), None, None)
        rtp_sock.bind(("0.0.0.0", 0))
        rtp_port = rtp_sock.getsockname()[1]
        rtp_sock.settimeout(2.0)

        # RTSP signaling TCP socket
        rtsp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rtsp_sock.settimeout(5.0)
        if self.bind_ip:
            rtsp_sock.bind((self.bind_ip, 0))

        try:
            rtsp_sock.connect((self.drone_ip, self.video_port))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print("[rtsp-video] RTSP connect failed: %s" % e)
            rtp_sock.close()
            rtsp_sock.close()
            return

        cseq = 1
        try:
            # DESCRIBE
            resp = self._rtsp_exchange(rtsp_sock,
                "DESCRIBE %s RTSP/1.0\r\n"
                "CSeq: %d\r\n"
                "Accept: application/sdp\r\n\r\n" % (rtsp_url, cseq))
            cseq += 1
            if "200" not in resp.split("\r\n")[0]:
                print("[rtsp-video] DESCRIBE failed: %s" %
                      resp.split("\r\n")[0])
                return

            # Parse SDP for control track
            track = "track0"  # default
            for line in resp.split("\r\n"):
                if line.startswith("a=control:") and line.strip() != "a=control:*":
                    track = line.split(":", 1)[1].strip()

            # SETUP (RTP/AVP over UDP)
            setup_url = "%s/%s" % (rtsp_url, track)
            resp = self._rtsp_exchange(rtsp_sock,
                "SETUP %s RTSP/1.0\r\n"
                "CSeq: %d\r\n"
                "Transport: RTP/AVP;unicast;client_port=%d-%d\r\n\r\n"
                % (setup_url, cseq, rtp_port, rtp_port + 1))
            cseq += 1

            if "200" not in resp.split("\r\n")[0]:
                print("[rtsp-video] SETUP failed: %s" %
                      resp.split("\r\n")[0])
                return

            # Extract session ID and server RTP port
            session_id = ""
            server_rtp_port = 0
            for line in resp.split("\r\n"):
                low = line.lower()
                if low.startswith("session:"):
                    session_id = line.split(":", 1)[1].strip().split(";")[0]
                if low.startswith("transport:"):
                    m = re.search(r"server_port=(\d+)", line)
                    if m:
                        server_rtp_port = int(m.group(1))

            if not session_id:
                print("[rtsp-video] No session ID in SETUP response")
                return

            print("[rtsp-video] RTSP session=%s, server_rtp=%d, client_rtp=%d"
                  % (session_id[:16], server_rtp_port, rtp_port))

            # Hole-punch: send dummy packet to open firewall / NAT
            if server_rtp_port:
                rtp_sock.sendto(b"\x00\x00\x00\x00",
                                (self.drone_ip, server_rtp_port))

            # PLAY
            resp = self._rtsp_exchange(rtsp_sock,
                "PLAY %s RTSP/1.0\r\n"
                "CSeq: %d\r\n"
                "Session: %s\r\n"
                "Range: npt=0.000-\r\n\r\n"
                % (rtsp_url, cseq, session_id))
            cseq += 1

            if "200" not in resp.split("\r\n")[0]:
                print("[rtsp-video] PLAY failed: %s" %
                      resp.split("\r\n")[0])
                return

            print("[rtsp-video] PLAY started, receiving RTP...")

            # Receive RTP packets and reassemble JPEG frames
            self._receive_rtp(rtp_sock, rtsp_sock, session_id, cseq,
                              server_rtp_port)

            # TEARDOWN
            self._rtsp_exchange(rtsp_sock,
                "TEARDOWN %s RTSP/1.0\r\n"
                "CSeq: %d\r\n"
                "Session: %s\r\n\r\n"
                % (rtsp_url, cseq, session_id))

        finally:
            try:
                rtsp_sock.close()
            except Exception:
                pass
            try:
                rtp_sock.close()
            except Exception:
                pass

    def _receive_rtp(self, rtp_sock, rtsp_sock, session_id, cseq,
                     server_rtp_port):
        # type: (socket.socket, socket.socket, str, int, int) -> None
        """Receive RTP packets and reassemble RFC 2435 MJPEG frames."""
        frame_buf = bytearray()
        frame_ts = None       # type: Optional[int]
        frame_width = 0
        frame_height = 0
        frame_type = 0
        frame_dri = 0
        frame_qtables = b""   # type: bytes
        last_keepalive = time.time()

        while self._running:
            # Periodic camera keepalive (every 2s)
            now = time.time()
            if now - last_keepalive > 2.0:
                last_keepalive = now
                self._send_camera_init()
                # Re-punch in case NAT/firewall state expired
                if server_rtp_port:
                    try:
                        rtp_sock.sendto(b"\x00\x00\x00\x00",
                                        (self.drone_ip, server_rtp_port))
                    except OSError:
                        pass
                self._log_stats()

            try:
                data, addr = rtp_sock.recvfrom(65536)
            except socket.timeout:
                self._log_stats()
                continue
            except (ConnectionResetError, OSError):
                break

            if len(data) < 12:
                continue

            self.bytes_rx += len(data)
            self._stats_bytes += len(data)

            # Parse RTP header
            pt = data[1] & 0x7F
            marker = (data[1] >> 7) & 1
            seq = struct.unpack(">H", data[2:4])[0]
            ts = struct.unpack(">I", data[4:8])[0]
            payload = data[12:]

            if pt != 26 or len(payload) < 8:
                continue

            # RFC 2435 JPEG header (8 bytes)
            frag_offset = ((payload[1] << 16) | (payload[2] << 8)
                           | payload[3])
            jpeg_type = payload[4]
            q_value = payload[5]
            w8 = payload[6]
            h8 = payload[7]
            hdr_len = 8

            # Restart marker header (type >= 64)
            dri = 0
            if jpeg_type >= 64 and len(payload) > hdr_len + 4:
                dri = struct.unpack(">H", payload[hdr_len:hdr_len + 2])[0]
                hdr_len += 4

            # Quantization tables (Q >= 128, first fragment only)
            qtables = b""
            if q_value >= 128 and frag_offset == 0:
                if len(payload) > hdr_len + 4:
                    qt_length = struct.unpack(
                        ">H", payload[hdr_len + 2:hdr_len + 4])[0]
                    hdr_len += 4
                    if qt_length > 0 and len(payload) >= hdr_len + qt_length:
                        qtables = bytes(payload[hdr_len:hdr_len + qt_length])
                        hdr_len += qt_length

            jpeg_data = bytes(payload[hdr_len:])

            # New frame (frag_offset == 0)?
            if frag_offset == 0:
                frame_buf = bytearray()
                frame_ts = ts
                frame_width = w8 * 8
                frame_height = h8 * 8
                frame_type = jpeg_type
                frame_dri = dri
                if qtables:
                    frame_qtables = qtables

            # Append scan data
            frame_buf.extend(jpeg_data)

            # End of frame (marker bit set)
            if marker and len(frame_buf) > 0 and frame_qtables:
                jpeg = _build_jpeg(
                    frame_width, frame_height, frame_type,
                    frame_qtables, frame_dri, bytes(frame_buf))
                self._emit_frame(jpeg)

    def _emit_frame(self, jpeg_data):
        # type: (bytes) -> None
        """Queue a complete JPEG frame."""
        self._last_frame_time = time.time()
        self._frame_count += 1
        self._stats_frames += 1

        frame = VideoFrame(frame_id=self._frame_count, data=jpeg_data)
        self.frames_ok += 1

        try:
            self._frame_q.put(frame, timeout=0.1)
        except queue.Full:
            try:
                self._frame_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_q.put_nowait(frame)
            except queue.Full:
                self.frames_dropped += 1

        if self.frames_ok <= 3 or self.frames_ok % 100 == 0:
            print("[rtsp-video] Frame %d: %d bytes (%dx%d)  ok=%d" %
                  (self._frame_count, len(jpeg_data),
                   0, 0, self.frames_ok))

    def _log_stats(self):
        # type: () -> None
        now = time.time()
        if now - self._stats_time >= 5.0:
            elapsed = now - self._stats_time
            fps = self._stats_frames / elapsed if elapsed > 0 else 0
            kbps = self._stats_bytes / elapsed / 1024 if elapsed > 0 else 0
            print("[rtsp-video] STATS: %.1f fps | %.1f KB/s | ok=%d dropped=%d"
                  % (fps, kbps, self.frames_ok, self.frames_dropped))
            self._stats_frames = 0
            self._stats_bytes = 0
            self._stats_time = now
