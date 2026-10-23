"""ZeroLink Master Gateway & LAN Discovery Service
Listens and responds to UDP broadcast discovery requests from Android devices on the LAN,
runs a persistent lightweight TCP Master Gateway (port 8886) for remote module wake-up and USB discovery,
and receives mirrored mobile notifications.
"""

import json
import socket
import threading
import time
from typing import Optional, List
from PyQt6.QtCore import QObject, pyqtSignal


class LanDiscoveryService(QObject):
    DISCOVERY_PORT = 8887  # UDP beacon & notifications
    GATEWAY_PORT = 8886    # TCP Master Gateway & ZeroWake
    BEACON_INTERVAL = 2.0  # seconds

    notification_received = pyqtSignal(str, str, str)  # app_name, title, text
    module_wake_requested = pyqtSignal(str)            # module_id
    module_sleep_requested = pyqtSignal(str)           # module_id

    def __init__(self, tcp_port: int = 8888, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.tcp_port = tcp_port
        self.local_ip = local_ip
        self.hostname = socket.gethostname()
        self.last_client_ip = "127.0.0.1"
        self.is_running = False
        self._udp_thread: Optional[threading.Thread] = None
        self._tcp_thread: Optional[threading.Thread] = None
        self._udp_sock: Optional[socket.socket] = None
        self._tcp_sock: Optional[socket.socket] = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True

        # Start UDP Discovery Listener
        self._udp_thread = threading.Thread(target=self._run_udp, daemon=True)
        self._udp_thread.start()

        # Start TCP Master Gateway (ZeroWake & Discovery)
        self._tcp_thread = threading.Thread(target=self._run_tcp_gateway, daemon=True)
        self._tcp_thread.start()

    def stop(self):
        self.is_running = False
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except Exception:
                pass
            self._udp_sock = None

        if self._tcp_sock:
            try:
                self._tcp_sock.close()
            except Exception:
                pass
            self._tcp_sock = None

    def _get_beacon_payload(self) -> bytes:
        return json.dumps({
            "type": "ZEROLINK_BEACON",
            "ip": self.local_ip,
            "port": self.tcp_port,
            "gateway_port": self.GATEWAY_PORT,
            "name": f"ZeroLink PC ({self.hostname})"
        }).encode("utf-8")

    def _run_udp(self):
        try:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._udp_sock.bind(("", self.DISCOVERY_PORT))
            self._udp_sock.settimeout(1.0)
        except Exception as e:
            print(f"[Discovery] UDP Bind warning: {e}")
            return

        last_beacon_time = 0.0

        while self.is_running:
            now = time.time()
            if now - last_beacon_time >= self.BEACON_INTERVAL:
                self._broadcast_beacon()
                last_beacon_time = now

            try:
                data, addr = self._udp_sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="ignore").strip()

                if "ZEROLINK_DISCOVER" in msg or "ZEROCAST_DISCOVERY_REQ" in msg:
                    payload = self._get_beacon_payload()
                    self._udp_sock.sendto(payload, addr)

                elif "ZEROLINK_NOTIFY" in msg:
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
        if not self._udp_sock:
            return
        try:
            payload = self._get_beacon_payload()
            self._udp_sock.sendto(payload, ("255.255.255.255", self.DISCOVERY_PORT))
        except Exception:
            pass

    def _run_tcp_gateway(self):
        """Persistent TCP Master Gateway on port 8886 for reliable USB/Wi-Fi discovery & ZeroWake."""
        try:
            self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._tcp_sock.bind(("", self.GATEWAY_PORT))
            self._tcp_sock.listen(10)
            self._tcp_sock.settimeout(1.0)
            print(f"[ZeroWake] Master Gateway active on TCP port {self.GATEWAY_PORT}")
        except Exception as e:
            print(f"[ZeroWake] TCP Gateway bind error: {e}")
            return

        while self.is_running:
            try:
                client_sock, client_addr = self._tcp_sock.accept()
                threading.Thread(target=self._handle_tcp_client, args=(client_sock, client_addr), daemon=True).start()
            except (socket.timeout, BlockingIOError):
                continue
            except OSError:
                break
            except Exception:
                continue

    def _handle_tcp_client(self, sock: socket.socket, addr):
        try:
            if addr and len(addr) > 0 and addr[0]:
                self.last_client_ip = addr[0]
            sock.settimeout(4.0)
            data = sock.recv(4096)
            if not data:
                return

            text = data.decode("utf-8", errors="ignore").strip()
            response_dict = None

            # 1. PING / Discovery Handshake
            if "PING" in text.upper():
                response_dict = {
                    "status": "PONG",
                    "type": "ZEROLINK_GATEWAY",
                    "name": f"ZeroLink PC ({self.hostname})",
                    "ip": self.local_ip,
                    "port": self.tcp_port
                }

            # 2. Remote Module Wake-up (ZeroWake)
            elif "WAKE" in text.upper():
                try:
                    payload = json.loads(text)
                    mod_id = payload.get("module", "").lower()
                    if mod_id:
                        self.module_wake_requested.emit(mod_id)
                        if mod_id == "zeromix":
                            self.module_wake_requested.emit("zerocast")
                        response_dict = {
                            "status": "READY",
                            "module": mod_id,
                            "name": f"ZeroLink PC ({self.hostname})"
                        }
                except Exception:
                    pass

            # 2b. Remote Module Sleep / Deactivate (On Mobile Disconnect)
            elif "SLEEP" in text.upper() or "CLOSE" in text.upper():
                try:
                    payload = json.loads(text)
                    mod_id = payload.get("module", "").lower()
                    if mod_id:
                        self.module_sleep_requested.emit(mod_id)
                        if mod_id == "zeromix":
                            self.module_sleep_requested.emit("zerocast")
                        response_dict = {
                            "status": "STOPPED",
                            "module": mod_id,
                            "name": f"ZeroLink PC ({self.hostname})"
                        }
                except Exception:
                    pass

            # 3. Direct Notification over TCP
            elif "NOTIFY" in text.upper():
                try:
                    payload = json.loads(text)
                    app = payload.get("app", "Phone Notification")
                    title = payload.get("title", "")
                    body = payload.get("text", "")
                    if title or body:
                        self.notification_received.emit(app, title, body)
                    response_dict = {"status": "OK"}
                except Exception:
                    pass

            if response_dict:
                reply_bytes = (json.dumps(response_dict) + "\n").encode("utf-8")
                sock.sendall(reply_bytes)
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
