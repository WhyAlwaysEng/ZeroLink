"""ZeroLink Master Gateway & LAN Discovery Service
Listens and responds to UDP broadcast discovery requests from Android devices on the LAN,
runs a persistent lightweight TCP Master Gateway (port 8886) for remote module wake-up and USB discovery,
and receives mirrored mobile notifications.
"""

import json
import socket
import threading
import time
import ipaddress
from typing import Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

try:
    import psutil
except ImportError:
    psutil = None


class LanDiscoveryService(QObject):
    DISCOVERY_PORT = 8887  # UDP beacon & notifications
    GATEWAY_PORT = 8886    # TCP Master Gateway & ZeroWake
    BEACON_INTERVAL = 2.0  # seconds

    notification_received = pyqtSignal(str, str, str)  # app_name, title, text
    module_wake_requested = pyqtSignal(str)            # module_id
    module_sleep_requested = pyqtSignal(str)           # module_id
    gateway_client_updated = pyqtSignal(dict)          # client_info dict

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

    def _get_best_local_ip_for(self, target_ip: str) -> str:
        """Determines which local IPv4 address routes to the target IP (e.g. USB Tethering vs Wi-Fi)."""
        if not target_ip or target_ip.startswith("127."):
            return "127.0.0.1"
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target_ip, 80))
            return s.getsockname()[0]
        except Exception:
            return self.local_ip
        finally:
            s.close()

    def _get_broadcast_targets(self) -> List[Tuple[str, str]]:
        """Returns a list of (broadcast_ip, interface_ip) for all active adapters (Wi-Fi, USB Tether, Hotspot)."""
        targets = [("255.255.255.255", self.local_ip)]
        if not psutil:
            return targets

        try:
            stats = psutil.net_if_stats()
            for iface_name, addrs in psutil.net_if_addrs().items():
                if_stat = stats.get(iface_name)
                if if_stat and not if_stat.isup:
                    continue

                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        try:
                            net = ipaddress.IPv4Network(f"{addr.address}/{addr.netmask}", strict=False)
                            bcast = str(net.broadcast_address)
                            if bcast and bcast != "255.255.255.255":
                                targets.append((bcast, addr.address))
                        except Exception:
                            pass
        except Exception:
            pass
        return targets

    def _get_beacon_payload(self, override_ip: Optional[str] = None) -> bytes:
        ip_to_use = override_ip or self.local_ip
        return json.dumps({
            "type": "ZEROLINK_BEACON",
            "ip": ip_to_use,
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
                    client_ip = addr[0] if addr else ""
                    best_ip = self._get_best_local_ip_for(client_ip)
                    payload = self._get_beacon_payload(override_ip=best_ip)
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
        targets = self._get_broadcast_targets()
        for bcast_ip, iface_ip in targets:
            try:
                payload = self._get_beacon_payload(override_ip=iface_ip)
                self._udp_sock.sendto(payload, (bcast_ip, self.DISCOVERY_PORT))
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

            # Ensure ADB reverse for all ecosystem ports for instant USB connectivity
            try:
                from core.adb_helper import AdbManager
                adb = AdbManager()
                if adb.is_available():
                    adb.reverse_ecosystem_ports()
            except Exception:
                pass
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
        client_ip = addr[0] if (addr and len(addr) > 0 and addr[0]) else "127.0.0.1"
        self.last_client_ip = client_ip
        device_model = "Android Device"
        session_id = ""

        if client_ip.startswith("127."):
            link_mode = "USB (ADB)"
        elif client_ip.startswith("10.") or client_ip.startswith("192.168.42.") or client_ip.startswith("192.168.43."):
            link_mode = "USB Tethering"
        else:
            link_mode = "Wi-Fi LAN"

        try:
            sock.settimeout(10.0)  # Heartbeat ping is every 2s, 10s timeout detects dead link gracefully
            sock_file = sock.makefile("r", encoding="utf-8")

            while self.is_running:
                line = sock_file.readline()
                if not line:
                    # Remote client closed socket cleanly
                    break

                text = line.strip()
                if not text:
                    continue

                response_dict = None
                payload = {}
                if text.startswith("{") and text.endswith("}"):
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = {}

                if payload.get("model") or payload.get("device_model"):
                    device_model = payload.get("model") or payload.get("device_model")
                if payload.get("session_id"):
                    session_id = payload.get("session_id")

                action = payload.get("action", "").upper() if payload else ("PING" if "PING" in text.upper() else "")

                if action == "DISCONNECT":
                    break

                # 1. PING / Discovery Handshake / Keepalive
                if "PING" in text.upper() or action == "PING" or action == "CONNECT":
                    connected_ip = sock.getsockname()[0]
                    if not connected_ip or connected_ip == "0.0.0.0":
                        connected_ip = self._get_best_local_ip_for(client_ip)

                    response_dict = {
                        "status": "PONG",
                        "type": "ZEROLINK_GATEWAY",
                        "name": f"ZeroLink PC ({self.hostname})",
                        "session_id": session_id,
                        "ip": connected_ip,
                        "port": self.tcp_port
                    }

                    self.gateway_client_updated.emit({
                        "client_ip": client_ip,
                        "model": device_model,
                        "mode": link_mode,
                        "session_id": session_id,
                        "timestamp": time.time(),
                        "status": "CONNECTED"
                    })

                # 2. Remote Module Wake-up (ZeroWake)
                elif "WAKE" in text.upper():
                    try:
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
            try:
                self.gateway_client_updated.emit({
                    "client_ip": client_ip,
                    "model": device_model,
                    "mode": link_mode,
                    "session_id": session_id,
                    "timestamp": time.time(),
                    "status": "DISCONNECTED"
                })
            except Exception:
                pass
