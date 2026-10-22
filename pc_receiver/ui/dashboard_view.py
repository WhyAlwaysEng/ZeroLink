"""ZeroLink Hub - Dashboard View (Monochrome Minimalist Edition)
Clean, uncluttered, pure black & white design with hairline borders and high-contrast typography.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea
)
from core.module_manager import ModuleManager


class ModuleCard(QFrame):
    """Ultra-clean minimal monochrome card with hairline border."""
    toggle_clicked = pyqtSignal(str, bool)  # module_id, target_state
    open_clicked = pyqtSignal(str)          # module_id

    def __init__(self, module_id: str, title: str, glyph: str, desc: str,
                 is_enabled: bool, is_available: bool = True, port_info: str = "", parent=None):
        super().__init__(parent)
        self.module_id = module_id
        self.is_enabled = is_enabled
        self.is_available = is_available
        self.port_info = port_info

        self.setObjectName("moduleCard")
        self.setStyleSheet("""
            QFrame#moduleCard {
                background-color: #0D0D0D;
                border: 1px solid #1C1C1C;
                border-radius: 8px;
            }
            QFrame#moduleCard:hover {
                border-color: #333333;
                background-color: #121212;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header: Glyph + Title + Status Pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel(glyph)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 18))
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #FFFFFF; letter-spacing: 0.3px;")
        title_col.addWidget(title_lbl)

        if port_info:
            port_lbl = QLabel(port_info)
            port_lbl.setFont(QFont("Consolas", 10))
            port_lbl.setStyleSheet("color: #666666;")
            title_col.addWidget(port_lbl)

        header_row.addLayout(title_col)
        header_row.addStretch()

        self.status_pill = QLabel()
        self.status_pill.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._update_pill()
        header_row.addWidget(self.status_pill)

        layout.addLayout(header_row)

        # Description
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont("Segoe UI", 11))
        desc_lbl.setStyleSheet("color: #888888; line-height: 1.5;")
        layout.addWidget(desc_lbl)

        layout.addStretch()

        # Action Buttons
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)

        if is_available:
            self.toggle_btn = QPushButton()
            self._update_toggle_btn()
            self.toggle_btn.clicked.connect(self._on_toggle)
            footer_row.addWidget(self.toggle_btn)

            self.open_btn = QPushButton("Open Viewport →")
            self.open_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #FFFFFF;
                    border: 1px solid #282828;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #1A1A1A;
                    border-color: #444444;
                }
            """)
            self.open_btn.clicked.connect(lambda: self.open_clicked.emit(self.module_id))
            footer_row.addWidget(self.open_btn)
        else:
            coming_lbl = QLabel("In Development")
            coming_lbl.setStyleSheet("color: #555555; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;")
            footer_row.addWidget(coming_lbl)

        layout.addLayout(footer_row)

    def _update_pill(self):
        if not self.is_available:
            self.status_pill.setText("UPCOMING")
            self.status_pill.setStyleSheet("""
                background-color: #161616;
                color: #555555;
                padding: 3px 8px;
                border: 1px solid #222222;
                border-radius: 4px;
                font-size: 9px;
                letter-spacing: 0.5px;
            """)
        elif self.is_enabled:
            self.status_pill.setText("● ACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #111111;
                color: #FFFFFF;
                padding: 3px 8px;
                border: 1px solid #333333;
                border-radius: 4px;
                font-size: 9px;
                letter-spacing: 0.5px;
            """)
        else:
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #111111;
                color: #555555;
                padding: 3px 8px;
                border: 1px solid #1E1E1E;
                border-radius: 4px;
                font-size: 9px;
                letter-spacing: 0.5px;
            """)

    def _update_toggle_btn(self):
        if self.is_enabled:
            self.toggle_btn.setText("Disable Module")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #141414;
                    color: #888888;
                    border: 1px solid #262626;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #202020;
                    color: #FFFFFF;
                    border-color: #404040;
                }
            """)
        else:
            self.toggle_btn.setText("Enable Module")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #000000;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #E2E2E2;
                }
            """)

    def _on_toggle(self):
        target = not self.is_enabled
        self.toggle_clicked.emit(self.module_id, target)

    def set_active_state(self, active: bool):
        self.is_enabled = active
        self._update_pill()
        if self.is_available:
            self._update_toggle_btn()


class DashboardView(QWidget):
    """Monochrome Minimalist Dashboard."""
    navigate_to_module = pyqtSignal(str)
    module_toggle_requested = pyqtSignal(str, bool)

    def __init__(self, module_manager: ModuleManager, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.module_manager = module_manager
        self.local_ip = local_ip
        self.cards = {}

        self._setup_ui()
        self.module_manager.module_toggled.connect(self._on_module_toggled)

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #000000; }")

        container = QWidget()
        container.setStyleSheet("background-color: #000000;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(32)

        # Top Bar: Page Title & System IP Info
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = QLabel("Overview")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: -0.5px;")
        title_col.addWidget(title)

        subtitle = QLabel("Cross-Device Bridge • Windows & Android")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #666666;")
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col)

        header_row.addStretch()

        ip_badge = QFrame()
        ip_badge.setStyleSheet("background-color: #0C0C0C; border: 1px solid #1C1C1C; border-radius: 6px; padding: 6px 14px;")
        ip_layout = QHBoxLayout(ip_badge)
        ip_layout.setContentsMargins(8, 4, 8, 4)
        ip_layout.setSpacing(8)

        ip_lbl = QLabel("IP")
        ip_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        ip_lbl.setStyleSheet("color: #555555;")
        ip_layout.addWidget(ip_lbl)

        ip_val = QLabel(self.local_ip)
        ip_val.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        ip_val.setStyleSheet("color: #FFFFFF;")
        ip_layout.addWidget(ip_val)

        header_row.addWidget(ip_badge)
        layout.addLayout(header_row)

        # Section Divider & Label
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("border: none; border-top: 1px solid #161616;")
        layout.addWidget(divider)

        sec_lbl = QLabel("MODULES")
        sec_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sec_lbl.setStyleSheet("color: #555555; letter-spacing: 1.5px;")
        layout.addWidget(sec_lbl)

        # Modules Grid
        grid = QGridLayout()
        grid.setSpacing(16)

        # ZeroCast
        mod_cast = self.module_manager.get_module("zerocast")
        cast_active = mod_cast.is_active if mod_cast else False
        card_cast = ModuleCard(
            module_id="zerocast",
            title="ZeroCast",
            glyph="📺",
            desc="Low-latency GPU H.264 screen & internal audio mirroring with OBS Virtual Camera and reverse control.",
            is_enabled=cast_active,
            is_available=True,
            port_info="Port 8888 (TCP)"
        )
        card_cast.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_cast.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zerocast"] = card_cast
        grid.addWidget(card_cast, 0, 0)

        # ZeroDrop
        card_drop = ModuleCard(
            module_id="zerodrop",
            title="ZeroDrop",
            glyph="📁",
            desc="Local peer-to-peer file and directory transfers between PC and Android over LAN or USB cable.",
            is_enabled=False,
            is_available=False,
            port_info="Port 8890"
        )
        self.cards["zerodrop"] = card_drop
        grid.addWidget(card_drop, 0, 1)

        # ZeroClip
        card_clip = ModuleCard(
            module_id="zeroclip",
            title="ZeroClip",
            glyph="📋",
            desc="Real-time encrypted two-way clipboard text and link synchronization between devices.",
            is_enabled=False,
            is_available=False,
            port_info="Sync Stream"
        )
        self.cards["zeroclip"] = card_clip
        grid.addWidget(card_clip, 1, 0)

        # ZeroPad
        card_pad = ModuleCard(
            module_id="zeropad",
            title="ZeroPad",
            glyph="🎮",
            desc="Transform your phone into a low-latency virtual gamepad, custom macro deck, or wireless PC touchpad.",
            is_enabled=False,
            is_available=False,
            port_info="Direct Injection"
        )
        self.cards["zeropad"] = card_pad
        grid.addWidget(card_pad, 1, 1)

        layout.addLayout(grid)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _on_module_toggled(self, module_id: str, is_active: bool):
        if module_id in self.cards:
            self.cards[module_id].set_active_state(is_active)
