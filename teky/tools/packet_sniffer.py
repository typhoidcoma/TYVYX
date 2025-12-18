"""Packet sniffing utility for TEKY drone traffic.

This tool attempts to capture UDP packets to/from the drone for protocol
analysis. It prefers `scapy` (libpcap) when available. If scapy/pcap is not
installed, it will try to use `tshark` (part of Wireshark) as a fallback.

Usage examples:
  # Capture for 30 seconds and save pcap
  python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 30 --out drone.pcap

  # Capture and also produce a hex log
  python -m teky.tools.packet_sniffer --dst 192.168.1.1 --port 7099 --duration 20 --out drone.pcap --hexlog drone_hex.log

Notes:
- On Windows, running scapy sniffing requires WinPcap/NPcap and admin privileges.
- tshark fallback also requires Wireshark/tshark installed and may require admin privileges.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def has_tshark() -> bool:
    return shutil.which('tshark') is not None


def run_tshark_capture(bpf_filter: str, iface: Optional[str], duration: int, out_pcap: str) -> int:
    cmd = ['tshark']
    if iface:
        cmd += ['-i', iface]
    # capture duration
    cmd += ['-a', f'duration:{duration}']
    # write pcap
    cmd += ['-w', out_pcap]
    # use capture filter for efficiency
    if bpf_filter:
        cmd += ['-f', bpf_filter]
    print('Running tshark:', ' '.join(cmd))
    try:
        p = subprocess.run(cmd, check=False)
        return p.returncode
    except FileNotFoundError:
        print('tshark not found')
        return 2


def tshark_hex_dump(pcap_file: str, hex_log: str) -> None:
    # Use tshark -x to dump packet bytes in hex
    cmd = ['tshark', '-r', pcap_file, '-x']
    print('Producing hex dump with tshark...')
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        with open(hex_log, 'w', encoding='utf-8') as fh:
            fh.write(p.stdout)
        print(f'Wrote hex log to {hex_log}')
    except Exception as e:
        print('Failed to run tshark hex dump:', e)


def scapy_capture(filter_expr: str, iface: Optional[str], duration: int, out_pcap: str):
    try:
        from scapy.all import sniff, wrpcap
    except Exception as e:
        print('Scapy not available (No module named "scapy").')
        print('Install with `pip install scapy` or `pip install -r requirements.txt`.')
        print('On Windows, install Npcap (https://nmap.org/npcap/) and run with administrator rights.')
        return 2

    print('Starting scapy sniff (ctrl-C to stop early)')
    pkts = sniff(filter=filter_expr, iface=iface, timeout=duration)
    try:
        wrpcap(out_pcap, pkts)
    except Exception as e:
        print('Failed to write pcap:', e)
        return 3
    print(f'Captured {len(pkts)} packets, wrote {out_pcap}')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iface', help='Interface name to capture on (optional)')
    parser.add_argument('--src', help='Source IP to filter (optional)')
    parser.add_argument('--dst', help='Destination IP to filter (optional)')
    parser.add_argument('--port', type=int, help='UDP port to filter (optional)')
    parser.add_argument('--duration', type=int, default=20, help='Capture duration in seconds')
    parser.add_argument('--out', default='capture.pcap', help='Output pcap file')
    parser.add_argument('--hexlog', help='Optional hex dump text file of captured packets')
    parser.add_argument('--use-tshark', action='store_true', help='Force using tshark instead of scapy')

    args = parser.parse_args()

    # Build BPF filter
    parts = []
    if args.port:
        parts.append(f'udp port {args.port}')
    if args.src and args.dst:
        parts.append(f'host {args.src} or host {args.dst}')
    elif args.src:
        parts.append(f'host {args.src}')
    elif args.dst:
        parts.append(f'host {args.dst}')

    bpf = ' and '.join(parts) if parts else ''

    out_pcap = args.out
    iface = args.iface

    # Prefer scapy unless forced or unavailable
    if not args.use_tshark:
        try:
            code = scapy_capture(bpf, iface, args.duration, out_pcap)
            if code == 0:
                if args.hexlog:
                    # try to produce hex log via tshark if available
                    if has_tshark():
                        tshark_hex_dump(out_pcap, args.hexlog)
                    else:
                        print('tshark not available to produce hex log; install tshark or use --use-tshark')
                return
            else:
                print('Scapy capture failed or unavailable, falling back to tshark')
        except Exception as e:
            print('Scapy capture raised exception, falling back to tshark:', e)

    # Fallback to tshark
    if not has_tshark():
        print('Neither scapy nor tshark available. You can use the UDP proxy: python -m teky.tools.udp_proxy')
        return

    # Build capture filter for tshark (BPF)
    bpf_filter = bpf
    rc = run_tshark_capture(bpf_filter, iface, args.duration, out_pcap)
    if rc == 0:
        print(f'Capture complete, saved to {out_pcap}')
        if args.hexlog:
            tshark_hex_dump(out_pcap, args.hexlog)
    else:
        print('tshark failed with return code', rc)


if __name__ == '__main__':
    main()
