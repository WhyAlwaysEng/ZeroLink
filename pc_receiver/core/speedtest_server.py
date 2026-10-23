"""ZeroLink SpeedTest & Latency Benchmark Server
Runs on port 8890. Measures real-world network latency (RTT), jitter,
and raw throughput (Mbps) between Android client and PC Hub over USB Cable or Wi-Fi.
"""

import json
import socket
import struct
import threading
import time
from typing import Optional, Callable
from PyQt6.QtCore import QObject, pyqtSignal

from core.adb_helper import AdbManager

SPEEDTEST_PORT = 8890
CHUNK_SIZE = 64 * 1024  # 64 KB buffer chunks


class SpeedTestServer(QObject):
    """ZeroLink Benchmark Server: Handles Ping probes and high-speed throughput measurement."""

    status_changed = pyqtSignal(str)
    test_progress = pyqtSignal(float, float)  # (progress 0.0-1.0, current_mbps)
    test_completed = pyqtSignal(dict)         # Result summary dict

    def __init__(self, port: int = SPEEDTEST_PORT, parent=None):
        super().__init__(parent)
        self.port = port
        self.is_running = False
        self._server_sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self.adb_manager = AdbManager()

    def start(self) -> bool:
        if self.is_running:
            return True
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind(("0.0.0.0", self.port))
            self._server_sock.listen(2)
            self.is_running = True

            # Ensure ADB reverse port tunnel for USB connection
            if self.adb_manager.is_available():
                self.adb_manager.reverse_port(self.port)

            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            self.status_changed.emit(f"SpeedTest server active on port {self.port}")
            return True
        except Exception as e:
            self.status_changed.emit(f"SpeedTest server failed: {e}")
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
                client_sock, client_addr = self._server_sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    daemon=True
                ).start()
            except Exception:
                break

    def _handle_client(self, sock: socket.socket, addr):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_ip = addr[0]
        is_usb = client_ip in ("127.0.0.1", "localhost", "::1")

        try:
            while self.is_running:
                # Read 4-byte message length
                raw_len = self._recv_all(sock, 4)
                if not raw_len:
                    break
                msg_len = struct.unpack("!I", raw_len)[0]
                if msg_len <= 0 or msg_len > 1_000_000:
                    break

                raw_data = self._recv_all(sock, msg_len)
                if not raw_data:
                    break

                try:
                    req = json.loads(raw_data.decode("utf-8"))
                except Exception:
                    continue

                cmd = req.get("cmd", "")

                if cmd == "PING":
                    # Echo ping probe back with server reception timestamp
                    ts = req.get("ts", time.time())
                    resp = json.dumps({"cmd": "PONG", "ts": ts, "server_ts": time.time()}).encode("utf-8")
                    self._send_frame(sock, resp)

                elif cmd == "START_BANDWIDTH_TEST":
                    # Stream high-speed test data to client for measured duration
                    duration_sec = float(req.get("duration", 3.0))
                    self._run_bandwidth_transmission(sock, duration_sec, is_usb, client_ip)
                    break  # Test complete for this session

                elif cmd == "UPLINK_START":
                    # Client is sending data to server; measure received bytes
                    duration_sec = float(req.get("duration", 3.0))
                    self._run_bandwidth_reception(sock, duration_sec, is_usb, client_ip)
                    break

        except Exception as e:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _run_bandwidth_transmission(self, sock: socket.socket, duration_sec: float, is_usb: bool, client_ip: str):
        """Pumps high-speed test buffers to client and measures throughput."""
        start_time = time.time()
        end_time = start_time + duration_sec
        total_bytes = 0
        test_payload = b"\xAA" * CHUNK_SIZE

        # Send initial confirmation header
        init_msg = json.dumps({"status": "TRANSMITTING", "chunk_size": CHUNK_SIZE}).encode("utf-8")
        self._send_frame(sock, init_msg)

        last_report = start_time
        while time.time() < end_time and self.is_running:
            try:
                sock.sendall(test_payload)
                total_bytes += CHUNK_SIZE
                now = time.time()
                if now - last_report >= 0.15:
                    elapsed = now - start_time
                    current_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
                    progress = min(1.0, elapsed / duration_sec)
                    self.test_progress.emit(progress, current_mbps)
                    last_report = now
            except Exception:
                break

        elapsed = max(0.001, time.time() - start_time)
        final_mbps = (total_bytes * 8) / (elapsed * 1_000_000)

        # Notify summary
        summary = {
            "is_usb": is_usb,
            "client_ip": client_ip,
            "duration": elapsed,
            "mbps": round(final_mbps, 2),
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }
        self.test_progress.emit(1.0, final_mbps)
        self.test_completed.emit(summary)

    def _run_bandwidth_reception(self, sock: socket.socket, duration_sec: float, is_usb: bool, client_ip: str):
        """Receives high-speed chunks from client to measure phone-to-PC throughput."""
        start_time = time.time()
        end_time = start_time + duration_sec
        total_bytes = 0
        buf = bytearray(CHUNK_SIZE)

        last_report = start_time
        while time.time() < end_time and self.is_running:
            try:
                n = sock.recv_into(buf)
                if n <= 0:
                    break
                total_bytes += n
                now = time.time()
                if now - last_report >= 0.15:
                    elapsed = now - start_time
                    current_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
                    progress = min(1.0, elapsed / duration_sec)
                    self.test_progress.emit(progress, current_mbps)
                    last_report = now
            except Exception:
                break

        elapsed = max(0.001, time.time() - start_time)
        final_mbps = (total_bytes * 8) / (elapsed * 1_000_000)

        summary = {
            "is_usb": is_usb,
            "client_ip": client_ip,
            "duration": elapsed,
            "mbps": round(final_mbps, 2),
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }
        self.test_progress.emit(1.0, final_mbps)
        self.test_completed.emit(summary)

    def _send_frame(self, sock: socket.socket, data: bytes):
        header = struct.pack("!I", len(data))
        sock.sendall(header + data)

    def _recv_all(self, sock: socket.socket, n: int) -> Optional[bytes]:
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)
