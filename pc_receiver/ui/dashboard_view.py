"""ZeroLink Hub - Dashboard View (Light Minimalist Edition)
Crisp white cards with subtle hairline borders, soft drop shadows, and high-contrast black typography.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QGraphicsDropShadowEffect
)
from core.module_manager import ModuleManager


class ModuleCard(QFrame):
    """Crisp white minimal card with subtle hairline border and soft shadow."""
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
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
            QFrame#moduleCard:hover {
                border-color: #D1D5DB;
                background-color: #FAFAFA;
            }
        """)

        # Soft ambient shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 10))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        # Header: Glyph + Title + Status Pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel(glyph)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 20))
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827; letter-spacing: -0.2px;")
        title_col.addWidget(title_lbl)

        if port_info:
            port_lbl = QLabel(port_info)
            port_lbl.setFont(QFont("Consolas", 10))
            port_lbl.setStyleSheet("color: #6B7280;")
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
        desc_lbl.setStyleSheet("color: #4B5563; line-height: 1.5;")
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
                    background-color: #FFFFFF;
                    color: #111827;
                    border: 1px solid #D1D5DB;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #F3F4F6;
                    border-color: #9CA3AF;
                }
            """)
            self.open_btn.clicked.connect(lambda: self.open_clicked.emit(self.module_id))
            footer_row.addWidget(self.open_btn)
        else:
            coming_lbl = QLabel("In Development")
            coming_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;")
            footer_row.addWidget(coming_lbl)

        layout.addLayout(footer_row)

    def _update_pill(self):
        if not self.is_available:
            self.status_pill.setText("UPCOMING")
            self.status_pill.setStyleSheet("""
                background-color: #F3F4F6;
                color: #9CA3AF;
                padding: 3px 8px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 0.5px;
            """)
        elif self.is_enabled:
            self.status_pill.setText("● ACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #F0FDF4;
                color: #166534;
                padding: 3px 8px;
                border: 1px solid #BBF7D0;
                border-radius: 4px;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 0.5px;
            """)
        else:
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("""
                background-color: #F3F4F6;
                color: #6B7280;
                padding: 3px 8px;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 0.5px;
            """)

    def _update_toggle_btn(self):
        if self.is_enabled:
            self.toggle_btn.setText("Disable Module")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #F3F4F6;
                    color: #4B5563;
                    border: 1px solid #D1D5DB;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #E5E7EB;
                    color: #111827;
                }
            """)
        else:
            self.toggle_btn.setText("Enable Module")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #000000;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #1F2937;
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
    """Crisp White Minimalist Dashboard."""
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
        scroll.setStyleSheet("QScrollArea { border: none; background: #F9FAFB; }")

        container = QWidget()
        container.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(28)

        # Top Bar: Page Title & System IP Info
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = QLabel("Overview")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #111827; letter-spacing: -0.5px;")
        title_col.addWidget(title)

        subtitle = QLabel("Cross-Device Bridge • Windows & Android Ecosystem")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #6B7280;")
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col)

        header_row.addStretch()

        ip_badge = QFrame()
        ip_badge.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 6px 14px;")
        ip_layout = QHBoxLayout(ip_badge)
        ip_layout.setContentsMargins(8, 4, 8, 4)
        ip_layout.setSpacing(8)

        ip_lbl = QLabel("IP")
        ip_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        ip_lbl.setStyleSheet("color: #9CA3AF;")
        ip_layout.addWidget(ip_lbl)

        ip_val = QLabel(self.local_ip)
        ip_val.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        ip_val.setStyleSheet("color: #111827;")
        ip_layout.addWidget(ip_val)

        header_row.addWidget(ip_badge)
        layout.addLayout(header_row)

        # Section Divider & Label
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("border: none; border-top: 1px solid #E5E7EB;")
        layout.addWidget(divider)

        sec_lbl = QLabel("PLUGGABLE ECOSYSTEM MODULES")
        sec_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sec_lbl.setStyleSheet("color: #9CA3AF; letter-spacing: 1.2px;")
        layout.addWidget(sec_lbl)

        # Modules Grid
        grid = QGridLayout()
        grid.setSpacing(18)

        # ZeroCast
        mod_cast = self.module_manager.get_module("zerocast")
        cast_active = mod_cast.is_active if mod_cast else False
        card_cast = ModuleCard(
            module_id="zerocast",
            title="ZeroCast",
            glyph="📺",
            desc="Ultra-low latency GPU H.264 screen & internal audio mirroring with OBS Virtual Camera and reverse control.",
            is_enabled=cast_active,
            is_available=True,
            port_info="Port 8888 (TCP)"
        )
        card_cast.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_cast.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zerocast"] = card_cast
        grid.addWidget(card_cast, 0, 0)

        # ZeroDrop
        mod_drop = self.module_manager.get_module("zerodrop")
        drop_active = mod_drop.is_active if mod_drop else False
        card_drop = ModuleCard(
            module_id="zerodrop",
            title="ZeroDrop",
            glyph="📁",
            desc="High-speed bidirectional LAN & USB file sharing between Windows PC and Android with drag-and-drop.",
            is_enabled=drop_active,
            is_available=True,
            port_info="Port 8890 (TCP)"
        )
        card_drop.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_drop.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zerodrop"] = card_drop
        grid.addWidget(card_drop, 0, 1)

        # ZeroClip
        mod_clip = self.module_manager.get_module("zeroclip")
        clip_active = mod_clip.is_active if mod_clip else False
        card_clip = ModuleCard(
            module_id="zeroclip",
            title="ZeroClip",
            glyph="📋",
            desc="Instant bidirectional shared clipboard. Copy text or links on PC and paste directly on mobile, or vice versa in real-time.",
            is_enabled=clip_active,
            is_available=True,
            port_info="Port 8889 (TCP)"
        )
        card_clip.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_clip.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zeroclip"] = card_clip
        grid.addWidget(card_clip, 1, 0)

        # ZeroMix
        mod_mix = self.module_manager.get_module("zeromix")
        mix_active = mod_mix.is_active if mod_mix else False
        card_mix = ModuleCard(
            module_id="zeromix",
            title="ZeroMix",
            glyph="🎛️",
            desc="Virtual audio mixer & soundboard. Mix mic with music, auto-duck background audio while speaking, and trigger meme sounds wirelessly.",
            is_enabled=mix_active,
            is_available=True,
            port_info="Port 8891 (TCP)"
        )
        card_mix.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_mix.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zeromix"] = card_mix
        grid.addWidget(card_mix, 1, 1)

        # ZeroDisplay
        mod_display = self.module_manager.get_module("zerodisplay")
        display_active = mod_display.is_active if mod_display else False
        card_display = ModuleCard(
            module_id="zerodisplay",
            title="ZeroDisplay",
            glyph="🖥️",
            desc="Wireless PC Screen Mirror & Remote Touch Control. Turn your Android tablet or phone into a remote display with full touch gestures.",
            is_enabled=display_active,
            is_available=True,
            port_info="Port 8892 (TCP)"
        )
        card_display.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_display.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zerodisplay"] = card_display
        grid.addWidget(card_display, 2, 0)

        # ZeroCam
        mod_cam = self.module_manager.get_module("zerocam")
        cam_active = mod_cam.is_active if mod_cam else False
        card_cam = ModuleCard(
            module_id="zerocam",
            title="ZeroCam [Beta]",
            glyph="📷",
            desc="Wireless mobile webcam & OBS/Discord Virtual Camera Feeder. [Status: Beta / อยู่ระหว่างปรับปรุงประสิทธิภาพและความคมชัด]",
            is_enabled=cam_active,
            is_available=True,
            port_info="Port 8893 (TCP)"
        )
        card_cam.toggle_clicked.connect(self.module_toggle_requested.emit)
        card_cam.open_clicked.connect(self.navigate_to_module.emit)
        self.cards["zerocam"] = card_cam
        grid.addWidget(card_cam, 2, 1)

        layout.addLayout(grid)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _on_module_toggled(self, module_id: str, is_active: bool):
        if module_id in self.cards:
            self.cards[module_id].set_active_state(is_active)
