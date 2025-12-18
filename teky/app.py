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
try:
    # Prefer advanced controller when available
    from .drone_controller_advanced import TEKYDroneControllerAdvanced as _PreferredController
except Exception:
    from .drone_controller import TEKYDroneController as _PreferredController
import shutil
import subprocess
import logging
import json
from pathlib import Path


app = Flask(__name__, template_folder="templates")
app.logger.setLevel(logging.INFO)

# Shared video stream instance. We'll lazily initialize when first requested.
_video_stream = None
_video_lock = threading.Lock()
_video_source = None
_last_successful_ports = None
# Drone controller singleton
_drone_controller = None


# Config persistence
_config_path = Path("teky_config.json")

# Sniffer job tracking
_sniff_jobs = {}
_sniff_job_counter = 0
_sniff_jobs_path = Path("sniffs")
_sniff_jobs_path.mkdir(exist_ok=True)


def _load_config():
    global _video_source, _last_successful_ports
    try:
        if _config_path.exists():
            with open(_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            _video_source = cfg.get("video_source", _video_source)
            _last_successful_ports = cfg.get("last_successful_ports", _last_successful_ports)
            # Apply drone network settings if present
            drone_cfg = cfg.get("drone", {}) or {}
            try:
                d = _drone_controller
                if d is not None:
                    d.DRONE_IP = drone_cfg.get("ip", d.DRONE_IP)
                    d.UDP_PORT = int(drone_cfg.get("udp_port", d.UDP_PORT))
                    d.RTSP_PORT = int(drone_cfg.get("rtsp_port", d.RTSP_PORT))
            except Exception:
                pass
            app.logger.info(f"Loaded config from {_config_path}")
    except Exception as e:
        app.logger.warning(f"Failed to load config: {e}")


def _save_config():
    try:
        # include drone network settings if controller exists
        drone_cfg = {}
        try:
            d = _drone_controller
            if d is not None:
                drone_cfg = {"ip": d.DRONE_IP, "udp_port": int(d.UDP_PORT), "rtsp_port": int(d.RTSP_PORT)}
        except Exception:
            drone_cfg = {}

        cfg = {"video_source": _video_source, "last_successful_ports": _last_successful_ports, "drone": drone_cfg}
        with open(_config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        app.logger.info(f"Saved config to {_config_path}")
    except Exception as e:
        app.logger.warning(f"Failed to save config: {e}")


# load persisted config if present
_load_config()


def get_drone_controller():
    global _drone_controller
    if _drone_controller is None:
        # Instantiate preferred controller (advanced if available)
        try:
            _drone_controller = _PreferredController()
        except Exception:
            # last-resort fallback to basic controller class
            from .drone_controller import TEKYDroneController
            _drone_controller = TEKYDroneController()

        # apply persisted drone config if any
        try:
            if _config_path.exists():
                with open(_config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                drone_cfg = cfg.get('drone', {}) or {}
                _drone_controller.DRONE_IP = drone_cfg.get('ip', _drone_controller.DRONE_IP)
                _drone_controller.UDP_PORT = int(drone_cfg.get('udp_port', _drone_controller.UDP_PORT))
                _drone_controller.RTSP_PORT = int(drone_cfg.get('rtsp_port', _drone_controller.RTSP_PORT))
        except Exception:
            pass
    return _drone_controller


def get_video_stream() -> OpenCVVideoStream:
    global _video_stream
    with _video_lock:
        if _video_stream is None:
            # Default RTSP source — drone default IP and port
            controller = get_drone_controller()
            source = _video_source or f"rtsp://{controller.DRONE_IP}:{controller.RTSP_PORT}/webcam"
            # prefer TCP for RTSP streams to avoid Unsupported Transport errors
            if isinstance(source, str) and source.lower().startswith('rtsp://'):
                _video_stream = OpenCVVideoStream(source, prefer_tcp=True, max_retries=5, retry_delay=1.5, buffer_size=1)
            else:
                _video_stream = OpenCVVideoStream(source)
            started = _video_stream.start(timeout=6.0)
            app.logger.info(f"Video stream started: {started} (source={source})")
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
                controller = get_drone_controller()
                src = f"rtsp://{controller.DRONE_IP}:{controller.RTSP_PORT}/webcam"
            elif feed_type == 'http_mjpeg':
                controller = get_drone_controller()
                src = f"http://{controller.DRONE_IP}:{controller.RTSP_PORT}/mjpeg"
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
            # prefer TCP for RTSP streams to avoid Unsupported Transport errors
            if isinstance(src, str) and src.lower().startswith('rtsp://'):
                _video_stream = OpenCVVideoStream(src, prefer_tcp=True, max_retries=5, retry_delay=1.5, buffer_size=1)
            else:
                _video_stream = OpenCVVideoStream(src)
            started = _video_stream.start(timeout=6.0)
            app.logger.info(f"set_video_source -> started={started} src={src}")
            if started:
                try:
                    _save_config()
                except Exception:
                    pass
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
        app.logger.info("/networks endpoint disabled in simplified app")
        return jsonify({"networks": []})
    except Exception as e:
        app.logger.error(f"Error scanning networks: {e}")
        return jsonify({"networks": [], "error": str(e)})


def _connect_platform(ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
    """Attempt to connect to the given SSID using platform tooling.

    Returns (success, message). This uses best-effort methods and may
    require elevated privileges depending on the host OS.
    """
    # Network-based connection disabled in simplified app
    return False, "platform connect disabled"


def wait_for_network_ready(timeout: int = 20, interval: float = 1.0) -> bool:
    """Wait until diagnostics.test_ping() returns True or timeout.

    Returns True if ping succeeded within timeout.
    """
    # Network readiness checks removed in simplified app
    return False


def get_signal_info(ssid: str = None) -> dict:
    """Attempt to read signal strength / connection info from OS tools.

    This is best-effort and may return empty dict on failure.
    """
    # Signal info not available in simplified app
    return {}


def verify_connected_to_ssid(ssid: str, timeout: int = 20, interval: float = 1.0) -> bool:
    """Best-effort verification that the host is associated to `ssid`.

    Uses OS-specific tooling (netsh/nmcli/airport) and repeated checks
    until `timeout` seconds elapse. Returns True if association detected.
    """
    app.logger.info(f"Verifying host association to SSID '{ssid}' (timeout={timeout})")
    system = __import__("platform").system().lower()
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Windows
            if system == 'windows' and shutil.which('netsh'):
                out = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, text=True, timeout=5)
                text = out.stdout or out.stderr or ''
                if ssid in text:
                    app.logger.info(f"verify: found ssid in netsh output")
                    return True

            # Linux
            if system == 'linux' and shutil.which('nmcli'):
                out = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'], capture_output=True, text=True, timeout=5)
                text = out.stdout or out.stderr or ''
                for line in text.splitlines():
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[0] == 'yes' and parts[1] == ssid:
                        app.logger.info("verify: nmcli reports active connection to ssid")
                        return True

            # macOS
            if system == 'darwin':
                # try airport
                try:
                    airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
                    if shutil.which(airport) or Path(airport).exists():
                        out = subprocess.run([airport, '-I'], capture_output=True, text=True, timeout=5)
                        text = out.stdout or out.stderr or ''
                        if ssid in text:
                            app.logger.info('verify: airport reports association')
                            return True
                except Exception:
                    pass

            # Generic psutil/netifaces fallback: check connection list
            try:
                import importlib as _importlib
                ps = _importlib.import_module('psutil')
                # On many platforms the active SSID isn't exposed; skip if unavailable
            except Exception:
                ps = None

        except Exception as e:
            app.logger.error(f"verify_connected_to_ssid check error: {e}")

        time.sleep(interval)

    app.logger.info(f"verify_connected_to_ssid: timed out waiting for SSID {ssid}")
    return False


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
    controller = get_drone_controller()
    ip = ip or controller.DRONE_IP
    # candidate patterns
    ports = ports or [controller.RTSP_PORT, 554, 8554]
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
    for p in [80, 8080, controller.RTSP_PORT]:
        for path in http_paths:
            url = f"http://{ip}:{p}{path}"
            ok = try_start_source(url, timeout=timeout_per)
            results.append({"url": url, "ok": ok})
            if ok:
                return results

    return results


@app.route("/connect", methods=["POST"])
def connect():
    return jsonify({"success": False, "message": "Connect disabled in simplified app"}), 403


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
        app.logger.info(f"Running feed probe for ip={ip}")
        results = probe_video_feeds(ip=ip, ports=ports_list)
        return jsonify({'results': results})
    except Exception as e:
        app.logger.error(f"Probe endpoint failed: {e}")
        return jsonify({'results': [], 'error': str(e)}), 500


@app.route('/video_status')
def video_status():
    """Return JSON status of the current video stream."""
    try:
        with _video_lock:
            vs = _video_stream
            running = bool(vs and getattr(vs, 'is_opened', lambda: False)())
            source = globals().get('_video_source', None)
            using_ffmpeg = bool(vs and getattr(vs, '_using_ffmpeg', False))
            ff_stderr = None
            try:
                if vs and hasattr(vs, '_ffmpeg_stderr'):
                    ff_stderr = getattr(vs, '_ffmpeg_stderr')
            except Exception:
                ff_stderr = None
        return jsonify({'running': running, 'source': str(source) if source is not None else None, 'using_ffmpeg': using_ffmpeg, 'ffmpeg_stderr': ff_stderr})
    except Exception as e:
        app.logger.error(f"video_status error: {e}")
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
        app.logger.error(f"suggested_ports error: {e}")
        return jsonify({'ports': []})


@app.route('/drone/status')
def drone_status():
    """Return simple status of controller (connected, running video)."""
    try:
        d = get_drone_controller()
        status = {
            'is_connected': bool(getattr(d, 'is_connected', False)),
            'is_running': bool(getattr(d, 'is_running', False)),
            'device_type': getattr(d, 'device_type', None)
        }
        # include controller class name for UI display
        try:
            status['controller_class'] = d.__class__.__name__
        except Exception:
            status['controller_class'] = None
        return jsonify({'ok': True, 'status': status})
    except Exception as e:
        app.logger.error(f"drone_status error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/drone/config', methods=['GET', 'POST'])
def drone_config():
    """GET returns current drone config; POST accepts JSON {ip, udp_port, rtsp_port} and persists it."""
    try:
        d = get_drone_controller()
        if request.method == 'GET':
            return jsonify({'ok': True, 'drone': {'ip': d.DRONE_IP, 'udp_port': int(d.UDP_PORT), 'rtsp_port': int(d.RTSP_PORT)}})

        # POST - update
        data = request.json or {}
        ip = data.get('ip')
        udp = data.get('udp_port')
        rtsp = data.get('rtsp_port')
        if ip:
            d.DRONE_IP = str(ip)
        if udp:
            try:
                d.UDP_PORT = int(udp)
            except Exception:
                pass
        if rtsp:
            try:
                d.RTSP_PORT = int(rtsp)
            except Exception:
                pass

        try:
            _save_config()
        except Exception:
            pass

        return jsonify({'ok': True, 'drone': {'ip': d.DRONE_IP, 'udp_port': int(d.UDP_PORT), 'rtsp_port': int(d.RTSP_PORT)}})
    except Exception as e:
        app.logger.error(f"drone_config error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/sniff/run', methods=['POST'])
def sniff_run():
    """Start a packet sniff capture in background. JSON: {duration, dst, src, port, iface}
    Returns a job id which can be polled via /sniff/status and downloaded when complete.
    """
    global _sniff_job_counter
    data = request.json or {}
    duration = int(data.get('duration', 20))
    dst = data.get('dst')
    src = data.get('src')
    port = data.get('port')
    iface = data.get('iface')

    out_name = f"sniff_{int(time.time())}.pcap"
    out_path = _sniff_jobs_path / out_name

    # prepare arg list
    args = ['python', '-m', 'teky.tools.packet_sniffer', '--duration', str(duration), '--out', str(out_path)]
    if dst:
        args += ['--dst', str(dst)]
    if src:
        args += ['--src', str(src)]
    if port:
        args += ['--port', str(port)]
    if iface:
        args += ['--iface', str(iface)]

    job_id = None
    try:
        _sniff_job_counter += 1
        job_id = str(_sniff_job_counter)
        _sniff_jobs[job_id] = {'status': 'running', 'out': str(out_path), 'started_at': time.time()}

        def _run_capture(job, args, outp):
            try:
                proc = subprocess.run(args, capture_output=True, text=True, check=False)
                if proc.returncode != 0:
                    _sniff_jobs[job]['status'] = 'error'
                    _sniff_jobs[job]['error'] = f'capture process failed: returncode={proc.returncode} stderr={proc.stderr.strip()}'
                    _sniff_jobs[job]['stderr'] = (proc.stderr or '').strip()[:2000]
                    _sniff_jobs[job]['stdout'] = (proc.stdout or '').strip()[:2000]
                    return
                # ensure output file was created
                if not Path(outp).exists():
                    _sniff_jobs[job]['status'] = 'error'
                    _sniff_jobs[job]['error'] = 'capture completed but output file missing'
                    _sniff_jobs[job]['stderr'] = (proc.stderr or '').strip()[:2000]
                    _sniff_jobs[job]['stdout'] = (proc.stdout or '').strip()[:2000]
                    return
                _sniff_jobs[job]['status'] = 'done'
                _sniff_jobs[job]['stderr'] = (proc.stderr or '').strip()[:2000]
                _sniff_jobs[job]['stdout'] = (proc.stdout or '').strip()[:2000]
            except Exception as e:
                _sniff_jobs[job]['status'] = 'error'
                _sniff_jobs[job]['error'] = str(e)

        t = threading.Thread(target=_run_capture, args=(job_id, args, str(out_path)), daemon=True)
        t.start()
        return jsonify({'ok': True, 'job': job_id})
    except Exception as e:
        app.logger.error(f"sniff_run error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/sniff/status')
def sniff_status():
    """Return status for all sniff jobs."""
    try:
        data = {jid: dict(info) for jid, info in _sniff_jobs.items()}
        return jsonify({'ok': True, 'jobs': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/sniff/download')
def sniff_download():
    """Download completed pcap. Query param `job` required."""
    job = request.args.get('job')
    if not job or job not in _sniff_jobs:
        return jsonify({'ok': False, 'error': 'job not found'}), 404
    info = _sniff_jobs[job]
    if info.get('status') != 'done':
        return jsonify({'ok': False, 'error': 'job not complete'}), 409
    path = Path(info['out'])
    if not path.exists():
        return jsonify({'ok': False, 'error': 'file missing'}), 404
    return app.send_static_file(str(path)) if False else app.send_file(str(path), as_attachment=True)


@app.route('/drone/connect_controller', methods=['POST'])
def drone_connect_controller():
    """Attempt to start UDP controller connection (assumes host on drone WiFi)."""
    data = request.json or {}
    ssid = data.get('ssid')
    if ssid:
        ok = verify_connected_to_ssid(ssid, timeout=10)
        if not ok:
            return jsonify({'ok': False, 'message': f'Host not associated to SSID {ssid}'}), 409

    try:
        d = get_drone_controller()
        connected = d.connect()
        return jsonify({'ok': bool(connected), 'message': 'controller_connected' if connected else 'failed'})
    except Exception as e:
        app.logger.error(f"drone_connect_controller error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/drone/disconnect', methods=['POST'])
def drone_disconnect():
    try:
        d = get_drone_controller()
        d.disconnect()
        return jsonify({'ok': True})
    except Exception as e:
        app.logger.error(f"drone_disconnect error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/drone/command', methods=['POST'])
def drone_command():
    """Send a flight/control command to the drone controller.

    JSON payload: {action: 'takeoff'|'land'|'switch_camera'|'start_video'|'stop_video'|'send', params: {...}}
    """
    data = request.json or {}
    action = data.get('action')
    params = data.get('params') or {}
    if not action:
        return jsonify({'ok': False, 'error': 'No action specified'}), 400

    try:
        d = get_drone_controller()
        # safety: ensure host appears connected to drone network
        # do not block long here
        # Map actions
        if action == 'connect':
            ok = d.connect()
            return jsonify({'ok': bool(ok)})
        if action == 'disconnect':
            d.disconnect()
            return jsonify({'ok': True})
        if action == 'start_video':
            ok = d.start_video_stream()
            return jsonify({'ok': bool(ok)})
        if action == 'stop_video':
            try:
                if getattr(d, 'video_stream', None):
                    d.video_stream.stop()
                return jsonify({'ok': True})
            except Exception as e:
                return jsonify({'ok': False, 'error': str(e)}), 500
        if action == 'switch_camera':
            cam = int(params.get('camera', 1))
            d.switch_camera(cam)
            return jsonify({'ok': True, 'camera': cam})
        if action == 'switch_screen':
            mode = int(params.get('mode', 1))
            d.switch_screen_mode(mode)
            return jsonify({'ok': True, 'mode': mode})
        if action == 'send':
            # send arbitrary hex bytes: params.bytes = '010203'
            b = params.get('bytes')
            if not b:
                return jsonify({'ok': False, 'error': 'no bytes provided'}), 400
            try:
                payload = bytes.fromhex(b)
            except Exception as e:
                return jsonify({'ok': False, 'error': f'invalid hex: {e}'}), 400
            ok = d.send_command(payload)
            return jsonify({'ok': bool(ok)})

        return jsonify({'ok': False, 'error': f'Unknown action {action}'}), 400
    except Exception as e:
        app.logger.error(f"drone_command error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == "__main__":
    # Development server only. Use a production WSGI server for real deployments.
    app.run(host="0.0.0.0", port=5000, debug=True)
