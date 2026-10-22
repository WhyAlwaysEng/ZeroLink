"""ZeroLink Hub - Dashboard View
Overview of ecosystem status, active connections, and dynamic module toggle cards.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QGraphicsDropShadowEffect
)
from core.module_manager import ModuleManager


class ModuleCard(QFrame):
    """Modern Glassmorphic Card for an ecosystem module with ON/OFF switch."""
    toggle_clicked = pyqtSignal(str, bool)  # module_id, target_state
    open_clicked = pyqtSignal(str)          # module_id

    def __init__(self, module_id: str, title: str, icon: str, desc: str,
                 is_enabled: bool, is_available: bool = True, port_info: str = "", parent=None):
        super().__init__(parent)
        self.module_id = module_id
        self.is_enabled = is_enabled
        self.is_available = is_available
        self.port_info = port_info

        self.setObjectName("moduleCard")
        self.setStyleSheet("""
            QFrame#moduleCard {
                background-color: #12151E;
                border: 1px solid #1E2433;
                border-radius: 14px;
            }
            QFrame#moduleCard:hover {
                border-color: #2D3748;
                background-color: #151924;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Row: Icon + Title + Status Pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #FFFFFF;")
        title_col.addWidget(title_lbl)

        if port_info:
            port_lbl = QLabel(port_info)
            port_lbl.setFont(QFont("Consolas", 10))
            port_lbl.setStyleSheet("color: #64B5F6;")
            title_col.addWidget(port_lbl)

        header_row.addLayout(title_col)
        header_row.addStretch()

        self.status_pill = QLabel()
        self.status_pill.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._update_pill()
        header_row.addWidget(self.status_pill)

        layout.addLayout(header_row)

        # Description
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont("Segoe UI", 11))
        desc_lbl.setStyleSheet("color: #A0AEC0; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        layout.addStretch()

        # Action Buttons Footer
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
                    background-color: #1A202C;
                    color: #FFFFFF;
                    border: 1px solid #2D3748;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #2D3748;
                    border-color: #4A5568;
                }
            """)
            self.open_btn.clicked.connect(lambda: self.open_clicked.emit(self.module_id))
            footer_row.addWidget(self.open_btn)
        else:
            coming_lbl = QLabel("🚀 In Development")
            coming_lbl.setStyleSheet("color: #718096; font-size: 11px; font-weight: bold;")
            footer_row.addWidget(coming_lbl)

        layout.addLayout(footer_row)

    def _update_pill(self):
        if not self.is_available:
            self.status_pill.setText("COMING SOON")
            self.status_pill.setStyleSheet("""
                background-color: #1A202C;
                color: #718096;
                padding: 4px 10px;
                border-radius: 10px;
                font-size: 10px;
            """)
        elif self.is_enabled:
            self.status_pill.setText("● ACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #0E3320;
                color: #00E676;
                padding: 4px 10px;
                border-radius: 10px;
                font-size: 10px;
            """)
        else:
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #261619;
                color: #FF5252;
                padding: 4px 10px;
                border-radius: 10px;
                font-size: 10px;
            """)

    def _update_toggle_btn(self):
        if self.is_enabled:
            self.toggle_btn.setText("Disable Module")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2D1518;
                    color: #FF5252;
                    border: 1px solid #742A2A;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #742A2A;
                    color: #FFFFFF;
                }
            """)
        else:
            self.toggle_btn.setText("▶ Enable Module")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E676, stop:1 #38BDF8);
                    color: #0B0D13;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-weight: 800;
                }
                QPushButton:hover {
                    background: #FFFFFF;
                    color: #000000;
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
    """Main dashboard displaying system health, IP, and the ecosystem module grid."""
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
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        # Hero Banner
        hero = QFrame()
        hero.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #111624, stop:1 #0B0D14);
                border: 1px solid #1E2436;
                border-radius: 16px;
                padding: 16px;
            }
        """)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(6)

        title = QLabel("ZeroLink Ecosystem Hub")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #FFFFFF;")
        hero_text.addWidget(title)

        subtitle = QLabel("Cross-Device Bridge: Windows PC & Android • Modular Hardware Acceleration")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #A0AEC0;")
        hero_text.addWidget(subtitle)

        hero_layout.addLayout(hero_text)
        hero_layout.addStretch()

        ip_box = QFrame()
        ip_box.setStyleSheet("background-color: #161A26; border-radius: 10px; padding: 10px 16px;")
        ip_box_l = QVBoxLayout(ip_box)
        ip_box_l.setSpacing(2)
        ip_t = QLabel("LOCAL SUITE IP")
        ip_t.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        ip_t.setStyleSheet("color: #718096;")
        ip_box_l.addWidget(ip_t)

        ip_v = QLabel(self.local_ip)
        ip_v.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        ip_v.setStyleSheet("color: #38BDF8;")
        ip_box_l.addWidget(ip_v)

        hero_layout.addWidget(ip_box)
        layout.addWidget(hero)

        # Section Heading
        sec_lbl = QLabel("PLUGGABLE ECOSYSTEM MODULES")
        sec_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sec_lbl.setStyleSheet("color: #718096; letter-spacing: 1px;")
        layout.addWidget(sec_lbl)

        # Grid of Modules
        grid = QGridLayout()
        grid.setSpacing(20)

        # Module 1: ZeroCast
        mod_cast = self.module_manager.get_module("zerocast")
        cast_active = mod_cast.is_active if mod_cast else False
        card_cast = ModuleCard(
            module_id="zerocast",
            title="ZeroCast",
            icon="📺",
            desc="Ultra-low latency GPU H.264 screen & internal audio mirroring with OBS Virtual Camera and reverse touch control.",
            is_enabled=cast_active,
            is_available=True,
            port_info="TCP Port: 8888 • UDP: 8889"
        )
        card_cast.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_cast.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zerocast"] = card_cast
        grid.addWidget(card_cast, 0, 0)

        # Module 2: ZeroDrop
        card_drop = ModuleCard(
            module_id="zerodrop",
            title="ZeroDrop",
            icon="📁",
            desc="Blazing fast local Wi-Fi / USB file and folder transfers directly between PC and Android without internet.",
            is_enabled=False,
            is_available=False,
            port_info="TCP Port: 8890"
        )
        self.cards["zerodrop"] = card_drop
        grid.addWidget(card_drop, 0, 1)

        # Module 3: ZeroClip
        card_clip = ModuleCard(
            module_id="zeroclip",
            title="ZeroClip",
            icon="📋",
            desc="Real-time two-way clipboard text and image synchronization between PC and mobile device.",
            is_enabled=False,
            is_available=False,
            port_info="Encrypted Sync"
        )
        self.cards["zeroclip"] = card_clip
        grid.addWidget(card_clip, 1, 0)

        # Module 4: ZeroPad
        card_pad = ModuleCard(
            module_id="zeropad",
            title="ZeroPad",
            icon="🎮",
            desc="Transform your phone into a low-latency virtual gamepad, streamer macro pad, or wireless PC touchpad.",
            is_enabled=False,
            is_available=False,
            port_info="Direct Input Injection"
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
