"""ZeroLink Hub - ZeroCast Module (Monochrome Minimalist Edition)
Ultra-low latency GPU H.264 screen & internal audio mirroring, OBS Virtual Camera,
and reverse control with clean black & white aesthetic.
"""

import os
import io
import json
import time
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QFont, QMouseEvent, QKeyEvent,
    QPen, QBrush, QKeySequence, QShortcut, QDesktopServices, QTransform, QIcon
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QComboBox, QDialog, QSlider, QMainWindow,
    QStackedWidget, QCheckBox, QGraphicsDropShadowEffect, QSizePolicy, QMenu
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
from core.speedtest_server import SpeedTestServer, SPEEDTEST_PORT
from ui.speedtest_dialog import SpeedTestDialog
from modules.zerocast.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, DEFAULT_PORT
)

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


class ModernVideoCanvas(QWidget):
    """Hardware-accelerated viewport with clean monochrome typography."""
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.current_pixmap: QPixmap = QPixmap()
        self.show_hud = True
        self.rotation_angle = 0
        self.stats: TelemetryStats = TelemetryStats()
        self.resolution_text = "Idle"
        self.codec_text = "None"
        self.connection_mode = "STANDBY"
        self.input_enabled = True
        self.on_touch_event = None
        self.on_key_event = None
        self.on_context_menu = None
        self.is_module_active = True
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor("#000000"))
        self.setPalette(p)

        # Floating Overlay Button (shown in Screen-Only mode)
        self.overlay_btn = QPushButton("⛶ Show Controls", self)
        self.overlay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overlay_btn.setToolTip("Restore top and bottom bars (or press Esc)")
        self.overlay_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(17, 24, 39, 0.82);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.96);
                border-color: rgba(255, 255, 255, 0.6);
            }
        """)
        self.overlay_btn.setVisible(False)

    def set_rotation(self, angle: int):
        """Sets manual rotation angle (0, 90, 180, 270 degrees)."""
        self.rotation_angle = angle % 360
        self.update()

    def update_frame(self, pixmap: QPixmap, stats: TelemetryStats, codec_name: str = "MJPEG"):
        self.current_pixmap = pixmap
        self.stats = stats
        self.codec_text = codec_name
        if not pixmap.isNull():
            is_swapped = self.rotation_angle in (90, 270)
            w = pixmap.height() if is_swapped else pixmap.width()
            h = pixmap.width() if is_swapped else pixmap.height()
            self.resolution_text = f"{w}x{h}"
        self.update()

    def get_video_rect(self) -> QRect:
        if self.current_pixmap.isNull():
            return QRect(0, 0, self.width(), self.height())

        is_swapped = self.rotation_angle in (90, 270)
        pw = self.current_pixmap.height() if is_swapped else self.current_pixmap.width()
        ph = self.current_pixmap.width() if is_swapped else self.current_pixmap.height()
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
            if self.rotation_angle != 0:
                rotated = self.current_pixmap.transformed(
                    QTransform().rotate(self.rotation_angle),
                    Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(v_rect, rotated)
            else:
                painter.drawPixmap(v_rect, self.current_pixmap)
        else:
            self._draw_standby_screen(painter)

        if self.show_hud and not self.current_pixmap.isNull():
            self._draw_modern_hud(painter)

    def _draw_inactive_screen(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#F9FAFB"))
        card_w = max(260, min(520, self.width() - 32))
        card_h = min(220, self.height() - 32)
        cx = (self.width() - card_w) // 2
        cy = (self.height() - card_h) // 2
        card_rect = QRect(cx, cy, card_w, card_h)

        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#E5E7EB"), 1.5))
        painter.drawRoundedRect(card_rect, 12, 12)

        badge_rect = QRect(cx + 24, cy + 24, 130, 24)
        painter.setBrush(QColor("#F3F4F6"))
        painter.setPen(QPen(QColor("#E5E7EB"), 1))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#6B7280"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "○ MODULE INACTIVE")

        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        painter.setPen(QColor("#111827"))
        painter.drawText(cx + 24, cy + 80, "ZeroCast Service is Turned Off")

        painter.setFont(QFont("Segoe UI", 11))
        painter.setPen(QColor("#6B7280"))
        painter.drawText(cx + 24, cy + 112, "Port 8888 is closed. Mobile devices cannot connect.")
        painter.drawText(cx + 24, cy + 134, "Click 'Enable Module' in the top bar or dashboard to start.")

    def _draw_standby_screen(self, painter: QPainter):
        painter.fillRect(self.rect(), QColor("#F9FAFB"))
        card_w = max(260, min(520, self.width() - 32))
        card_h = min(240, self.height() - 32)
        cx = (self.width() - card_w) // 2
        cy = (self.height() - card_h) // 2
        card_rect = QRect(cx, cy, card_w, card_h)

        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#E5E7EB"), 1.5))
        painter.drawRoundedRect(card_rect, 12, 12)

        badge_rect = QRect(cx + 24, cy + 24, 110, 24)
        painter.setBrush(QColor("#000000"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.ExtraBold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "ZEROCAST v1.0")

        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        painter.setPen(QColor("#111827"))
        painter.drawText(cx + 24, cy + 80, "Ready for Device Stream")

        painter.setFont(QFont("Segoe UI", 11))
        painter.setPen(QColor("#374151"))
        painter.drawText(cx + 24, cy + 112, "1. Connect Android via USB Cable (Auto ADB) or Wi-Fi.")
        painter.drawText(cx + 24, cy + 134, "2. Open ZeroLink app on phone, tap ZeroCast, and start stream.")

    def _draw_modern_hud(self, painter: QPainter):
        hud_items = [
            ("MEDIA", getattr(self, "connection_mode", "STANDBY")),
            ("FPS", f"{self.stats.fps:.0f}"),
            ("LATENCY", f"{self.stats.latency_ms:.0f} ms"),
            ("BITRATE", f"{self.stats.bitrate_mbps:.1f} Mbps"),
            ("CODEC", self.codec_text),
            ("RES", self.resolution_text),
        ]

        box_width = 186
        box_height = 16 + len(hud_items) * 22 + 8
        painter.setBrush(QColor(9, 9, 11, 235))
        painter.setPen(QPen(QColor(63, 63, 70), 1))
        painter.drawRoundedRect(QRect(20, 20, box_width, box_height), 6, 6)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#A1A1AA"))
        painter.drawText(30, 34, "TELEMETRY")

        y = 54
        for label, val in hud_items:
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#E4E4E7"))
            painter.drawText(30, y, label)

            painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(QRect(70, y - 12, 124, 18), Qt.AlignmentFlag.AlignRight, val)
            y += 22

    def _normalize_coords(self, pos: QPoint):
        if self.current_pixmap.isNull() or not self.on_touch_event:
            return None
        v_rect = self.get_video_rect()
        if not v_rect.contains(pos):
            return None
        click_x = (pos.x() - v_rect.x()) / v_rect.width()
        click_y = (pos.y() - v_rect.y()) / v_rect.height()

        if self.rotation_angle == 90:
            norm_x = click_y
            norm_y = 1.0 - click_x
        elif self.rotation_angle == 180:
            norm_x = 1.0 - click_x
            norm_y = 1.0 - click_y
        elif self.rotation_angle == 270:
            norm_x = 1.0 - click_y
            norm_y = click_x
        else:
            norm_x = click_x
            norm_y = click_y

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
        elif key == Qt.Key.Key_F1:
            self.on_key_event("KEY", 187)  # Recent Apps
        elif key == Qt.Key.Key_F2:
            self.on_key_event("KEY", 3)    # Home
        elif key == Qt.Key.Key_F3:
            self.on_key_event("NOTIF", 0)  # Notifications
        elif key == Qt.Key.Key_F4:
            self.on_key_event("KEY", 26)   # Power/Lock
        elif key == Qt.Key.Key_F5:
            self.on_key_event("KEY", 25)   # Vol Down
        elif key == Qt.Key.Key_F6:
            self.on_key_event("KEY", 24)   # Vol Up
        else:
            text = event.text()
            if text and text.isprintable():
                self.on_key_event("TEXT", text)
            else:
                super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay_btn") and self.overlay_btn:
            bw = 118
            bh = 30
            self.overlay_btn.setGeometry(self.width() - bw - 14, 14, bw, bh)

    def contextMenuEvent(self, event):
        if hasattr(self, "on_context_menu") and self.on_context_menu:
            self.on_context_menu(event.globalPos())
        else:
            super().contextMenuEvent(event)


class ZeroCastPopoutWindow(QMainWindow):
    """Independent floating window for ZeroCast streaming session."""

    def __init__(self, cast_module, parent=None):
        super().__init__(parent)
        self.cast_module = cast_module
        self.is_fullscreen = False
        self.is_pinned = False

        self.setWindowTitle("ZeroCast — Screen Mirror")
        icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(560, 880)
        self.setMinimumSize(360, 500)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #FFFFFF;
            }
        """)

        # Shortcuts
        self.shortcut_f11 = QShortcut(QKeySequence("F11"), self)
        self.shortcut_f11.activated.connect(self._toggle_fullscreen)

        self.shortcut_esc = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_esc.activated.connect(self._exit_fullscreen_on_esc)

    def toggle_pin(self, checked: bool = None):
        if checked is None:
            self.is_pinned = not self.is_pinned
        else:
            self.is_pinned = checked
        flag = Qt.WindowType.WindowStaysOnTopHint
        pos = self.pos()
        size = self.size()
        if self.is_pinned:
            self.setWindowFlags(self.windowFlags() | flag)
        else:
            self.setWindowFlags(self.windowFlags() & ~flag)
        self.resize(size)
        self.move(pos)
        self.show()
        if hasattr(self.cast_module, "btn_pin") and self.cast_module.btn_pin:
            if self.is_pinned:
                self.cast_module.btn_pin.setText("⚲ Pinned")
                self.cast_module.btn_pin.setStyleSheet("background-color: #111827; color: #FFFFFF; font-weight: 700; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
            else:
                self.cast_module.btn_pin.setText("⚲ Pin")
                self.cast_module.btn_pin.setStyleSheet("background-color: #F3F4F6; color: #374151; font-weight: 600; border: 1px solid #D1D5DB; border-radius: 4px; padding: 4px 8px; font-size: 11px;")

    def fit_to_stream_aspect_ratio(self):
        """Dynamically adjusts window geometry to perfectly fit the active stream aspect ratio."""
        if not self.cast_module.canvas.current_pixmap.isNull():
            pm = self.cast_module.canvas.current_pixmap
            is_swapped = self.cast_module.canvas.rotation_angle in (90, 270)
            pw = pm.height() if is_swapped else pm.width()
            ph = pm.width() if is_swapped else pm.height()
            if pw > 0 and ph > 0:
                aspect = pw / ph
                bar_h = 0 if getattr(self.cast_module, "is_screen_only", False) else 82
                if aspect >= 1.0: # Landscape orientation
                    target_w = 900
                    target_h = int(target_w / aspect) + bar_h
                else: # Portrait orientation
                    target_h = 760
                    target_w = int((target_h - bar_h) * aspect)
                self.resize(max(340, target_w), max(380, target_h))

    def _toggle_fullscreen(self):
        if not self.is_fullscreen:
            self.showFullScreen()
            self.is_fullscreen = True
        else:
            self.showNormal()
            self.is_fullscreen = False

    def _exit_fullscreen_on_esc(self):
        if self.is_fullscreen:
            self._toggle_fullscreen()
        elif hasattr(self.cast_module, "is_screen_only") and self.cast_module.is_screen_only:
            self.cast_module.set_screen_only(False)

    def closeEvent(self, event):
        event.ignore()
        self.cast_module.dock_back()


class ZeroCastModule(BaseModule):
    """Monochrome Minimalist ZeroCast Module."""
    toggle_fullscreen_requested = pyqtSignal()
    toggle_pin_requested = pyqtSignal()
    audio_pcm_received = pyqtSignal(bytes)

    def __init__(self, port: int = 8888, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self.use_external_mixer = False

        self.telemetry = TelemetryTracker()
        self.server = StreamServer(host="0.0.0.0", port=self.port)
        self.adb_manager = AdbManager()
        self.audio_player = AudioPlayer()
        self.h264_decoder = H264Decoder()
        self.input_controller = InputController(self.adb_manager)
        self.virtual_cam = VirtualCameraManager(target_width=1280, target_height=720, fps=30)
        self.discovery = LanDiscoveryService(tcp_port=self.port, local_ip=self.local_ip)
        self.speedtest_server = SpeedTestServer(port=SPEEDTEST_PORT, parent=self)

        self.current_codec_name = "MJPEG"
        self._widget: Optional[QWidget] = None
        self.canvas: Optional[ModernVideoCanvas] = None
        self.status_pill: Optional[QLabel] = None
        self.log_label: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None
        self.usb_pill: Optional[QLabel] = None
        self.combo_audio_dev: Optional[QComboBox] = None
        self.btn_vcam: Optional[QPushButton] = None
        self.btn_audio: Optional[QPushButton] = None
        self.slider_volume: Optional[QSlider] = None
        self.lbl_volume: Optional[QLabel] = None
        self.combo_rotate: Optional[QComboBox] = None
        self._prev_volume: int = 100

        # Detachable Popout State
        self.is_popped_out: bool = False
        self.is_screen_only: bool = False
        self.popout_window: Optional[ZeroCastPopoutWindow] = None
        self._stacked_container: Optional[QStackedWidget] = None
        self._dock_container: Optional[QWidget] = None
        self._dock_layout: Optional[QVBoxLayout] = None
        self._content_widget: Optional[QWidget] = None
        self._placeholder_widget: Optional[QWidget] = None
        self.top_bar: Optional[QFrame] = None
        self.bottom_bar: Optional[QFrame] = None
        self.btn_popout: Optional[QPushButton] = None
        self.btn_screen_only: Optional[QPushButton] = None
        self.chk_auto_popout: Optional[QCheckBox] = None

        self._bind_events()
        self._init_usb_tunnel()

        self.usb_timer = QTimer(self)
        self.usb_timer.timeout.connect(self._check_usb_device_status)
        self.usb_timer.start(3000)

    @property
    def module_id(self) -> str:
        return MODULE_ID

    @property
    def display_name(self) -> str:
        return MODULE_NAME

    @property
    def icon_glyph(self) -> str:
        return MODULE_ICON

    @property
    def description(self) -> str:
        return MODULE_DESCRIPTION

    def start_service(self) -> bool:
        self.server.start()
        self.discovery.start()
        self.speedtest_server.start()
        self._is_active = True
        if self._widget:
            self.canvas.is_module_active = True
            self.btn_power.setText("Disable Module")
            self.btn_power.setStyleSheet("""
                QPushButton {
                    background-color: #141414;
                    color: #888888;
                    border: 1px solid #282828;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #202020;
                    color: #FFFFFF;
                }
            """)
            self.status_pill.setText("● READY")
            self.status_pill.setStyleSheet("color: #FFFFFF; background-color: #141414; border: 1px solid #282828; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            self.canvas.update()
        self.status_changed.emit(self.module_id, "ZeroCast service started")
        return True

    def stop_service(self) -> bool:
        self.server.stop()
        self.discovery.stop()
        self.speedtest_server.stop()
        self.audio_player.stop()
        self.virtual_cam.stop()
        self._is_active = False

        if self._widget:
            self.canvas.is_module_active = False
            self.canvas.current_pixmap = QPixmap()
            self.btn_power.setText("Enable Module")
            self.btn_power.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #000000;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #E2E2E2;
                }
            """)
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("color: #555555; background-color: #111111; border: 1px solid #1E1E1E; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            self.canvas.update()

        self.status_changed.emit(self.module_id, "ZeroCast service stopped")
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
        self.server.config_received.connect(self._on_config_received)
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
            self.usb_pill.setText("USB: No ADB")
            self.usb_pill.setStyleSheet("color: #555555; background: #0E0E0E; border: 1px solid #1C1C1C; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
            return

        conn_type = self.adb_manager.get_connection_type()
        devs = self.adb_manager.get_devices()
        if devs:
            dev_id = devs[0][0]
            if conn_type == "WIRELESS_ADB":
                self.usb_pill.setText("⚡ ADB: Wireless Wi-Fi (No Cable)")
                self.usb_pill.setToolTip("Connected via Wireless Debugging over Wi-Fi. Real USB cable is not plugged in.")
                self.usb_pill.setStyleSheet("color: #F59E0B; background: #2A1A05; border: 1px solid #D97706; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            else:
                short_id = dev_id if len(dev_id) <= 12 else (dev_id[:10] + "..")
                self.usb_pill.setText(f"⚡ USB Cable: {short_id}")
                self.usb_pill.setToolTip("Connected via physical USB cable (High-Speed ADB).")
                self.usb_pill.setStyleSheet("color: #38BDF8; background: #0C2340; border: 1px solid #0284C7; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        else:
            self.usb_pill.setText("USB: Unplugged")
            self.usb_pill.setStyleSheet("color: #555555; background: #0E0E0E; border: 1px solid #1C1C1C; padding: 4px 8px; border-radius: 4px; font-size: 10px;")

    def _setup_ui(self):
        self._stacked_container = QStackedWidget()

        # Page 0: Embedded Dock Container
        self._dock_container = QWidget()
        self._dock_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._dock_layout = QVBoxLayout(self._dock_container)
        self._dock_layout.setContentsMargins(0, 0, 0, 0)
        self._dock_layout.setSpacing(0)

        # Content widget containing top bar, canvas, and bottom bar
        self._content_widget = QWidget()
        self._content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #FFFFFF; border-bottom: 1px solid #E5E7EB;")
        self.top_bar = top_bar
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(14, 8, 14, 8)
        bar_layout.setSpacing(8)

        self.btn_power = QPushButton("Disable Module" if self.is_active else "Enable Module")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● READY" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.usb_pill = QLabel("USB: Checking...")
        self.usb_pill.setStyleSheet("color: #4B5563; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.usb_pill)

        self.wifi_pill = QLabel(f"Wi-Fi: {self.local_ip}:{self.port}")
        self.wifi_pill.setStyleSheet("color: #4B5563; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-family: Consolas;")
        bar_layout.addWidget(self.wifi_pill)

        bar_layout.addStretch()

        # Pin Button (Pop-out mode only)
        self.btn_pin = QPushButton("📌 Pin")
        self.btn_pin.setToolTip("Always on Top (Keep floating above other windows)")
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #374151;
                font-weight: 600;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_pin.clicked.connect(lambda: self.popout_window.toggle_pin() if self.popout_window else None)
        self.btn_pin.setVisible(False)
        bar_layout.addWidget(self.btn_pin)

        self.btn_vcam = QPushButton("V-Cam: OFF")
        self.btn_vcam.clicked.connect(self._toggle_virtual_cam)
        bar_layout.addWidget(self.btn_vcam)

        # Manual Orientation Selector
        self.combo_rotate = QComboBox()
        self.combo_rotate.addItem("↻ Auto (0°)", 0)
        self.combo_rotate.addItem("↻ 90°", 90)
        self.combo_rotate.addItem("↻ 180°", 180)
        self.combo_rotate.addItem("↻ 270°", 270)
        self.combo_rotate.setToolTip("Force manual orientation (0°, 90°, 180°, 270°)")
        self.combo_rotate.currentIndexChanged.connect(self._on_rotation_changed)
        bar_layout.addWidget(self.combo_rotate)

        # Auto Pop-out Checkbox
        self.chk_auto_popout = QCheckBox("Auto Pop-out")
        self.chk_auto_popout.setStyleSheet("color: #374151; font-size: 11px;")
        self.chk_auto_popout.setToolTip("Automatically open in a floating window when phone connects")
        bar_layout.addWidget(self.chk_auto_popout)

        # Screen Dim Button
        self.btn_dim_screen = QPushButton("◒ Dim")
        self.btn_dim_screen.setToolTip("Dim phone display to 0% brightness to save battery & prevent heating while casting")
        self.btn_dim_screen.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_dim_screen.clicked.connect(self._toggle_dim_screen)
        bar_layout.addWidget(self.btn_dim_screen)

        # Screen Only Button (Pop-out mode only)
        self.btn_screen_only = QPushButton("□ Screen Only")
        self.btn_screen_only.setToolTip("Hide toolbars and show pure screen only (Press Esc or click 'Show Controls' to restore)")
        self.btn_screen_only.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
                border-color: #9CA3AF;
            }
        """)
        self.btn_screen_only.clicked.connect(lambda: self.set_screen_only(True))
        self.btn_screen_only.setVisible(False)
        bar_layout.addWidget(self.btn_screen_only)

        # Manual Pop-out Button
        self.btn_popout = QPushButton("↗ Pop-out")
        self.btn_popout.setToolTip("Detach ZeroCast into an independent floating window")
        self.btn_popout.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
                border-color: #9CA3AF;
            }
        """)
        self.btn_popout.clicked.connect(self._toggle_popout)
        bar_layout.addWidget(self.btn_popout)

        # Fit Aspect Ratio Button
        self.btn_fit = QPushButton("⇲ Fit Aspect")
        self.btn_fit.setToolTip("Dynamically fit window to the phone's exact aspect ratio")
        self.btn_fit.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
                border-color: #9CA3AF;
            }
        """)
        self.btn_fit.clicked.connect(self._fit_to_stream_aspect)
        bar_layout.addWidget(self.btn_fit)

        self.btn_snapshot = QPushButton("⧇ Snapshot")
        self.btn_snapshot.clicked.connect(self._take_snapshot)
        bar_layout.addWidget(self.btn_snapshot)

        self.btn_qr = QPushButton("QR Code")
        self.btn_qr.clicked.connect(self._show_qr_dialog)
        bar_layout.addWidget(self.btn_qr)

        self.btn_speedtest = QPushButton("⌁ Speed Test")
        self.btn_speedtest.setToolTip("Benchmark connection latency and throughput (USB vs Wi-Fi)")
        self.btn_speedtest.clicked.connect(self._show_speedtest_dialog)
        bar_layout.addWidget(self.btn_speedtest)

        layout.addWidget(top_bar)

        # Video Canvas
        self.canvas = ModernVideoCanvas(self._content_widget)
        self.canvas.is_module_active = self.is_active
        self.canvas.on_touch_event = self._handle_reverse_input
        self.canvas.on_key_event = self._handle_key_input
        self.canvas.double_clicked.connect(self.toggle_fullscreen_requested.emit)
        self.canvas.overlay_btn.clicked.connect(lambda: self.set_screen_only(False))
        self.canvas.on_context_menu = self._show_canvas_context_menu
        layout.addWidget(self.canvas, 1)

        # Bottom Bar Dock
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet("background-color: #FFFFFF; border-top: 1px solid #E5E7EB;")
        self.bottom_bar = bottom_bar
        bot_layout = QHBoxLayout(bottom_bar)
        bot_layout.setContentsMargins(14, 6, 14, 6)
        bot_layout.setSpacing(8)

        self.log_label = QLabel("ZeroCast Ready")
        self.log_label.setStyleSheet("color: #1F2937; font-size: 11px; font-weight: 500;")
        bot_layout.addWidget(self.log_label)

        bot_layout.addStretch()

        btn_back = QPushButton("← Back")
        btn_back.clicked.connect(lambda: self.input_controller.send_key_event(4))
        bot_layout.addWidget(btn_back)

        btn_home = QPushButton("○ Home")
        btn_home.clicked.connect(lambda: self.input_controller.send_key_event(3))
        bot_layout.addWidget(btn_home)

        btn_recent = QPushButton("▢ Recent")
        btn_recent.setToolTip("Recent Apps / App Switcher (F1)")
        btn_recent.clicked.connect(self.input_controller.send_recent_apps)
        bot_layout.addWidget(btn_recent)

        btn_notify = QPushButton("▤")
        btn_notify.setFixedWidth(30)
        btn_notify.setToolTip("Notification Shade (F3)")
        btn_notify.clicked.connect(self.input_controller.send_notifications)
        bot_layout.addWidget(btn_notify)

        btn_power = QPushButton("⏻")
        btn_power.setFixedWidth(30)
        btn_power.setToolTip("Screen Lock / Power (F4)")
        btn_power.clicked.connect(self.input_controller.send_power_key)
        bot_layout.addWidget(btn_power)

        bot_layout.addSpacing(4)

        # Volume Controls
        self.btn_audio = QPushButton("◗")
        self.btn_audio.setFixedWidth(32)
        self.btn_audio.setToolTip("Click to Mute / Unmute")
        self.btn_audio.clicked.connect(self._toggle_audio)
        bot_layout.addWidget(self.btn_audio)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(100)
        self.slider_volume.setFixedWidth(75)
        self.slider_volume.setToolTip("Volume: 100%")
        self.slider_volume.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #E5E7EB;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #111827;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #111827;
                border: 2px solid #FFFFFF;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #000000;
            }
        """)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        bot_layout.addWidget(self.slider_volume)

        self.lbl_volume = QLabel("100%")
        self.lbl_volume.setStyleSheet("color: #111827; font-size: 11px; font-weight: 700; min-width: 32px;")
        bot_layout.addWidget(self.lbl_volume)

        self.combo_audio_dev = QComboBox()
        self._populate_audio_devices()
        self.combo_audio_dev.currentIndexChanged.connect(self._on_audio_device_changed)
        bot_layout.addWidget(self.combo_audio_dev)

        self.btn_hud = QPushButton("HUD")
        self.btn_hud.setCheckable(True)
        self.btn_hud.setChecked(True)
        self.btn_hud.clicked.connect(self._toggle_hud)
        bot_layout.addWidget(self.btn_hud)

        layout.addWidget(bottom_bar)

        # Add content into Dock Container
        self._dock_layout.addWidget(self._content_widget)
        self._stacked_container.addWidget(self._dock_container)

        # Page 1: Detached Window Placeholder
        self._placeholder_widget = self._create_popout_placeholder()
        self._stacked_container.addWidget(self._placeholder_widget)

        self._widget = self._stacked_container

    def _toggle_power(self):
        if self.is_active:
            self.stop_service()
            self.state_changed.emit(self.module_id, False)
        else:
            self.start_service()
            self.state_changed.emit(self.module_id, True)

    def _on_client_connected(self, client_info: str):
        self.is_audio_only_stream = False
        client_ip = client_info.split(":")[0].strip()
        is_loopback = client_ip in ("127.0.0.1", "localhost", "::1")
        conn_type = self.adb_manager.get_connection_type() if is_loopback else "WIFI"

        if is_loopback and conn_type == "WIRELESS_ADB":
            mode_desc = "⚡ WIRELESS ADB (Wi-Fi Tunnel • Capped ~20 Mbps)"
            badge_text = "● LIVE: ⚡ WIRELESS ADB (Wi-Fi)"
            badge_style = "color: #F59E0B; background-color: #2A1A05; border: 1px solid #D97706; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 700;"
        elif is_loopback and conn_type == "USB":
            mode_desc = "⚡ PHYSICAL USB CABLE"
            badge_text = "● LIVE: ⚡ USB CABLE"
            badge_style = "color: #38BDF8; background-color: #0C2340; border: 1px solid #0284C7; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 700;"
        else:
            mode_desc = f"📡 WI-FI LAN ({client_ip})"
            badge_text = "● LIVE: 📡 WI-FI LAN"
            badge_style = "color: #34D399; background-color: #064E3B; border: 1px solid #059669; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 700;"

        if self.canvas:
            self.canvas.connection_mode = mode_desc
        if self.status_pill:
            self.status_pill.setText(badge_text)
            self.status_pill.setStyleSheet(badge_style)
        if self.log_label:
            self.log_label.setText(f"Connected: {client_info} [{mode_desc}]")
        self.telemetry.reset()
        self.h264_decoder.reset()

        if self.chk_auto_popout and self.chk_auto_popout.isChecked() and not self.is_popped_out:
            QTimer.singleShot(250, self._maybe_auto_popout)

    def _maybe_auto_popout(self):
        if self.chk_auto_popout and self.chk_auto_popout.isChecked() and not self.is_popped_out:
            if not getattr(self, "is_audio_only_stream", False):
                self.pop_out()

    def _on_config_received(self, config_str: str):
        try:
            cfg = json.loads(config_str)
            codec = cfg.get("codec", "")
            if codec in ("AUDIO_ONLY", "AUDIO_ONLY_ECO"):
                self.is_audio_only_stream = True
                if self.status_pill:
                    self.status_pill.setText("● AUDIO STREAM")
                    self.status_pill.setStyleSheet("color: #FFFFFF; background-color: #1A1A1A; border: 1px solid #444444; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 700;")
                if self.log_label:
                    model = cfg.get("device_model", "Android")
                    self.log_label.setText(f"Audio Cast: {model} (Eco)")
            else:
                self.is_audio_only_stream = False
        except Exception:
            pass

    def _on_client_disconnected(self):
        self.is_audio_only_stream = False
        if self.canvas:
            self.canvas.connection_mode = "STANDBY"
            self.canvas.current_pixmap = QPixmap()
            self.canvas.update()
        if self.status_pill:
            self.status_pill.setText("● READY" if self.is_active else "○ INACTIVE")
            self.status_pill.setStyleSheet("color: #FFFFFF; background-color: #141414; border: 1px solid #282828; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        if self.log_label:
            self.log_label.setText("Client disconnected")

    def _on_frame_received(self, payload: bytes, frame_type: int, timestamp_us: int):
        if not self.is_active:
            return

        if getattr(self, "is_audio_only_stream", False):
            # In audio-only eco mode, ignore incoming video frames so they don't display on screen or pop out
            return

        if frame_type == 0x02:  # TYPE_VIDEO_H264
            self.current_codec_name = "H.264"
            images = self.h264_decoder.decode(payload)
            if images:
                bytes_per_img = len(payload) // len(images)
                for img in images:
                    if self.virtual_cam.is_active:
                        self.virtual_cam.push_frame(img)
                    stats = self.telemetry.update(bytes_per_img, timestamp_us)
                    pixmap = QPixmap.fromImage(img)
                    if self.canvas:
                        self.canvas.update_frame(pixmap, stats, self.current_codec_name)
        else:  # TYPE_VIDEO_MJPEG
            self.current_codec_name = "MJPEG"
            pixmap = QPixmap()
            pixmap.loadFromData(payload)
            if not pixmap.isNull():
                if self.virtual_cam.is_active:
                    self.virtual_cam.push_frame(pixmap.toImage())
                stats = self.telemetry.update(len(payload), timestamp_us)
                if self.canvas:
                    self.canvas.update_frame(pixmap, stats, self.current_codec_name)

    def _show_speedtest_dialog(self):
        client_ip = "127.0.0.1"
        if self.server.current_client_info:
            client_ip = self.server.current_client_info.get("ip", "127.0.0.1")
        dlg = SpeedTestDialog(target_host=client_ip, parent=self._widget)
        dlg.exec()

    def _on_audio_received(self, pcm_data: bytes):
        if self.is_active:
            self.audio_pcm_received.emit(pcm_data)
            # Only play directly to default speaker if it's NOT an audio-only stream for ZeroMix
            if not getattr(self, "is_audio_only_stream", False) and not self.use_external_mixer and self.audio_player:
                self.audio_player.play_chunk(pcm_data)

    def _handle_reverse_input(self, action: str, nx: float, ny: float):
        self.input_controller.send_touch_event(action, nx, ny)

    def _handle_key_input(self, input_type: str, value):
        if input_type == "KEY":
            self.input_controller.send_key_event(value)
        elif input_type == "NOTIF":
            self.input_controller.send_notifications()
        elif input_type == "TEXT":
            self.input_controller.send_text(value)

    def _populate_audio_devices(self):
        self.combo_audio_dev.clear()
        devices = self.audio_player.get_available_devices()
        default_idx = 0
        for i, (desc, dev, is_def) in enumerate(devices):
            short_desc = desc if len(desc) <= 20 else (desc[:18] + "..")
            self.combo_audio_dev.addItem(short_desc, dev)
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

    def _on_volume_changed(self, val: int):
        vol = val / 100.0
        self.audio_player.set_volume(vol)
        if self.lbl_volume:
            self.lbl_volume.setText(f"{val}%")
        if self.slider_volume:
            self.slider_volume.setToolTip(f"Volume: {val}%")
        if self.btn_audio:
            if val == 0:
                self.btn_audio.setText("🔇")
            elif val < 50:
                self.btn_audio.setText("🔉")
            else:
                self.btn_audio.setText("🔊")

    def _toggle_audio(self):
        if not self.slider_volume:
            return
        if self.slider_volume.value() > 0:
            self._prev_volume = self.slider_volume.value()
            self.slider_volume.setValue(0)
        else:
            prev = getattr(self, "_prev_volume", 100)
            self.slider_volume.setValue(prev if prev > 0 else 100)

    def _on_rotation_changed(self, idx: int):
        if not self.combo_rotate or not self.canvas:
            return
        angle = self.combo_rotate.itemData(idx)
        if angle is None:
            angle = 0
        self.canvas.set_rotation(angle)

        # Force sync with Android device via ADB if connected
        if self.adb_manager.is_available():
            if angle == 0:
                # Re-enable accelerometer rotation
                self.input_controller._run_adb_async(["shell", "settings", "put", "system", "accelerometer_rotation", "1"])
            else:
                # Lock rotation: 0=portrait, 1=landscape 90, 2=inverted 180, 3=landscape 270
                adb_rot = {90: 1, 180: 2, 270: 3}.get(angle, 0)
                self.input_controller._run_adb_async(["shell", "settings", "put", "system", "accelerometer_rotation", "0"])
                self.input_controller._run_adb_async(["shell", "settings", "put", "system", "user_rotation", str(adb_rot)])

        if self.log_label:
            mode_str = "Landscape" if angle in (90, 270) else "Portrait"
            self.log_label.setText(f"Orientation: {angle}° ({mode_str})")

    def _toggle_hud(self):
        self.canvas.show_hud = self.btn_hud.isChecked()
        self.canvas.update()

    def _toggle_virtual_cam(self):
        if not self.virtual_cam.is_supported():
            return
        if self.virtual_cam.is_active:
            self.virtual_cam.stop()
            self.btn_vcam.setText("V-Cam: OFF")
            self.btn_vcam.setStyleSheet("")
        else:
            if self.virtual_cam.start():
                self.btn_vcam.setText("V-Cam: ON")
                self.btn_vcam.setStyleSheet("background-color: #FFFFFF; color: #000000; font-weight: 700; border: none;")

    def _take_snapshot(self):
        if self.canvas.current_pixmap.isNull():
            return
        save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "ZeroCast")
        os.makedirs(save_dir, exist_ok=True)
        fname = f"ZeroCast_{int(time.time())}.png"
        path = os.path.join(save_dir, fname)
        self.canvas.current_pixmap.save(path, "PNG")
        self.log_label.setText(f"Snapshot saved: {fname}")

    def _show_qr_dialog(self):
        dlg = QDialog(self._widget)
        dlg.setWindowTitle("Wireless Pairing")
        dlg.setFixedSize(280, 260)
        dlg.setStyleSheet("background-color: #0A0A0A; color: white; border: 1px solid #222222;")
        l = QVBoxLayout(dlg)
        l.setContentsMargins(24, 24, 24, 24)
        l.setSpacing(16)

        t = QLabel("Wireless Pairing")
        t.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(t)

        lbl = QLabel(f"Server IP: <b>{self.local_ip}</b><br>Port: <b>{self.port}</b>")
        lbl.setStyleSheet("color: #AAAAAA; font-family: Consolas; font-size: 13px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl)

        btn = QPushButton("Done")
        btn.clicked.connect(dlg.accept)
        l.addWidget(btn)
        dlg.exec()

    def _create_popout_placeholder(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setMaximumWidth(540)
        card.setMinimumWidth(300)
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 16px;
            }
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 6)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 32, 36, 32)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("📺")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 32))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(icon_lbl)

        title_lbl = QLabel("ZeroCast is Running in a Detached Window")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827; border: none;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel("Screen streaming and audio are active in an independent window.\nYou can freely use other modules in this Hub.")
        desc_lbl.setFont(QFont("Segoe UI", 10))
        desc_lbl.setStyleSheet("color: #6B7280; border: none;")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(desc_lbl)

        card_layout.addSpacing(8)

        btn_dock = QPushButton("↙ Dock Back to Hub")
        btn_dock.setFixedSize(180, 38)
        btn_dock.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: #FFFFFF;
                font-weight: 700;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        btn_dock.clicked.connect(self.dock_back)
        card_layout.addWidget(btn_dock, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(card)
        return container

    def _set_compact_mode(self, is_compact: bool):
        """Toggles between standard Hub mode and responsive compact mode for pop-out."""
        # Top bar
        if hasattr(self, "btn_power") and self.btn_power:
            self.btn_power.setVisible(not is_compact)
        if hasattr(self, "usb_pill") and self.usb_pill:
            self.usb_pill.setVisible(not is_compact)
        if hasattr(self, "wifi_pill") and self.wifi_pill:
            self.wifi_pill.setVisible(not is_compact)
        if hasattr(self, "chk_auto_popout") and self.chk_auto_popout:
            self.chk_auto_popout.setVisible(not is_compact)
        if hasattr(self, "btn_qr") and self.btn_qr:
            self.btn_qr.setVisible(not is_compact)
        if hasattr(self, "btn_snapshot") and self.btn_snapshot:
            self.btn_snapshot.setVisible(not is_compact)
        if hasattr(self, "btn_pin") and self.btn_pin:
            self.btn_pin.setVisible(is_compact)
        if hasattr(self, "btn_screen_only") and self.btn_screen_only:
            self.btn_screen_only.setVisible(is_compact)

        # Bottom bar
        if hasattr(self, "log_label") and self.log_label:
            self.log_label.setVisible(not is_compact)
        if hasattr(self, "combo_audio_dev") and self.combo_audio_dev:
            self.combo_audio_dev.setVisible(not is_compact)

    def _fit_to_stream_aspect(self):
        """Dynamically fits window to current video aspect ratio."""
        if self.is_popped_out and self.popout_window:
            self.popout_window.fit_to_stream_aspect_ratio()
        elif self.canvas:
            self.canvas.update()

    def _toggle_dim_screen(self):
        """Toggles phone screen dimming (brightness to 0 to save battery/heat)."""
        self.is_screen_dimmed = not getattr(self, "is_screen_dimmed", False)
        self.input_controller.set_screen_dimmed(self.is_screen_dimmed)
        if hasattr(self, "btn_dim_screen") and self.btn_dim_screen:
            if self.is_screen_dimmed:
                self.btn_dim_screen.setText("◓ Restore")
                self.btn_dim_screen.setStyleSheet("background-color: #111827; color: #FFFFFF; font-weight: 700; border-radius: 6px; padding: 4px 8px; font-size: 11px;")
                if self.log_label:
                    self.log_label.setText("Phone screen dimmed (Power save active)")
            else:
                self.btn_dim_screen.setText("◒ Dim")
                self.btn_dim_screen.setStyleSheet("background-color: #F3F4F6; color: #111827; border: 1px solid #D1D5DB; font-weight: 600; padding: 4px 8px; border-radius: 6px; font-size: 11px;")
                if self.log_label:
                    self.log_label.setText("Phone screen brightness restored")

    def toggle_screen_only(self):
        self.set_screen_only(not self.is_screen_only)

    def set_screen_only(self, enabled: bool):
        """Toggles pure screen mode (hiding top/bottom bars for unobstructed viewing)."""
        self.is_screen_only = enabled

        if hasattr(self, "top_bar") and self.top_bar:
            self.top_bar.setVisible(not enabled)
        if hasattr(self, "bottom_bar") and self.bottom_bar:
            self.bottom_bar.setVisible(not enabled)

        if hasattr(self.canvas, "overlay_btn") and self.canvas.overlay_btn:
            self.canvas.overlay_btn.setVisible(enabled)

        if self.popout_window:
            if enabled:
                self.popout_window.setMinimumSize(180, 240)
            else:
                self.popout_window.setMinimumSize(360, 500)

        if not enabled and self.is_popped_out:
            self._set_compact_mode(True)

    def _show_canvas_context_menu(self, pos: QPoint):
        """Minimalist right-click context menu on video viewport."""
        menu = QMenu(self.canvas)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #F3F4F6;
                color: #000000;
            }
            QMenu::separator {
                height: 1px;
                background: #E5E7EB;
                margin: 4px 8px;
            }
        """)

        if self.is_popped_out:
            if self.is_screen_only:
                act_screen = menu.addAction("⛶ Show Controls")
                act_screen.triggered.connect(lambda: self.set_screen_only(False))
            else:
                act_screen = menu.addAction("🖥️ Screen Only")
                act_screen.triggered.connect(lambda: self.set_screen_only(True))

            is_pinned = self.popout_window.is_pinned if self.popout_window else False
            act_pin = menu.addAction("📌 Always on Top" if not is_pinned else "📌 Unpin Window")
            act_pin.triggered.connect(lambda: self.popout_window.toggle_pin() if self.popout_window else None)

            act_dock = menu.addAction("↙ Dock Back to Hub")
            act_dock.triggered.connect(self.dock_back)
            menu.addSeparator()

        act_snap = menu.addAction("📸 Take Snapshot")
        act_snap.triggered.connect(self._take_snapshot)

        menu.exec(pos)

    def pop_out(self):
        """Detaches the ZeroCast streaming viewport into an independent floating window."""
        if self.is_popped_out or not self._content_widget:
            return
        self.is_popped_out = True
        if not self.popout_window:
            self.popout_window = ZeroCastPopoutWindow(self)

        self._set_compact_mode(True)
        if self.btn_popout:
            self.btn_popout.setText("↙ Dock")
            self.btn_popout.setToolTip("Dock ZeroCast back into the main Hub window")

        self._content_widget.setParent(None)
        self.popout_window.setCentralWidget(self._content_widget)
        self._content_widget.show()
        self.canvas.show()
        self.canvas.update()

        self.popout_window.show()
        self.popout_window.raise_()
        self.popout_window.activateWindow()

        if self._stacked_container:
            self._stacked_container.setCurrentIndex(1)
        if self.log_label:
            self.log_label.setText("ZeroCast floating in standalone window")

    def _force_dock_relayout(self):
        """Forces the content widget and layout to completely fill the dock container."""
        if not self.is_popped_out and self._dock_container and self._content_widget:
            target_rect = self._dock_container.rect()
            if target_rect.isValid() and not target_rect.isEmpty():
                self._content_widget.setGeometry(target_rect)
            if self._dock_layout:
                self._dock_layout.invalidate()
                self._dock_layout.activate()
            if self.canvas:
                self.canvas.update()

    def dock_back(self):
        """Re-attaches the ZeroCast streaming viewport back into the main Hub."""
        if not self.is_popped_out or not self._content_widget:
            return
        self.is_popped_out = False
        if self.is_screen_only:
            self.set_screen_only(False)

        if self.popout_window:
            self.popout_window.takeCentralWidget()
            self.popout_window.hide()

        self._set_compact_mode(False)
        if self.btn_popout:
            self.btn_popout.setText("↗ Pop-out")
            self.btn_popout.setToolTip("Detach ZeroCast into an independent floating window")

        # Switch to dock page first so dock_container is visible
        if self._stacked_container:
            self._stacked_container.setCurrentIndex(0)

        # Re-attach content widget into dock layout
        self._content_widget.setParent(self._dock_container)
        if self._dock_layout:
            self._dock_layout.addWidget(self._content_widget)

        # Force immediate relayout to match container size
        self._force_dock_relayout()
        QTimer.singleShot(0, self._force_dock_relayout)

        self._content_widget.show()
        self.canvas.show()
        self.canvas.update()

        # Bring main Hub window to front
        main_win = self._widget.window() if self._widget else None
        if main_win and main_win != self.popout_window:
            main_win.raise_()
            main_win.activateWindow()

        if self.log_label:
            self.log_label.setText("ZeroCast docked back to Hub")

    def _toggle_popout(self):
        if self.is_popped_out:
            self.dock_back()
        else:
            self.pop_out()
