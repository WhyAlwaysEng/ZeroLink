"""ZeroLink Hub - Active Connections & Device Bridge View
Displays all live client connections across ZeroCast, ZeroMix, ZeroClip, and ZeroDrop modules.
Provides both a Per-Device Topology overview (e.g. Phone 1 on ZeroCast, Phone 2 on ZeroMix)
and per-module breakdown with individual disconnection controls.
"""

import time
from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea
)

from modules.zerocast.cast_module import ZeroCastModule
from modules.zerodrop.drop_module import ZeroDropModule
from modules.zeroclip.clip_module import ZeroClipModule
from modules.zeromix.mix_module import ZeroMixModule


class DeviceSummaryCard(QFrame):
    """Card representing a physical client device and all modules it is linked to."""

    def __init__(self, device_data: Dict, on_disconnect_all_callback, parent=None):
        super().__init__(parent)
        self.device_data = device_data
        self.on_disconnect_all = on_disconnect_all_callback

        self.setStyleSheet("""
            DeviceSummaryCard {
                background-color: #FFFFFF;
                border: 1px solid #D1D5DB;
                border-radius: 12px;
                padding: 14px 18px;
            }
            DeviceSummaryCard:hover {
                border-color: #9CA3AF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Top row: Device identification & Disconnect All button
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        icon_lbl = QLabel("◈")
        icon_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        icon_lbl.setStyleSheet("color: #111827;")
        top_row.addWidget(icon_lbl)

        model_name = device_data.get("model", "Android Device")
        lbl_name = QLabel(model_name)
        lbl_name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_name.setStyleSheet("color: #111827;")
        top_row.addWidget(lbl_name)

        ip = device_data.get("ip", "127.0.0.1")
        is_usb = ip in ("127.0.0.1", "localhost")
        tunnel_badge = QLabel("⌁ USB ADB" if is_usb else "◫ Wi-Fi LAN")
        tunnel_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        if is_usb:
            tunnel_badge.setStyleSheet("""
                background-color: #111827; color: #FFFFFF;
                padding: 3px 8px; border-radius: 4px;
            """)
        else:
            tunnel_badge.setStyleSheet("""
                background-color: #F3F4F6; color: #111827;
                border: 1px solid #D1D5DB;
                padding: 3px 8px; border-radius: 4px;
            """)
        top_row.addWidget(tunnel_badge)

        lbl_ip = QLabel(f"IP: {ip}")
        lbl_ip.setStyleSheet("color: #6B7280; font-size: 11px;")
        top_row.addWidget(lbl_ip)

        top_row.addStretch()

        btn_disconnect_all = QPushButton("Disconnect Device")
        btn_disconnect_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_disconnect_all.setStyleSheet("""
            QPushButton {
                background-color: #FEE2E2;
                color: #B91C1C;
                border: 1px solid #FECACA;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FCA5A5;
                color: #7F1D1D;
            }
        """)
        btn_disconnect_all.clicked.connect(lambda: self.on_disconnect_all(ip))
        top_row.addWidget(btn_disconnect_all)
        layout.addLayout(top_row)

        # Bottom row: Active module badges with live stats
        mod_row = QHBoxLayout()
        mod_row.setSpacing(8)

        lbl_connected_to = QLabel("Connected to:")
        lbl_connected_to.setStyleSheet("color: #6B7280; font-size: 11px; font-weight: 600;")
        mod_row.addWidget(lbl_connected_to)

        modules = device_data.get("modules", [])
        for mod in modules:
            m_badge = QLabel(f"{mod.get('glyph', '◈')} {mod.get('name', 'Module')}{(' (' + mod.get('extra', '') + ')') if mod.get('extra') else ''}")
            m_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            m_badge.setStyleSheet("""
                background-color: #F3F4F6;
                color: #1F2937;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 3px 8px;
            """)
            mod_row.addWidget(m_badge)

        mod_row.addStretch()
        layout.addLayout(mod_row)


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
        icon_lbl = QLabel("◈")
        icon_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        icon_lbl.setStyleSheet("color: #111827;")
        layout.addWidget(icon_lbl)

        # Device Info
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        model_name = client_info.get("model", "Android Device")
        lbl_name = QLabel(model_name)
        lbl_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_name.setStyleSheet("color: #111827;")
        name_row.addWidget(lbl_name)

        ip = client_info.get("ip", "127.0.0.1")
        is_usb = ip in ("127.0.0.1", "localhost")
        tunnel_badge = QLabel("⌁ USB ADB" if is_usb else "◫ Wi-Fi LAN")
        tunnel_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        if is_usb:
            tunnel_badge.setStyleSheet("""
                background-color: #111827; color: #FFFFFF;
                padding: 2px 6px; border-radius: 4px;
            """)
        else:
            tunnel_badge.setStyleSheet("""
                background-color: #F3F4F6; color: #111827;
                border: 1px solid #D1D5DB;
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

        # Streaming Stats if present (e.g. ZeroCast)
        if "latency" in client_info:
            lbl_lat = QLabel(f"⌁ {client_info['latency']}")
            lbl_lat.setStyleSheet("color: #111827; font-size: 11px; font-weight: 600;")
            details_row.addWidget(lbl_lat)

        if "bitrate" in client_info:
            lbl_br = QLabel(f"◈ {client_info['bitrate']}")
            lbl_br.setStyleSheet("color: #4B5563; font-size: 11px; font-weight: 600;")
            details_row.addWidget(lbl_br)

        if "fps" in client_info:
            lbl_fps = QLabel(f"▣ {client_info['fps']}")
            lbl_fps.setStyleSheet("color: #111827; font-size: 11px; font-weight: 600;")
            details_row.addWidget(lbl_fps)

        self.lbl_duration = QLabel("Duration: 00m 00s")
        self.lbl_duration.setStyleSheet("color: #111827; font-size: 11px; font-weight: bold;")
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
                 mod_zerodisplay=None,
                 mod_zerocam=None,
                 mod_zeropad=None,
                 mod_zeroexplorer=None,
                 parent=None):
        super().__init__(parent)
        self.mod_zerocast = mod_zerocast
        self.mod_zerodrop = mod_zerodrop
        self.mod_zeroclip = mod_zeroclip
        self.mod_zeromix = mod_zeromix
        self.mod_zerodisplay = mod_zerodisplay
        self.mod_zerocam = mod_zerocam
        self.mod_zeropad = mod_zeropad
        self.mod_zeroexplorer = mod_zeroexplorer

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
        if self.mod_zerodisplay and hasattr(self.mod_zerodisplay, "server"):
            self.mod_zerodisplay.server.clients_updated.connect(self.refresh_devices)
        if self.mod_zerocam and hasattr(self.mod_zerocam, "server"):
            self.mod_zerocam.server.clients_updated.connect(self.refresh_devices)
        if self.mod_zeropad and hasattr(self.mod_zeropad, "server"):
            self.mod_zeropad.server.clients_updated.connect(self.refresh_devices)

        # Auto-refresh timer for durations & live stats
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
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

        btn_refresh = QPushButton("↻ Refresh")
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

        self.btn_autostart = QPushButton()
        self.btn_autostart.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_autostart_ui()
        self.btn_autostart.clicked.connect(self._toggle_autostart)
        header_row.addWidget(self.btn_autostart)

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

        self.lbl_usb_clients = QLabel("⌁ USB ADB: 0")
        self.lbl_usb_clients.setStyleSheet("color: #4B5563; font-size: 11px;")
        summary_layout.addWidget(self.lbl_usb_clients)

        self.lbl_wifi_clients = QLabel("◫ Wi-Fi LAN: 0")
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
        self.cards_layout.setSpacing(16)
        scroll.setWidget(self.cards_container)

        root_layout.addWidget(scroll, 1)

    def _update_autostart_ui(self):
        from ui.main_window import is_windows_autostart_enabled
        enabled = is_windows_autostart_enabled()
        if enabled:
            self.btn_autostart.setText("🚀 Windows Boot: ON")
            self.btn_autostart.setStyleSheet("""
                QPushButton {
                    background-color: #111827; color: #FFFFFF; border: 1px solid #111827;
                    border-radius: 6px; padding: 8px 14px; font-weight: bold; font-size: 11px;
                }
                QPushButton:hover { background-color: #374151; }
            """)
        else:
            self.btn_autostart.setText("🚀 Windows Boot: OFF")
            self.btn_autostart.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF; color: #6B7280; border: 1px solid #D1D5DB;
                    border-radius: 6px; padding: 8px 14px; font-weight: bold; font-size: 11px;
                }
                QPushButton:hover { background-color: #F3F4F6; color: #111827; }
            """)

    def _toggle_autostart(self):
        from ui.main_window import is_windows_autostart_enabled, set_windows_autostart
        new_state = not is_windows_autostart_enabled()
        set_windows_autostart(new_state)
        self._update_autostart_ui()

    def disconnect_device_all(self, ip: str):
        """Disconnects a physical device across all running services."""
        if hasattr(self.mod_zerocast, "server"):
            self.mod_zerocast.server.disconnect_client(ip)
        if hasattr(self.mod_zeromix, "service"):
            self.mod_zeromix.service.disconnect_client(ip)
        if hasattr(self.mod_zeroclip, "service"):
            self.mod_zeroclip.service.disconnect_client(ip)
        if hasattr(self.mod_zerodrop, "service"):
            self.mod_zerodrop.service.disconnect_client(ip)
        if self.mod_zerodisplay and hasattr(self.mod_zerodisplay, "server"):
            self.mod_zerodisplay.server.disconnect_client(ip)
        if self.mod_zerocam and hasattr(self.mod_zerocam, "server"):
            self.mod_zerocam.server.disconnect_client(ip)
        self.refresh_devices()

    def refresh_devices(self):
        """Polls connected clients across all modules and reconstructs cards."""
        # 1. Fetch clients from all services
        cast_clients = self.mod_zerocast.server.get_connected_clients() if hasattr(self.mod_zerocast, "server") else []
        for c in cast_clients:
            c["module"] = "ZeroCast"
            c["glyph"] = "⊡"
            if hasattr(self.mod_zerocast, "stats"):
                c["fps"] = f"{self.mod_zerocast.stats.fps:.0f} FPS"
                c["latency"] = f"{self.mod_zerocast.stats.latency_ms:.0f} ms"
                c["bitrate"] = f"{self.mod_zerocast.stats.bitrate_mbps:.1f} Mbps"

        mix_clients = self.mod_zeromix.service.get_connected_clients() if hasattr(self.mod_zeromix, "service") else []
        for c in mix_clients:
            c["module"] = "ZeroMix"
            c["glyph"] = "⧉"
            c["mode"] = "Mixer & Remote"

        clip_clients = self.mod_zeroclip.service.get_connected_clients() if hasattr(self.mod_zeroclip, "service") else []
        for c in clip_clients:
            c["module"] = "ZeroClip"
            c["glyph"] = "⎘"
            c["mode"] = "Clipboard Sync"

        drop_clients = self.mod_zerodrop.service.get_connected_clients() if hasattr(self.mod_zerodrop, "service") else []
        for c in drop_clients:
            c["module"] = "ZeroDrop"
            c["glyph"] = "⇄"
            c["mode"] = "File Drop"

        display_clients = self.mod_zerodisplay.server.get_connected_clients() if (self.mod_zerodisplay and hasattr(self.mod_zerodisplay, "server")) else []
        for c in display_clients:
            c["module"] = "ZeroDisplay"
            c["glyph"] = "▣"
            if hasattr(self.mod_zerodisplay, "server"):
                c["fps"] = f"{self.mod_zerodisplay.server.fps:.0f} FPS"
                c["bitrate"] = f"{self.mod_zerodisplay.server.bitrate_mbps:.1f} Mbps"

        cam_clients = self.mod_zerocam.server.get_connected_clients() if (self.mod_zerocam and hasattr(self.mod_zerocam, "server")) else []
        for c in cam_clients:
            c["module"] = "ZeroCam"
            c["glyph"] = "◎"
            if hasattr(self.mod_zerocam, "server"):
                c["fps"] = f"{self.mod_zerocam.server.fps:.0f} FPS"
                c["bitrate"] = f"{self.mod_zerocam.server.bitrate_mbps:.1f} Mbps"

        pad_clients = self.mod_zeropad.server.get_connected_clients() if (self.mod_zeropad and hasattr(self.mod_zeropad, "server")) else []
        for c in pad_clients:
            c["module"] = "ZeroPad"
            c["glyph"] = "▦"
            c["mode"] = "Macro Remote"

        all_clients = cast_clients + mix_clients + clip_clients + drop_clients + display_clients + cam_clients + pad_clients
        total = len(all_clients)
        usb_count = sum(1 for c in all_clients if c.get("ip") in ("127.0.0.1", "localhost"))
        wifi_count = total - usb_count

        self.lbl_total_clients.setText(f"Total Connections: {total}")
        self.lbl_usb_clients.setText(f"⌁ USB ADB: {usb_count}")
        self.lbl_wifi_clients.setText(f"◫ Wi-Fi LAN: {wifi_count}")

        # Count active modules
        services_list = [self.mod_zerocast, self.mod_zeromix, self.mod_zeroclip, self.mod_zerodrop]
        if self.mod_zerodisplay:
            services_list.append(self.mod_zerodisplay)
        if self.mod_zerocam:
            services_list.append(self.mod_zerocam)
        if self.mod_zeropad:
            services_list.append(self.mod_zeropad)
        active_count = sum(1 for s in services_list if getattr(s, "is_active", False))
        self.lbl_services_status.setText(f"Services: {active_count}/{len(services_list)} Online")

        # Clear existing layout
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()

        # ==================== Section 1: Active Devices Topology ====================
        # Group by physical device (IP)
        devices_map: Dict[str, Dict] = {}
        for c in all_clients:
            ip = c.get("ip", "127.0.0.1")
            if ip not in devices_map:
                devices_map[ip] = {
                    "ip": ip,
                    "model": c.get("model", "Android Device"),
                    "modules": []
                }
            # Add module info
            extra = c.get("fps") or c.get("mode") or ""
            devices_map[ip]["modules"].append({
                "name": c.get("module", "Module"),
                "glyph": c.get("glyph", "◈"),
                "extra": extra
            })

        if devices_map:
            sec_dev_lbl = QLabel("◈ ACTIVE DEVICES OVERVIEW (PHYSICAL PHONES / TABLETS)")
            sec_dev_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            sec_dev_lbl.setStyleSheet("color: #4B5563; letter-spacing: 0.5px;")
            self.cards_layout.addWidget(sec_dev_lbl)

            for ip, d_info in devices_map.items():
                card = DeviceSummaryCard(d_info, on_disconnect_all_callback=self.disconnect_device_all, parent=self.cards_container)
                self.cards_layout.addWidget(card)

        # ==================== Section 2: Module Breakdown ====================
        sec_mod_lbl = QLabel("◈ MODULE CONNECTIONS & GRANULAR CONTROLS")
        sec_mod_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sec_mod_lbl.setStyleSheet("color: #4B5563; letter-spacing: 0.5px; margin-top: 8px;")
        self.cards_layout.addWidget(sec_mod_lbl)

        # Add ZeroCast card
        card_cast = ModuleConnectionsCard(
            title="ZeroCast",
            glyph="⊡",
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
            glyph="⧉",
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
            glyph="⎘",
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
            glyph="⇄",
            port=self.mod_zerodrop.port,
            is_active=self.mod_zerodrop.is_active,
            clients=drop_clients,
            on_disconnect_callback=lambda addr: self.mod_zerodrop.service.disconnect_client(addr),
            parent=self.cards_container
        )
        self.cards.append(card_drop)
        self.cards_layout.addWidget(card_drop)

        # Add ZeroDisplay card if available
        if self.mod_zerodisplay:
            card_display = ModuleConnectionsCard(
                title="ZeroDisplay (Extended 2nd Monitor)",
                glyph="▣",
                port=self.mod_zerodisplay.port,
                is_active=self.mod_zerodisplay.is_active,
                clients=display_clients,
                on_disconnect_callback=lambda addr: self.mod_zerodisplay.server.disconnect_client(addr),
                parent=self.cards_container
            )
            self.cards.append(card_display)
            self.cards_layout.addWidget(card_display)

        # Add ZeroCam card if available
        if self.mod_zerocam:
            card_cam = ModuleConnectionsCard(
                title="ZeroCam (Wireless Webcam)",
                glyph="◎",
                port=self.mod_zerocam.port,
                is_active=self.mod_zerocam.is_active,
                clients=cam_clients,
                on_disconnect_callback=lambda addr: self.mod_zerocam.server.disconnect_client(addr),
                parent=self.cards_container
            )
            self.cards.append(card_cam)
            self.cards_layout.addWidget(card_cam)

        # Add ZeroPad card if available
        if self.mod_zeropad:
            card_pad = ModuleConnectionsCard(
                title="ZeroPad (Media & Macro Remote)",
                glyph="▦",
                port=self.mod_zeropad.port,
                is_active=self.mod_zeropad.is_active,
                clients=pad_clients,
                on_disconnect_callback=lambda addr: self.mod_zeropad.server.disconnect_client(addr),
                parent=self.cards_container
            )
            self.cards.append(card_pad)
            self.cards_layout.addWidget(card_pad)

        self.cards_layout.addStretch()

    def _on_tick(self):
        for c in self.cards:
            c.update_durations()
