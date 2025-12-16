"""Network diagnostics packaged under `teky`."""

import os
import os
import socket
import time
import sys
import shutil
import platform
from contextlib import closing
from datetime import datetime
from pathlib import Path
import importlib
from pathlib import Path


class DroneNetworkDiagnostics:
    """Network diagnostics for TEKY drone"""

    DRONE_IP = "192.168.1.1"
    UDP_PORT = 7099
    RTSP_PORT = 7070
    TCP_PORT = 5000

    def __init__(self):
        # Ensure logs directory exists (relative to repo root)
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to current directory if creation fails
            logs_dir = Path(".")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = str(logs_dir / f"drone_packets_{timestamp}.log")

    def log(self, message: str):
        """Log message to console and file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        # Ensure file writes use UTF-8 and do not raise on characters
        # unsupported by the platform default encoding (e.g. Windows cp1252).
        # Use 'replace' to avoid exceptions while preserving readable output.
        try:
            with open(self.log_file, "a", encoding="utf-8", errors="replace") as f:
                f.write(log_line + "\n")
        except Exception:
            # As a last resort, attempt to write with system default but replace errors.
            with open(self.log_file, "a", errors="replace") as f:
                f.write(log_line + "\n")

    def test_ping(self) -> bool:
        """Test if drone is reachable"""
        self.log("=" * 70)
        self.log("PING TEST")
        self.log("=" * 70)
        import subprocess
        import platform

        # Ensure the ping executable exists on PATH
        ping_exe = shutil.which("ping")
        if not ping_exe:
            self.log("⚠ Ping executable not found on PATH; skipping ping test")
            return False

        # Use appropriate ping parameter for count based on OS
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = [ping_exe, param, "3", self.DRONE_IP]

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log(f"✓ Drone at {self.DRONE_IP} is reachable")
                return True
            else:
                # Provide brief stdout/stderr for debugging
                out = (result.stdout or "").strip()
                err = (result.stderr or "").strip()
                self.log(f"✗ Drone at {self.DRONE_IP} is NOT reachable")
                if out:
                    self.log(f"  ping stdout: {out}")
                if err:
                    self.log(f"  ping stderr: {err}")
                return False
        except subprocess.TimeoutExpired:
            self.log("✗ Ping timed out")
            return False
        except Exception as e:
            self.log(f"✗ Ping failed: {e}")
            return False

    def test_udp_connection(self) -> bool:
        """Test UDP connection and capture responses"""
        self.log("\n" + "=" * 70)
        self.log("UDP CONNECTION TEST")
        self.log("=" * 70)
        sock = None
        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3.0)

            self.log(f"Sending heartbeat to {self.DRONE_IP}:{self.UDP_PORT}")

            # Send heartbeat command
            heartbeat = bytes([1, 1])
            try:
                sock.sendto(heartbeat, (self.DRONE_IP, self.UDP_PORT))
                self.log(f"Sent: {heartbeat.hex()}")
            except Exception as e:
                self.log(f"✗ Failed to send heartbeat: {e}")
                return False

            # Wait for response
            try:
                data, addr = sock.recvfrom(1024)
                self.log(f"✓ Received response from {addr}")
                self.log(f"  Data (hex): {data.hex()}")
                self.log(f"  Data (decimal): {list(data)}")
                self.log(f"  Length: {len(data)} bytes")

                # Parse response
                if len(data) >= 1:
                    self.log(f"  Byte 0 (device info): 0x{data[0]:02x} ({data[0]})")
                if len(data) >= 2:
                    self.log(f"  Byte 1 (camera state): 0x{data[1]:02x} ({data[1]})")
                if len(data) >= 3:
                    self.log(f"  Byte 2 (screen state): 0x{data[2]:02x} ({data[2]})")

                return True

            except socket.timeout:
                self.log("✗ No response received (timeout)")
                return False

        except Exception as e:
            self.log(f"✗ UDP test failed: {e}")
            return False

        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def capture_udp_packets(self, duration: int = 10):
        """
        Capture UDP packets for specified duration
        Args:
            duration: Capture duration in seconds
        """
        self.log("\n" + "=" * 70)
        self.log(f"UDP PACKET CAPTURE ({duration} seconds)")
        self.log("=" * 70)
        self.log("Sending heartbeats and capturing all responses...")

        sock = None
        start_time = time.time()
        packet_count = 0
        heartbeat_count = 0

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)

            while time.time() - start_time < duration:
                # Send heartbeat
                heartbeat = bytes([1, 1])
                try:
                    sock.sendto(heartbeat, (self.DRONE_IP, self.UDP_PORT))
                    heartbeat_count += 1
                except Exception as e:
                    self.log(f"✗ Failed to send heartbeat: {e}")
                    break

                # Try to receive response
                try:
                    data, addr = sock.recvfrom(1024)
                    packet_count += 1
                    self.log(f"Packet #{packet_count}: {data.hex()} ({list(data)})")
                except socket.timeout:
                    pass

                # Allow user to interrupt capture cleanly
                try:
                    time.sleep(1.0)
                except KeyboardInterrupt:
                    self.log("Capture interrupted by user")
                    break

            self.log("\nCapture complete:")
            self.log(f"  Heartbeats sent: {heartbeat_count}")
            self.log(f"  Responses received: {packet_count}")

        except Exception as e:
            self.log(f"✗ Capture failed: {e}")

        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def test_experimental_commands(self):
        """Test various command patterns to discover control protocol"""
        self.log("\n" + "=" * 70)
        self.log("EXPERIMENTAL COMMAND TEST")
        self.log("=" * 70)
        self.log("⚠️  WARNING: This will send various commands to the drone!")
        self.log("Make sure the drone is in a safe location.")

        # In non-interactive environments (CI, piped input), avoid blocking
        try:
            if not sys.stdin or not sys.stdin.isatty():
                self.log("⚠ Non-interactive stdin detected; skipping experimental commands")
                return
        except Exception:
            # If stdin properties are unavailable, skip to be safe
            self.log("⚠ stdin state unknown; skipping experimental commands")
            return

        try:
            response = input("\nProceed? (yes/no): ")
        except EOFError:
            self.log("✗ No input available; skipping experimental commands")
            return

        if response.lower() != "yes":
            self.log("Cancelled by user")
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)

            # Test various single-byte commands
            test_commands = [
                (bytes([100]), "Initialize"),
                (bytes([99]), "Special"),
                (bytes([6, 1]), "Camera 1"),
                (bytes([6, 2]), "Camera 2"),
                (bytes([9, 1]), "Screen Mode 1"),
                (bytes([9, 2]), "Screen Mode 2"),
            ]

            for cmd, description in test_commands:
                self.log(f"\nTesting: {description}")
                self.log(f"  Command: {cmd.hex()}")
                sock.sendto(cmd, (self.DRONE_IP, self.UDP_PORT))

                try:
                    data, addr = sock.recvfrom(1024)
                    self.log(f"  Response: {data.hex()}")
                except socket.timeout:
                    self.log("  No response")

                time.sleep(0.5)

            sock.close()
            self.log("\nExperimental command test complete")

        except Exception as e:
            self.log(f"✗ Test failed: {e}")

    def list_wifi_adapters(self):
        """List available WiFi adapters on the host.

        Returns a list of dicts: {name, description, state}
        This attempts several platform-specific strategies and logs
        useful information for diagnostic use.
        """
        adapters = []

        self.log("Starting WiFi adapter discovery...")

        try:
            system = platform.system().lower()

            # Windows: use netsh
            if system == "windows" and shutil.which("netsh"):
                try:
                    import subprocess

                    self.log("Using netsh to enumerate wireless interfaces")
                    out = subprocess.run(
                        ["netsh", "wlan", "show", "interfaces"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    text = out.stdout or out.stderr or ""
                    self.log("netsh output:\n" + text.strip())

                    # Parse interface blocks
                    current = {}
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("Name") and ":" in line:
                            # start of new block
                            if current:
                                adapters.append(current)
                                current = {}
                            _, val = line.split(":", 1)
                            current["name"] = val.strip()
                        else:
                            if ":" in line:
                                k, v = [p.strip() for p in line.split(":", 1)]
                                current[k.lower().replace(" ", "_")] = v
                    if current:
                        adapters.append(current)

                    self.log(f"Found {len(adapters)} adapter(s) via netsh")
                    if adapters:
                        self.log(f"Adapters: {[a.get('name') or a for a in adapters]}")
                    return adapters
                except Exception as e:
                    self.log(f"✗ netsh parse failed: {e}")

            # macOS: networksetup or airport
            if system == "darwin":
                # Try networksetup first
                try:
                    import subprocess
                    if shutil.which("networksetup"):
                        self.log("Using networksetup to enumerate hardware ports")
                        out = subprocess.run(
                            ["networksetup", "-listallhardwareports"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        text = out.stdout or out.stderr or ""
                        self.log("networksetup output:\n" + text.strip())
                        cur = {}
                        for line in text.splitlines():
                            if not line.strip():
                                if cur:
                                    # only include Wi-Fi/AirPort entries
                                    if cur.get("Hardware Port", "").lower().startswith("wi"):
                                        adapters.append(cur)
                                    cur = {}
                                continue
                            if ":" in line:
                                k, v = line.split(":", 1)
                                cur[k.strip()] = v.strip()
                        if cur and cur.get("Hardware Port", "").lower().startswith("wi"):
                            adapters.append(cur)

                        self.log(f"Found {len(adapters)} adapter(s) via networksetup")
                        if adapters:
                            self.log(f"Adapters: {[a.get('Device') or a for a in adapters]}")
                        return adapters
                except Exception as e:
                    self.log(f"✗ macOS networksetup parse failed: {e}")

            # Linux: try nmcli, then check wireless sysfs
            if system == "linux":
                try:
                    import subprocess
                    if shutil.which("nmcli"):
                        self.log("Using nmcli to enumerate devices")
                        out = subprocess.run(
                            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        text = out.stdout or out.stderr or ""
                        self.log("nmcli output:\n" + text.strip())
                        for line in text.splitlines():
                            parts = line.split(":")
                            if len(parts) >= 3 and parts[1] == "wifi":
                                adapters.append({"name": parts[0], "type": "wifi", "state": parts[2], "connection": parts[3] if len(parts) > 3 else ""})
                        self.log(f"Found {len(adapters)} adapter(s) via nmcli")
                        if adapters:
                            self.log(f"Adapters: {[a.get('name') for a in adapters]}")
                        if adapters:
                            return adapters
                except Exception as e:
                    self.log(f"✗ nmcli parse failed: {e}")

                # Fallback: check /sys/class/net for wireless directories
                try:
                    net_path = Path("/sys/class/net")
                    if net_path.exists():
                        for iface in net_path.iterdir():
                            if (iface / "wireless").exists() or (Path("/proc/net/wireless").exists() and iface.name in open("/proc/net/wireless").read()):
                                adapters.append({"name": iface.name, "type": "wifi"})
                        if adapters:
                            self.log(f"Found {len(adapters)} adapter(s) via sysfs/proc")
                            self.log(f"Adapters: {[a.get('name') for a in adapters]}")
                            return adapters
                except Exception as e:
                    self.log(f"✗ linux sysfs check failed: {e}")

            # Generic fallback: list network interfaces
            try:
                # Import psutil dynamically to avoid static analysis errors
                self.log("Falling back to psutil / generic interface listing")
                psutil = importlib.import_module("psutil")
                if hasattr(psutil, "net_if_addrs"):
                    for name in psutil.net_if_addrs().keys():
                        adapters.append({"name": name})
                    self.log(f"Found {len(adapters)} adapter(s) via psutil")
                    self.log(f"Adapters: {[a.get('name') for a in adapters]}")
                    return adapters
            except Exception as e:
                # psutil not available or failed; return what we have
                self.log(f"⚠ psutil fallback failed: {e}")

        except Exception as e:
            self.log(f"✗ list_wifi_adapters failed: {e}")

        # Final summary
        self.log(f"Adapter discovery complete. Total adapters found: {len(adapters)}")
        if adapters:
            try:
                self.log(f"Adapter names: {[a.get('name') for a in adapters]}")
            except Exception:
                pass

        return adapters

    def scan_wifi_networks(self, interface: str = None, timeout: int = 10):
        """Scan for WiFi networks using the specified interface where possible.

        Returns a list of SSID dicts (ssid, bssid, signal, security) when available.
        """
        results = []
        self.log(f"Starting WiFi network scan on interface: {interface or 'any'}")
        try:
            system = platform.system().lower()
            import subprocess

            # Windows: netsh wlan show networks
            if system == "windows" and shutil.which("netsh"):
                self.log("Using netsh to scan for networks")
                cmd = ["netsh", "wlan", "show", "networks", "mode=bssid"]
                if interface:
                    cmd = ["netsh", "wlan", "show", "networks", f"interface={interface}", "mode=bssid"]
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                text = out.stdout or out.stderr or ""
                self.log("netsh scan output:\n" + (text.strip()[:4000]))
                # crude parse: lines starting with SSID
                cur = {}
                for line in text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("ssid ") and ":" in line:
                        if cur:
                            results.append(cur)
                            cur = {}
                        _, val = line.split(":", 1)
                        cur["ssid"] = val.strip()
                    elif line.lower().startswith("bssid"):
                        _, val = line.split(":", 1)
                        cur.setdefault("bssid", val.strip())
                    elif line.lower().startswith("signal"):
                        _, val = line.split(":", 1)
                        cur.setdefault("signal", val.strip())
                if cur:
                    results.append(cur)
                self.log(f"Found {len(results)} network(s) via netsh")
                return results

            # macOS: airport -s
            if system == "darwin" and shutil.which("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"):
                airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
                self.log("Using airport utility to scan for networks")
                out = subprocess.run([airport, "-s"], capture_output=True, text=True, timeout=timeout)
                text = out.stdout or out.stderr or ""
                self.log("airport scan:\n" + text.strip())
                for line in text.splitlines()[1:]:
                    parts = [p for p in line.split(" ") if p]
                    if parts:
                        results.append({"ssid": parts[0], "signal": parts[-2] if len(parts) > 1 else ""})
                self.log(f"Found {len(results)} network(s) via airport")
                return results

            # Linux: nmcli dev wifi list
            if system == "linux" and shutil.which("nmcli"):
                cmd = ["nmcli", "-f", "SSID,BSSID,SIGNAL,SECURITY", "dev", "wifi", "list"]
                if interface:
                    cmd.extend(["ifname", interface])
                self.log("Using nmcli to scan for networks")
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                text = out.stdout or out.stderr or ""
                self.log("nmcli scan:\n" + (text.strip()[:4000]))
                for line in text.splitlines()[1:]:
                    parts = [p.strip() for p in line.split() if p.strip()]
                    if parts:
                        results.append({"ssid": parts[0]})
                self.log(f"Found {len(results)} network(s) via nmcli")
                return results

            # Try iwlist as fallback
            if system == "linux" and shutil.which("iwlist") and interface:
                self.log(f"Using iwlist to scan on interface {interface}")
                out = subprocess.run(["iwlist", interface, "scan"], capture_output=True, text=True, timeout=timeout)
                text = out.stdout or out.stderr or ""
                self.log("iwlist scan output trimmed:\n" + (text.strip()[:4000]))
                # crude parse for ESSID
                for line in text.splitlines():
                    if "ESSID:" in line:
                        ssid = line.split("ESSID:", 1)[1].strip().strip('"')
                        results.append({"ssid": ssid})
                self.log(f"Found {len(results)} network(s) via iwlist")
                return results

        except Exception as e:
            self.log(f"✗ scan_wifi_networks failed: {e}")

        self.log(f"Scan complete. Total networks found: {len(results)}")
        if results:
            try:
                self.log(f"Example networks: {[r.get('ssid') for r in results[:8]]}")
            except Exception:
                pass

        return results

    def check_ports(self):
        """Check if common ports are accessible"""
        self.log("\n" + "=" * 70)
        self.log("PORT ACCESSIBILITY TEST")
        self.log("=" * 70)

        ports = [
            (self.UDP_PORT, "UDP", "Control"),
            (self.RTSP_PORT, "TCP", "RTSP Video"),
            (self.TCP_PORT, "TCP", "TCP Server"),
        ]

        for port, protocol, description in ports:
            self.log(f"\nTesting {protocol} port {port} ({description})...")

            if protocol == "TCP":
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)
                    result = sock.connect_ex((self.DRONE_IP, port))
                    sock.close()

                    if result == 0:
                        self.log(f"  ✓ Port {port} is OPEN")
                    else:
                        self.log(f"  ✗ Port {port} is CLOSED or filtered")
                except Exception as e:
                    self.log(f"  ✗ Error: {e}")
            else:
                self.log("  ℹ UDP port (can't test directly)")

    def run_all_tests(self):
        """Run all diagnostic tests"""
        self.log("TEKY Drone Network Diagnostics")
        self.log(f"Log file: {self.log_file}")
        self.log("")

        # Run tests
        ping_ok = self.test_ping()

        if ping_ok:
            udp_ok = self.test_udp_connection()
            self.check_ports()

            if udp_ok:
                self.capture_udp_packets(duration=5)

        self.log("\n" + "=" * 70)
        self.log("DIAGNOSTICS COMPLETE")
        self.log(f"Results saved to: {self.log_file}")
        self.log("=" * 70)


def main():
    """Main function"""
    print("TEKY Drone Network Diagnostics Tool")
    print("=" * 70)
    print("\nThis tool will test connectivity to your TEKY drone.")
    print("Make sure you are connected to the drone's WiFi network!")
    print("\nOptions:")
    print("  1 - Run all diagnostic tests")
    print("  2 - Ping test only")
    print("  3 - UDP connection test only")
    print("  4 - Capture UDP packets (10 seconds)")
    print("  5 - Test experimental commands (CAUTION!)")
    print("  6 - Check port accessibility")
    print("  0 - Exit")
    print("=" * 70)

    diagnostics = DroneNetworkDiagnostics()

    while True:
        choice = input("\nSelect option: ").strip()

        if choice == "1":
            diagnostics.run_all_tests()
            break
        elif choice == "2":
            diagnostics.test_ping()
        elif choice == "3":
            diagnostics.test_udp_connection()
        elif choice == "4":
            diagnostics.capture_udp_packets(10)
        elif choice == "5":
            diagnostics.test_experimental_commands()
        elif choice == "6":
            diagnostics.check_ports()
        elif choice == "0":
            print("Exiting...")
            break
        else:
            print("Invalid option. Please try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
