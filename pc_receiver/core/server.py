"""ZeroCast TCP Server Engine
Handles incoming Android client connections, 16-byte protocol parsing, and frame dispatch.
"""

import socket
import threading
import time
import json
from typing import Optional, List, Dict
from PyQt6.QtCore import QObject, pyqtSignal

from core.protocol import (
    MAGIC_BYTE,
    HEADER_SIZE,
    unpack_header,
    pack_header,
    TYPE_VIDEO_MJPEG,
    TYPE_INPUT_CONTROL,
    TYPE_CONFIG_JSON
)


class StreamServer(QObject):
    # Signals for Qt UI thread
    client_connected = pyqtSignal(str)          # Client IP:port
    client_disconnected = pyqtSignal()
    clients_updated = pyqtSignal()              # Emitted when active client list changes
    frame_received = pyqtSignal(bytes, int, int) # payload, type, timestamp_us
    audio_received = pyqtSignal(bytes)           # raw PCM audio
    config_received = pyqtSignal(str)            # JSON config string
    status_changed = pyqtSignal(str)

    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        super().__init__()
        self.host = host
        self.port = port
        self.is_running = False
        self._server_sock: Optional[socket.socket] = None
        self._client_sock: Optional[socket.socket] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._client_thread: Optional[threading.Thread] = None
        self.current_client_info: Optional[Dict] = None

    def start(self):
        """Starts the TCP listener thread."""
        if self.is_running:
            return
        self.is_running = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        self.status_changed.emit(f"Server listening on {self.host}:{self.port}")

    def stop(self):
        """Stops the server and cleans up connections."""
        self.is_running = False
        self._close_client()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        self.status_changed.emit("Server stopped")

    def _close_client(self):
        if self._client_sock:
            try:
                self._client_sock.shutdown(socket.SHUT_RDWR)
                self._client_sock.close()
            except Exception:
                pass
            self._client_sock = None

    def send_control_packet(self, command_payload: bytes):
        """Send reverse input command (Packet Type 0x05) to Android client."""
        if not self._client_sock:
            return
        try:
            ts_us = int(time.time() * 1_000_000)
            header = pack_header(TYPE_INPUT_CONTROL, 0, len(command_payload), ts_us)
            self._client_sock.sendall(header + command_payload)
        except Exception as e:
            self.status_changed.emit(f"Failed to send control packet: {e}")

    def send_config_json(self, json_str: str):
        """Send config update (Packet Type 0x04) to Android client."""
        if not self._client_sock:
            return
        try:
            payload = json_str.encode("utf-8")
            ts_us = int(time.time() * 1_000_000)
            header = pack_header(TYPE_CONFIG_JSON, 0, len(payload), ts_us)
            self._client_sock.sendall(header + payload)
        except Exception as e:
            self.status_changed.emit(f"Failed to send config: {e}")

    def _listen_loop(self):
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(1)

            while self.is_running:
                try:
                    self._server_sock.settimeout(1.0)
                    client, addr = self._server_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                self.status_changed.emit(f"Connection from {addr[0]}:{addr[1]}")
                # Optimize socket for low-latency streaming
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
                
                self._close_client()
                self._client_sock = client
                self.current_client_info = {
                    "addr": f"{addr[0]}:{addr[1]}",
                    "ip": addr[0],
                    "port": addr[1],
                    "model": "Android Client",
                    "mode": "Screen Mirror",
                    "codec": "H.264",
                    "connected_at": time.time()
                }
                self.client_connected.emit(f"{addr[0]}:{addr[1]}")
                self.clients_updated.emit()

                # Handle client traffic
                self._handle_client(client)
                self.current_client_info = None
                self.client_disconnected.emit()
                self.clients_updated.emit()
                self.status_changed.emit("Client disconnected. Waiting for connection...")
        except Exception as e:
            if self.is_running:
                self.status_changed.emit(f"Server error: {e}")
        finally:
            self.stop()

    def _read_exact(self, sock: socket.socket, num_bytes: int) -> Optional[bytes]:
        """Reads exactly num_bytes from the socket or returns None on disconnection."""
        chunks = []
        bytes_left = num_bytes
        while bytes_left > 0:
            try:
                chunk = sock.recv(min(bytes_left, 65536))
                if not chunk:
                    return None
                chunks.append(chunk)
                bytes_left -= len(chunk)
            except (socket.timeout, BlockingIOError):
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                return None
        return b"".join(chunks)

    def _handle_client(self, client: socket.socket):
        client.settimeout(5.0)
        while self.is_running:
            try:
                # 1. Read 16-byte fixed header
                header_data = self._read_exact(client, HEADER_SIZE)
                if not header_data:
                    break

                # 2. Check Magic Byte
                if header_data[0] != MAGIC_BYTE:
                    # Sync lost: scan forward for next magic byte
                    continue

                parsed = unpack_header(header_data)
                if not parsed:
                    continue

                packet_type, flags, payload_len, timestamp_us = parsed

                # Sanity check payload size (Max 25 MB per packet)
                if payload_len <= 0 or payload_len > 25 * 1024 * 1024:
                    break

                # 3. Read payload data
                payload = self._read_exact(client, payload_len)
                if not payload:
                    break

                # 4. Dispatch packet
                if packet_type in (TYPE_VIDEO_MJPEG, 0x02):
                    self.frame_received.emit(payload, packet_type, timestamp_us)
                elif packet_type == 0x03:  # TYPE_AUDIO
                    self.audio_received.emit(payload)
                elif packet_type == TYPE_CONFIG_JSON:
                    try:
                        cfg_str = payload.decode("utf-8")
                        self.config_received.emit(cfg_str)
                        cfg = json.loads(cfg_str)
                        if self.current_client_info:
                            model = cfg.get("device_model") or cfg.get("model")
                            if model:
                                self.current_client_info["model"] = model
                            if "codec" in cfg:
                                self.current_client_info["codec"] = cfg["codec"]
                            if "mode" in cfg:
                                self.current_client_info["mode"] = cfg["mode"]
                            self.clients_updated.emit()
                    except Exception:
                        pass
            except Exception:
                break

    def get_connected_clients(self) -> List[Dict]:
        """Returns list of currently connected streaming clients."""
        if self.current_client_info:
            return [dict(self.current_client_info)]
        return []

    def disconnect_client(self, addr: Optional[str] = None):
        """Forcefully disconnects current stream client."""
        self._close_client()

