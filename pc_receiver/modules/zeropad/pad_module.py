"""ZeroLink Hub - ZeroPad Module
Wireless PC Media & Macro Remote Controller (Stream Deck for Mobile).
"""

import time
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QScrollArea, QGridLayout
)

from core.base_module import BaseModule
from core.pad_server import PadServer
from core.adb_helper import AdbManager
from modules.zeropad.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


class ZeroPadModule(BaseModule):
    """ZeroPad Module: Remote Control & Macro Hub for Mobile."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self.adb_manager = AdbManager()
        self.server = PadServer(port=self.port, parent=self)

        self._widget: Optional[QWidget] = None
        self._is_active = False

        # UI elements
        self.status_pill: Optional[QLabel] = None
        self.client_pill: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None
        self.log_box: Optional[QTextEdit] = None

        # Wire server signals
        self.server.command_executed.connect(self._on_command_executed)
        self.server.client_connected.connect(self._on_client_connected)
        self.server.client_disconnected.connect(self._on_client_disconnected)

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
        if self._is_active:
            return True
        ok = self.server.start()
        if ok:
            self._is_active = True
            if self.adb_manager.is_available():
                self.adb_manager.reverse_port(self.port)
            if self.status_pill:
                self.status_pill.setText("● REMOTE PAD ACTIVE")
                self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("Disable Pad Server")
            self.status_changed.emit(self.module_id, "ZeroPad server running")
            return True
        return False

    def stop_service(self) -> bool:
        if not self._is_active:
            return True
        self.server.stop()
        self._is_active = False
        if self.status_pill:
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("color: #6B7280; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        if self.btn_power:
            self.btn_power.setText("Enable Pad Server")
        self.status_changed.emit(self.module_id, "ZeroPad server stopped")
        return True

    def get_widget(self) -> QWidget:
        if not self._widget:
            self._setup_ui()
        return self._widget

    def _setup_ui(self):
        container = QWidget()
        container.setStyleSheet("background-color: #F9FAFB;")
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top Bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #FFFFFF; border-bottom: 1px solid #E5E7EB;")
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(18, 10, 18, 10)
        bar_layout.setSpacing(10)

        self.btn_power = QPushButton("⏻ Disable Server" if self.is_active else "⏻ Enable Server")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● REMOTE PAD ACTIVE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("⌖ Mobile: Offline")
        self.client_pill.setStyleSheet("color: #4B5563; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        bar_layout.addStretch()

        port_info = QLabel(f"Port: {self.port} • IP: {self.local_ip}")
        port_info.setStyleSheet("color: #4B5563; font-size: 11px;")
        bar_layout.addWidget(port_info)
        root_layout.addWidget(top_bar)

        # Scrollable Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(28, 20, 28, 24)
        content_layout.setSpacing(20)

        # Left Column: Features & Quick PC Test
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # Card 1: Supported Actions
        desc_card = QFrame()
        desc_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        d_layout = QVBoxLayout(desc_card)
        d_layout.setSpacing(10)

        d_title = QLabel("⌖ Mobile Stream Deck & Macro Controller")
        d_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        d_title.setStyleSheet("color: #111827;")
        d_layout.addWidget(d_title)

        d_desc = QLabel("Turn your Android phone into a tactile wireless macro pad. Control Windows volume, music tracks, mute Discord microphone, take screenshots, or launch PC apps with a single tap.")
        d_desc.setFont(QFont("Segoe UI", 10))
        d_desc.setStyleSheet("color: #6B7280;")
        d_desc.setWordWrap(True)
        d_layout.addWidget(d_desc)
        left_col.addWidget(desc_card)

        # Card 2: Quick Test Grid
        test_card = QFrame()
        test_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        t_layout = QVBoxLayout(test_card)
        t_layout.setSpacing(10)

        t_title = QLabel("◈ Quick Action Tester (Test from PC)")
        t_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        t_title.setStyleSheet("color: #111827;")
        t_layout.addWidget(t_title)

        grid = QGridLayout()
        grid.setSpacing(8)

        btn_play = QPushButton("▷ Play / Pause")
        btn_play.clicked.connect(lambda: self.server._handle_command('{"action":"MEDIA_KEY","key":"PLAY_PAUSE"}', "Local"))
        grid.addWidget(btn_play, 0, 0)

        btn_mute = QPushButton("◖ Mute Audio")
        btn_mute.clicked.connect(lambda: self.server._handle_command('{"action":"MEDIA_KEY","key":"MUTE"}', "Local"))
        grid.addWidget(btn_mute, 0, 1)

        btn_vol_up = QPushButton("◗ Vol +")
        btn_vol_up.clicked.connect(lambda: self.server._handle_command('{"action":"MEDIA_KEY","key":"VOL_UP"}', "Local"))
        grid.addWidget(btn_vol_up, 1, 0)

        btn_vol_down = QPushButton("◗ Vol -")
        btn_vol_down.clicked.connect(lambda: self.server._handle_command('{"action":"MEDIA_KEY","key":"VOL_DOWN"}', "Local"))
        grid.addWidget(btn_vol_down, 1, 1)

        btn_shot = QPushButton("⧇ Screenshot (Win+Shift+S)")
        btn_shot.clicked.connect(lambda: self.server._handle_command('{"action":"MACRO","name":"SCREENSHOT"}', "Local"))
        grid.addWidget(btn_shot, 2, 0)

        btn_desk = QPushButton("▣ Show Desktop (Win+D)")
        btn_desk.clicked.connect(lambda: self.server._handle_command('{"action":"MACRO","name":"SHOW_DESKTOP"}', "Local"))
        grid.addWidget(btn_desk, 2, 1)

        t_layout.addLayout(grid)
        left_col.addWidget(test_card)

        content_layout.addLayout(left_col, 3)

        # Right Column: Live Event Log & USB Tunnel
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Log Card
        log_card = QFrame()
        log_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        l_layout = QVBoxLayout(log_card)
        l_layout.setSpacing(10)

        l_title = QLabel("◈ Live Macro & Event Log")
        l_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        l_title.setStyleSheet("color: #111827;")
        l_layout.addWidget(l_title)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("""
            QTextEdit {
                background-color: #111827;
                color: #A7F3D0;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        self.log_box.append("[ZeroPad] Server listening for mobile inputs...")
        l_layout.addWidget(self.log_box)

        btn_clear_log = QPushButton("Clear Log")
        btn_clear_log.setStyleSheet("padding: 4px 8px; font-size: 10px;")
        btn_clear_log.clicked.connect(lambda: self.log_box.clear())
        l_layout.addWidget(btn_clear_log)
        right_col.addWidget(log_card)

        # USB Tunnel Card
        usb_card = QFrame()
        usb_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        u_layout = QVBoxLayout(usb_card)
        u_layout.setSpacing(8)

        u_title = QLabel("⌁ USB Cable Zero-Lag Link")
        u_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        u_title.setStyleSheet("color: #111827;")
        u_layout.addWidget(u_title)

        btn_usb = QPushButton("⌁ Activate USB Cable Tunnel (Port 8894)")
        btn_usb.setStyleSheet("""
            QPushButton {
                background-color: #111827; color: #FFFFFF; border-radius: 6px;
                padding: 7px 14px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #374151; }
        """)
        lbl_usb_msg = QLabel("Forward port 8894 for 0ms physical wire connection.")
        lbl_usb_msg.setStyleSheet("color: #6B7280; font-size: 10px;")

        def _forward_usb():
            ok, msg = self.adb_manager.reverse_port(self.port)
            if ok:
                lbl_usb_msg.setText("USB Tunnel Active! On phone, connect to 127.0.0.1.")
                lbl_usb_msg.setStyleSheet("color: #111827; font-size: 10px; font-weight: bold;")
            else:
                lbl_usb_msg.setText(f"{msg}")
                lbl_usb_msg.setStyleSheet("color: #DC2626; font-size: 10px;")

        btn_usb.clicked.connect(_forward_usb)
        u_layout.addWidget(btn_usb)
        u_layout.addWidget(lbl_usb_msg)
        right_col.addWidget(usb_card)

        content_layout.addLayout(right_col, 2)
        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll, 1)

        self._widget = container

    def _toggle_power(self):
        if self._is_active:
            self.stop_service()
        else:
            self.start_service()

    def _on_command_executed(self, action: str, details: str):
        t_str = time.strftime("%H:%M:%S")
        if self.log_box:
            self.log_box.append(f"[{t_str}] {action}: {details}")

    def _on_client_connected(self, ip: str, model: str):
        if self.client_pill:
            self.client_pill.setText(f"📱 {model} ({ip})")
            self.client_pill.setStyleSheet("color: #059669; background: #ECFDF5; border: 1px solid #A7F3D0; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;")
        if self.log_box:
            self.log_box.append(f"[{time.strftime('%H:%M:%S')}] 🟢 Controller connected: {model} ({ip})")

    def _on_client_disconnected(self, ip: str):
        if self.client_pill:
            self.client_pill.setText("📱 Mobile: Offline")
            self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        if self.log_box:
            self.log_box.append(f"[{time.strftime('%H:%M:%S')}] 🔴 Controller disconnected: {ip}")
