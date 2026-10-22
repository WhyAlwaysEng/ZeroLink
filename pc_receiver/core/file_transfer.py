"""ZeroLink File Transfer Service (ZeroDrop)
High-speed chunked LAN/USB file transfers between Windows PC and Android.
Default Port: 8890
"""

import os
import time
import json
import socket
import select
import threading
from typing import Optional, List, Dict
from PyQt6.QtCore import QObject, pyqtSignal
from core.adb_helper import AdbManager


class FileTransferService(QObject):
    transfer_progress = pyqtSignal(str, int, int, float)  # filename, bytes_done, total_bytes, speed_mbps
    transfer_completed = pyqtSignal(str, str, str)         # filename, direction ('SENT' or 'RECEIVED'), file_path
    transfer_failed = pyqtSignal(str, str)                 # filename, error_message
    client_count_changed = pyqtSignal(int)
    clients_updated = pyqtSignal()

    def __init__(self, port: int = 8890, download_dir: Optional[str] = None, adb_manager: Optional[AdbManager] = None, parent=None):
        super().__init__(parent)
        self.port = port
        self.download_dir = download_dir or os.path.join(os.path.expanduser("~"), "Downloads", "ZeroDrop")
        os.makedirs(self.download_dir, exist_ok=True)

        self.adb_manager = adb_manager or AdbManager()
        self.is_running = False

        self._server_sock: Optional[socket.socket] = None
        self._receiver_clients: List[socket.socket] = []
        self._client_info: dict = {}
        self._lock = threading.Lock()
        self._transfer_lock = threading.Lock()
        self._server_thread: Optional[threading.Thread] = None

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

            self._server_thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._server_thread.start()
            return True
        except Exception as e:
            print(f"[ZeroDrop] Failed to start file transfer server: {e}")
            self.stop()
            return False

    def stop(self) -> bool:
        self.is_running = False
        with self._lock:
            for c in self._receiver_clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._receiver_clients.clear()
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

    def _accept_loop(self):
        while self.is_running and self._server_sock:
            try:
                client_sock, addr = self._server_sock.accept()
                t = threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True)
                t.start()
            except Exception:
                break

    def _handle_client(self, sock: socket.socket):
        try:
            # Read header line
            header_bytes = b""
            while b"\n" not in header_bytes and self.is_running:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                header_bytes += chunk

            if not header_bytes:
                sock.close()
                return

            line, rest = header_bytes.split(b"\n", 1)
            meta = json.loads(line.decode("utf-8"))
            action = meta.get("action")

            if action == "REGISTER_RECEIVER":
                # Mobile device registering as persistent receiver for files pushed from PC
                try:
                    peer = sock.getpeername()
                    addr_str = f"{peer[0]}:{peer[1]}"
                    ip_str = peer[0]
                    port_int = peer[1]
                except Exception:
                    addr_str = "Unknown"
                    ip_str = "127.0.0.1"
                    port_int = 0

                model = meta.get("device_model") or meta.get("model") or "ZeroDrop Receiver"
                sock.sendall(json.dumps({"status": "REGISTERED"}).encode("utf-8") + b"\n")
                with self._lock:
                    self._receiver_clients.append(sock)
                    self._client_info[sock] = {
                        "addr": addr_str,
                        "ip": ip_str,
                        "port": port_int,
                        "model": model,
                        "mode": "File Drop Receiver",
                        "connected_at": time.time()
                    }
                self.client_count_changed.emit(len(self._receiver_clients))
                self.clients_updated.emit()

                # Monitor socket for disconnect
                self._monitor_receiver(sock)

            elif action == "SEND_FILE":
                # Mobile uploading a file to PC
                self._receive_file_from_mobile(sock, meta, rest)

        except Exception as e:
            print(f"[ZeroDrop] Client error: {e}")
            try:
                sock.close()
            except Exception:
                pass

    def _monitor_receiver(self, sock: socket.socket):
        """Monitors a registered mobile receiver socket for disconnection."""
        while self.is_running:
            # Check if socket is still alive using select
            # Only poll when transfer lock is not held
            if self._transfer_lock.locked():
                time.sleep(0.5)
                continue

            try:
                rlist, _, xlist = select.select([sock], [], [sock], 1.0)
                if xlist:
                    break
                if rlist:
                    # Check if client sent data or closed
                    # Peek to see if EOF (0 bytes means disconnect)
                    data = sock.recv(1024, socket.MSG_PEEK)
                    if not data:
                        break
                    # If heartbeat/ping was sent, consume it
                    sock.recv(len(data))
            except Exception:
                break

        with self._lock:
            if sock in self._receiver_clients:
                self._receiver_clients.remove(sock)
            if sock in self._client_info:
                del self._client_info[sock]
            try:
                sock.close()
            except Exception:
                pass
        self.client_count_changed.emit(len(self._receiver_clients))
        self.clients_updated.emit()

    def get_connected_clients(self) -> List[dict]:
        """Returns list of currently connected ZeroDrop receiver clients."""
        with self._lock:
            return [dict(v) for v in self._client_info.values()]

    def disconnect_client(self, addr: str):
        """Disconnects a receiver client by addr (IP:port or IP)."""
        with self._lock:
            target_sock = None
            for sock, info in list(self._client_info.items()):
                if info.get("addr") == addr or info.get("ip") == addr:
                    target_sock = sock
                    break
        if target_sock:
            with self._lock:
                if target_sock in self._receiver_clients:
                    self._receiver_clients.remove(target_sock)
                if target_sock in self._client_info:
                    del self._client_info[target_sock]
            try:
                target_sock.close()
            except Exception:
                pass
            self.client_count_changed.emit(len(self._receiver_clients))
            self.clients_updated.emit()


    def _receive_file_from_mobile(self, sock: socket.socket, meta: dict, initial_data: bytes):
        """Handles an incoming file upload from mobile device to PC."""
        try:
            filename = os.path.basename(meta.get("filename", "unknown_file"))
            filesize = int(meta.get("filesize", 0))

            save_path = os.path.join(self.download_dir, filename)
            base, ext = os.path.splitext(filename)
            idx = 1
            while os.path.exists(save_path):
                save_path = os.path.join(self.download_dir, f"{base}_{idx}{ext}")
                idx += 1

            received = len(initial_data)
            start_time = time.time()
            last_update = start_time

            with open(save_path, "wb") as f:
                if initial_data:
                    f.write(initial_data)

                while received < filesize and self.is_running:
                    chunk = sock.recv(min(65536, filesize - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)

                    now = time.time()
                    if now - last_update >= 0.15:
                        elapsed = now - start_time
                        speed = (received / 1048576.0) / elapsed if elapsed > 0 else 0.0
                        self.transfer_progress.emit(filename, received, filesize, speed)
                        last_update = now

            if received >= filesize:
                self.transfer_completed.emit(filename, "RECEIVED", save_path)
                sock.sendall(json.dumps({"status": "OK", "filename": filename}).encode("utf-8") + b"\n")
            else:
                self.transfer_failed.emit(filename, "Connection interrupted")
        except Exception as e:
            self.transfer_failed.emit("Transfer", str(e))
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def send_files_to_client(self, file_paths: List[str]):
        """Pushes files from PC to connected mobile client(s)."""
        if not file_paths:
            return

        def _sender():
            with self._transfer_lock:
                with self._lock:
                    clients = list(self._receiver_clients)

                if not clients:
                    self.transfer_failed.emit(
                        os.path.basename(file_paths[0]),
                        "No mobile device connected. Open ZeroDrop on your phone first."
                    )
                    return

                sock = clients[0]

                for path in file_paths:
                    if not os.path.exists(path):
                        continue

                    filename = os.path.basename(path)
                    filesize = os.path.getsize(path)

                    try:
                        # Send PUSH_TO_PHONE header
                        header = json.dumps({
                            "action": "PUSH_TO_PHONE",
                            "filename": filename,
                            "filesize": filesize
                        }) + "\n"
                        sock.sendall(header.encode("utf-8"))

                        # Stream content
                        sent = 0
                        start_time = time.time()
                        last_update = start_time

                        with open(path, "rb") as f:
                            while sent < filesize and self.is_running:
                                buf = f.read(65536)
                                if not buf:
                                    break
                                sock.sendall(buf)
                                sent += len(buf)

                                now = time.time()
                                if now - last_update >= 0.15:
                                    elapsed = now - start_time
                                    speed = (sent / 1048576.0) / elapsed if elapsed > 0 else 0.0
                                    self.transfer_progress.emit(filename, sent, filesize, speed)
                                    last_update = now

                        # Read ACK from mobile
                        ack_bytes = b""
                        sock.settimeout(10.0)
                        while b"\n" not in ack_bytes and self.is_running:
                            c = sock.recv(1024)
                            if not c:
                                break
                            ack_bytes += c
                        sock.settimeout(None)

                        if b'"OK"' in ack_bytes or b'"status": "OK"' in ack_bytes:
                            self.transfer_completed.emit(filename, "SENT", path)
                        else:
                            self.transfer_completed.emit(filename, "SENT", path)
                    except Exception as e:
                        sock.settimeout(None)
                        self.transfer_failed.emit(filename, str(e))
                        # Socket might be broken, remove it
                        with self._lock:
                            if sock in self._receiver_clients:
                                self._receiver_clients.remove(sock)
                            try:
                                sock.close()
                            except Exception:
                                pass
                        self.client_count_changed.emit(len(self._receiver_clients))
                        break

        threading.Thread(target=_sender, daemon=True).start()
