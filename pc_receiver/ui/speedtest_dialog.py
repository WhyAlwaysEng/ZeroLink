"""ZeroLink SpeedTest & Latency Benchmark Dialog
Interactive GUI on PC for testing connection throughput (Mbps), latency (RTT), and jitter
between PC Hub and Android device over USB or Wi-Fi.
"""

import time
import socket
import struct
import json
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QWidget
)

from core.speedtest_server import SPEEDTEST_PORT, CHUNK_SIZE


class SpeedTestClientWorker(QObject):
    """Client worker to test against local or remote SpeedTest server."""
    progress = pyqtSignal(float, float)      # progress, current_mbps
    ping_result = pyqtSignal(float, float)    # avg_ping_ms, jitter_ms
    finished = pyqtSignal(dict)              # summary dict
    error = pyqtSignal(str)

    def __init__(self, host: str = "127.0.0.1", port: int = SPEEDTEST_PORT):
        super().__init__()
        self.host = host
        self.port = port
        self.is_cancelled = False

    def run_test(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.host, self.port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            # 1. Ping Phase
            pings = []
            for _ in range(8):
                if self.is_cancelled:
                    break
                t0 = time.time()
                ping_payload = json.dumps({"cmd": "PING", "ts": t0}).encode("utf-8")
                header = struct.pack("!I", len(ping_payload))
                sock.sendall(header + ping_payload)

                raw_len = sock.recv(4)
                if not raw_len:
                    break
                resp_len = struct.unpack("!I", raw_len)[0]
                resp_data = sock.recv(resp_len)
                t1 = time.time()
                rtt_ms = (t1 - t0) * 1000.0
                pings.append(rtt_ms)
                time.sleep(0.04)

            avg_ping = sum(pings) / len(pings) if pings else 0.0
            jitter = (max(pings) - min(pings)) if len(pings) > 1 else 0.0
            self.ping_result.emit(round(avg_ping, 1), round(jitter, 1))

            # 2. Bandwidth Download Phase (PC receiving stream from server)
            bw_req = json.dumps({"cmd": "START_BANDWIDTH_TEST", "duration": 3.0}).encode("utf-8")
            sock.sendall(struct.pack("!I", len(bw_req)) + bw_req)

            # Read confirmation
            raw_len = sock.recv(4)
            if raw_len:
                resp_len = struct.unpack("!I", raw_len)[0]
                sock.recv(resp_len)

            start_time = time.time()
            total_bytes = 0
            buf = bytearray(CHUNK_SIZE)
            sock.settimeout(1.0)

            while time.time() - start_time < 3.0 and not self.is_cancelled:
                try:
                    n = sock.recv_into(buf)
                    if n <= 0:
                        break
                    total_bytes += n
                    elapsed = max(0.001, time.time() - start_time)
                    mbps = (total_bytes * 8) / (elapsed * 1_000_000)
                    self.progress.emit(min(1.0, elapsed / 3.0), mbps)
                except socket.timeout:
                    break

            elapsed = max(0.001, time.time() - start_time)
            final_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
            sock.close()

            is_usb = self.host in ("127.0.0.1", "localhost")
            summary = {
                "mbps": round(final_mbps, 1),
                "avg_ping_ms": round(avg_ping, 1),
                "jitter_ms": round(jitter, 1),
                "is_usb": is_usb,
                "host": self.host
            }
            self.finished.emit(summary)

        except Exception as e:
            self.error.emit(f"Connection error: {e}")


class SpeedTestDialog(QDialog):
    """Modern dark-themed speed test benchmark window."""

    def __init__(self, target_host: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.target_host = target_host
        self.worker: Optional[SpeedTestClientWorker] = None
        self.worker_thread: Optional[threading.Thread] = None

        self.setWindowTitle("ZeroLink Connection Benchmark")
        self.setFixedSize(480, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #0A0A0A;
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Header
        head_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("SPEED & LATENCY BENCHMARK")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: 800; letter-spacing: 1.5px; color: #FFFFFF;")
        lbl_sub = QLabel("Measures raw throughput and latency between PC and Android.")
        lbl_sub.setStyleSheet("font-size: 11px; color: #666666;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        head_layout.addLayout(title_box)

        is_usb = self.target_host in ("127.0.0.1", "localhost")
        self.badge_media = QLabel("⚡ USB CABLE" if is_usb else f"📡 WI-FI ({self.target_host})")
        if is_usb:
            self.badge_media.setStyleSheet("background: #0C2340; color: #38BDF8; border: 1px solid #0284C7; border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: 700;")
        else:
            self.badge_media.setStyleSheet("background: #064E3B; color: #34D399; border: 1px solid #059669; border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: 700;")
        head_layout.addWidget(self.badge_media, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head_layout)

        # Main Speed Display Card
        speed_card = QFrame()
        speed_card.setStyleSheet("background-color: #111111; border: 1px solid #222222; border-radius: 12px; padding: 20px;")
        sc_layout = QVBoxLayout(speed_card)
        sc_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sc_layout.setSpacing(6)

        self.lbl_speed_val = QLabel("0.0")
        self.lbl_speed_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_speed_val.setStyleSheet("font-size: 58px; font-weight: 900; color: #FFFFFF; font-family: 'Consolas', sans-serif;")
        sc_layout.addWidget(self.lbl_speed_val)

        lbl_unit = QLabel("Mbps (Megabits / sec)")
        lbl_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_unit.setStyleSheet("font-size: 11px; font-weight: 600; color: #777777; letter-spacing: 1px;")
        sc_layout.addWidget(lbl_unit)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1A1A1A;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #38BDF8;
                border-radius: 3px;
            }
        """)
        sc_layout.addWidget(self.progress_bar)
        layout.addWidget(speed_card)

        # Metrics Row (Ping & Jitter)
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        # Ping Box
        ping_box = QFrame()
        ping_box.setStyleSheet("background-color: #111111; border: 1px solid #222222; border-radius: 8px; padding: 12px;")
        pb_layout = QVBoxLayout(ping_box)
        pb_title = QLabel("LATENCY (PING)")
        pb_title.setStyleSheet("font-size: 9px; font-weight: 700; color: #666666; letter-spacing: 1px;")
        self.lbl_ping_val = QLabel("-- ms")
        self.lbl_ping_val.setStyleSheet("font-size: 18px; font-weight: 800; color: #FFFFFF; font-family: 'Consolas', sans-serif;")
        pb_layout.addWidget(pb_title)
        pb_layout.addWidget(self.lbl_ping_val)
        metrics_layout.addWidget(ping_box)

        # Jitter Box
        jitter_box = QFrame()
        jitter_box.setStyleSheet("background-color: #111111; border: 1px solid #222222; border-radius: 8px; padding: 12px;")
        jb_layout = QVBoxLayout(jitter_box)
        jb_title = QLabel("JITTER (VARIATION)")
        jb_title.setStyleSheet("font-size: 9px; font-weight: 700; color: #666666; letter-spacing: 1px;")
        self.lbl_jitter_val = QLabel("-- ms")
        self.lbl_jitter_val.setStyleSheet("font-size: 18px; font-weight: 800; color: #FFFFFF; font-family: 'Consolas', sans-serif;")
        jb_layout.addWidget(jb_title)
        jb_layout.addWidget(self.lbl_jitter_val)
        metrics_layout.addWidget(jitter_box)

        layout.addLayout(metrics_layout)

        # Smart Recommendation Card
        self.rec_card = QFrame()
        self.rec_card.setStyleSheet("background-color: #141414; border: 1px solid #2A2A2A; border-radius: 8px; padding: 12px;")
        rc_layout = QVBoxLayout(self.rec_card)
        rc_title = QLabel("⚡ SMART CONNECTION ADVISOR")
        rc_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #9CA3AF; letter-spacing: 1px;")
        self.lbl_rec_desc = QLabel("Tap 'Run Benchmark' to measure your USB or Wi-Fi throughput.")
        self.lbl_rec_desc.setWordWrap(True)
        self.lbl_rec_desc.setStyleSheet("font-size: 11px; color: #CCCCCC; line-height: 1.4;")
        rc_layout.addWidget(rc_title)
        rc_layout.addWidget(self.lbl_rec_desc)
        layout.addWidget(self.rec_card)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("START BENCHMARK")
        self.btn_run.setFixedHeight(38)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                font-size: 11px;
                font-weight: 800;
                border: none;
                border-radius: 6px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: #E5E5E5;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #666666;
            }
        """)
        self.btn_run.clicked.connect(self.start_test)
        btn_layout.addWidget(self.btn_run)

        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedHeight(38)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #999999;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                border-color: #666666;
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def start_test(self):
        self.btn_run.setEnabled(False)
        self.btn_run.setText("TESTING...")
        self.lbl_speed_val.setText("0.0")
        self.progress_bar.setValue(0)
        self.lbl_ping_val.setText("Testing...")
        self.lbl_jitter_val.setText("Testing...")
        self.lbl_rec_desc.setText("Measuring real-world RTT latency and raw TCP throughput...")

        self.worker = SpeedTestClientWorker(host=self.target_host, port=SPEEDTEST_PORT)
        self.worker.progress.connect(self._on_progress)
        self.worker.ping_result.connect(self._on_ping_result)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)

        self.worker_thread = threading.Thread(target=self.worker.run_test, daemon=True)
        self.worker_thread.start()

    def _on_progress(self, progress: float, mbps: float):
        self.progress_bar.setValue(int(progress * 100))
        self.lbl_speed_val.setText(f"{mbps:.1f}")

    def _on_ping_result(self, avg_ping: float, jitter: float):
        self.lbl_ping_val.setText(f"{avg_ping:.1f} ms")
        self.lbl_jitter_val.setText(f"{jitter:.1f} ms")

    def _on_finished(self, summary: dict):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("RUN AGAIN")
        self.progress_bar.setValue(100)
        mbps = summary.get("mbps", 0.0)
        ping = summary.get("avg_ping_ms", 0.0)
        is_usb = summary.get("is_usb", False)

        # Smart Recommendation Logic
        if is_usb or mbps >= 60.0:
            rec_text = (
                f"✅ <b>Exceptional Connection ({mbps:.1f} Mbps • {ping:.1f}ms):</b><br>"
                "Ideal for <b>Extreme Quality (50 - 80 Mbps @ 60 FPS)</b> with ultra-low input lag and lossless fidelity."
            )
            self.rec_card.setStyleSheet("background-color: #064E3B; border: 1px solid #059669; border-radius: 8px; padding: 12px;")
        elif mbps >= 25.0:
            rec_text = (
                f"👍 <b>Strong Stable Link ({mbps:.1f} Mbps • {ping:.1f}ms):</b><br>"
                "Recommended for <b>High Performance (25 - 35 Mbps @ 60 FPS)</b>."
            )
            self.rec_card.setStyleSheet("background-color: #0C2340; border: 1px solid #0284C7; border-radius: 8px; padding: 12px;")
        elif mbps >= 12.0:
            rec_text = (
                f"⚖️ <b>Balanced Wi-Fi Link ({mbps:.1f} Mbps • {ping:.1f}ms):</b><br>"
                "Recommended for <b>14 - 18 Mbps Balanced Mode</b>. Connect via USB Cable for extreme 80 Mbps speeds."
            )
            self.rec_card.setStyleSheet("background-color: #141414; border: 1px solid #444444; border-radius: 8px; padding: 12px;")
        else:
            rec_text = (
                f"⚠️ <b>Limited Bandwidth ({mbps:.1f} Mbps • {ping:.1f}ms):</b><br>"
                "Recommended for <b>6 - 10 Mbps Low Latency Mode</b>. Switching to USB Cable (ADB) is strongly advised."
            )
            self.rec_card.setStyleSheet("background-color: #451A03; border: 1px solid #D97706; border-radius: 8px; padding: 12px;")

        self.lbl_rec_desc.setText(rec_text)

    def _on_error(self, err_msg: str):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("RETRY")
        self.lbl_rec_desc.setText(f"❌ {err_msg}<br>Ensure SpeedTest server is active or phone is connected.")
        self.rec_card.setStyleSheet("background-color: #450A0A; border: 1px solid #DC2626; border-radius: 8px; padding: 12px;")
