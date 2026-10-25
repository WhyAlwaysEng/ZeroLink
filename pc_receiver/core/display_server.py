"""ZeroDisplay Streaming Server
Captures PC desktop monitor and streams ultra-low-latency video frames to mobile devices over TCP.
Receives reverse touch and mouse events from the mobile device to control PC cursor with touch.
"""

import json
import socket
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class DisplayServer(QObject):
    """ZeroDisplay TCP Server for wireless second monitor streaming and remote touch."""

    client_connected = pyqtSignal(str, str)     # ip, model
    client_disconnected = pyqtSignal(str)       # ip
    clients_updated = pyqtSignal()
    stats_updated = pyqtSignal(float, float)    # fps, bitrate_mbps

    MAGIC = b"ZDIS"  # 4-byte header magic

    def __init__(self, port: int = 8892, parent=None):
        super().__init__(parent)
        self.port = port
        self.is_running = False

        # Configuration
        self.selected_monitor_idx = 1  # 1-indexed for mss monitors list
        self.target_fps = 60
        self.quality = 90              # High-clarity 90% default (adjustable 50-100%)
        self.enable_touch = True
        self.scale_factor = 1.0        # 1.0 = native, 0.75 = downscale for performance
        self.enable_444_chroma = True  # Crystal-clear text clarity (4:4:4 JPEG chroma)
        self.sharpen_amount = 0.0      # 0.0 to 1.0 detail enhancer

        # Server socket & threads
        self._server_sock: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._capture_thread: Optional[threading.Thread] = None

        # Connected clients: sock -> dict
        self._lock = threading.Lock()
        self._clients: List[socket.socket] = []
        self._client_info: Dict[socket.socket, Dict] = {}

        # Stats
        self.fps = 0.0
        self.bitrate_mbps = 0.0
        self._frame_count = 0
        self._bytes_sent = 0
        self._last_stat_time = time.time()

    def get_monitors_list(self) -> List[Dict]:
        """Returns list of detected display monitors on the host PC."""
        monitors = []
        if HAS_MSS:
            try:
                with mss.mss() as sct:
                    for idx, m in enumerate(sct.monitors):
                        if idx == 0:
                            # Monitor 0 in mss is the combined virtual desktop
                            monitors.append({
                                "index": 0,
                                "name": f"All Displays Combined ({m['width']}x{m['height']})",
                                "left": m["left"],
                                "top": m["top"],
                                "width": m["width"],
                                "height": m["height"]
                            })
                        else:
                            monitors.append({
                                "index": idx,
                                "name": f"Display {idx} ({m['width']}x{m['height']})",
                                "left": m["left"],
                                "top": m["top"],
                                "width": m["width"],
                                "height": m["height"]
                            })
            except Exception as e:
                print(f"[ZeroDisplay] Error enumerating monitors: {e}")

        if not monitors:
            monitors.append({
                "index": 1,
                "name": "Primary Display (1920x1080)",
                "left": 0,
                "top": 0,
                "width": 1920,
                "height": 1080
            })
        return monitors

    def start(self) -> bool:
        if self.is_running:
            return True

        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._server_sock.bind(("0.0.0.0", self.port))
            self._server_sock.listen(4)
            self.is_running = True

            self._server_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._server_thread.start()

            self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()

            print(f"[ZeroDisplay] Server started on port {self.port}")
            return True
        except Exception as e:
            print(f"[ZeroDisplay] Start error: {e}")
            self.stop()
            return False

    def stop(self):
        self.is_running = False
        with self._lock:
            for s in list(self._clients):
                try:
                    s.close()
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

        self.fps = 0.0
        self.bitrate_mbps = 0.0
        self.stats_updated.emit(0.0, 0.0)
        self.clients_updated.emit()
        print("[ZeroDisplay] Server stopped.")

    def _listen_loop(self):
        while self.is_running and self._server_sock:
            try:
                client_sock, addr = self._server_sock.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)
                except Exception:
                    pass
                ip = addr[0]

                info = {
                    "addr": f"{addr[0]}:{addr[1]}",
                    "ip": ip,
                    "model": "Android Display Client",
                    "connected_at": time.time(),
                    "mode": "Extended 2nd Monitor"
                }

                with self._lock:
                    self._clients.append(client_sock)
                    self._client_info[client_sock] = info

                print(f"[ZeroDisplay] Client connected from {addr}")
                self.client_connected.emit(ip, info["model"])
                self.clients_updated.emit()

                # Start reader thread for reverse touch inputs
                t = threading.Thread(target=self._client_read_loop, args=(client_sock,), daemon=True)
                t.start()
            except Exception:
                break

    def _client_read_loop(self, client_sock: socket.socket):
        """Reads reverse touch/gesture events from the phone and maps to Windows mouse."""
        buffer = ""
        while self.is_running:
            try:
                data = client_sock.recv(4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="ignore")
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            self._handle_client_message(client_sock, msg)
                        except Exception:
                            pass
            except Exception:
                break

        self._remove_client(client_sock)

    def _handle_client_message(self, client_sock: socket.socket, msg: Dict):
        action = msg.get("action") or msg.get("type")
        if not action:
            return

        # Handshake / device info
        if action in ("HANDSHAKE", "CONNECT", "REGISTER"):
            model = msg.get("model") or msg.get("device_model")
            with self._lock:
                if client_sock in self._client_info and model:
                    self._client_info[client_sock]["model"] = model
            self.clients_updated.emit()
            return

        # Touch & Mouse Simulation
        if not self.enable_touch or not HAS_WIN32:
            return

        monitors = self.get_monitors_list()
        target_mon = None
        for m in monitors:
            if m["index"] == self.selected_monitor_idx:
                target_mon = m
                break
        if not target_mon and monitors:
            target_mon = monitors[0]

        mon_left = target_mon.get("left", 0)
        mon_top = target_mon.get("top", 0)
        mon_w = target_mon.get("width", 1920)
        mon_h = target_mon.get("height", 1080)

        # Normalized coordinates from mobile screen (0.0 to 1.0)
        norm_x = msg.get("norm_x", 0.0)
        norm_y = msg.get("norm_y", 0.0)
        target_x = int(mon_left + norm_x * mon_w)
        target_y = int(mon_top + norm_y * mon_h)

        if action == "TOUCH_MOVE" or action == "MOUSE_MOVE":
            win32api.SetCursorPos((target_x, target_y))

        elif action == "TOUCH_DOWN" or action == "MOUSE_DOWN":
            win32api.SetCursorPos((target_x, target_y))
            btn = msg.get("button", "left")
            flags = win32con.MOUSEEVENTF_RIGHTDOWN if btn == "right" else win32con.MOUSEEVENTF_LEFTDOWN
            win32api.mouse_event(flags, 0, 0, 0, 0)

        elif action == "TOUCH_UP" or action == "MOUSE_UP":
            win32api.SetCursorPos((target_x, target_y))
            btn = msg.get("button", "left")
            flags = win32con.MOUSEEVENTF_RIGHTUP if btn == "right" else win32con.MOUSEEVENTF_LEFTUP
            win32api.mouse_event(flags, 0, 0, 0, 0)

        elif action == "CLICK":
            win32api.SetCursorPos((target_x, target_y))
            btn = msg.get("button", "left")
            if btn == "right":
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            else:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        elif action == "SCROLL":
            dy = int(msg.get("dy", 0) * 120)
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, dy, 0)

    def _remove_client(self, client_sock: socket.socket):
        with self._lock:
            if client_sock in self._clients:
                self._clients.remove(client_sock)
            info = self._client_info.pop(client_sock, None)
            try:
                client_sock.close()
            except Exception:
                pass

        if info:
            self.client_disconnected.emit(info.get("ip", ""))
        self.clients_updated.emit()

    def get_connected_clients(self) -> List[Dict]:
        with self._lock:
            return [dict(v) for v in self._client_info.values()]

    def disconnect_client(self, addr: str):
        with self._lock:
            target = None
            for s, info in self._client_info.items():
                if info.get("addr") == addr or info.get("ip") == addr:
                    target = s
                    break
        if target:
            self._remove_client(target)

    def _capture_loop(self):
        """Continuously captures monitor frames and sends them to connected clients with persistent capture context."""
        interval = 1.0 / max(1, self.target_fps)
        sct = None
        if HAS_MSS:
            try:
                sct = mss.mss()
            except Exception as e:
                print(f"[ZeroDisplay] Error initializing persistent mss: {e}")

        try:
            while self.is_running:
                t_start = time.time()

                with self._lock:
                    has_clients = len(self._clients) > 0

                if not has_clients or sct is None:
                    time.sleep(0.05)
                    continue

                frame_bytes = self._grab_and_compress_frame(sct)
                if frame_bytes:
                    self._broadcast_frame(frame_bytes)

                elapsed = time.time() - t_start
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

                # Update stats every 1 second
                now = time.time()
                if now - self._last_stat_time >= 1.0:
                    dt = now - self._last_stat_time
                    self.fps = self._frame_count / dt
                    self.bitrate_mbps = (self._bytes_sent * 8.0) / (dt * 1_000_000.0)
                    self.stats_updated.emit(self.fps, self.bitrate_mbps)
                    self._frame_count = 0
                    self._bytes_sent = 0
                    self._last_stat_time = now
        finally:
            if sct is not None:
                try:
                    sct.close()
                except Exception:
                    pass

    def _grab_and_compress_frame(self, sct) -> Optional[bytes]:
        """Captures selected monitor screen and returns JPEG encoded byte payload."""
        if not HAS_MSS or sct is None:
            return None

        try:
            idx = self.selected_monitor_idx
            if idx < 0 or idx >= len(sct.monitors):
                idx = 1 if len(sct.monitors) > 1 else 0
            monitor = sct.monitors[idx]

            sct_img = sct.grab(monitor)
            frame = np.array(sct_img)  # BGRA

            # Downscale if requested
            if self.scale_factor < 0.99:
                h, w = frame.shape[:2]
                new_w = int(w * self.scale_factor)
                new_h = int(h * self.scale_factor)
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Optional Detail Enhancer / Sharpening
            if self.sharpen_amount > 0:
                blurred = cv2.GaussianBlur(frame, (0, 0), 1.5)
                frame = cv2.addWeighted(frame, 1.0 + self.sharpen_amount, blurred, -self.sharpen_amount, 0)

            # Encode as high-efficiency JPEG with optional 4:4:4 crystal-clear text chroma
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.quality)]
            if self.enable_444_chroma and hasattr(cv2, 'IMWRITE_JPEG_SAMPLING_FACTOR_444'):
                encode_param.extend([int(cv2.IMWRITE_JPEG_SAMPLING_FACTOR), int(cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444)])

            _, buf = cv2.imencode(".jpg", frame, encode_param)
            return buf.tobytes()
        except Exception:
            return None

    def _broadcast_frame(self, frame_bytes: bytes):
        """Constructs packet [ZDIS (4B)][Length (4B)][Timestamp (8B)] + JPEG payload and sends to all clients."""
        payload_len = len(frame_bytes)
        now_ms = int(time.time() * 1000)
        header = struct.pack("!4sIQ", self.MAGIC, payload_len, now_ms)
        packet = header + frame_bytes

        dead = []
        with self._lock:
            for s in self._clients:
                try:
                    s.sendall(packet)
                except Exception:
                    dead.append(s)

            for d in dead:
                self._remove_client(d)

        self._frame_count += 1
        self._bytes_sent += len(packet)
