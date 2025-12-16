"""UDP proxy / logger for capturing TEKY drone UDP traffic.

Usage:
  python -m teky.tools.udp_proxy --listen-port 17099 --drone-ip 192.168.1.1 --drone-port 7099

How it works:
- Listens on `--listen-port` for UDP packets from your controller/UI.
- Forwards those packets to the real drone at `--drone-ip:--drone-port`.
- Receives responses from the drone and forwards them back to the original client.
- Logs each packet with timestamp, direction, and hex payload to a log file.

Notes:
- Run this on the same host running the controller/web UI. Point the controller's
  drone config (`/drone/config`) to `127.0.0.1` and the `udp_port` to the
  proxy `--listen-port` while the proxy is running.
- For full network sniffing across interfaces, use Wireshark/tshark with npcap.
"""

import argparse
import socket
import threading
import time
from pathlib import Path


def hexdump(b: bytes) -> str:
    return b.hex()


class UDPProxy:
    def __init__(self, listen_port: int, drone_ip: str, drone_port: int, log_file: str = 'udp_capture.log'):
        self.listen_port = listen_port
        self.drone_ip = drone_ip
        self.drone_port = drone_port
        self.log_path = Path(log_file)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.listen_port))
        self.sock.settimeout(1.0)

        # Map client_addr -> last_seen timestamp
        self.clients = {}
        self.running = False

    def _log(self, direction: str, src, dst, data: bytes):
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        line = f"[{ts}] {direction} {src}->{dst} {len(data)} bytes: {hexdump(data)}\n"
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'a', encoding='utf-8') as fh:
                fh.write(line)
        except Exception:
            pass
        print(line, end='')

    def start(self):
        self.running = True
        t = threading.Thread(target=self._main_loop, daemon=True)
        t.start()
        print(f"UDP proxy listening on 0.0.0.0:{self.listen_port}, forwarding to {self.drone_ip}:{self.drone_port}")
        try:
            while self.running:
                time.sleep(0.2)
        except KeyboardInterrupt:
            print('Interrupted, stopping...')
            self.stop()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass

    def _main_loop(self):
        # Use the same socket for receiving from both client(s) and drone
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65536)
            except socket.timeout:
                continue
            except OSError:
                break

            # If packet came from the drone address, forward to all known clients
            if addr[0] == self.drone_ip and addr[1] == self.drone_port:
                # drone -> clients
                self._log('DRONE->CLIENT', addr, 'clients', data)
                for caddr in list(self.clients.keys()):
                    try:
                        self.sock.sendto(data, caddr)
                    except Exception:
                        pass
                continue

            # Otherwise treat as client -> drone
            client_addr = addr
            self.clients[client_addr] = time.time()
            self._log('CLIENT->DRONE', client_addr, (self.drone_ip, self.drone_port), data)

            # forward to drone
            try:
                self.sock.sendto(data, (self.drone_ip, self.drone_port))
            except Exception as e:
                self._log('ERROR', ('proxy', 0), (self.drone_ip, self.drone_port), str(e).encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--listen-port', type=int, default=17099, help='Local UDP port to listen on')
    parser.add_argument('--drone-ip', type=str, default='192.168.1.1', help='Real drone IP')
    parser.add_argument('--drone-port', type=int, default=7099, help='Real drone UDP port')
    parser.add_argument('--log-file', type=str, default='udp_capture.log', help='File to append logs to')
    args = parser.parse_args()

    proxy = UDPProxy(args.listen_port, args.drone_ip, args.drone_port, args.log_file)
    proxy.start()


if __name__ == '__main__':
    main()
