"""ZeroLink Audio Mixer Control Service (ZeroMix)
TCP Server on Port 8891. Provides remote wireless mixer faders,
mute toggles, ducking controls, and soundboard trigger/refresh for Android mobile.
"""

import json
import time
import socket
import select
import threading
from typing import Optional, List, Dict
from PyQt6.QtCore import QObject, pyqtSignal
from core.adb_helper import AdbManager
from core.audio_mixer import AudioMixerEngine


class ZeroMixService(QObject):
    client_count_changed = pyqtSignal(int)

    def __init__(self, engine: AudioMixerEngine, port: int = 8891, adb_manager: Optional[AdbManager] = None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.port = port
        self.adb_manager = adb_manager or AdbManager()
        self.is_running = False

        self._server_sock: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._lock = threading.Lock()
        self._server_thread: Optional[threading.Thread] = None

        # Hook engine signals to broadcast updates to mobile
        self.engine.soundboard_list_changed.connect(self.broadcast_sound_list)
        self.engine.state_changed.connect(self.broadcast_state)

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

            self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self._server_thread.start()
            return True
        except Exception as e:
            print(f"[ZeroMix] Failed to start control service on port {self.port}: {e}")
            self.stop()
            return False

    def stop(self) -> bool:
        self.is_running = False
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        self.client_count_changed.emit(0)
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
                        self.client_count_changed.emit(len(self._clients))
                        # Send initial state immediately
                        self._send_to_client(client_sock, self._get_full_state_payload())
                    else:
                        self._read_client(s)
            except Exception:
                break

    def _read_client(self, sock: socket.socket):
        try:
            data = sock.recv(16384)
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
                    self._handle_command(sock, msg)
                except Exception as e:
                    print(f"[ZeroMix] JSON parse error: {e}")
        except Exception:
            self._remove_client(sock)

    def _handle_command(self, sock: socket.socket, msg: Dict):
        action = msg.get("action")

        if action in ("GET_STATE", "CONNECT"):
            self._send_to_client(sock, self._get_full_state_payload())

        elif action in ("GET_SOUNDS", "REFRESH_SOUNDS"):
            # Explicit refresh request from mobile phone
            payload = {
                "action": "SOUND_LIST",
                "sounds": [{"id": item["id"], "name": item["name"]} for item in self.engine.soundboard_items]
            }
            self._send_to_client(sock, payload)

        elif action == "PLAY_SOUND":
            sound_id = msg.get("id", "")
            if sound_id:
                self.engine.play_sound(sound_id)

        elif action == "STOP_SOUND":
            self.engine.stop_sound()

        elif action == "SET_VOLUME":
            ch = msg.get("channel", "")
            vol = int(msg.get("volume", 100))
            if ch == "mic":
                self.engine.set_mic_volume(vol)
            elif ch == "music":
                self.engine.set_music_volume(vol)
            elif ch == "soundboard":
                self.engine.set_soundboard_volume(vol)

        elif action == "SET_MUTE":
            ch = msg.get("channel", "")
            muted = bool(msg.get("muted", False))
            if ch == "mic":
                self.engine.set_mic_mute(muted)
            elif ch == "music":
                self.engine.set_music_mute(muted)
            elif ch == "soundboard":
                self.engine.set_soundboard_mute(muted)

        elif action == "SET_DUCKING":
            enabled = bool(msg.get("enabled", self.engine.ducking_enabled))
            level = int(msg.get("level", int(self.engine.ducking_level * 100)))
            self.engine.set_ducking_config(enabled, level)

    def _get_full_state_payload(self) -> Dict:
        return {
            "action": "STATE_UPDATE",
            "mic_vol": int(self.engine.vol_mic * 100),
            "music_vol": int(self.engine.vol_music * 100),
            "sound_vol": int(self.engine.vol_soundboard * 100),
            "mic_muted": self.engine.mute_mic,
            "music_muted": self.engine.mute_music,
            "sound_muted": self.engine.mute_soundboard,
            "ducking_enabled": self.engine.ducking_enabled,
            "ducking_level": int(self.engine.ducking_level * 100),
            "sounds": [{"id": item["id"], "name": item["name"]} for item in self.engine.soundboard_items]
        }

    def broadcast_state(self):
        """Broadcasts latest mixer state (volumes, mutes, ducking, sounds) to all connected mobile clients."""
        payload = self._get_full_state_payload()
        self.broadcast(payload)

    def broadcast_sound_list(self):
        """Notifies all connected mobile clients with the latest soundboard list."""
        payload = {
            "action": "SOUND_LIST",
            "sounds": [{"id": item["id"], "name": item["name"]} for item in self.engine.soundboard_items]
        }
        self.broadcast(payload)

    def broadcast(self, payload: Dict):
        encoded = (json.dumps(payload) + "\n").encode("utf-8")
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
                try:
                    d.close()
                except Exception:
                    pass
        if dead:
            self.client_count_changed.emit(len(self._clients))

    def _send_to_client(self, sock: socket.socket, payload: Dict):
        try:
            encoded = (json.dumps(payload) + "\n").encode("utf-8")
            sock.sendall(encoded)
        except Exception:
            self._remove_client(sock)

    def _remove_client(self, sock: socket.socket):
        with self._lock:
            if sock in self._clients:
                self._clients.remove(sock)
            try:
                sock.close()
            except Exception:
                pass
        self.client_count_changed.emit(len(self._clients))
