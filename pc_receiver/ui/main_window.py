"""ZeroCast PC Receiver - Modern Glassmorphic UI & Ultra-Low Latency Engine
Features:
- Dual Codec: H.264 (PyAV Hardware-Accelerated) & MJPEG auto-detection
- Real-Time Internal Audio Player (PyQt6.QtMultimedia PCM 16-bit)
- UDP LAN Auto-Discovery Service (port 8889)
- Reverse Touch & Navigation Control (Mouse Click/Drag, Back, Home)
- Auto-detects ADB and devices automatically
- Screenshot / Snapshot capturing to Pictures/ZeroCast
- Fullscreen mode (F11 / Double-click)
- Sleek HUD with latency color coding (<35ms green, <65ms orange, >65ms red)
- Always on top toggle
"""

import os
import io
import json
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QMouseEvent, QKeyEvent,
    QPen, QBrush, QKeySequence, QShortcut
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QDialog, QMessageBox, QFrame, QSizePolicy, QSlider, QComboBox
)

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


def get_local_ip() -> str:
    """Finds the local IPv4 address."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Dark background
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

        # Draw video frame
        if not self.current_pixmap.isNull():
            v_rect = self.get_video_rect()
            painter.drawPixmap(v_rect, self.current_pixmap)
        else:
            self._draw_standby_screen(painter)

        # Draw Telemetry HUD
        if self.show_hud and not self.current_pixmap.isNull():
            self._draw_modern_hud(painter)

    def _draw_standby_screen(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#0D1017"))

        # Center card container
        card_w, card_h = 560, 300
        cx = (self.width() - card_w) // 2
        cy = (self.height() - card_h) // 2
        card_rect = QRect(cx, cy, card_w, card_h)

        # Card shadow & background
        painter.setBrush(QColor("#161922"))
        painter.setPen(QPen(QColor("#242B38"), 1.5))
        painter.drawRoundedRect(card_rect, 16, 16)

        # Logo / Badge
        badge_rect = QRect(cx + 25, cy + 25, 120, 28)
        painter.setBrush(QColor("#00E676"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.ExtraBold))
        painter.setPen(QColor("#000000"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "ZEROCAST v1.0")

        # Heading
        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(cx + 25, cy + 85, "Ready for Ultra-Low Latency Stream")

        # Instructions
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#A0AEC0"))
        instructions = (
            "⚡ USB Mode: Plug phone in with USB Debugging (Zero Latency)\n"
            "📡 Wi-Fi Mode: Tap 'Auto-Discover' on phone or enter PC IP\n"
            "🔊 Internal Audio: Streams phone sound to PC speakers automatically\n"
            "🖱️ Reverse Control: Click & Drag on screen to control phone touch"
        )
        painter.drawText(QRect(cx + 25, cy + 105, card_w - 50, 170), Qt.TextFlag.TextWordWrap, instructions)

    def _draw_modern_hud(self, painter: QPainter):
        lat = self.stats.latency_ms
        lat_color = QColor("#00E676") if lat < 35 else (QColor("#FFB300") if lat < 65 else QColor("#FF5252"))

        hud_items = [
            ("CODEC", self.codec_text, QColor("#38BDF8")),
            ("FPS", f"{self.stats.fps:.1f}", QColor("#FFFFFF")),
            ("LATENCY", f"{lat:.1f} ms", lat_color),
            ("BITRATE", f"{self.stats.bitrate_mbps:.2f} Mbps", QColor("#64B5F6")),
            ("FRAME", f"{self.stats.last_frame_kb:.0f} KB", QColor("#B0BEC5")),
            ("RES", self.resolution_text, QColor("#E0E0E0")),
        ]

        box_width = 190
        box_height = len(hud_items) * 25 + 24
        hud_rect = QRect(20, 20, box_width, box_height)

        # Semi-transparent dark glass container
        painter.setBrush(QColor(18, 22, 32, 220))
        painter.setPen(QPen(QColor(45, 55, 75, 180), 1))
        painter.drawRoundedRect(hud_rect, 10, 10)

        # Header bar
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
            self.on_key_event("KEY", 67)  # Android KEYCODE_DEL
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.on_key_event("KEY", 66)  # Android KEYCODE_ENTER
        elif key == Qt.Key.Key_Tab:
            self.on_key_event("KEY", 61)  # Android KEYCODE_TAB
        elif key == Qt.Key.Key_Escape:
            self.on_key_event("KEY", 4)   # Android KEYCODE_BACK
        elif key == Qt.Key.Key_Home:
            self.on_key_event("KEY", 3)   # Android KEYCODE_HOME
        elif key == Qt.Key.Key_Space:
            self.on_key_event("TEXT", " ")
        else:
            text = event.text()
            if text and text.isprintable():
                self.on_key_event("TEXT", text)
            else:
                super().keyPressEvent(event)


class ModernQRDialog(QDialog):
    def __init__(self, ip: str, port: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ZeroCast Wireless Pairing")
        self.setFixedSize(400, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #12151D;
                color: #FFFFFF;
                border-radius: 12px;
            }
            QLabel {
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #00E676;
                color: #000000;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #00C853;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Connect via Wi-Fi")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Scan with your phone or tap 'Auto-Discover'")
        subtitle.setStyleSheet("color: #718096; font-size: 13px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        qr_frame = QFrame()
        qr_frame.setStyleSheet("background-color: #FFFFFF; border-radius: 12px; padding: 12px;")
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        connection_info = {"ip": ip, "port": port, "system": "ZeroCast"}
        qr_data = json.dumps(connection_info)

        if HAS_QRCODE:
            qr = qrcode.QRCode(box_size=6, border=1)
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qimage = QImage.fromData(buffer.getvalue())
            qr_label.setPixmap(QPixmap.fromImage(qimage))
        else:
            qr_label.setText(f"IP: {ip}\nPort: {port}")

        qr_layout.addWidget(qr_label)
        layout.addWidget(qr_frame)

        info_card = QFrame()
        info_card.setStyleSheet("background-color: #1A1E29; border-radius: 8px; padding: 10px;")
        info_layout = QHBoxLayout(info_card)
        info_layout.setContentsMargins(12, 6, 12, 6)

        ip_lbl = QLabel(f"Server IP: <b>{ip}</b>")
        ip_lbl.setStyleSheet("color: #00E676; font-size: 14px; font-family: Consolas;")
        info_layout.addWidget(ip_lbl)

        port_lbl = QLabel(f"Port: <b>{port}</b>")
        port_lbl.setStyleSheet("color: #64B5F6; font-size: 14px; font-family: Consolas;")
        info_layout.addWidget(port_lbl)

        layout.addWidget(info_card)

        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class MainWindow(QMainWindow):
    def __init__(self, port: int = 8888):
        super().__init__()
        self.port = port
        self.local_ip = get_local_ip()

        self.setWindowTitle("ZeroCast Receiver v1.0")
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icon.png")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        self.resize(1180, 760)
        self.setMinimumSize(800, 500)

        self.telemetry = TelemetryTracker()
        self.server = StreamServer(host="0.0.0.0", port=self.port)
        self.adb_manager = AdbManager()
        self.audio_player = AudioPlayer()
        self.h264_decoder = H264Decoder()
        self.input_controller = InputController(self.adb_manager)
        self.virtual_cam = VirtualCameraManager(target_width=1280, target_height=720, fps=30)
        self.discovery = LanDiscoveryService(tcp_port=self.port, local_ip=self.local_ip)
        self.is_fullscreen = False
        self.current_codec_name = "MJPEG"

        self._setup_ui()
        self._setup_shortcuts()
        self._bind_events()

        # Start servers
        self.server.start()
        self.discovery.start()

        # Setup automatic USB reverse & timer to monitor device connection
        self._init_usb_tunnel()
        self.usb_timer = QTimer(self)
        self.usb_timer.timeout.connect(self._check_usb_device_status)
        self.usb_timer.start(3000)

    def _setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0B0D13;
            }
            QWidget {
                color: #FFFFFF;
                font-family: 'Segoe UI', Inter, sans-serif;
            }
            QPushButton {
                background-color: #181C26;
                color: #E2E8F0;
                border: 1px solid #283042;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #242B3B;
                border-color: #3B465E;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #12151E;
            }
            QComboBox {
                background-color: #181C26;
                color: #E2E8F0;
                border: 1px solid #283042;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QComboBox:hover {
                background-color: #242B3B;
                border-color: #3B465E;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox QAbstractItemView {
                background-color: #12151E;
                color: #FFFFFF;
                selection-background-color: #2563EB;
                border: 1px solid #283042;
                border-radius: 6px;
            }
            QFrame#topBar {
                background-color: #11141D;
                border-bottom: 1px solid #1E2330;
            }
            QFrame#bottomBar {
                background-color: #11141D;
                border-top: 1px solid #1E2330;
            }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ----------------- Top Header Ribbon -----------------
        self.top_bar = QFrame()
        self.top_bar.setObjectName("topBar")
        bar_layout = QHBoxLayout(self.top_bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        bar_layout.setSpacing(10)

        brand_lbl = QLabel("ZEROCAST")
        brand_lbl.setStyleSheet("font-weight: 900; font-size: 14px; letter-spacing: 1px; color: #FFFFFF;")
        bar_layout.addWidget(brand_lbl)

        self.status_pill = QLabel("● OFFLINE")
        self.status_pill.setStyleSheet("""
            background-color: #2D1518;
            color: #FF5252;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        bar_layout.addWidget(self.status_pill)

        self.usb_pill = QLabel("⚡ USB: Checking...")
        self.usb_pill.setStyleSheet("""
            background-color: #1A202C;
            color: #A0AEC0;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        """)
        bar_layout.addWidget(self.usb_pill)

        self.wifi_pill = QLabel(f"📡 Wi-Fi: {self.local_ip}:{self.port}")
        self.wifi_pill.setStyleSheet("""
            background-color: #132238;
            color: #64B5F6;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        """)
        bar_layout.addWidget(self.wifi_pill)

        bar_layout.addStretch()

        # Tools & View Toggles on Top Right
        self.btn_vcam = QPushButton("🎥 V-Cam: OFF")
        self.btn_vcam.setToolTip("Stream live phone camera/screen into OBS Virtual Camera for Discord / Zoom / Teams")
        self.btn_vcam.clicked.connect(self._toggle_virtual_cam)
        bar_layout.addWidget(self.btn_vcam)

        self.btn_snapshot = QPushButton("📸 Snapshot")
        self.btn_snapshot.setToolTip("Save high-res screenshot to Pictures/ZeroCast")
        self.btn_snapshot.clicked.connect(self._take_snapshot)
        bar_layout.addWidget(self.btn_snapshot)

        self.btn_qr = QPushButton("🔗 Pair QR")
        self.btn_qr.setToolTip("Show QR code for wireless mobile pairing")
        self.btn_qr.clicked.connect(self._show_qr_dialog)
        bar_layout.addWidget(self.btn_qr)

        self.btn_topmost = QPushButton("📌 Pin")
        self.btn_topmost.setCheckable(True)
        self.btn_topmost.setToolTip("Keep window always on top")
        self.btn_topmost.clicked.connect(self._toggle_topmost)
        bar_layout.addWidget(self.btn_topmost)

        self.btn_fullscreen = QPushButton("🔲 Fullscreen")
        self.btn_fullscreen.setToolTip("Toggle Fullscreen (F11)")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        bar_layout.addWidget(self.btn_fullscreen)

        main_layout.addWidget(self.top_bar)

        # ----------------- Video Canvas -----------------
        self.canvas = ModernVideoCanvas(self)
        self.canvas.on_touch_event = self._handle_reverse_input
        self.canvas.on_key_event = self._handle_key_input
        self.canvas.double_clicked.connect(self._toggle_fullscreen)
        main_layout.addWidget(self.canvas, 1)

        # ----------------- Bottom Status & Control Bar -----------------
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("bottomBar")
        bot_layout = QHBoxLayout(self.bottom_bar)
        bot_layout.setContentsMargins(16, 7, 16, 7)
        bot_layout.setSpacing(10)

        # Status & Message on the left
        self.lbl_status = QLabel("Ready. Auto-Discovery active (UDP 8889).")
        self.lbl_status.setStyleSheet("color: #718096; font-size: 12px;")
        bot_layout.addWidget(self.lbl_status)

        bot_layout.addStretch()

        # Remote Phone Navigation Controls
        self.btn_back = QPushButton("◀ Back")
        self.btn_back.setToolTip("Trigger Android Back Key")
        self.btn_back.clicked.connect(self.input_controller.send_back_key)
        bot_layout.addWidget(self.btn_back)

        self.btn_home = QPushButton("⚪ Home")
        self.btn_home.setToolTip("Trigger Android Home Key")
        self.btn_home.clicked.connect(self.input_controller.send_home_key)
        bot_layout.addWidget(self.btn_home)

        # Separator line
        v_sep = QFrame()
        v_sep.setFrameShape(QFrame.Shape.VLine)
        v_sep.setStyleSheet("color: #283042;")
        bot_layout.addWidget(v_sep)

        # Audio Output Device & Volume Controls
        self.btn_audio = QPushButton("🔊")
        self.btn_audio.setFixedWidth(34)
        self.btn_audio.setToolTip("Toggle Mute")
        self.btn_audio.clicked.connect(self._toggle_audio)
        bot_layout.addWidget(self.btn_audio)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(100)
        self.slider_volume.setFixedWidth(75)
        self.slider_volume.setToolTip("Volume Level")
        self.slider_volume.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #283042;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00E676;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
        """)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        bot_layout.addWidget(self.slider_volume)

        self.lbl_volume = QLabel("100%")
        self.lbl_volume.setStyleSheet("font-size: 11px; color: #A0AEC0; font-family: Consolas;")
        bot_layout.addWidget(self.lbl_volume)

        self.combo_audio_dev = QComboBox()
        self.combo_audio_dev.setFixedWidth(165)
        self.combo_audio_dev.setToolTip("Select Audio Output Device (Headphones / Speakers)")
        self._populate_audio_devices()
        self.combo_audio_dev.currentIndexChanged.connect(self._on_audio_device_changed)
        bot_layout.addWidget(self.combo_audio_dev)

        # HUD Toggle
        self.btn_hud = QPushButton("HUD: ON")
        self.btn_hud.setToolTip("Toggle On-Screen Telemetry HUD")
        self.btn_hud.clicked.connect(self._toggle_hud_button)
        bot_layout.addWidget(self.btn_hud)

        # Telemetry Stats Pill
        self.lbl_stats_summary = QLabel("0.0 FPS | 0 ms | 0.00 Mbps")
        self.lbl_stats_summary.setStyleSheet("background-color: #121824; border: 1px solid #202838; padding: 4px 10px; border-radius: 6px; color: #38BDF8; font-family: Consolas; font-size: 11px; font-weight: bold;")
        bot_layout.addWidget(self.lbl_stats_summary)

        main_layout.addWidget(self.bottom_bar)

    def _setup_shortcuts(self):
        shortcut_f11 = QShortcut(QKeySequence("F11"), self)
        shortcut_f11.activated.connect(self._toggle_fullscreen)

        shortcut_esc = QShortcut(QKeySequence("Esc"), self)
        shortcut_esc.activated.connect(self._exit_fullscreen_on_esc)

    def _bind_events(self):
        self.server.client_connected.connect(self._on_client_connected)
        self.server.client_disconnected.connect(self._on_client_disconnected)
        self.server.frame_received.connect(self._on_frame_received)
        self.server.audio_received.connect(self.audio_player.write_pcm)
        self.server.status_changed.connect(self._on_status_changed)

    def _init_usb_tunnel(self):
        self._check_usb_device_status()

    def _check_usb_device_status(self):
        if not self.adb_manager.is_available():
            self.adb_manager.refresh()

        if not self.adb_manager.is_available():
            self.usb_pill.setText("⚡ USB: ADB Not Installed")
            self.usb_pill.setStyleSheet("background-color: #2D1518; color: #FF5252; padding: 4px 10px; border-radius: 12px;")
            return

        devices = self.adb_manager.get_devices()
        if devices:
            dev_id = devices[0][0]
            short_id = dev_id[:16] + "..." if len(dev_id) > 16 else dev_id
            self.usb_pill.setText(f"⚡ USB Ready: {short_id}")
            self.usb_pill.setStyleSheet("background-color: #0E3320; color: #00E676; padding: 4px 10px; border-radius: 12px; font-weight: bold;")
            self.adb_manager.reverse_port(self.port)
        else:
            self.usb_pill.setText("⚡ USB: No device detected")
            self.usb_pill.setStyleSheet("background-color: #1A202C; color: #A0AEC0; padding: 4px 10px; border-radius: 12px;")

    def _on_client_connected(self, client_addr: str):
        self.status_pill.setText("● STREAMING LIVE")
        self.status_pill.setStyleSheet("""
            background-color: #0E3320;
            color: #00E676;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        self.lbl_status.setText(f"Active stream from {client_addr}")
        self.setWindowTitle(f"ZeroCast Receiver - [Streaming {client_addr}]")
        self.telemetry.reset()

    def _on_client_disconnected(self):
        self.status_pill.setText("● OFFLINE")
        self.status_pill.setStyleSheet("""
            background-color: #2D1518;
            color: #FF5252;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        self.lbl_status.setText("Phone disconnected. Ready for new stream.")
        self.setWindowTitle("ZeroCast Receiver v1.0")
        self.canvas.update_frame(QPixmap(), self.telemetry.get_stats(), "None")
        self.lbl_stats_summary.setText("0.0 FPS | 0 ms | 0.00 Mbps")

    def _on_frame_received(self, payload: bytes, packet_type: int, timestamp_us: int):
        if packet_type == 0x02:  # H.264
            self.current_codec_name = "H.264 (Hardware)"
            images = self.h264_decoder.decode(payload)
            for img in images:
                if self.virtual_cam.is_active:
                    self.virtual_cam.push_frame(img)
                self.telemetry.record_frame(len(payload), timestamp_us)
                stats = self.telemetry.get_stats()
                pixmap = QPixmap.fromImage(img)
                self.canvas.update_frame(pixmap, stats, self.current_codec_name)
                self.lbl_stats_summary.setText(
                    f"{stats.fps:.1f} FPS | {stats.latency_ms:.1f} ms | {stats.bitrate_mbps:.2f} Mbps | {pixmap.width()}x{pixmap.height()} ({self.current_codec_name})"
                )
        else:  # MJPEG
            self.current_codec_name = "MJPEG"
            image = QImage.fromData(payload)
            if not image.isNull():
                if self.virtual_cam.is_active:
                    self.virtual_cam.push_frame(image)
                self.telemetry.record_frame(len(payload), timestamp_us)
                stats = self.telemetry.get_stats()
                pixmap = QPixmap.fromImage(image)
                self.canvas.update_frame(pixmap, stats, self.current_codec_name)
                self.lbl_stats_summary.setText(
                    f"{stats.fps:.1f} FPS | {stats.latency_ms:.1f} ms | {stats.bitrate_mbps:.2f} Mbps | {pixmap.width()}x{pixmap.height()} ({self.current_codec_name})"
                )

    def _on_status_changed(self, msg: str):
        self.lbl_status.setText(msg)

    def _on_volume_changed(self, val: int):
        level = val / 100.0
        self.audio_player.set_volume(level)
        self.lbl_volume.setText(f"{val}%")
        if val == 0:
            self.btn_audio.setText("🔇")
        else:
            self.btn_audio.setText("🔊")

    def _toggle_audio(self):
        self.audio_player.is_active = not self.audio_player.is_active
        if self.audio_player.is_active:
            self.btn_audio.setText("🔊")
            self.btn_audio.setStyleSheet("")
            self.audio_player.set_volume(self.slider_volume.value() / 100.0)
        else:
            self.btn_audio.setText("🔇")
            self.btn_audio.setStyleSheet("color: #FF5252; border-color: #552222;")
            self.audio_player.set_volume(0.0)

    def _take_snapshot(self):
        if self.canvas.current_pixmap.isNull():
            QMessageBox.information(self, "Snapshot", "No active video stream to capture.")
            return

        pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures", "ZeroCast")
        os.makedirs(pictures_dir, exist_ok=True)

        filename = f"ZeroCast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        full_path = os.path.join(pictures_dir, filename)

        if self.canvas.current_pixmap.save(full_path, "PNG"):
            self.lbl_status.setText(f"📸 Snapshot saved to {filename}")
            QMessageBox.information(self, "Snapshot Saved", f"Image saved successfully to:\n{full_path}")
        else:
            QMessageBox.warning(self, "Error", "Failed to save snapshot image.")

    def _toggle_hud_button(self):
        self.canvas.show_hud = not self.canvas.show_hud
        self.btn_hud.setText("HUD: ON" if self.canvas.show_hud else "HUD: OFF")
        self.canvas.update()

    def _toggle_topmost(self, checked: bool):
        flag = Qt.WindowType.WindowStaysOnTopHint
        if checked:
            self.setWindowFlags(self.windowFlags() | flag)
            self.btn_topmost.setText("📌 Pinned")
            self.btn_topmost.setStyleSheet("background-color: #243B53; border-color: #64B5F6; color: #64B5F6;")
        else:
            self.setWindowFlags(self.windowFlags() & ~flag)
            self.btn_topmost.setText("📌 Pin")
            self.btn_topmost.setStyleSheet("")
        self.show()

    def _toggle_fullscreen(self):
        if not self.is_fullscreen:
            self.top_bar.hide()
            self.bottom_bar.hide()
            self.showFullScreen()
            self.is_fullscreen = True
        else:
            self.top_bar.show()
            self.bottom_bar.show()
            self.showNormal()
            self.is_fullscreen = False

    def _exit_fullscreen_on_esc(self):
        if self.is_fullscreen:
            self._toggle_fullscreen()

    def _show_qr_dialog(self):
        dlg = ModernQRDialog(self.local_ip, self.port, self)
        dlg.exec()

    def _handle_reverse_input(self, action: str, norm_x: float, norm_y: float):
        # 1. Direct ADB touch injection
        self.input_controller.handle_mouse_event(action, norm_x, norm_y)

        # 2. Socket backchannel fallback
        payload = json.dumps({
            "action": action,
            "x": norm_x,
            "y": norm_y
        }).encode("utf-8")
        self.server.send_control_packet(payload)

    def _handle_key_input(self, event_type: str, data):
        if not self.input_controller:
            return
        if event_type == "KEY":
            self.input_controller.send_keyevent(data)
        elif event_type == "TEXT":
            self.input_controller.send_text(data)

    def _populate_audio_devices(self):
        self.combo_audio_dev.clear()
        devices = self.audio_player.get_available_devices()
        default_idx = 0
        for i, (desc, dev, is_def) in enumerate(devices):
            prefix = "🎧 " if any(w in desc.lower() for w in ["head", "stinger", "ear"]) else "🔊 "
            # Clean up long device strings
            short_desc = desc if len(desc) <= 22 else (desc[:20] + "..")
            self.combo_audio_dev.addItem(f"{prefix}{short_desc}", dev)
            self.combo_audio_dev.setItemData(i, desc, Qt.ItemDataRole.ToolTipRole)
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
            self._on_status_changed(f"Audio Output routed to: {device.description()}")

    def _toggle_virtual_cam(self):
        if not self.virtual_cam.is_supported():
            QMessageBox.warning(self, "Virtual Camera", "Virtual Camera backend not available.")
            return

        if self.virtual_cam.is_active:
            self.virtual_cam.stop()
            self.btn_vcam.setText("🎥 V-Cam: OFF")
            self.btn_vcam.setStyleSheet("")
            self._on_status_changed("Virtual Camera stopped.")
        else:
            success = self.virtual_cam.start()
            if success:
                self.btn_vcam.setText("🎥 V-Cam: ON")
                self.btn_vcam.setStyleSheet("""
                    QPushButton {
                        background-color: #0E3320;
                        color: #00E676;
                        border: 1px solid #00E676;
                    }
                """)
                self._on_status_changed(f"Virtual Camera ACTIVE: Select '{self.virtual_cam.device_name}' in Discord / Zoom / OBS")
            else:
                QMessageBox.critical(self, "Virtual Camera Error", f"Failed to start virtual camera: {self.virtual_cam.device_name}")

    def closeEvent(self, event):
        self.discovery.stop()
        self.server.stop()
        self.audio_player.stop()
        self.virtual_cam.stop()
        super().closeEvent(event)
