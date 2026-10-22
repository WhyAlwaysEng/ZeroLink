"""ZeroLink Hub - Active Connections & Device Bridge View
Displays all live client connections across ZeroCast, ZeroMix, ZeroClip, and ZeroDrop modules.
Allows independent inspection and individual disconnection.
"""

import time
from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QMessageBox
)

from modules.zerocast.cast_module import ZeroCastModule
from modules.zerodrop.drop_module import ZeroDropModule
from modules.zeroclip.clip_module import ZeroClipModule
from modules.zeromix.mix_module import ZeroMixModule


class ClientRowWidget(QFrame):
    """Card representing an active client device connected to a specific module."""

    def __init__(self, client_info: Dict, on_disconnect_callback, parent=None):
        super().__init__(parent)
        self.client_info = client_info
        self.connected_at = client_info.get("connected_at", time.time())
        self.on_disconnect_callback = on_disconnect_callback

        self.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 10px 14px;
            }
            QFrame:hover {
                background-color: #F3F4F6;
                border-color: #D1D5DB;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Device Icon
        icon_lbl = QLabel("📱")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 16))
        layout.addWidget(icon_lbl)

        # Device Info
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        model_name = client_info.get("model", "Android Device")
        lbl_name = QLabel(model_name)
        lbl_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_name.setStyleSheet("color: #111827;")
        name_row.addWidget(lbl_name)

        ip = client_info.get("ip", "127.0.0.1")
        is_usb = ip in ("127.0.0.1", "localhost")
        tunnel_badge = QLabel("⚡ USB ADB" if is_usb else "📶 Wi-Fi LAN")
        tunnel_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        if is_usb:
            tunnel_badge.setStyleSheet("""
                background-color: #111827; color: #FFFFFF;
                padding: 2px 6px; border-radius: 4px;
            """)
        else:
            tunnel_badge.setStyleSheet("""
                background-color: #E0E7FF; color: #3730A3;
                padding: 2px 6px; border-radius: 4px;
            """)
        name_row.addWidget(tunnel_badge)
        name_row.addStretch()
        info_col.addLayout(name_row)

        details_row = QHBoxLayout()
        details_row.setSpacing(12)

        addr = client_info.get("addr", f"{ip}:{client_info.get('port', 0)}")
        lbl_addr = QLabel(f"Addr: {addr}")
        lbl_addr.setStyleSheet("color: #6B7280; font-size: 11px;")
        details_row.addWidget(lbl_addr)

        mode = client_info.get("mode") or client_info.get("codec") or "Active"
        lbl_mode = QLabel(f"Mode: {mode}")
        lbl_mode.setStyleSheet("color: #4B5563; font-size: 11px; font-weight: 500;")
        details_row.addWidget(lbl_mode)

        self.lbl_duration = QLabel("Duration: 00m 00s")
        self.lbl_duration.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        details_row.addWidget(self.lbl_duration)
        details_row.addStretch()
        info_col.addLayout(details_row)

        layout.addLayout(info_col, 1)

        # Disconnect Action Button
        btn_disconnect = QPushButton("Disconnect")
        btn_disconnect.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_disconnect.setStyleSheet("""
            QPushButton {
                background-color: #FEE2E2;
                color: #B91C1C;
                border: 1px solid #FECACA;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FCA5A5;
                color: #7F1D1D;
            }
        """)
        btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        layout.addWidget(btn_disconnect)

        self.update_duration()

    def update_duration(self):
        elapsed = int(max(0, time.time() - self.connected_at))
        mins, secs = divmod(elapsed, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            self.lbl_duration.setText(f"Duration: {hours:02d}h {mins:02d}m {secs:02d}s")
        else:
            self.lbl_duration.setText(f"Duration: {mins:02d}m {secs:02d}s")

    def _on_disconnect_clicked(self):
        addr = self.client_info.get("addr")
        if self.on_disconnect_callback and addr:
            self.on_disconnect_callback(addr)


class ModuleConnectionsCard(QFrame):
    """Section card listing active connections for one specific module."""

    def __init__(self, title: str, glyph: str, port: int, is_active: bool,
                 clients: List[Dict], on_disconnect_callback, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            ModuleConnectionsCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
                padding: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Card Header
        header = QHBoxLayout()
        header.setSpacing(10)

        glyph_lbl = QLabel(glyph)
        glyph_lbl.setFont(QFont("Segoe UI Emoji", 14))
        header.addWidget(glyph_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827;")
        header.addWidget(title_lbl)

        port_badge = QLabel(f"Port {port}")
        port_badge.setStyleSheet("color: #6B7280; font-size: 11px; background-color: #F3F4F6; padding: 2px 6px; border-radius: 4px;")
        header.addWidget(port_badge)

        status_dot = QLabel("● Active" if is_active else "○ Stopped")
        status_dot.setStyleSheet(f"color: {'#059669' if is_active else '#9CA3AF'}; font-size: 11px; font-weight: bold;")
        header.addWidget(status_dot)

        header.addStretch()

        count_badge = QLabel(f"{len(clients)} Connected")
        count_badge.setStyleSheet("""
            background-color: #111827; color: #FFFFFF; font-size: 11px; font-weight: bold;
            padding: 3px 8px; border-radius: 10px;
        """)
        header.addWidget(count_badge)
        layout.addLayout(header)

        # Client list
        self.rows: List[ClientRowWidget] = []
        if clients:
            clients_layout = QVBoxLayout()
            clients_layout.setSpacing(8)
            for c in clients:
                row = ClientRowWidget(c, on_disconnect_callback, self)
                self.rows.append(row)
                clients_layout.addWidget(row)
            layout.addLayout(clients_layout)
        else:
            empty_lbl = QLabel("No devices connected to this module.")
            empty_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px; font-style: italic; padding: 6px 2px;")
            layout.addWidget(empty_lbl)

    def update_durations(self):
        for r in self.rows:
            r.update_duration()


class ConnectionsView(QWidget):
    """Central Device Bridge dashboard showing all active connections."""

    def __init__(self, mod_zerocast: ZeroCastModule,
                 mod_zerodrop: ZeroDropModule,
                 mod_zeroclip: ZeroClipModule,
                 mod_zeromix: ZeroMixModule,
                 parent=None):
        super().__init__(parent)
        self.mod_zerocast = mod_zerocast
        self.mod_zerodrop = mod_zerodrop
        self.mod_zeroclip = mod_zeroclip
        self.mod_zeromix = mod_zeromix

        self.cards: List[ModuleConnectionsCard] = []

        self._init_ui()

        # Connect signals from all module services
        if hasattr(self.mod_zerocast, "server"):
            self.mod_zerocast.server.clients_updated.connect(self.refresh_devices)
        if hasattr(self.mod_zeromix, "service"):
            self.mod_zeromix.service.clients_updated.connect(self.refresh_devices)
        if hasattr(self.mod_zeroclip, "service"):
            self.mod_zeroclip.service.clients_updated.connect(self.refresh_devices)
        if hasattr(self.mod_zerodrop, "service"):
            self.mod_zerodrop.service.clients_updated.connect(self.refresh_devices)

        # 1-second timer to tick durations
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_durations)
        self.timer.start(1000)

        self.refresh_devices()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(18)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        header_col = QVBoxLayout()
        header_col.setSpacing(4)
        title = QLabel("Device Bridge & Connections")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #111827; letter-spacing: -0.3px;")
        header_col.addWidget(title)

        subtitle = QLabel("Real-time list of all connected Android phones & tablets. Inspect each module or disconnect individually.")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet("color: #6B7280;")
        header_col.addWidget(subtitle)
        header_row.addLayout(header_col, 1)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #111827; border: 1px solid #D1D5DB;
                border-radius: 6px; padding: 8px 14px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #F3F4F6; }
        """)
        btn_refresh.clicked.connect(self.refresh_devices)
        header_row.addWidget(btn_refresh)

        root_layout.addLayout(header_row)

        # Summary Bar
        self.summary_bar = QFrame()
        self.summary_bar.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 10px 16px;
            }
        """)
        summary_layout = QHBoxLayout(self.summary_bar)
        summary_layout.setSpacing(20)

        self.lbl_total_clients = QLabel("Total Connections: 0")
        self.lbl_total_clients.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_total_clients.setStyleSheet("color: #111827;")
        summary_layout.addWidget(self.lbl_total_clients)

        self.lbl_usb_clients = QLabel("⚡ USB ADB: 0")
        self.lbl_usb_clients.setStyleSheet("color: #4B5563; font-size: 11px;")
        summary_layout.addWidget(self.lbl_usb_clients)

        self.lbl_wifi_clients = QLabel("📶 Wi-Fi LAN: 0")
        self.lbl_wifi_clients.setStyleSheet("color: #4B5563; font-size: 11px;")
        summary_layout.addWidget(self.lbl_wifi_clients)

        summary_layout.addStretch()

        self.lbl_services_status = QLabel("Services: 4/4 Online")
        self.lbl_services_status.setStyleSheet("color: #059669; font-weight: bold; font-size: 11px;")
        summary_layout.addWidget(self.lbl_services_status)

        root_layout.addWidget(self.summary_bar)

        # Scrollable Cards Container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(14)
        scroll.setWidget(self.cards_container)

        root_layout.addWidget(scroll, 1)

    def refresh_devices(self):
        """Polls connected clients across all 4 modules and reconstructs cards."""
        # 1. Fetch clients
        cast_clients = self.mod_zerocast.server.get_connected_clients() if hasattr(self.mod_zerocast, "server") else []
        mix_clients = self.mod_zeromix.service.get_connected_clients() if hasattr(self.mod_zeromix, "service") else []
        clip_clients = self.mod_zeroclip.service.get_connected_clients() if hasattr(self.mod_zeroclip, "service") else []
        drop_clients = self.mod_zerodrop.service.get_connected_clients() if hasattr(self.mod_zerodrop, "service") else []

        all_clients = cast_clients + mix_clients + clip_clients + drop_clients
        total = len(all_clients)
        usb_count = sum(1 for c in all_clients if c.get("ip") in ("127.0.0.1", "localhost"))
        wifi_count = total - usb_count

        self.lbl_total_clients.setText(f"Total Connections: {total}")
        self.lbl_usb_clients.setText(f"⚡ USB ADB: {usb_count}")
        self.lbl_wifi_clients.setText(f"📶 Wi-Fi LAN: {wifi_count}")

        # Count active modules
        active_count = sum([
            1 if getattr(self.mod_zerocast, "is_active", False) else 0,
            1 if getattr(self.mod_zeromix, "is_active", False) else 0,
            1 if getattr(self.mod_zeroclip, "is_active", False) else 0,
            1 if getattr(self.mod_zerodrop, "is_active", False) else 0,
        ])
        self.lbl_services_status.setText(f"Services: {active_count}/4 Online")

        # Clear existing cards
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()

        # Add ZeroCast card
        card_cast = ModuleConnectionsCard(
            title="ZeroCast",
            glyph="📺",
            port=self.mod_zerocast.port,
            is_active=self.mod_zerocast.is_active,
            clients=cast_clients,
            on_disconnect_callback=lambda addr: self.mod_zerocast.server.disconnect_client(addr),
            parent=self.cards_container
        )
        self.cards.append(card_cast)
        self.cards_layout.addWidget(card_cast)

        # Add ZeroMix card
        card_mix = ModuleConnectionsCard(
            title="ZeroMix (Audio Mixer & Remote)",
            glyph="🎛️",
            port=self.mod_zeromix.port,
            is_active=self.mod_zeromix.is_active,
            clients=mix_clients,
            on_disconnect_callback=lambda addr: self.mod_zeromix.service.disconnect_client(addr),
            parent=self.cards_container
        )
        self.cards.append(card_mix)
        self.cards_layout.addWidget(card_mix)

        # Add ZeroClip card
        card_clip = ModuleConnectionsCard(
            title="ZeroClip (Clipboard Sync)",
            glyph="📋",
            port=self.mod_zeroclip.port,
            is_active=self.mod_zeroclip.is_active,
            clients=clip_clients,
            on_disconnect_callback=lambda addr: self.mod_zeroclip.service.disconnect_client(addr),
            parent=self.cards_container
        )
        self.cards.append(card_clip)
        self.cards_layout.addWidget(card_clip)

        # Add ZeroDrop card
        card_drop = ModuleConnectionsCard(
            title="ZeroDrop (File Drop)",
            glyph="📁",
            port=self.mod_zerodrop.port,
            is_active=self.mod_zerodrop.is_active,
            clients=drop_clients,
            on_disconnect_callback=lambda addr: self.mod_zerodrop.service.disconnect_client(addr),
            parent=self.cards_container
        )
        self.cards.append(card_drop)
        self.cards_layout.addWidget(card_drop)

        self.cards_layout.addStretch()

    def _tick_durations(self):
        for c in self.cards:
            c.update_durations()
