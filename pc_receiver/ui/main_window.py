"""ZeroLink Hub - Master PC Application Window (Monochrome Minimalist Edition)
Ultra-clean black & white design with hairline borders, generous spacing, and modern typography.
"""

import os
import sys
import re
import math
from typing import Optional

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QUrl, QPointF
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap, QDesktopServices, QAction, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QMessageBox, QButtonGroup,
    QSystemTrayIcon, QMenu
)

from core.module_manager import ModuleManager
from core.updater import UpdateCheckWorker, CURRENT_VERSION
from core.discovery import LanDiscoveryService
from modules.zerocast.cast_module import ZeroCastModule
from modules.zerodrop.drop_module import ZeroDropModule
from modules.zeroclip.clip_module import ZeroClipModule
from modules.zeromix.mix_module import ZeroMixModule
from modules.zerodisplay.display_module import ZeroDisplayModule
from modules.zerocam.cam_module import ZeroCamModule
from modules.zeropad.pad_module import ZeroPadModule
from modules.zeroexplorer.explorer_module import ZeroExplorerModule
from modules.zerodev.dev_module import ZeroDevModule
from ui.dashboard_view import DashboardView
from ui.connections_view import ConnectionsView
from ui.settings_view import SettingsView
from core.settings import AppSettings
from ui.theme import GLOBAL_APP_STYLESHEET, create_gear_pixmap


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


def is_windows_autostart_enabled() -> bool:
    """Checks if ZeroLink is registered in Windows Startup (HKCU Run)."""
    if os.name != 'nt':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, "ZeroLink")
        winreg.CloseKey(key)
        return bool(val)
    except OSError:
        return False


def set_windows_autostart(enable: bool) -> bool:
    """Registers or unregisters ZeroLink in Windows Startup to start minimized."""
    if os.name != 'nt':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        if enable:
            if getattr(sys, 'frozen', False):
                cmd = f'"{sys.executable}" --minimized'
            else:
                main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
                py_exe = sys.executable
                pyw = os.path.join(os.path.dirname(py_exe), "pythonw.exe")
                if os.path.exists(pyw):
                    py_exe = pyw
                cmd = f'"{py_exe}" "{main_py}" --minimized'
            winreg.SetValueEx(key, "ZeroLink", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "ZeroLink")
            except OSError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[AutoStart] Registry error: {e}")
        return False


class NavButton(QPushButton):
    """Minimalist monochrome sidebar item with subtle active indicator."""
    def __init__(self, text: str, glyph: str = "", icon_pixmap: Optional[QPixmap] = None, badge: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        if icon_pixmap is not None:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon_pixmap)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(icon_lbl)
        else:
            icon_lbl = QLabel(glyph)
            icon_lbl.setFont(QFont("Segoe UI Symbol", 13))
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(icon_lbl)

        text_lbl = QLabel(text)
        text_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        text_lbl.setStyleSheet("color: inherit;")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(text_lbl)

        layout.addStretch()

        if badge:
            badge_lbl = QLabel(badge)
            badge_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            badge_lbl.setStyleSheet("""
                background-color: #F3F4F6;
                color: #111827;
                padding: 2px 6px;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
            """)
            badge_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(badge_lbl)

        self.setStyleSheet("""
            NavButton {
                background-color: transparent;
                color: #374151;
                border: none;
                border-radius: 6px;
                text-align: left;
            }
            NavButton:hover {
                background-color: #F3F4F6;
                color: #000000;
            }
            NavButton:checked {
                background-color: #F3F4F6;
                color: #000000;
                font-weight: bold;
                border-left: 3px solid #000000;
            }
        """)


class MainWindow(QMainWindow):
    """ZeroLink Hub Central Application Window (Minimalist Edition)."""

    def __init__(self, port: int = 8888, start_minimized: bool = False):
        super().__init__()
        self.port = port
        self.local_ip = get_local_ip()
        self.app_settings = AppSettings()
        self.start_minimized = start_minimized or self.app_settings.start_minimized

        self.setWindowTitle(f"ZeroLink Hub v{CURRENT_VERSION}")
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1180, 760)
        self.setMinimumSize(880, 540)
        self.is_fullscreen = False

        # Module Manager
        self.module_manager = ModuleManager(self)

        # Register Ecosystem Modules - All 10 Modules Always-Live on startup
        self.mod_zerocast = ZeroCastModule(port=self.port, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zerocast)

        self.mod_zerodrop = ZeroDropModule(port=8890, local_ip=self.local_ip, download_dir=self.app_settings.download_dir, parent=self)
        self.module_manager.register_module(self.mod_zerodrop)

        self.mod_zeroclip = ZeroClipModule(port=8889, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zeroclip)

        self.mod_zeromix = ZeroMixModule(port=8891, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zeromix)

        self.mod_zerodisplay = ZeroDisplayModule(port=8892, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zerodisplay)

        self.mod_zerocam = ZeroCamModule(port=8893, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zerocam)

        self.mod_zeropad = ZeroPadModule(port=8894, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zeropad)

        self.mod_zeroexplorer = ZeroExplorerModule(port=8896, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zeroexplorer)

        self.mod_zerodev = ZeroDevModule(port=8897, local_ip=self.local_ip, parent=self)
        self.module_manager.register_module(self.mod_zerodev)

        # Boot and listen on ALL module services simultaneously
        for mod_id in ["zerocast", "zerodrop", "zeroclip", "zeromix", "zerodisplay", "zerocam", "zeropad", "zeroexplorer", "zerodev"]:
            self.module_manager.toggle_module(mod_id, True)

        # Bridge ZeroCast phone audio stream into ZeroMix mixer engine
        self.mod_zerocast.audio_pcm_received.connect(self.mod_zeromix.engine.write_phone_pcm)
        self.mod_zerocast.use_external_mixer = False
        self.mod_zeromix.state_changed.connect(self._on_zeromix_state_changed)

        self._setup_ui()
        self._bind_events()

        # System Tray
        self._is_quitting = False
        self._tray_notified = False
        self._setup_tray_icon()

        # LAN Auto-Discovery & Notification Bridge (UDP 8887 & TCP 8886 Master Gateway)
        self.discovery_service = LanDiscoveryService(tcp_port=self.port, local_ip=self.local_ip, parent=self)
        self.discovery_service.notification_received.connect(self._on_phone_notification)
        self.discovery_service.module_wake_requested.connect(self._on_remote_wake_module)
        self.discovery_service.module_sleep_requested.connect(self._on_remote_sleep_module)
        self.discovery_service.gateway_client_updated.connect(self.dashboard_view.update_client_connection)
        self.discovery_service.start()

        # Update Checker
        self.latest_release_url = f"https://github.com/WhyAlwaysEng/ZeroLink/releases"
        self.latest_release_tag = ""
        self.latest_release_notes = ""
        QTimer.singleShot(2500, self._check_for_updates)

        if getattr(self, "start_minimized", False):
            QTimer.singleShot(1000, lambda: self.tray_icon.showMessage(
                "ZeroLink Hub",
                "ZeroLink started minimized to tray. Background services are active.",
                QSystemTrayIcon.MessageIcon.Information,
                2500
            ))

    def _setup_ui(self):
        self.setStyleSheet(GLOBAL_APP_STYLESHEET)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==================== Left Sidebar ====================
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 24, 16, 20)
        side_layout.setSpacing(6)

        # Brand Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)

        logo_path = os.path.join(os.path.dirname(__file__), "..", "icon.png")
        if os.path.exists(logo_path):
            logo_lbl = QLabel()
            pix = QPixmap(logo_path).scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            brand_row.addWidget(logo_lbl)

        brand_text_col = QVBoxLayout()
        brand_text_col.setSpacing(0)
        app_name = QLabel("ZeroLink")
        app_name.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        app_name.setStyleSheet("color: #111827; letter-spacing: 0.3px;")
        brand_text_col.addWidget(app_name)

        self.hub_badge = QLabel(f"HUB v{CURRENT_VERSION}")
        self.hub_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.hub_badge.setStyleSheet("color: #6B7280; letter-spacing: 0.8px;")
        self.hub_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hub_badge.setToolTip("Click to check for updates from GitHub")
        self.hub_badge.mousePressEvent = lambda _: self._check_for_updates(is_manual=True)
        brand_text_col.addWidget(self.hub_badge)

        brand_row.addLayout(brand_text_col)
        brand_row.addStretch()
        side_layout.addLayout(brand_row)

        side_layout.addSpacing(20)

        # Nav Buttons
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_nav_dashboard = NavButton("Dashboard", "⊞")
        self.btn_nav_dashboard.setChecked(True)
        self.btn_nav_dashboard.clicked.connect(lambda: self.stacked.setCurrentIndex(0))
        self.nav_group.addButton(self.btn_nav_dashboard)
        side_layout.addWidget(self.btn_nav_dashboard)

        self.btn_nav_cast = NavButton("ZeroCast", "⊡", badge="CORE")
        self.btn_nav_cast.clicked.connect(lambda: self.stacked.setCurrentIndex(1))
        self.nav_group.addButton(self.btn_nav_cast)
        side_layout.addWidget(self.btn_nav_cast)

        self.btn_nav_drop = NavButton("ZeroDrop", "⇄")
        self.btn_nav_drop.clicked.connect(lambda: self.stacked.setCurrentIndex(2))
        self.nav_group.addButton(self.btn_nav_drop)
        side_layout.addWidget(self.btn_nav_drop)

        self.btn_nav_clip = NavButton("ZeroClip", "⎘")
        self.btn_nav_clip.clicked.connect(lambda: self.stacked.setCurrentIndex(3))
        self.nav_group.addButton(self.btn_nav_clip)
        side_layout.addWidget(self.btn_nav_clip)

        self.btn_nav_mix = NavButton("ZeroMix", "⧉")
        self.btn_nav_mix.clicked.connect(lambda: self.stacked.setCurrentIndex(4))
        self.nav_group.addButton(self.btn_nav_mix)
        side_layout.addWidget(self.btn_nav_mix)

        self.btn_nav_display = NavButton("ZeroDisplay", "▣")
        self.btn_nav_display.clicked.connect(lambda: self.stacked.setCurrentIndex(5))
        self.nav_group.addButton(self.btn_nav_display)
        side_layout.addWidget(self.btn_nav_display)

        self.btn_nav_cam = NavButton("ZeroCam", "◎")
        self.btn_nav_cam.clicked.connect(lambda: self.stacked.setCurrentIndex(6))
        self.nav_group.addButton(self.btn_nav_cam)
        side_layout.addWidget(self.btn_nav_cam)

        self.btn_nav_pad = NavButton("ZeroPad", "▦")
        self.btn_nav_pad.clicked.connect(lambda: self.stacked.setCurrentIndex(7))
        self.nav_group.addButton(self.btn_nav_pad)
        side_layout.addWidget(self.btn_nav_pad)

        self.btn_nav_explorer = NavButton("ZeroExplorer", "▤")
        self.btn_nav_explorer.clicked.connect(lambda: self.stacked.setCurrentIndex(8))
        self.nav_group.addButton(self.btn_nav_explorer)
        side_layout.addWidget(self.btn_nav_explorer)

        self.btn_nav_dev = NavButton("ZeroDev", "</>", badge="DEV")
        self.btn_nav_dev.clicked.connect(lambda: self.stacked.setCurrentIndex(9))
        self.nav_group.addButton(self.btn_nav_dev)
        side_layout.addWidget(self.btn_nav_dev)

        self.btn_nav_connections = NavButton("Connections", "◈")
        self.btn_nav_connections.clicked.connect(lambda: self.stacked.setCurrentIndex(10))
        self.nav_group.addButton(self.btn_nav_connections)
        side_layout.addWidget(self.btn_nav_connections)

        self.btn_nav_settings = NavButton("Settings", icon_pixmap=create_gear_pixmap(18, "#374151"))
        self.btn_nav_settings.clicked.connect(lambda: self.stacked.setCurrentIndex(11))
        self.nav_group.addButton(self.btn_nav_settings)
        side_layout.addWidget(self.btn_nav_settings)

        side_layout.addStretch()

        # Update Pill
        self.btn_update = QPushButton("Update Available")
        self.btn_update.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: #FFFFFF;
                font-weight: 700;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        self.btn_update.setVisible(False)
        self.btn_update.clicked.connect(self._on_update_clicked)
        side_layout.addWidget(self.btn_update)

        # Bottom Tools
        self.btn_pin = QPushButton("Pin Window")
        self.btn_pin.setCheckable(True)
        self.btn_pin.clicked.connect(self._toggle_pin)
        side_layout.addWidget(self.btn_pin)

        self.btn_fullscreen = QPushButton("Fullscreen (F11)")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        side_layout.addWidget(self.btn_fullscreen)

        main_layout.addWidget(sidebar)

        # ==================== Right Viewport ====================
        self.stacked = QStackedWidget(self)

        # Page 0: Dashboard
        self.dashboard_view = DashboardView(self.module_manager, local_ip=self.local_ip, parent=self)
        self.dashboard_view.navigate_to_module.connect(self._on_navigate_to_module)
        self.stacked.addWidget(self.dashboard_view)

        # Page 1: ZeroCast Viewport
        self.cast_widget = self.mod_zerocast.get_widget()
        self.mod_zerocast.toggle_fullscreen_requested.connect(self._toggle_fullscreen)
        self.stacked.addWidget(self.cast_widget)

        # Page 2: ZeroDrop Viewport
        self.drop_widget = self.mod_zerodrop.get_widget()
        self.stacked.addWidget(self.drop_widget)

        # Page 3: ZeroClip Viewport
        self.clip_widget = self.mod_zeroclip.get_widget()
        self.stacked.addWidget(self.clip_widget)

        # Page 4: ZeroMix Viewport
        self.mix_widget = self.mod_zeromix.get_widget()
        self.stacked.addWidget(self.mix_widget)

        # Page 5: ZeroDisplay Viewport
        self.display_widget = self.mod_zerodisplay.get_widget()
        self.stacked.addWidget(self.display_widget)

        # Page 6: ZeroCam Viewport
        self.cam_widget = self.mod_zerocam.get_widget()
        self.stacked.addWidget(self.cam_widget)

        # Page 7: ZeroPad Viewport
        self.pad_widget = self.mod_zeropad.get_widget()
        self.stacked.addWidget(self.pad_widget)

        # Page 8: ZeroExplorer Viewport
        self.explorer_widget = self.mod_zeroexplorer.get_widget()
        self.stacked.addWidget(self.explorer_widget)

        # Page 9: ZeroDev Viewport
        self.dev_widget = self.mod_zerodev.get_widget()
        self.stacked.addWidget(self.dev_widget)

        # Page 10: Connections / Device Bridge
        self.connections_view = ConnectionsView(
            self.mod_zerocast,
            self.mod_zerodrop,
            self.mod_zeroclip,
            self.mod_zeromix,
            mod_zerodisplay=self.mod_zerodisplay,
            mod_zerocam=self.mod_zerocam,
            mod_zeropad=self.mod_zeropad,
            mod_zeroexplorer=self.mod_zeroexplorer,
            parent=self
        )
        self.stacked.addWidget(self.connections_view)

        # Page 11: Settings
        self.settings_view = SettingsView(parent=self)
        self.settings_view.check_updates_requested.connect(lambda: self._check_for_updates(is_manual=True))
        self.stacked.addWidget(self.settings_view)

        main_layout.addWidget(self.stacked, 1)

    def _create_placeholder_page(self, title: str, subtitle: str) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        l = QVBoxLayout(page)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.setSpacing(14)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #111827;")
        l.addWidget(t_lbl)

        s_lbl = QLabel(subtitle)
        s_lbl.setFont(QFont("Segoe UI", 11))
        s_lbl.setStyleSheet("color: #6B7280; max-width: 500px;")
        s_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_lbl.setWordWrap(True)
        l.addWidget(s_lbl)

        back_btn = QPushButton("← Return to Dashboard")
        back_btn.clicked.connect(lambda: self._on_navigate_to_module("dashboard"))
        l.addWidget(back_btn)
        return page

    def _bind_events(self):
        # Auto-Focus and Realtime Dashboard Sync on Connect:
        # All modules support simultaneous multi-tasking in the background.
        if hasattr(self.mod_zerocast, "server"):
            self.mod_zerocast.server.client_connected.connect(lambda ip, model: self._on_module_client_connected("zerocast", ip, model))
            self.mod_zerocast.server.client_disconnected.connect(lambda ip: self._on_module_client_disconnected("zerocast", ip))

        if hasattr(self.mod_zerocam, "server"):
            self.mod_zerocam.server.client_connected.connect(lambda ip, model: self._on_module_client_connected("zerocam", ip, model))
            self.mod_zerocam.server.client_disconnected.connect(lambda ip: self._on_module_client_disconnected("zerocam", ip))

        if hasattr(self.mod_zerodisplay, "server"):
            self.mod_zerodisplay.server.client_connected.connect(lambda ip, model: self._on_module_client_connected("zerodisplay", ip, model))
            self.mod_zerodisplay.server.client_disconnected.connect(lambda ip: self._on_module_client_disconnected("zerodisplay", ip))

        if hasattr(self.mod_zeropad, "server"):
            self.mod_zeropad.server.client_connected.connect(lambda ip, model: self._on_module_client_connected("zeropad", ip, model))
            self.mod_zeropad.server.client_disconnected.connect(lambda ip: self._on_module_client_disconnected("zeropad", ip))

        if hasattr(self.mod_zeromix, "service"):
            self.mod_zeromix.service.client_connected.connect(lambda *_: self._on_module_client_connected("zeromix", "127.0.0.1", "ZeroMix Client"))

    def _on_module_client_connected(self, module_id: str, ip: str = "", model: str = ""):
        print(f"[MultiTask] Mobile client linked to '{module_id}' from {ip} ({model})")
        self.dashboard_view.set_module_streaming(module_id, True)
        if ip:
            link_mode = "USB (ADB)" if ip.startswith("127.") else ("USB Tethering" if ip.startswith("10.") or ip.startswith("192.168.42.") or ip.startswith("192.168.43.") else "Wi-Fi LAN")
            self.dashboard_view.update_client_connection({
                "client_ip": ip,
                "model": model or "Android Device",
                "mode": link_mode,
                "status": "CONNECTED"
            })
        self._on_client_connected_lifecycle(module_id)

    def _on_module_client_disconnected(self, module_id: str, ip: str = ""):
        print(f"[MultiTask] Mobile client disconnected from '{module_id}'")
        self.dashboard_view.set_module_streaming(module_id, False)

    def _on_client_connected_lifecycle(self, module_id: str):
        print(f"[MultiTask] Mobile client linked to '{module_id}' -> activating & switching view.")
        mod = self.module_manager.get_module(module_id)
        if mod and not mod.is_active:
            self.module_manager.toggle_module(module_id, True)
        if module_id == "zeromix":
            cast_mod = self.module_manager.get_module("zerocast")
            if cast_mod and not cast_mod.is_active:
                self.module_manager.toggle_module("zerocast", True)
        self._restore_from_tray()
        self._on_navigate_to_module(module_id)

    def _on_navigate_to_module(self, module_id: str):
        # On-Demand: Activate module service when navigated to
        if module_id not in ["dashboard", "connections"]:
            mod = self.module_manager.get_module(module_id)
            if mod and not mod.is_active:
                self.module_manager.toggle_module(module_id, True)

        # ZeroMix & ZeroCast Synchronization:
        # ZeroMix receives phone audio streamed to ZeroCast port 8888; ensure ZeroCast is live
        if module_id == "zeromix":
            cast_mod = self.module_manager.get_module("zerocast")
            if cast_mod and not cast_mod.is_active:
                self.module_manager.toggle_module("zerocast", True)
                print("[ZeroLink Sync] Auto-activated ZeroCast service for ZeroMix phone audio stream")

        if module_id == "zerocast":
            self.stacked.setCurrentIndex(1)
            self.btn_nav_cast.setChecked(True)
        elif module_id == "zerodrop":
            self.stacked.setCurrentIndex(2)
            self.btn_nav_drop.setChecked(True)
        elif module_id == "zeroclip":
            self.stacked.setCurrentIndex(3)
            self.btn_nav_clip.setChecked(True)
        elif module_id == "zeromix":
            self.stacked.setCurrentIndex(4)
            self.btn_nav_mix.setChecked(True)
        elif module_id == "zerodisplay":
            self.stacked.setCurrentIndex(5)
            self.btn_nav_display.setChecked(True)
        elif module_id == "zerocam":
            self.stacked.setCurrentIndex(6)
            self.btn_nav_cam.setChecked(True)
        elif module_id == "zeropad":
            self.stacked.setCurrentIndex(7)
            self.btn_nav_pad.setChecked(True)
        elif module_id == "zeroexplorer":
            self.stacked.setCurrentIndex(8)
            self.btn_nav_explorer.setChecked(True)
        elif module_id == "zerodev":
            self.stacked.setCurrentIndex(9)
            self.btn_nav_dev.setChecked(True)
        elif module_id == "connections":
            self.stacked.setCurrentIndex(10)
            self.btn_nav_connections.setChecked(True)
        else:
            self.stacked.setCurrentIndex(0)
            self.btn_nav_dashboard.setChecked(True)

    def send_file_via_zerodrop(self, file_path: str):
        if not os.path.exists(file_path):
            return
        self._restore_from_tray()
        self._on_navigate_to_module("zerodrop")
        drop_mod = self.module_manager.get_module("zerodrop")
        if drop_mod and hasattr(drop_mod, "_send_files"):
            drop_mod._send_files([file_path])

    def _on_module_toggle_requested(self, module_id: str, enable: bool):
        self.module_manager.toggle_module(module_id, enable)
        if module_id == "zeromix":
            cast_mod = self.module_manager.get_module("zerocast")
            if cast_mod and cast_mod.is_active != enable:
                self.module_manager.toggle_module("zerocast", enable)
                print(f"[ZeroLink Sync] Synced ZeroCast state to {enable} matching ZeroMix")

    def _on_zeromix_state_changed(self, module_id: str, is_active: bool):
        if module_id == "zeromix":
            self.mod_zerocast.use_external_mixer = is_active
            cast_mod = self.module_manager.get_module("zerocast")
            if cast_mod and cast_mod.is_active != is_active:
                self.module_manager.toggle_module("zerocast", is_active)
                print(f"[ZeroLink Sync] Synced ZeroCast service to {is_active} matching ZeroMix")

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.showFullScreen()
            self.btn_fullscreen.setText("Exit Fullscreen")
        else:
            self.showNormal()
            self.btn_fullscreen.setText("Fullscreen (F11)")

    def _toggle_pin(self):
        is_pinned = self.btn_pin.isChecked()
        flags = self.windowFlags()
        if is_pinned:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
            self.btn_pin.setStyleSheet("background-color: #FFFFFF; color: #000000; font-weight: 700; border: none;")
        else:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
            self.btn_pin.setStyleSheet("")
        self.show()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape and self.is_fullscreen:
            self._toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def _check_for_updates(self, is_manual: bool = False):
        if is_manual:
            self.hub_badge.setText("Checking...")
        self.update_worker = UpdateCheckWorker(CURRENT_VERSION, is_manual=is_manual, parent=self)
        self.update_worker.update_available.connect(self._on_update_available)
        self.update_worker.no_update.connect(self._on_no_update)
        self.update_worker.check_failed.connect(self._on_update_failed)
        self.update_worker.start()

    def _on_update_available(self, tag_name: str, html_url: str, notes: str):
        self.latest_release_url = html_url
        self.latest_release_tag = tag_name
        self.latest_release_notes = notes
        self.hub_badge.setText(f"NEW: {tag_name}")
        self.hub_badge.setStyleSheet("color: #10B981; font-weight: bold; letter-spacing: 0.8px;")
        self.btn_update.setText(f"Update: {tag_name}")
        self.btn_update.setVisible(True)

    def _on_no_update(self, is_manual: bool):
        self.hub_badge.setText(f"HUB v{CURRENT_VERSION}")
        self.hub_badge.setStyleSheet("color: #6B7280; letter-spacing: 0.8px;")
        if is_manual:
            box = QMessageBox(self)
            box.setWindowTitle("ZeroLink Update")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(f"<h3>You're Up to Date!</h3><p>ZeroLink v{CURRENT_VERSION} is currently the latest version.</p>")
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.exec()

    def _on_update_failed(self, err: str, is_manual: bool):
        self.hub_badge.setText(f"HUB v{CURRENT_VERSION}")
        self.hub_badge.setStyleSheet("color: #6B7280; letter-spacing: 0.8px;")
        if is_manual:
            box = QMessageBox(self)
            box.setWindowTitle("ZeroLink Update")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f"<h3>Update Check Failed</h3><p>Could not reach GitHub Releases.<br><small>{err}</small></p>")
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.exec()

    def _on_update_clicked(self):
        box = QMessageBox(self)
        box.setWindowTitle("ZeroLink Update")
        snippet = self.latest_release_notes.strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        notes_html = f"<pre style='background:#F3F4F6; padding:8px; border-radius:4px;'>{snippet}</pre>" if snippet else ""
        box.setText(f"<h3>New Release Available: {self.latest_release_tag}</h3>"
                    f"<p>Current: v{CURRENT_VERSION}</p>"
                    f"{notes_html}"
                    f"<p>Open download page on GitHub?</p>")
        download_btn = box.addButton("Download Release", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        if box.clickedButton() == download_btn:
            QDesktopServices.openUrl(QUrl(self.latest_release_url))

    def _setup_tray_icon(self):
        """Sets up Windows System Tray icon with quick actions and minimize-to-tray."""
        self.tray_icon = QSystemTrayIcon(self)

        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "zerolink_logo.png")
        if os.path.exists(logo_path):
            self.tray_icon.setIcon(QIcon(logo_path))
        else:
            self.tray_icon.setIcon(self.windowIcon())

        self.tray_icon.setToolTip("ZeroLink Ecosystem Hub (Active in Background)")

        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 6px;
                font-family: 'Segoe UI';
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                color: #111827;
            }
            QMenu::item:selected {
                background-color: #F3F4F6;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E5E7EB;
                margin: 4px 0;
            }
        """)

        action_open = QAction("🖥️ Open ZeroLink Hub", self)
        action_open.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(action_open)

        action_drop = QAction("⇄ Open ZeroDrop (Send/Receive)", self)
        action_drop.triggered.connect(lambda: (self._restore_from_tray(), self._on_navigate_to_module("zerodrop")))
        tray_menu.addAction(action_drop)

        action_downloads = QAction("📥 Open Downloads Folder", self)
        action_downloads.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(os.path.expanduser("~"), "Downloads"))))
        tray_menu.addAction(action_downloads)

        tray_menu.addSeparator()

        self.action_autostart = QAction("🚀 Start with Windows", self)
        self.action_autostart.setCheckable(True)
        self.action_autostart.setChecked(is_windows_autostart_enabled())
        self.action_autostart.toggled.connect(self._on_toggle_autostart)
        tray_menu.addAction(self.action_autostart)

        tray_menu.addSeparator()

        action_quit = QAction("❌ Exit ZeroLink", self)
        action_quit.triggered.connect(self._really_quit)
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_toggle_autostart(self, enabled: bool):
        ok = set_windows_autostart(enabled)
        if hasattr(self, "tray_icon") and self.tray_icon:
            if ok:
                msg = "ZeroLink will now start minimized to tray on Windows boot." if enabled else "ZeroLink removed from Windows startup."
                self.tray_icon.showMessage("Windows Startup", msg, QSystemTrayIcon.MessageIcon.Information, 2500)
            else:
                self.tray_icon.showMessage("Windows Startup", "Failed to update Windows startup settings.", QSystemTrayIcon.MessageIcon.Warning, 2500)

    def _restore_from_tray(self):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self._restore_from_tray()

    def _really_quit(self):
        self._is_quitting = True
        if hasattr(self, "discovery_service"):
            self.discovery_service.stop()
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        self.module_manager.stop_all()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def _extract_otp(self, text: str) -> Optional[str]:
        """Detects 4-8 digit OTP verification codes from notification content."""
        if not text:
            return None
        keywords = ["otp", "code", "verification", "รหัส", "password", "pin", "auth", "ยืนยัน", "passcode"]
        text_lower = text.lower()
        if not any(k in text_lower for k in keywords):
            return None

        # Look for 4 to 8 consecutive digits
        matches = re.findall(r"\b\d{4,8}\b", text)
        return matches[0] if matches else None

    def _on_phone_notification(self, app_name: str, title: str, text: str):
        if not getattr(self.app_settings, "notify_popup", True):
            return
        if hasattr(self, "tray_icon") and self.tray_icon:
            full_msg = f"{title} {text}".strip()
            otp = self._extract_otp(full_msg) if getattr(self.app_settings, "auto_copy_otp", True) else None
            if otp:
                # Feature 1: Smart OTP Auto-Copy to Windows Clipboard
                from PyQt6.QtWidgets import QApplication
                cb = QApplication.clipboard()
                if cb:
                    cb.setText(otp)
                body = f"[OTP AUTO-COPIED: {otp}]\n{title}\n{text}" if title else f"[OTP AUTO-COPIED: {otp}]\n{text}"
                self.tray_icon.showMessage(f"📋 OTP Copied • {app_name}", body, QSystemTrayIcon.MessageIcon.Information, 6000)
            else:
                msg = f"{title}\n{text}" if title else text
                self.tray_icon.showMessage(f"📱 {app_name}", msg, QSystemTrayIcon.MessageIcon.Information, 4500)

    def _on_remote_wake_module(self, module_id: str):
        mod = self.module_manager.get_module(module_id)
        if mod and not mod.is_active:
            self.module_manager.toggle_module(module_id, True)
            print(f"[ZeroWake] Remotely activated module: {module_id}")
        if module_id == "zeromix":
            cast_mod = self.module_manager.get_module("zerocast")
            if cast_mod and not cast_mod.is_active:
                self.module_manager.toggle_module("zerocast", True)
                print(f"[ZeroWake] Synced activation: zerocast activated with zeromix")
        if module_id == "zeroexplorer":
            client_ip = getattr(self.discovery_service, "last_client_ip", "")
            if client_ip and client_ip not in ("127.0.0.1", "0.0.0.0"):
                if hasattr(self.mod_zeroexplorer, "set_phone_host"):
                    self.mod_zeroexplorer.set_phone_host(client_ip)
        self._restore_from_tray()
        self._on_navigate_to_module(module_id)

    def _on_remote_sleep_module(self, module_id: str):
        # Multi-tasking enabled: leaving a menu does not force-stop background services
        pass

    def closeEvent(self, event):
        if getattr(self, "_is_quitting", False) or not getattr(self.app_settings, "close_to_tray", True):
            self._really_quit()
            super().closeEvent(event)
        else:
            event.ignore()
            self.hide()
            if not getattr(self, "_tray_notified", False):
                self._tray_notified = True
                self.tray_icon.showMessage(
                    "ZeroLink Hub",
                    "ZeroLink is minimized to the system tray. Background services (ZeroClip, ZeroDrop, ZeroMix) are active.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2500
                )
