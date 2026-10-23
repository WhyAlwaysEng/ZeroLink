"""ZeroPad TCP Server
Receives remote media, macro, and application commands from Android mobile devices.
"""

import ctypes
import json
import os
import socket
import subprocess
import threading
import time
from typing import Dict, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal

# Windows Virtual-Key Codes
VK_LWIN = 0x5B
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B
VK_SNAPSHOT = 0x2C  # PrintScreen

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_KEYUP = 0x0002

# Windows Mouse Event Flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

from ctypes import wintypes

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_ulonglong)
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT)]
    _anonymous_ = ('_input',)
    _fields_ = [
        ('type', wintypes.DWORD),
        ('_input', _INPUT)
    ]

KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1


def _type_unicode_text(text: str):
    """Types any UTF-8/Unicode string (English, Thai, etc.) into the active window."""
    if os.name != 'nt' or not text:
        return
    inputs = []
    for char in text:
        if char == '\n':
            down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0x0D, wScan=0, dwFlags=0, time=0, dwExtraInfo=0))
            up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0x0D, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))
            inputs.extend([down, up])
        else:
            code = ord(char)
            down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0))
            up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))
            inputs.extend([down, up])
    if inputs:
        arr = (INPUT * len(inputs))(*inputs)
        ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _press_and_release(vk_code: int):
    """Presses and releases a single virtual key."""
    if os.name != 'nt':
        return
    u32 = ctypes.windll.user32
    u32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.02)
    u32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def _send_combo(keys: List[int]):
    """Presses a combination of keys and releases them in reverse order."""
    if os.name != 'nt':
        return
    u32 = ctypes.windll.user32
    for k in keys:
        u32.keybd_event(k, 0, 0, 0)
        time.sleep(0.01)
    time.sleep(0.03)
    for k in reversed(keys):
        u32.keybd_event(k, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)


class PadServer(QObject):
    """TCP Server for ZeroPad Remote Controller."""

    command_executed = pyqtSignal(str, str)  # action, details
    client_connected = pyqtSignal(str, str)   # ip, model
    client_disconnected = pyqtSignal(str)     # ip
    clients_updated = pyqtSignal()

    def __init__(self, port: int = 8894, parent=None):
        super().__init__(parent)
        self.port = port
        self.is_running = False
        self._server_sock: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._clients: Dict[str, Dict] = {}

    def start(self) -> bool:
        if self.is_running:
            return True

        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._server_sock.bind(("0.0.0.0", self.port))
            self._server_sock.listen(5)
            self.is_running = True

            self._server_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._server_thread.start()
            print(f"[ZeroPad] Server listening on port {self.port}")
            return True
        except Exception as e:
            print(f"[ZeroPad] Start error: {e}")
            self.stop()
            return False

    def stop(self):
        self.is_running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

    def _listen_loop(self):
        while self.is_running and self._server_sock:
            try:
                client_sock, addr = self._server_sock.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                ip = addr[0]
                t = threading.Thread(target=self._client_worker, args=(client_sock, addr), daemon=True)
                t.start()
            except Exception:
                break

    def _client_worker(self, client_sock: socket.socket, addr):
        ip = addr[0]
        info = {
            "ip": ip,
            "addr": f"{addr[0]}:{addr[1]}",
            "model": "Mobile Controller",
            "connected_at": time.time(),
            "mode": "Stream Deck / Macro Pad"
        }

        with self._lock:
            self._clients[ip] = info
        self.client_connected.emit(ip, info["model"])
        self.clients_updated.emit()

        try:
            buf = b""
            while self.is_running:
                data = client_sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line_str = line.decode("utf-8", errors="ignore").strip()
                    if line_str:
                        self._handle_command(line_str, ip)
        except Exception:
            pass
        finally:
            with self._lock:
                if ip in self._clients:
                    del self._clients[ip]
            try:
                client_sock.close()
            except Exception:
                pass
            self.client_disconnected.emit(ip)
            self.clients_updated.emit()

    def _handle_command(self, cmd_json: str, client_ip: str):
        try:
            msg = json.loads(cmd_json)
            action = msg.get("action", "")

            if action == "CONNECT":
                model = msg.get("model") or msg.get("device_model", "Android Controller")
                with self._lock:
                    if client_ip in self._clients:
                        self._clients[client_ip]["model"] = model
                self.clients_updated.emit()
                return

            if action == "MOUSE_MOVE":
                dx = int(msg.get("dx", 0))
                dy = int(msg.get("dy", 0))
                if os.name == 'nt' and (dx != 0 or dy != 0):
                    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)
                return

            elif action == "MOUSE_CLICK":
                btn = msg.get("button", "left").lower()
                if os.name == 'nt':
                    if btn == "left":
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    elif btn == "right":
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                    elif btn == "middle":
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
                        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
                self.command_executed.emit("Click", btn)
                return

            elif action == "MOUSE_DOWN":
                btn = msg.get("button", "left").lower()
                if os.name == 'nt':
                    flag = MOUSEEVENTF_LEFTDOWN if btn == "left" else MOUSEEVENTF_RIGHTDOWN
                    ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)
                return

            elif action == "MOUSE_UP":
                btn = msg.get("button", "left").lower()
                if os.name == 'nt':
                    flag = MOUSEEVENTF_LEFTUP if btn == "left" else MOUSEEVENTF_RIGHTUP
                    ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)
                return

            elif action == "MOUSE_SCROLL":
                dy = int(msg.get("dy", 0))
                if os.name == 'nt' and dy != 0:
                    ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, dy, 0)
                return

            elif action == "TYPE_TEXT":
                text = msg.get("text", "")
                _type_unicode_text(text)
                self.command_executed.emit("Type", text[:25] if len(text) > 25 else text)
                return

            elif action == "SPECIAL_KEY":
                key = msg.get("key", "").upper()
                if key == "BACKSPACE":
                    _press_and_release(0x08)
                elif key == "ENTER":
                    _press_and_release(0x0D)
                elif key == "SPACE":
                    _press_and_release(0x20)
                elif key == "TAB":
                    _press_and_release(0x09)
                elif key == "ESC":
                    _press_and_release(0x1B)
                self.command_executed.emit("Key", key)
                return

            if action == "MEDIA_KEY":
                key = msg.get("key", "").upper()
                if key == "PLAY_PAUSE":
                    _press_and_release(VK_MEDIA_PLAY_PAUSE)
                elif key == "NEXT":
                    _press_and_release(VK_MEDIA_NEXT_TRACK)
                elif key == "PREV":
                    _press_and_release(VK_MEDIA_PREV_TRACK)
                elif key == "VOL_UP":
                    _press_and_release(VK_VOLUME_UP)
                elif key == "VOL_DOWN":
                    _press_and_release(VK_VOLUME_DOWN)
                elif key == "MUTE":
                    _press_and_release(VK_VOLUME_MUTE)
                self.command_executed.emit("Media", key)

            elif action == "MACRO":
                name = msg.get("name", "").upper()
                if name == "DISCORD_MUTE":
                    # Ctrl + Shift + M (Default Discord toggle mute)
                    _send_combo([VK_CONTROL, VK_SHIFT, ord('M')])
                elif name == "DISCORD_DEAFEN":
                    # Ctrl + Shift + D (Default Discord toggle deafen)
                    _send_combo([VK_CONTROL, VK_SHIFT, ord('D')])
                elif name == "SCREENSHOT":
                    # Win + Shift + S
                    _send_combo([VK_LWIN, VK_SHIFT, ord('S')])
                elif name == "SHOW_DESKTOP":
                    # Win + D
                    _send_combo([VK_LWIN, ord('D')])
                elif name == "TASK_MANAGER":
                    # Ctrl + Shift + Esc
                    _send_combo([VK_CONTROL, VK_SHIFT, VK_ESCAPE])
                elif name == "LOCK_PC":
                    if os.name == 'nt':
                        ctypes.windll.user32.LockWorkStation()
                self.command_executed.emit("Macro", name)

            elif action == "LAUNCH":
                target = msg.get("target", "").lower()
                if target == "chrome":
                    subprocess.Popen(["cmd", "/c", "start", "chrome"], shell=True)
                elif target == "discord":
                    subprocess.Popen(["cmd", "/c", "start", "discord:"], shell=True)
                elif target == "notepad":
                    subprocess.Popen(["notepad.exe"])
                elif target == "calc":
                    subprocess.Popen(["calc.exe"])
                elif target == "explorer":
                    subprocess.Popen(["explorer.exe"])
                self.command_executed.emit("Launch", target)

        except Exception as e:
            print(f"[ZeroPad] Command error: {e}")

    def get_connected_clients(self) -> List[Dict]:
        with self._lock:
            return list(self._clients.values())

    def disconnect_client(self, ip: str):
        with self._lock:
            if ip in self._clients:
                del self._clients[ip]
        self.clients_updated.emit()
