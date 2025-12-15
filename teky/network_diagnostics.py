"""Network diagnostics packaged under `teky`."""

import socket
import time
import sys
from datetime import datetime


class DroneNetworkDiagnostics:
    """Network diagnostics for TEKY drone"""

    DRONE_IP = "192.168.1.1"
    UDP_PORT = 7099
    RTSP_PORT = 7070
    TCP_PORT = 5000

    def __init__(self):
        self.log_file = f"drone_packets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    def log(self, message: str):
        """Log message to console and file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        with open(self.log_file, "a") as f:
            f.write(log_line + "\n")

    def test_ping(self) -> bool:
        """Test if drone is reachable"""
        self.log("=" * 70)
        self.log("PING TEST")
        self.log("=" * 70)

        import subprocess
        import platform

        # Use appropriate ping command for OS
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "3", self.DRONE_IP]

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.log(f"✓ Drone at {self.DRONE_IP} is reachable")
                return True
            else:
                self.log(f"✗ Drone at {self.DRONE_IP} is NOT reachable")
                return False
        except Exception as e:
            self.log(f"✗ Ping failed: {e}")
            return False

    def test_udp_connection(self) -> bool:
        """Test UDP connection and capture responses"""
        self.log("\n" + "=" * 70)
        self.log("UDP CONNECTION TEST")
        self.log("=" * 70)

        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3.0)

            self.log(f"Sending heartbeat to {self.DRONE_IP}:{self.UDP_PORT}")

            # Send heartbeat command
            heartbeat = bytes([1, 1])
            sock.sendto(heartbeat, (self.DRONE_IP, self.UDP_PORT))
            self.log(f"Sent: {heartbeat.hex()}")

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

                sock.close()
                return True

            except socket.timeout:
                self.log("✗ No response received (timeout)")
                sock.close()
                return False

        except Exception as e:
            self.log(f"✗ UDP test failed: {e}")
            return False

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

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)

            start_time = time.time()
            packet_count = 0
            heartbeat_count = 0

            while time.time() - start_time < duration:
                # Send heartbeat
                heartbeat = bytes([1, 1])
                sock.sendto(heartbeat, (self.DRONE_IP, self.UDP_PORT))
                heartbeat_count += 1

                # Try to receive response
                try:
                    data, addr = sock.recvfrom(1024)
                    packet_count += 1
                    self.log(f"Packet #{packet_count}: {data.hex()} ({list(data)})")
                except socket.timeout:
                    pass

                time.sleep(1.0)

            sock.close()
            self.log("\nCapture complete:")
            self.log(f"  Heartbeats sent: {heartbeat_count}")
            self.log(f"  Responses received: {packet_count}")

        except Exception as e:
            self.log(f"✗ Capture failed: {e}")

    def test_experimental_commands(self):
        """Test various command patterns to discover control protocol"""
        self.log("\n" + "=" * 70)
        self.log("EXPERIMENTAL COMMAND TEST")
        self.log("=" * 70)
        self.log("⚠️  WARNING: This will send various commands to the drone!")
        self.log("Make sure the drone is in a safe location.")

        response = input("\nProceed? (yes/no): ")
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
