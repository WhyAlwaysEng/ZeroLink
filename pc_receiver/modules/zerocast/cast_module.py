"""ZeroLink Hub - ZeroCast Module
Encapsulates low-latency H.264 screen & audio streaming, OBS Virtual Camera,
and reverse control as a pluggable module.
"""

import os
import io
import json
import time
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QMouseEvent, QKeyEvent,
    QPen, QBrush, QKeySequence, QShortcut, QDesktopServices
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QComboBox, QDialog, QStackedWidget
)

from core.base_module import BaseModule
from core.server import StreamServer
from core.telemetry import TelemetryTracker, TelemetryStats
from core.adb_helper import AdbManager
from core.audio_player import AudioPlayer
from core.h264_decoder import H264Decoder
from core.discovery import LanDiscoveryService
from core.input_controller import InputController
from core.virtual_cam import VirtualCameraManager
from core.protocol import TYPE_VIDEO_MJPEG

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


class ModernVideoCanvas(QWidget):
    """Hardware-accelerated viewport with smooth scaling and modern telemetry overlay."""
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.current_pixmap: QPixmap = QPixmap()
        self.show_hud = True
        self.stats: TelemetryStats = TelemetryStats()
        self.resolution_text = "Idle"
        self.codec_text = "None"
        self.input_enabled = True
        self.on_touch_event = None
        self.on_key_event = None
        self.is_module_active = True
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor("#0B0D13"))
        self.setPalette(p)

    def update_frame(self, pixmap: QPixmap, stats: TelemetryStats, codec_name: str = "MJPEG"):
        self.current_pixmap = pixmap
        self.stats = stats
        self.codec_text = codec_name
        if not pixmap.isNull():
            self.resolution_text = f"{pixmap.width()}x{pixmap.height()}"
        self.update()

    def get_video_rect(self) -> QRect:
        if self.current_pixmap.isNull():
            return QRect(0, 0, self.width(), self.height())

        pw = self.current_pixmap.width()
        ph = self.current_pixmap.height()
        ww = self.width()
        wh = self.height()

        scale = min(ww / pw, wh / ph)
        target_w = int(pw * scale)
        target_h = int(ph * scale)
        x = (ww - target_w) // 2
        y = (wh - target_h) // 2
        return QRect(x, y, target_w, target_h)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.is_module_active:
            self._draw_inactive_screen(painter)
            return

        if not self.current_pixmap.isNull():
            v_rect = self.get_video_rect()
            painter.drawPixmap(v_rect, self.current_pixmap)
        else:
            self._draw_standby_screen(painter)

        if self.show_hud and not self.current_pixmap.isNull():
            self._draw_modern_hud(painter)

    def _draw_inactive_screen(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#0B0D13"))
        card_w, card_h = 580, 260
        cx = (self.width() - card_w) // 2
        cy = (self.height() - card_h) // 2
        card_rect = QRect(cx, cy, card_w, card_h)

        painter.setBrush(QColor("#151822"))
        painter.setPen(QPen(QColor("#2A3142"), 1.5))
        painter.drawRoundedRect(card_rect, 16, 16)

        badge_rect = QRect(cx + 25, cy + 25, 140, 28)
        painter.setBrush(QColor("#2D1518"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#FF5252"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "○ MODULE INACTIVE")

        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(cx + 25, cy + 85, "ZeroCast Service is Turned OFF")

        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#A0AEC0"))
        painter.drawText(cx + 25, cy + 120, "Port 8888 is closed. Mobile devices cannot connect.")
        painter.drawText(cx + 25, cy + 145, "Enable this module from the top bar or dashboard to start.")

    def _draw_standby_screen(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#0B0D13"))
        card_w, card_h = 560, 280
        cx = (self.width() - card_w) // 2
        cy = (self.height() - card_h) // 2
        card_rect = QRect(cx, cy, card_w, card_h)

        painter.setBrush(QColor("#151822"))
        painter.setPen(QPen(QColor("#242B38"), 1.5))
        painter.drawRoundedRect(card_rect, 16, 16)

        badge_rect = QRect(cx + 25, cy + 25, 120, 28)
        painter.setBrush(QColor("#00E676"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.ExtraBold))
        painter.setPen(QColor("#000000"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "ZEROCAST v1.0")

        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(cx + 25, cy + 85, "Ready for Ultra-Low Latency Stream")

        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#A0AEC0"))
        painter.drawText(cx + 25, cy + 120, "1. Connect phone via USB (Auto ADB) or Wi-Fi.")
        painter.drawText(cx + 25, cy + 145, "2. Open ZeroCast on Android and tap 'Start Streaming'.")

    def _draw_modern_hud(self, painter: QPainter):
        hud_items = [
            ("FPS", f"{self.stats.fps:.0f}", QColor("#00E676")),
            ("LATENCY", f"{self.stats.latency_ms:.0f} ms",
             QColor("#00E676") if self.stats.latency_ms < 35 else (
                 QColor("#FFA726") if self.stats.latency_ms < 65 else QColor("#FF5252"))),
            ("BITRATE", f"{self.stats.bitrate_mbps:.1f} Mbps", QColor("#64B5F6")),
            ("CODEC", self.codec_text, QColor("#E040FB")),
            ("RES", self.resolution_text, QColor("#FFFFFF")),
        ]

        box_width = 200
        box_height = 20 + len(hud_items) * 24 + 10
        painter.setBrush(QColor(15, 18, 26, 190))
        painter.setPen(QPen(QColor(40, 48, 66, 180), 1))
        painter.drawRoundedRect(QRect(20, 20, box_width, box_height), 10, 10)

        header_rect = QRect(20, 20, box_width, 18)
        painter.setBrush(QColor(30, 38, 52, 200))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRect(20, 20, box_width, 18), 10, 10)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#718096"))
        painter.drawText(30, 33, "PERFORMANCE HUD")

        y = 54
        for label, val, color in hud_items:
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.setPen(QColor("#718096"))
            painter.drawText(30, y, label)

            painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            painter.setPen(color)
            painter.drawText(QRect(80, y - 13, 115, 20), Qt.AlignmentFlag.AlignRight, val)
            y += 24

    def _normalize_coords(self, pos: QPoint):
        if self.current_pixmap.isNull() or not self.on_touch_event:
            return None
        v_rect = self.get_video_rect()
        if not v_rect.contains(pos):
            return None
        norm_x = (pos.x() - v_rect.x()) / v_rect.width()
        norm_y = (pos.y() - v_rect.y()) / v_rect.height()
        return max(0.0, min(1.0, norm_x)), max(0.0, min(1.0, norm_y))

    def mousePressEvent(self, event: QMouseEvent):
        if self.input_enabled and event.button() == Qt.MouseButton.LeftButton:
            norm = self._normalize_coords(event.pos())
            if norm and self.on_touch_event:
                self.on_touch_event("DOWN", norm[0], norm[1])

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.input_enabled and event.buttons() & Qt.MouseButton.LeftButton:
            norm = self._normalize_coords(event.pos())
            if norm and self.on_touch_event:
                self.on_touch_event("MOVE", norm[0], norm[1])

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.input_enabled and event.button() == Qt.MouseButton.LeftButton:
            norm = self._normalize_coords(event.pos())
            if norm and self.on_touch_event:
                self.on_touch_event("UP", norm[0], norm[1])

    def keyPressEvent(self, event: QKeyEvent):
        if not self.input_enabled or not self.on_key_event:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Backspace:
            self.on_key_event("KEY", 67)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.on_key_event("KEY", 66)
        elif key == Qt.Key.Key_Tab:
            self.on_key_event("KEY", 61)
        elif key == Qt.Key.Key_Escape:
            self.on_key_event("KEY", 4)
        else:
            text = event.text()
            if text and text.isprintable():
                self.on_key_event("TEXT", text)
            else:
                super().keyPressEvent(event)


class ZeroCastModule(BaseModule):
    """Pluggable ZeroCast Module implementation."""
    toggle_fullscreen_requested = pyqtSignal()
    toggle_pin_requested = pyqtSignal()

    def __init__(self, port: int = 8888, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip

        self.telemetry = TelemetryTracker()
        self.server = StreamServer(host="0.0.0.0", port=self.port)
        self.adb_manager = AdbManager()
        self.audio_player = AudioPlayer()
        self.h264_decoder = H264Decoder()
        self.input_controller = InputController(self.adb_manager)
        self.virtual_cam = VirtualCameraManager(target_width=1280, target_height=720, fps=30)
        self.discovery = LanDiscoveryService(tcp_port=self.port, local_ip=self.local_ip)

        self.current_codec_name = "MJPEG"
        self._widget: Optional[QWidget] = None

        self._bind_events()
        self._init_usb_tunnel()

        # USB poll timer
        self.usb_timer = QTimer(self)
        self.usb_timer.timeout.connect(self._check_usb_device_status)
        self.usb_timer.start(3000)

    @property
    def module_id(self) -> str:
        return "zerocast"

    @property
    def display_name(self) -> str:
        return "ZeroCast"

    @property
    def icon_glyph(self) -> str:
        return "📺"

    @property
    def description(self) -> str:
        return "Ultra-low latency GPU H.264 screen & internal audio mirroring with OBS Virtual Camera."

    def start_service(self) -> bool:
        """Starts streaming server and UDP discovery."""
        self.server.start()
        self.discovery.start()
        self._is_active = True
        if self._widget:
            self.canvas.is_module_active = True
            self.btn_power.setText("Disable Module")
            self.btn_power.setStyleSheet("""
                QPushButton {
                    background-color: #2D1518;
                    color: #FF5252;
                    border: 1px solid #742A2A;
                    border-radius: 6px;
                }
            """)
            self.canvas.update()
        self.status_changed.emit(self.module_id, "ZeroCast service started (Port 8888 listening)")
        return True

    def stop_service(self) -> bool:
        """Stops streaming server, closes socket (Port 8888), frees audio and vcam."""
        self.server.stop()
        self.discovery.stop()
        self.audio_player.stop()
        self.virtual_cam.stop()
        self._is_active = False

        if self._widget:
            self.canvas.is_module_active = False
            self.canvas.current_pixmap = QPixmap()
            self.btn_power.setText("▶ Enable ZeroCast")
            self.btn_power.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E676, stop:1 #38BDF8);
                    color: #0B0D13;
                    font-weight: 800;
                    border: none;
                    border-radius: 6px;
                }
            """)
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #261619;
                color: #FF5252;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: bold;
            """)
            self.canvas.update()

        self.status_changed.emit(self.module_id, "ZeroCast service stopped (Port 8888 closed)")
        return True

    def get_widget(self) -> QWidget:
        if not self._widget:
            self._setup_ui()
        return self._widget

    def _bind_events(self):
        self.server.client_connected.connect(self._on_client_connected)
        self.server.client_disconnected.connect(self._on_client_disconnected)
        self.server.frame_received.connect(self._on_frame_received)
        self.server.audio_received.connect(self._on_audio_received)
        self.server.status_changed.connect(lambda s: self.status_changed.emit(self.module_id, s))

    def _init_usb_tunnel(self):
        if self.adb_manager.is_available():
            devs = self.adb_manager.get_devices()
            if devs:
                self.adb_manager.reverse_port(self.port)

    def _check_usb_device_status(self):
        if not self._widget:
            return
        if not self.adb_manager.is_available():
            self.usb_pill.setText("⚡ USB: No ADB")
            self.usb_pill.setStyleSheet("background-color: #1A202C; color: #718096; padding: 4px 10px; border-radius: 12px; font-size: 11px;")
            return

        devs = self.adb_manager.get_devices()
        if devs:
            dev_id = devs[0][0]
            short_id = dev_id if len(dev_id) <= 12 else (dev_id[:10] + "..")
            self.usb_pill.setText(f"⚡ USB: {short_id} (Ready)")
            self.usb_pill.setStyleSheet("background-color: #0E3320; color: #00E676; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;")
        else:
            self.usb_pill.setText("⚡ USB: Unplugged")
            self.usb_pill.setStyleSheet("background-color: #1A202C; color: #A0AEC0; padding: 4px 10px; border-radius: 12px; font-size: 11px;")

    def _setup_ui(self):
        self._widget = QWidget()
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top Control Ribbon
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #11141D; border-bottom: 1px solid #1E2330;")
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        bar_layout.setSpacing(10)

        # Module Power Button
        self.btn_power = QPushButton("Disable Module" if self.is_active else "▶ Enable ZeroCast")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● OFFLINE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("background-color: #2D1518; color: #FF5252; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;")
        bar_layout.addWidget(self.status_pill)

        self.usb_pill = QLabel("⚡ USB: Checking...")
        self.usb_pill.setStyleSheet("background-color: #1A202C; color: #A0AEC0; padding: 4px 10px; border-radius: 12px; font-size: 11px;")
        bar_layout.addWidget(self.usb_pill)

        self.wifi_pill = QLabel(f"📡 Wi-Fi: {self.local_ip}:{self.port}")
        self.wifi_pill.setStyleSheet("background-color: #132238; color: #64B5F6; padding: 4px 10px; border-radius: 12px; font-size: 11px;")
        bar_layout.addWidget(self.wifi_pill)

        bar_layout.addStretch()

        self.btn_vcam = QPushButton("🎥 V-Cam: OFF")
        self.btn_vcam.clicked.connect(self._toggle_virtual_cam)
        bar_layout.addWidget(self.btn_vcam)

        self.btn_snapshot = QPushButton("📸 Snapshot")
        self.btn_snapshot.clicked.connect(self._take_snapshot)
        bar_layout.addWidget(self.btn_snapshot)

        self.btn_qr = QPushButton("🔗 Pair QR")
        self.btn_qr.clicked.connect(self._show_qr_dialog)
        bar_layout.addWidget(self.btn_qr)

        layout.addWidget(top_bar)

        # Video Canvas
        self.canvas = ModernVideoCanvas(self._widget)
        self.canvas.is_module_active = self.is_active
        self.canvas.on_touch_event = self._handle_reverse_input
        self.canvas.on_key_event = self._handle_key_input
        self.canvas.double_clicked.connect(self.toggle_fullscreen_requested.emit)
        layout.addWidget(self.canvas, 1)

        # Bottom Bar
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet("background-color: #11141D; border-top: 1px solid #1E2330;")
        bot_layout = QHBoxLayout(bottom_bar)
        bot_layout.setContentsMargins(16, 7, 16, 7)
        bot_layout.setSpacing(10)

        self.log_label = QLabel("ZeroCast Ready")
        self.log_label.setStyleSheet("color: #718096; font-size: 11px;")
        bot_layout.addWidget(self.log_label)

        bot_layout.addStretch()

        btn_back = QPushButton("◀ Back")
        btn_back.clicked.connect(lambda: self.input_controller.send_key_event(4))
        bot_layout.addWidget(btn_back)

        btn_home = QPushButton("⌂ Home")
        btn_home.clicked.connect(lambda: self.input_controller.send_key_event(3))
        bot_layout.addWidget(btn_home)

        bot_layout.addSpacing(10)

        self.btn_audio = QPushButton("🔊 Audio: ON")
        self.btn_audio.clicked.connect(self._toggle_audio)
        bot_layout.addWidget(self.btn_audio)

        self.combo_audio_dev = QComboBox()
        self._populate_audio_devices()
        self.combo_audio_dev.currentIndexChanged.connect(self._on_audio_device_changed)
        bot_layout.addWidget(self.combo_audio_dev)

        self.btn_hud = QPushButton("📊 HUD")
        self.btn_hud.setCheckable(True)
        self.btn_hud.setChecked(True)
        self.btn_hud.clicked.connect(self._toggle_hud)
        bot_layout.addWidget(self.btn_hud)

        layout.addWidget(bottom_bar)

    def _toggle_power(self):
        if self.is_active:
            self.stop_service()
            self.state_changed.emit(self.module_id, False)
        else:
            self.start_service()
            self.state_changed.emit(self.module_id, True)

    def _on_client_connected(self, client_info: str):
        self.status_pill.setText("● CONNECTED")
        self.status_pill.setStyleSheet("background-color: #0E3320; color: #00E676; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;")
        self.log_label.setText(f"Streaming: {client_info}")
        self.telemetry.reset()
        self.h264_decoder.reset()

    def _on_client_disconnected(self):
        self.status_pill.setText("● OFFLINE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("background-color: #2D1518; color: #FF5252; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;")
        self.log_label.setText("Client disconnected")
        self.canvas.current_pixmap = QPixmap()
        self.canvas.update()

    def _on_frame_received(self, payload: bytes, frame_type: int, timestamp_us: int):
        if not self.is_active:
            return

        pixmap = None
        if frame_type == 1:  # H.264
            self.current_codec_name = "H.264 GPU"
            img = self.h264_decoder.decode(payload)
            if img:
                pixmap = QPixmap.fromImage(img)
                if self.virtual_cam.is_active:
                    self.virtual_cam.send_qimage(img)
        else:
            self.current_codec_name = "MJPEG"
            pixmap = QPixmap()
            pixmap.loadFromData(payload)
            if self.virtual_cam.is_active and not pixmap.isNull():
                self.virtual_cam.send_qimage(pixmap.toImage())

        if pixmap and not pixmap.isNull():
            stats = self.telemetry.update(len(payload), timestamp_us)
            self.canvas.update_frame(pixmap, stats, self.current_codec_name)

    def _on_audio_received(self, pcm_data: bytes):
        if self.is_active:
            self.audio_player.play_chunk(pcm_data)

    def _handle_reverse_input(self, action: str, nx: float, ny: float):
        self.input_controller.send_touch_event(action, nx, ny)

    def _handle_key_input(self, input_type: str, value):
        if input_type == "KEY":
            self.input_controller.send_key_event(value)
        elif input_type == "TEXT":
            self.input_controller.send_text(value)

    def _populate_audio_devices(self):
        self.combo_audio_dev.clear()
        devices = self.audio_player.get_available_devices()
        default_idx = 0
        for i, (desc, dev, is_def) in enumerate(devices):
            prefix = "🎧 " if any(w in desc.lower() for w in ["head", "stinger", "ear"]) else "🔊 "
            short_desc = desc if len(desc) <= 20 else (desc[:18] + "..")
            self.combo_audio_dev.addItem(f"{prefix}{short_desc}", dev)
            if is_def:
                default_idx = i
        if devices:
            self.combo_audio_dev.setCurrentIndex(default_idx)

    def _on_audio_device_changed(self, idx: int):
        if idx < 0:
            return
        device = self.combo_audio_dev.itemData(idx)
        if device:
            self.audio_player.set_device(device)

    def _toggle_audio(self):
        is_muted = self.audio_player.toggle_mute()
        self.btn_audio.setText("🔇 Audio: MUTED" if is_muted else "🔊 Audio: ON")

    def _toggle_hud(self):
        self.canvas.show_hud = self.btn_hud.isChecked()
        self.canvas.update()

    def _toggle_virtual_cam(self):
        if not self.virtual_cam.is_supported():
            return
        if self.virtual_cam.is_active:
            self.virtual_cam.stop()
            self.btn_vcam.setText("🎥 V-Cam: OFF")
            self.btn_vcam.setStyleSheet("")
        else:
            if self.virtual_cam.start():
                self.btn_vcam.setText("🎥 V-Cam: ON")
                self.btn_vcam.setStyleSheet("QPushButton { background-color: #0E3320; color: #00E676; border: 1px solid #00E676; }")

    def _take_snapshot(self):
        if self.canvas.current_pixmap.isNull():
            return
        save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "ZeroCast")
        os.makedirs(save_dir, exist_ok=True)
        fname = f"ZeroCast_{int(time.time())}.png"
        path = os.path.join(save_dir, fname)
        self.canvas.current_pixmap.save(path, "PNG")
        self.log_label.setText(f"Saved: {fname}")

    def _show_qr_dialog(self):
        dlg = QDialog(self._widget)
        dlg.setWindowTitle("ZeroCast Wireless Pairing")
        dlg.setFixedSize(300, 320)
        dlg.setStyleSheet("background-color: #12151E; color: white;")
        l = QVBoxLayout(dlg)
        lbl = QLabel(f"Server IP: <b>{self.local_ip}</b><br>Port: <b>{self.port}</b>")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl)
        btn = QPushButton("Done")
        btn.clicked.connect(dlg.accept)
        l.addWidget(btn)
        dlg.exec()
