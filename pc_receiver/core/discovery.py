"""ZeroLink LAN Auto-Discovery & Notification Bridge Service
Listens and responds to UDP broadcast discovery requests from Android devices on the LAN,
and receives mirrored mobile notifications.
"""

import json
import socket
import threading
import time
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal


class LanDiscoveryService(QObject):
    DISCOVERY_PORT = 8887
    BEACON_INTERVAL = 2.0  # seconds

    notification_received = pyqtSignal(str, str, str)  # app_name, title, text

    def __init__(self, tcp_port: int = 8888, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.tcp_port = tcp_port
        self.local_ip = local_ip
        self.hostname = socket.gethostname()
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

    def _get_beacon_payload(self) -> bytes:
        return json.dumps({
            "type": "ZEROLINK_BEACON",
            "ip": self.local_ip,
            "port": self.tcp_port,
            "name": f"ZeroLink PC ({self.hostname})"
        }).encode("utf-8")

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
                data, addr = self._sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="ignore").strip()

                if "ZEROLINK_DISCOVER" in msg or "ZEROCAST_DISCOVERY_REQ" in msg:
                    # Reply directly to phone sender
                    payload = self._get_beacon_payload()
                    self._sock.sendto(payload, addr)

                elif "ZEROLINK_NOTIFY" in msg:
                    # Android notification packet
                    try:
                        parsed = json.loads(msg)
                        app = parsed.get("app", "Phone Notification")
                        title = parsed.get("title", "")
                        text = parsed.get("text", "")
                        if title or text:
                            self.notification_received.emit(app, title, text)
                    except Exception:
                        pass

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
            payload = self._get_beacon_payload()
            self._sock.sendto(payload, ("255.255.255.255", self.DISCOVERY_PORT))
        except Exception:
            pass
