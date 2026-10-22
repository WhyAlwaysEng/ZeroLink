"""ZeroLink Clipboard Sync Service
Handles local clipboard monitoring and real-time TCP synchronization with mobile devices.
Default Port: 8889
"""

import json
import time
import socket
import select
import threading
from typing import List, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from core.adb_helper import AdbManager


class ClipboardService(QObject):
    clip_received = pyqtSignal(str, str, float)  # text, source ('PC' or 'PHONE'), timestamp
    client_count_changed = pyqtSignal(int)
    clients_updated = pyqtSignal()

    def __init__(self, port: int = 8889, adb_manager: Optional[AdbManager] = None, parent=None):
        super().__init__(parent)
        self.port = port
        self.adb_manager = adb_manager or AdbManager()
        self.is_running = False
        self.sync_enabled = True

        self._server_sock: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._client_info: dict = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._last_synced_text: str = ""
        self._last_synced_time: float = 0.0

    def start(self) -> bool:
        if self.is_running:
            return True

        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind(("0.0.0.0", self.port))
            self._server_sock.listen(5)
            self.is_running = True

            # USB tunnel
            if self.adb_manager.is_available():
                self.adb_manager.reverse_port(self.port)

            self._thread = threading.Thread(target=self._server_loop, daemon=True)
            self._thread.start()

            # Hook into Qt Clipboard dataChanged
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.dataChanged.connect(self._on_local_clipboard_changed)

            return True
        except Exception as e:
            print(f"[ZeroClip] Failed to start server on port {self.port}: {e}")
            self.stop()
            return False

    def stop(self) -> bool:
        self.is_running = False
        try:
            clipboard = QApplication.clipboard()
            if clipboard:
                try:
                    clipboard.dataChanged.disconnect(self._on_local_clipboard_changed)
                except Exception:
                    pass
        except Exception:
            pass

        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
            self._client_info.clear()

        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        self.client_count_changed.emit(0)
        self.clients_updated.emit()
        return True

    def _server_loop(self):
        while self.is_running and self._server_sock:
            try:
                rlist, _, _ = select.select([self._server_sock] + self._clients, [], [], 1.0)
                for s in rlist:
                    if s is self._server_sock:
                        client_sock, addr = self._server_sock.accept()
                        client_sock.setblocking(False)
                        with self._lock:
                            self._clients.append(client_sock)
                            self._client_info[client_sock] = {
                                "addr": f"{addr[0]}:{addr[1]}",
                                "ip": addr[0],
                                "port": addr[1],
                                "model": "ZeroClip Client",
                                "mode": "Live Clipboard Sync",
                                "connected_at": time.time()
                            }
                        self.client_count_changed.emit(len(self._clients))
                        self.clients_updated.emit()
                    else:
                        self._read_client_data(s)
            except Exception:
                break

    def _read_client_data(self, sock: socket.socket):
        try:
            data = sock.recv(65536)
            if not data:
                self._remove_client(sock)
                return

            lines = data.decode("utf-8", errors="ignore").splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    action = msg.get("action")
                    if action == "SYNC_CLIP":
                        model = msg.get("device_model") or msg.get("model")
                        if model and sock in self._client_info:
                            self._client_info[sock]["model"] = model
                            self.clients_updated.emit()
                        text = msg.get("text", "")
                        source = msg.get("source", "PHONE")
                        ts = msg.get("timestamp", time.time())
                        if text and text != self._last_synced_text:
                            self._last_synced_text = text
                            self._last_synced_time = ts

                            # Update local Windows clipboard
                            clipboard = QApplication.clipboard()
                            if clipboard and self.sync_enabled:
                                # Temporarily block self._on_local_clipboard_changed
                                clipboard.blockSignals(True)
                                clipboard.setText(text)
                                clipboard.blockSignals(False)

                            self.clip_received.emit(text, source, ts)
                except Exception:
                    pass
        except Exception:
            self._remove_client(sock)

    def _remove_client(self, sock: socket.socket):
        with self._lock:
            if sock in self._clients:
                self._clients.remove(sock)
            if sock in self._client_info:
                del self._client_info[sock]
            try:
                sock.close()
            except Exception:
                pass
        self.client_count_changed.emit(len(self._clients))
        self.clients_updated.emit()

    def _on_local_clipboard_changed(self):
        if not self.sync_enabled or not self.is_running:
            return
        clipboard = QApplication.clipboard()
        if not clipboard:
            return
        text = clipboard.text()
        if not text or text == self._last_synced_text:
            return

        now = time.time()
        # Debounce quick duplicate events
        if now - self._last_synced_time < 0.2 and text == self._last_synced_text:
            return

        self._last_synced_text = text
        self._last_synced_time = now

        self.clip_received.emit(text, "PC", now)
        self.broadcast_clipboard(text)

    def broadcast_clipboard(self, text: str):
        """Sends the clipboard text to all connected mobile devices."""
        if not self.is_running or not self._clients:
            return

        payload = json.dumps({
            "action": "SYNC_CLIP",
            "text": text,
            "source": "PC",
            "timestamp": time.time()
        }) + "\n"
        encoded = payload.encode("utf-8")

        dead = []
        with self._lock:
            for c in self._clients:
                try:
                    c.sendall(encoded)
                except Exception:
                    dead.append(c)

            for d in dead:
                if d in self._clients:
                    self._clients.remove(d)
                if d in self._client_info:
                    del self._client_info[d]
                try:
                    d.close()
                except Exception:
                    pass

        if dead:
            self.client_count_changed.emit(len(self._clients))
            self.clients_updated.emit()

    def get_connected_clients(self) -> List[dict]:
        """Returns list of currently connected ZeroClip clients."""
        with self._lock:
            return [dict(v) for v in self._client_info.values()]

    def disconnect_client(self, addr: str):
        """Disconnects a client by addr (IP:port or IP)."""
        with self._lock:
            target_sock = None
            for sock, info in list(self._client_info.items()):
                if info.get("addr") == addr or info.get("ip") == addr:
                    target_sock = sock
                    break
        if target_sock:
            self._remove_client(target_sock)

