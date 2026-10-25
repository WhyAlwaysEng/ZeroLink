"""ZeroLink Hub - Dashboard View (Unified Connection & Ecosystem Control)
Clean, minimalist command center integrating the active Master Gateway connection panel
with instant 1-click access to all permanently listening ecosystem modules.
"""

import time
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QGraphicsDropShadowEffect, QApplication
)
from core.module_manager import ModuleManager
from core.adb_helper import AdbManager


class ModuleCard(QFrame):
    """Crisp white minimal card with real-time port state and instant viewport launcher."""
    open_clicked = pyqtSignal(str)          # module_id

    def __init__(self, module_id: str, title: str, glyph: str, desc: str,
                 port_info: str = "", is_available: bool = True, parent=None):
        super().__init__(parent)
        self.module_id = module_id
        self.port_info = port_info
        self.is_available = is_available
        self.is_streaming = False

        self.setObjectName("moduleCard")
        self.setStyleSheet("""
            QFrame#moduleCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
            QFrame#moduleCard:hover {
                border-color: #9CA3AF;
                background-color: #FAFAFA;
            }
        """)

        # Soft ambient shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 8))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Header: Glyph + Title + Status Pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel(glyph)
        icon_lbl.setFont(QFont("Segoe UI Symbol", 20))
        icon_lbl.setStyleSheet("color: #111827;")
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827; letter-spacing: -0.2px;")
        title_col.addWidget(title_lbl)

        if port_info:
            port_lbl = QLabel(port_info)
            port_lbl.setFont(QFont("Consolas", 10))
            port_lbl.setStyleSheet("color: #6B7280;")
            title_col.addWidget(port_lbl)

        header_row.addLayout(title_col)
        header_row.addStretch()

        self.status_pill = QLabel("● READY")
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.status_pill.setStyleSheet("""
            background-color: #F0FDF4;
            color: #15803D;
            padding: 3px 8px;
            border: 1px solid #BBF7D0;
            border-radius: 4px;
            letter-spacing: 0.5px;
        """)
        header_row.addWidget(self.status_pill)

        layout.addLayout(header_row)

        # Description
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont("Segoe UI", 10))
        desc_lbl.setStyleSheet("color: #4B5563; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        layout.addStretch()

        # Action: Direct Viewport Switcher
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)

        if is_available:
            self.open_btn = QPushButton("Open Viewport →")
            self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.open_btn.setStyleSheet("""
                QPushButton {
                    background-color: #111827;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #374151;
                }
            """)
            self.open_btn.clicked.connect(lambda: self.open_clicked.emit(self.module_id))
            footer_row.addWidget(self.open_btn)
        else:
            coming_lbl = QLabel("In Development")
            coming_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: 600;")
            footer_row.addWidget(coming_lbl)

        layout.addLayout(footer_row)

    def set_streaming(self, is_streaming: bool):
        self.is_streaming = is_streaming
        if is_streaming:
            self.status_pill.setText("⚡ LIVE STREAMING")
            self.status_pill.setStyleSheet("""
                background-color: #FEF2F2;
                color: #B91C1C;
                padding: 3px 8px;
                border: 1px solid #FECACA;
                border-radius: 4px;
                letter-spacing: 0.5px;
            """)
        else:
            self.status_pill.setText("● READY")
            self.status_pill.setStyleSheet("""
                background-color: #F0FDF4;
                color: #15803D;
                padding: 3px 8px;
                border: 1px solid #BBF7D0;
                border-radius: 4px;
                letter-spacing: 0.5px;
            """)


class ConnectionHeroCard(QFrame):
    """Central Gateway Control Panel displayed on the Dashboard."""

    def __init__(self, local_ip: str, parent=None):
        super().__init__(parent)
        self.local_ip = local_ip
        self.adb_manager = AdbManager()

        self.setObjectName("connectionHeroCard")
        self.setStyleSheet("""
            QFrame#connectionHeroCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 14px;
            }
        """)

        # Ambient card shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 10))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        # Header Row: Title & Master Status Pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel("⌁")
        icon_lbl.setFont(QFont("Segoe UI Symbol", 22, QFont.Weight.Bold))
        icon_lbl.setStyleSheet("color: #111827;")
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_lbl = QLabel("Unified Connection Gateway")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827;")
        title_col.addWidget(title_lbl)

        self.subtitle_lbl = QLabel("All 10 Ecosystem Services Active & Listening • Zero Delay Handover")
        self.subtitle_lbl.setFont(QFont("Segoe UI", 10))
        self.subtitle_lbl.setStyleSheet("color: #6B7280;")
        title_col.addWidget(self.subtitle_lbl)

        header_row.addLayout(title_col)
        header_row.addStretch()

        self.status_badge = QLabel("● WAITING FOR MOBILE")
        self.status_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_badge.setStyleSheet("""
            background-color: #F3F4F6;
            color: #374151;
            padding: 5px 12px;
            border: 1px solid #D1D5DB;
            border-radius: 6px;
            letter-spacing: 0.5px;
        """)
        header_row.addWidget(self.status_badge)
        layout.addLayout(header_row)

        # Metrics & Connection Badges Row
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(14)

        # Badge 1: Device
        self.box_device = self._create_metric_box("CONNECTED DEVICE", "No Device Linked", "📱")
        metrics_row.addWidget(self.box_device)

        # Badge 2: Link Mode
        self.box_mode = self._create_metric_box("ACTIVE LINK MODE", "Standby (USB / Wi-Fi)", "⚡")
        metrics_row.addWidget(self.box_mode)

        # Badge 3: Gateway IP & Port
        self.box_ip = self._create_metric_box("GATEWAY ENDPOINT", f"{self.local_ip} : 8886", "🌐")
        metrics_row.addWidget(self.box_ip)

        layout.addLayout(metrics_row)

        # Quick Actions Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self.btn_copy_ip = QPushButton("📋 Copy LAN IP")
        self.btn_copy_ip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_ip.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #E5E7EB; }
        """)
        self.btn_copy_ip.clicked.connect(self._copy_ip)
        actions_row.addWidget(self.btn_copy_ip)

        self.btn_reverse_adb = QPushButton("🔄 Re-Reverse ADB Ports (10/10)")
        self.btn_reverse_adb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reverse_adb.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #E5E7EB; }
        """)
        self.btn_reverse_adb.clicked.connect(self._reverse_adb_ports)
        actions_row.addWidget(self.btn_reverse_adb)

        self.lbl_action_hint = QLabel("")
        self.lbl_action_hint.setFont(QFont("Segoe UI", 10))
        self.lbl_action_hint.setStyleSheet("color: #15803D; font-weight: bold;")
        actions_row.addWidget(self.lbl_action_hint)

        actions_row.addStretch()
        layout.addLayout(actions_row)

    def _create_metric_box(self, label: str, value: str, icon: str) -> QFrame:
        box = QFrame()
        box.setStyleSheet("background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px 14px;")
        l = QVBoxLayout(box)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)

        top_l = QHBoxLayout()
        top_l.setSpacing(6)
        ic = QLabel(icon)
        ic.setFont(QFont("Segoe UI Symbol", 10))
        top_l.addWidget(ic)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #6B7280; letter-spacing: 0.5px;")
        top_l.addWidget(lbl)
        top_l.addStretch()
        l.addLayout(top_l)

        val_lbl = QLabel(value)
        val_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        val_lbl.setStyleSheet("color: #111827;")
        val_lbl.setObjectName("val_lbl")
        l.addWidget(val_lbl)
        return box

    def _copy_ip(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self.local_ip)
            self.lbl_action_hint.setText(f"Copied {self.local_ip} to clipboard!")

    def _reverse_adb_ports(self):
        if self.adb_manager.is_available():
            ok = self.adb_manager.reverse_ecosystem_ports()
            if ok:
                self.lbl_action_hint.setText("All 10 ports mapped over USB ADB (127.0.0.1)")
            else:
                self.lbl_action_hint.setText("ADB ready (Connect phone via USB cable)")
        else:
            self.lbl_action_hint.setText("ADB not found on PC PATH")

    def update_client_state(self, info: dict):
        client_ip = info.get("client_ip", "")
        model = info.get("model", "Android Device")
        mode = info.get("mode", "Wi-Fi LAN")
        status = info.get("status", "CONNECTED")

        if status == "CONNECTED":
            self.status_badge.setText(f"● LINKED ({mode.upper()})")
            self.status_badge.setStyleSheet("""
                background-color: #F0FDF4;
                color: #15803D;
                padding: 5px 12px;
                border: 1px solid #BBF7D0;
                border-radius: 6px;
                letter-spacing: 0.5px;
            """)
            self.box_device.findChild(QLabel, "val_lbl").setText(f"{model} ({client_ip})")
            self.box_mode.findChild(QLabel, "val_lbl").setText(mode)
            self.subtitle_lbl.setText(f"Active Session: Linked with {model} • Ready for ZeroCast, ZeroCam & ZeroDisplay")
        else:
            self.status_badge.setText("● WAITING FOR MOBILE")
            self.status_badge.setStyleSheet("""
                background-color: #F3F4F6;
                color: #374151;
                padding: 5px 12px;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                letter-spacing: 0.5px;
            """)
            self.box_device.findChild(QLabel, "val_lbl").setText("No Device Linked")
            self.box_mode.findChild(QLabel, "val_lbl").setText("Standby (USB / Wi-Fi)")
            self.subtitle_lbl.setText("All 10 Ecosystem Services Active & Listening • Zero Delay Handover")


class DashboardView(QWidget):
    """ZeroLink Central Command Dashboard (Always-Live Modules Edition)."""
    navigate_to_module = pyqtSignal(str)

    def __init__(self, module_manager: ModuleManager, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.module_manager = module_manager
        self.local_ip = local_ip
        self.cards = {}
        self.hero_card: ConnectionHeroCard = None

        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #F9FAFB; }")

        container = QWidget()
        container.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 30, 36, 36)
        layout.setSpacing(24)

        # 1. Master Connection Hero Card
        self.hero_card = ConnectionHeroCard(local_ip=self.local_ip, parent=self)
        layout.addWidget(self.hero_card)

        # Section Divider & Label
        sec_lbl = QLabel("ALL ECOSYSTEM SERVICES (PERMANENTLY ACTIVE)")
        sec_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sec_lbl.setStyleSheet("color: #9CA3AF; letter-spacing: 1.2px; margin-top: 4px;")
        layout.addWidget(sec_lbl)

        # 2. Modules Grid
        grid = QGridLayout()
        grid.setSpacing(16)

        modules_data = [
            ("zerocast", "ZeroCast", "⊡", "GPU H.264 screen & internal audio mirroring with reverse touch & keyboard control.", "Port 8888 (TCP)"),
            ("zerocam", "ZeroCam", "◎", "Wireless HD/4K mobile camera into Virtual Webcam for Discord, OBS, Zoom, and Teams.", "Port 8893 (TCP)"),
            ("zerodisplay", "ZeroDisplay", "▣", "Wireless 2nd Monitor & Remote Touch. Turn your phone into an extended desktop.", "Port 8892 (TCP)"),
            ("zeromix", "ZeroMix", "⧉", "Virtual Audio Mixer & Soundboard. Mix mic with music, auto-ducking, and sound triggers.", "Port 8891 (TCP)"),
            ("zerodrop", "ZeroDrop", "⇄", "High-speed bidirectional LAN & USB file sharing between Windows PC and Android.", "Port 8890 (TCP)"),
            ("zeroclip", "ZeroClip", "⎘", "Instant bidirectional shared clipboard between PC and Android in real-time.", "Port 8889 (TCP)"),
            ("zeropad", "ZeroPad", "▦", "Wireless PC Media & Macro Remote Controller / Stream Deck for Windows audio and shortcuts.", "Port 8894 (TCP)"),
            ("zeroexplorer", "ZeroExplorer", "▤", "Wireless Android file manager, gallery previewer, 4K video streamer, and APK installer.", "Port 8896 (HTTP)"),
            ("zerodev", "ZeroDev Console", "</>", "Developer workshop, cross-platform code scaffolder, and real-time network port probe.", "Port 8897 (Probe)")
        ]

        row = 0
        col = 0
        for mod_id, title, glyph, desc, port_str in modules_data:
            card = ModuleCard(
                module_id=mod_id,
                title=title,
                glyph=glyph,
                desc=desc,
                port_info=port_str,
                is_available=True,
                parent=self
            )
            card.open_clicked.connect(self.navigate_to_module.emit)
            self.cards[mod_id] = card
            grid.addWidget(card, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        layout.addLayout(grid)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def update_client_connection(self, info: dict):
        if self.hero_card:
            self.hero_card.update_client_state(info)

    def set_module_streaming(self, module_id: str, is_streaming: bool):
        if module_id in self.cards:
            self.cards[module_id].set_streaming(is_streaming)
