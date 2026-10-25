"""ZeroLink Hub - Settings View (Swiss Monochrome Minimalist Edition)
Dedicated PC application preferences, system startup, storage, and update management.
"""

import os
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QCheckBox, QScrollArea, QSizePolicy
)

from core.settings import AppSettings
from core.updater import CURRENT_VERSION


class SettingsCard(QFrame):
    """Reusable card with subtle hairline border and header."""
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            SettingsCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(14)

        if title:
            header_layout = QVBoxLayout()
            header_layout.setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            title_lbl.setStyleSheet("color: #111827; border: none;")
            header_layout.addWidget(title_lbl)

            if subtitle:
                sub_lbl = QLabel(subtitle)
                sub_lbl.setFont(QFont("Segoe UI", 9))
                sub_lbl.setStyleSheet("color: #6B7280; border: none;")
                header_layout.addWidget(sub_lbl)

            self.layout.addLayout(header_layout)


class SettingsView(QWidget):
    """Centralized Settings View for ZeroLink PC Hub."""
    check_updates_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = AppSettings()
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(20)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel("⚙")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("color: #111827;")
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        view_title = QLabel("Settings & Preferences")
        view_title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        view_title.setStyleSheet("color: #111827; letter-spacing: -0.3px;")
        title_col.addWidget(view_title)

        view_sub = QLabel("Configure ecosystem behavior, startup, directories, and updates")
        view_sub.setFont(QFont("Segoe UI", 10))
        view_sub.setStyleSheet("color: #6B7280;")
        title_col.addWidget(view_sub)

        header_row.addLayout(title_col)
        header_row.addStretch()
        main_layout.addLayout(header_row)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 8, 0, 16)
        container_layout.setSpacing(16)

        # ---------------- Section 1: System & Window Behavior ----------------
        card_system = SettingsCard("System & Startup", "Control background execution and Windows startup")

        # Windows Startup Toggle
        self.chk_autostart = QCheckBox("Launch ZeroLink on Windows startup")
        self.chk_autostart.setFont(QFont("Segoe UI", 10))
        self.chk_autostart.setStyleSheet("color: #111827; spacing: 8px;")
        try:
            from ui.main_window import is_windows_autostart_enabled
            self.chk_autostart.setChecked(is_windows_autostart_enabled())
        except Exception:
            self.chk_autostart.setChecked(False)
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        card_system.layout.addWidget(self.chk_autostart)

        # Minimize to Tray on Close
        self.chk_close_tray = QCheckBox("Minimize to system tray when closing the window")
        self.chk_close_tray.setFont(QFont("Segoe UI", 10))
        self.chk_close_tray.setStyleSheet("color: #111827; spacing: 8px;")
        self.chk_close_tray.setChecked(self.settings.close_to_tray)
        self.chk_close_tray.toggled.connect(lambda v: setattr(self.settings, 'close_to_tray', v))
        card_system.layout.addWidget(self.chk_close_tray)

        # Start Minimized
        self.chk_start_min = QCheckBox("Start minimized to tray silently")
        self.chk_start_min.setFont(QFont("Segoe UI", 10))
        self.chk_start_min.setStyleSheet("color: #111827; spacing: 8px;")
        self.chk_start_min.setChecked(self.settings.start_minimized)
        self.chk_start_min.toggled.connect(lambda v: setattr(self.settings, 'start_minimized', v))
        card_system.layout.addWidget(self.chk_start_min)

        container_layout.addWidget(card_system)

        # ---------------- Section 2: Storage & File Transfers ----------------
        card_storage = SettingsCard("Storage & File Transfers", "Default destination for received files (ZeroDrop & ZeroExplorer)")

        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)

        self.lbl_path = QLabel(self.settings.download_dir)
        self.lbl_path.setFont(QFont("Consolas", 10))
        self.lbl_path.setStyleSheet("""
            QLabel {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 8px 12px;
                color: #111827;
            }
        """)
        self.lbl_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dir_row.addWidget(self.lbl_path)

        btn_browse = QPushButton("Change...")
        btn_browse.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        btn_browse.clicked.connect(self._browse_download_dir)
        dir_row.addWidget(btn_browse)

        btn_open = QPushButton("Open Folder")
        btn_open.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        btn_open.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        btn_open.clicked.connect(self._open_download_dir)
        dir_row.addWidget(btn_open)

        card_storage.layout.addLayout(dir_row)
        container_layout.addWidget(card_storage)

        # ---------------- Section 3: Notification & Productivity ----------------
        card_productivity = SettingsCard("Smart Productivity", "Intelligent mirroring and clipboard automation")

        self.chk_otp = QCheckBox("Smart OTP Auto-Copy: Automatically extract and copy 4-8 digit codes to PC clipboard")
        self.chk_otp.setFont(QFont("Segoe UI", 10))
        self.chk_otp.setStyleSheet("color: #111827; spacing: 8px;")
        self.chk_otp.setChecked(self.settings.auto_copy_otp)
        self.chk_otp.toggled.connect(lambda v: setattr(self.settings, 'auto_copy_otp', v))
        card_productivity.layout.addWidget(self.chk_otp)

        self.chk_popup = QCheckBox("Show system tray notification bubbles for incoming phone alerts")
        self.chk_popup.setFont(QFont("Segoe UI", 10))
        self.chk_popup.setStyleSheet("color: #111827; spacing: 8px;")
        self.chk_popup.setChecked(self.settings.notify_popup)
        self.chk_popup.toggled.connect(lambda v: setattr(self.settings, 'notify_popup', v))
        card_productivity.layout.addWidget(self.chk_popup)

        container_layout.addWidget(card_productivity)

        # ---------------- Section 4: About & Updates ----------------
        card_about = SettingsCard("About ZeroLink & Updates", f"Current Version: v{CURRENT_VERSION} • Open Source Ecosystem")

        about_row = QHBoxLayout()
        about_row.setSpacing(10)

        btn_check_update = QPushButton("Check for Updates")
        btn_check_update.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        btn_check_update.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 9px 16px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        btn_check_update.clicked.connect(lambda: self.check_updates_requested.emit())
        about_row.addWidget(btn_check_update)

        btn_github = QPushButton("GitHub Repository")
        btn_github.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        btn_github.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 9px 16px;
            }
            QPushButton:hover {
                background-color: #F9FAFB;
            }
        """)
        btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/WhyAlwaysEng/ZeroLink")))
        about_row.addWidget(btn_github)

        btn_releases = QPushButton("Releases & Changelog")
        btn_releases.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        btn_releases.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 9px 16px;
            }
            QPushButton:hover {
                background-color: #F9FAFB;
            }
        """)
        btn_releases.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/WhyAlwaysEng/ZeroLink/releases")))
        about_row.addWidget(btn_releases)

        about_row.addStretch()
        card_about.layout.addLayout(about_row)
        container_layout.addWidget(card_about)

        container_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _browse_download_dir(self):
        cur = self.settings.download_dir
        selected = QFileDialog.getExistingDirectory(self, "Select Download Directory", cur)
        if selected:
            self.settings.download_dir = selected
            self.lbl_path.setText(selected)

    def _open_download_dir(self):
        d = self.settings.download_dir
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _on_autostart_toggled(self, checked: bool):
        try:
            from ui.main_window import set_windows_autostart
            set_windows_autostart(checked)
        except Exception as e:
            print(f"[Settings] Error setting autostart: {e}")
