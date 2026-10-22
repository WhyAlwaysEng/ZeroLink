"""ZeroCast LAN Auto-Discovery Service
Listens and responds to UDP broadcast discovery requests from Android devices on the LAN.
"""

import json
import socket
import threading
import time
from typing import Optional


class LanDiscoveryService:
    DISCOVERY_PORT = 8889
    BEACON_INTERVAL = 2.0  # seconds

    def __init__(self, tcp_port: int = 8888, local_ip: str = "127.0.0.1"):
        self.tcp_port = tcp_port
        self.local_ip = local_ip
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.bind(("", self.DISCOVERY_PORT))
            self._sock.settimeout(1.0)
        except Exception:
            return

        last_beacon_time = 0.0

        while self.is_running:
            now = time.time()
            # Periodic broadcast beacon
            if now - last_beacon_time >= self.BEACON_INTERVAL:
                self._broadcast_beacon()
                last_beacon_time = now

            try:
                data, addr = self._sock.recvfrom(2048)
                msg = data.decode("utf-8", errors="ignore").strip()

                if "ZEROCAST_DISCOVERY_REQ" in msg:
                    # Reply directly to sender
                    payload = json.dumps({
                        "type": "ZEROCAST_BEACON",
                        "ip": self.local_ip,
                        "port": self.tcp_port,
                        "name": "ZeroCast PC"
                    }).encode("utf-8")
                    self._sock.sendto(payload, addr)
            except (socket.timeout, BlockingIOError):
                continue
            except OSError:
                break
            except Exception:
                continue

    def _broadcast_beacon(self):
        if not self._sock:
            return
        try:
            payload = json.dumps({
                "type": "ZEROCAST_BEACON",
                "ip": self.local_ip,
                "port": self.tcp_port,
                "name": "ZeroCast PC"
            }).encode("utf-8")
            self._sock.sendto(payload, ("255.255.255.255", self.DISCOVERY_PORT))
        except Exception:
            pass
