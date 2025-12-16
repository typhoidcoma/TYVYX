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
from .drone_controller import TEKYDroneController
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
_drone_controller: Optional[TEKYDroneController] = None


# Config persistence
_config_path = Path("teky_config.json")


def _load_config():
    global _video_source, _last_successful_ports
    try:
        if _config_path.exists():
            with open(_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            _video_source = cfg.get("video_source", _video_source)
            _last_successful_ports = cfg.get("last_successful_ports", _last_successful_ports)
            app.logger.info(f"Loaded config from {_config_path}")
    except Exception as e:
        app.logger.warning(f"Failed to load config: {e}")


def _save_config():
    try:
        cfg = {"video_source": _video_source, "last_successful_ports": _last_successful_ports}
        with open(_config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        app.logger.info(f"Saved config to {_config_path}")
    except Exception as e:
        app.logger.warning(f"Failed to save config: {e}")


# load persisted config if present
_load_config()


def get_drone_controller() -> TEKYDroneController:
    global _drone_controller
    if _drone_controller is None:
        _drone_controller = TEKYDroneController()
    return _drone_controller


def get_video_stream() -> OpenCVVideoStream:
    global _video_stream
    with _video_lock:
        if _video_stream is None:
            # Default RTSP source — drone default IP and port
            controller = get_drone_controller()
            source = _video_source or f"rtsp://{controller.DRONE_IP}:{controller.RTSP_PORT}/webcam"
            _video_stream = OpenCVVideoStream(source)
            started = _video_stream.start(timeout=3.0)
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
            _video_stream = OpenCVVideoStream(src)
            started = _video_stream.start(timeout=3.0)
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
            running = bool(_video_stream and getattr(_video_stream, 'is_opened', lambda: False)())
            source = globals().get('_video_source', None)
        return jsonify({'running': running, 'source': str(source) if source is not None else None})
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
        return jsonify({'ok': True, 'status': status})
    except Exception as e:
        app.logger.error(f"drone_status error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


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
        diagnostics.log(f"drone_command error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == "__main__":
    # Development server only. Use a production WSGI server for real deployments.
    app.run(host="0.0.0.0", port=5000, debug=True)
