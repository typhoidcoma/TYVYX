"""Flask web front-end packaged under `teky`.

Provides a simple UI that shows a live MJPEG video feed and a dropdown
of available WiFi networks. Users can select a network (the drone)
and request the host to connect to it. This is a development/demo UI
— network connection actions use platform tooling and require
appropriate privileges on the host.
"""

from flask import Flask, render_template, Response, request, jsonify
import threading
import time
import cv2
from typing import Optional, Tuple

from .video_stream import OpenCVVideoStream
from .network_diagnostics import DroneNetworkDiagnostics
import shutil
import subprocess


app = Flask(__name__, template_folder="templates")

# Shared diagnostics instance for system operations and logging
diagnostics = DroneNetworkDiagnostics()

# Shared video stream instance. We'll lazily initialize when first requested.
_video_stream = None
_video_lock = threading.Lock()
_video_source = None
_last_successful_ports = None


def get_video_stream() -> OpenCVVideoStream:
    global _video_stream
    with _video_lock:
        if _video_stream is None:
            # Default RTSP source — drone default IP and port
            source = _video_source or f"rtsp://{diagnostics.DRONE_IP}:{diagnostics.RTSP_PORT}/webcam"
            _video_stream = OpenCVVideoStream(source)
            started = _video_stream.start(timeout=3.0)
            diagnostics.log(f"Video stream started: {started} (source={source})")
        return _video_stream


def set_video_source(feed_type: str) -> Tuple[bool, str]:
    """Set the global video source according to a feed type and restart stream.

    feed_type: one of 'rtsp', 'http_mjpeg', 'local0'
    Returns (started, message).
    """
    global _video_stream, _video_source
    with _video_lock:
        # stop existing stream
        if _video_stream:
            try:
                _video_stream.stop()
            except Exception:
                pass
            _video_stream = None

        # Map feed type to source
        try:
            if feed_type.startswith('rtsp://') or feed_type.startswith('http://'):
                # explicit full URL provided
                src = feed_type
            elif feed_type == 'rtsp':
                src = f"rtsp://{diagnostics.DRONE_IP}:{diagnostics.RTSP_PORT}/webcam"
            elif feed_type == 'http_mjpeg':
                src = f"http://{diagnostics.DRONE_IP}:{diagnostics.RTSP_PORT}/mjpeg"
            elif feed_type.startswith('local'):
                # expected like local0, local1
                try:
                    idx = int(feed_type.replace('local', ''))
                except Exception:
                    idx = 0
                src = idx
            else:
                return False, f"Unknown feed type: {feed_type}"

            _video_source = src
            _video_stream = OpenCVVideoStream(src)
            started = _video_stream.start(timeout=3.0)
            diagnostics.log(f"set_video_source -> started={started} src={src}")
            return bool(started), f"started={started} src={src}"
        except Exception as e:
            return False, str(e)


@app.route("/")
def home():
    """Render the main UI page."""
    return render_template("index.html")


@app.route("/networks")
def networks():
    """Return JSON list of nearby WiFi networks (SSID strings)."""
    try:
        results = diagnostics.scan_wifi_networks()
        # Normalize to simple list of SSIDs where possible
        ssids = []
        for r in results:
            ssid = r.get("ssid") if isinstance(r, dict) else None
            if ssid:
                ssids.append({"ssid": ssid, "info": r})
        return jsonify({"networks": ssids})
    except Exception as e:
        diagnostics.log(f"Error scanning networks: {e}")
        return jsonify({"networks": [], "error": str(e)})


def _connect_platform(ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
    """Attempt to connect to the given SSID using platform tooling.

    Returns (success, message). This uses best-effort methods and may
    require elevated privileges depending on the host OS.
    """
    system = diagnostics and diagnostics.log and __import__("platform").system().lower()
    try:
        import subprocess
        import shutil

        diagnostics.log(f"Attempting to connect to SSID: {ssid} (platform={system})")

        # Linux: nmcli
        if system == "linux" and shutil.which("nmcli"):
            cmd = ["nmcli", "device", "wifi", "connect", ssid]
            if password:
                cmd.extend(["password", password])
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if out.returncode == 0:
                return True, out.stdout.strip()
            return False, out.stderr.strip() or out.stdout.strip()

        # macOS: networksetup
        if system == "darwin" and shutil.which("networksetup"):
            # networksetup expects an interface name; try to find 'Wi-Fi'
            iface = "Wi-Fi"
            cmd = ["networksetup", "-setairportnetwork", iface, ssid]
            if password:
                cmd.append(password)
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if out.returncode == 0:
                return True, out.stdout.strip()
            return False, out.stderr.strip() or out.stdout.strip()

        # Windows: netsh (best-effort)
        if system == "windows" and shutil.which("netsh"):
            # Try the simple connect command; may require a saved profile
            cmd = ["netsh", "wlan", "connect", f"ssid={ssid}"]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if out.returncode == 0:
                return True, out.stdout.strip()
            # If failed, return stderr for diagnostics
            return False, out.stderr.strip() or out.stdout.strip()

        return False, f"No supported connection tool found for platform {system}"
    except Exception as e:
        return False, str(e)


def wait_for_network_ready(timeout: int = 20, interval: float = 1.0) -> bool:
    """Wait until diagnostics.test_ping() returns True or timeout.

    Returns True if ping succeeded within timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            if diagnostics.test_ping():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def get_signal_info(ssid: str = None) -> dict:
    """Attempt to read signal strength / connection info from OS tools.

    This is best-effort and may return empty dict on failure.
    """
    info = {}
    system = __import__("platform").system().lower()
    try:
        if system == 'windows' and shutil.which('netsh'):
            out = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, text=True, timeout=5)
            text = out.stdout or out.stderr or ''
            for line in text.splitlines():
                if ':' in line:
                    k, v = [p.strip() for p in line.split(':', 1)]
                    info[k.lower().replace(' ', '_')] = v
            return info

        if system == 'linux' and shutil.which('nmcli'):
            out = subprocess.run(['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL', 'dev', 'wifi'], capture_output=True, text=True, timeout=5)
            text = out.stdout or out.stderr or ''
            for line in text.splitlines():
                parts = line.split(':')
                if len(parts) >= 3:
                    in_use, ss, sig = parts[0], parts[1], parts[2]
                    if in_use == '*' or (ssid and ss == ssid):
                        info['ssid'] = ss
                        info['signal'] = sig
                        break
            return info
    except Exception:
        pass
    return info


def try_start_source(src, timeout: float = 3.0) -> bool:
    """Try to start an OpenCVVideoStream for `src` and return True if opened."""
    try:
        s = OpenCVVideoStream(src)
        ok = s.start(timeout=timeout)
        if not ok:
            try:
                s.stop()
            except Exception:
                pass
            return False
        # If started, stop and return success
        try:
            s.stop()
        except Exception:
            pass
        return True
    except Exception:
        return False


def probe_video_feeds(ip: str = None, ports: Optional[list] = None, timeout_per: float = 2.0) -> list:
    """Probe a set of likely video feed URLs on the given IP.

    Returns a list of dicts with attempt results.
    """
    results = []
    ip = ip or diagnostics.DRONE_IP
    # candidate patterns
    ports = ports or [diagnostics.RTSP_PORT, 554, 8554]
    rtsp_paths = ["/webcam", "/live", "/stream", ""]
    http_paths = ["/mjpeg", "/video", "/stream"]

    # Try RTSP combinations
    for p in ports:
        for path in rtsp_paths:
            url = f"rtsp://{ip}:{p}{path}"
            ok = try_start_source(url, timeout=timeout_per)
            results.append({"url": url, "ok": ok})
            if ok:
                return results

    # Try HTTP MJPEG candidates
    for p in [80, 8080, diagnostics.RTSP_PORT]:
        for path in http_paths:
            url = f"http://{ip}:{p}{path}"
            ok = try_start_source(url, timeout=timeout_per)
            results.append({"url": url, "ok": ok})
            if ok:
                return results

    return results


@app.route("/connect", methods=["POST"])
def connect():
    """Connect the host to the selected SSID."""
    data = request.json or {}
    ssid = data.get("ssid")
    password = data.get("password")
    if not ssid:
        return jsonify({"success": False, "message": "No SSID provided"}), 400

    # Optional feed_type may be provided by front-end
    feed_type = data.get("feed_type")

    success, msg = _connect_platform(ssid, password)
    diagnostics.log(f"Connect result: initial={success} msg={msg}")

    # verify association to the requested SSID before proceeding
    verified = False
    if success:
        diagnostics.log(f"Verifying association to SSID '{ssid}'...")
        try:
            verified = verify_connected_to_ssid(ssid, timeout=20)
        except Exception as e:
            diagnostics.log(f"verify_connected_to_ssid error: {e}")

        if not verified:
            diagnostics.log(f"Failed to verify association to SSID '{ssid}'")
            # treat as failure for downstream actions
            success = False
            msg = f"Failed to associate to SSID {ssid}"

    response = {"success": success, "message": msg, "verified": verified}

    # If connection was successful and a feed type was provided, attempt to set it
    if success and feed_type and feed_type != 'auto':
        started, start_msg = set_video_source(feed_type)
        diagnostics.log(f"Auto-start video after connect: started={started} msg={start_msg}")
        response.update({"video_started": started, "video_msg": start_msg})

    # If probe requested (or feed_type=='auto'), perform network quality checks and probe candidate feeds
    probe_requested = data.get('probe', False) or (feed_type == 'auto')
    if success and probe_requested:
        diagnostics.log("Starting post-connect verification and feed probing...")
        net_ready = wait_for_network_ready(timeout=20)
        signal = get_signal_info(ssid)
        response.update({"network_ready": net_ready, "signal_info": signal})

        if net_ready:
            # honor user-provided trusted ports if present
            ports_param = data.get('ports')
            ports_list = None
            if ports_param:
                try:
                    ports_list = [int(p) for p in ports_param]
                except Exception:
                    ports_list = None

            probe_results = probe_video_feeds(ports=ports_list)
            # If probe found a working feed, auto-start it
            selected = None
            for p in probe_results:
                if p.get('ok'):
                    selected = p['url']
                    break

            if selected:
                # start and set as global source
                ok, msg2 = set_video_source(selected)
                diagnostics.log(f"Auto-start selected feed: ok={ok} src={selected}")
                # remember port(s) used for this successful feed
                try:
                    import re
                    m = re.search(r":(\d+)(?:/|$)", selected)
                    if m:
                        global _last_successful_ports
                        _last_successful_ports = [int(m.group(1))]
                except Exception:
                    pass

                response.update({"probe_results": probe_results, "selected_feed": selected, "selected_ok": ok, "selected_msg": msg2})
            else:
                response.update({"probe_results": probe_results})
        else:
            response.update({"probe_results": [], "selected_feed": None})

    return jsonify(response)


def gen_mjpeg(stream: OpenCVVideoStream):
    """Generator yielding MJPEG frames for Response streaming."""
    while True:
        ok, frame = stream.read()
        if not ok or frame is None:
            time.sleep(0.05)
            continue
        # Encode to JPEG
        ret, jpeg = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        chunk = jpeg.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + chunk + b'\r\n')


@app.route('/video_feed')
def video_feed():
    """MJPEG video feed endpoint."""
    stream = get_video_stream()
    return Response(gen_mjpeg(stream), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/set_feed', methods=['POST'])
def set_feed():
    data = request.json or {}
    feed_type = data.get('feed_type')
    if not feed_type:
        return jsonify({'success': False, 'message': 'No feed_type provided'}), 400
    ok, msg = set_video_source(feed_type)
    # remember port if a full URL was provided and started OK
    if ok and isinstance(feed_type, str) and (feed_type.startswith('rtsp://') or feed_type.startswith('http://')):
        try:
            import re
            m = re.search(r":(\d+)(?:/|$)", feed_type)
        except Exception:
            m = None
        try:
            if m:
                global _last_successful_ports
                _last_successful_ports = [int(m.group(1))]
        except Exception:
            pass
    return jsonify({'success': ok, 'message': msg})


@app.route('/probe', methods=['GET'])
def probe():
    """Run feed probing and return results (JSON). Optional query param `ip`."""
    ip = request.args.get('ip')
    ports_arg = request.args.get('ports')
    ports_list = None
    if ports_arg:
        try:
            ports_list = [int(p.strip()) for p in ports_arg.split(',') if p.strip()]
        except Exception:
            ports_list = None
    try:
        diagnostics.log(f"Running feed probe for ip={ip or diagnostics.DRONE_IP}")
        results = probe_video_feeds(ip=ip, ports=ports_list)
        return jsonify({'results': results})
    except Exception as e:
        diagnostics.log(f"Probe endpoint failed: {e}")
        return jsonify({'results': [], 'error': str(e)}), 500


@app.route('/video_status')
def video_status():
    """Return JSON status of the current video stream."""
    try:
        with _video_lock:
            running = bool(_video_stream and getattr(_video_stream, 'is_opened', lambda: False)())
            source = globals().get('_video_source', None)
        return jsonify({'running': running, 'source': str(source) if source is not None else None})
    except Exception as e:
        diagnostics.log(f"video_status error: {e}")
        return jsonify({'running': False, 'source': None, 'error': str(e)})


@app.route('/suggested_ports')
def suggested_ports():
    """Return suggested ports: last successful ports if known, otherwise platform defaults."""
    try:
        global _last_successful_ports
        if _last_successful_ports:
            return jsonify({'ports': _last_successful_ports})

        system = __import__('platform').system().lower()
        if system == 'windows':
            defaults = [7070, 554, 8554]
        elif system == 'linux' or system == 'darwin':
            defaults = [554, 7070, 8554]
        else:
            defaults = [7070, 554]
        return jsonify({'ports': defaults})
    except Exception as e:
        diagnostics.log(f"suggested_ports error: {e}")
        return jsonify({'ports': []})


if __name__ == "__main__":
    # Development server only. Use a production WSGI server for real deployments.
    app.run(host="0.0.0.0", port=5000, debug=True)
