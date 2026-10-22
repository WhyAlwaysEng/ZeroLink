"""ZeroLink Hub - ZeroDisplay Module
Turns mobile phone or tablet into an extended 2nd monitor with wireless screen streaming and remote touch control.
"""

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QSlider, QCheckBox, QScrollArea
)

from core.base_module import BaseModule
from core.display_server import DisplayServer
from modules.zerodisplay.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


class ZeroDisplayModule(BaseModule):
    """ZeroDisplay Module: PC to Mobile Wireless Secondary Display & Remote Touchpad."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self.server = DisplayServer(port=self.port, parent=self)

        self._widget: Optional[QWidget] = None
        self._is_active = False

        # UI elements
        self.status_pill: Optional[QLabel] = None
        self.client_pill: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None
        self.combo_monitors: Optional[QComboBox] = None
        self.slider_fps: Optional[QSlider] = None
        self.lbl_fps_val: Optional[QLabel] = None
        self.slider_quality: Optional[QSlider] = None
        self.lbl_quality_val: Optional[QLabel] = None
        self.chk_touch: Optional[QCheckBox] = None
        self.lbl_stat_fps: Optional[QLabel] = None
        self.lbl_stat_bitrate: Optional[QLabel] = None

        # Wire server signals
        self.server.stats_updated.connect(self._on_stats_updated)
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
            if self.status_pill:
                self.status_pill.setText("● DISPLAY SERVER ACTIVE")
                self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("Disable Display Server")
            self.status_changed.emit(self.module_id, "ZeroDisplay server running")
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
            self.btn_power.setText("Enable Display Server")
        self.status_changed.emit(self.module_id, "ZeroDisplay server stopped")
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

        self.btn_power = QPushButton("Disable Display Server" if self.is_active else "Enable Display Server")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● DISPLAY SERVER ACTIVE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("📱 Mobile: 0 Connected")
        self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        bar_layout.addStretch()

        port_info = QLabel(f"Port: {self.port} • IP: {self.local_ip}")
        port_info.setStyleSheet("color: #6B7280; font-size: 11px;")
        bar_layout.addWidget(port_info)

        root_layout.addWidget(top_bar)

        # Scrollable Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(28, 20, 28, 24)
        content_layout.setSpacing(16)

        # Info Header Banner
        banner = QFrame()
        banner.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setSpacing(6)

        b_title = QLabel("🖥️ ZeroDisplay: Extended 2nd Monitor for PC")
        b_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        b_title.setStyleSheet("color: #111827;")
        banner_layout.addWidget(b_title)

        b_sub = QLabel("Stream your PC screen or secondary monitor to your Android tablet / phone with ultra-low latency. Put Discord, Spotify, or chat windows on your tablet beside your PC, and touch to click or drag!")
        b_sub.setFont(QFont("Segoe UI", 10))
        b_sub.setStyleSheet("color: #6B7280;")
        b_sub.setWordWrap(True)
        banner_layout.addWidget(b_sub)
        content_layout.addWidget(banner)

        # Settings Card
        cfg_card = QFrame()
        cfg_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 18px;")
        cfg_layout = QVBoxLayout(cfg_card)
        cfg_layout.setSpacing(14)

        card_title = QLabel("⚙️ Stream Configuration")
        card_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        card_title.setStyleSheet("color: #111827;")
        cfg_layout.addWidget(card_title)

        # Monitor Selector Row
        mon_row = QHBoxLayout()
        mon_row.setSpacing(12)
        lbl_mon = QLabel("Select PC Display:")
        lbl_mon.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        lbl_mon.setStyleSheet("color: #374151; min-width: 140px;")
        mon_row.addWidget(lbl_mon)

        self.combo_monitors = QComboBox()
        self._populate_monitors()
        self.combo_monitors.currentIndexChanged.connect(self._on_monitor_changed)
        mon_row.addWidget(self.combo_monitors, 1)

        btn_refresh_mon = QPushButton("🔄 Refresh")
        btn_refresh_mon.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        btn_refresh_mon.clicked.connect(self._populate_monitors)
        mon_row.addWidget(btn_refresh_mon)
        cfg_layout.addLayout(mon_row)

        # Target Frame Rate Row
        fps_row = QHBoxLayout()
        fps_row.setSpacing(12)
        lbl_fps = QLabel("Target Frame Rate:")
        lbl_fps.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        lbl_fps.setStyleSheet("color: #374151; min-width: 140px;")
        fps_row.addWidget(lbl_fps)

        self.slider_fps = QSlider(Qt.Orientation.Horizontal)
        self.slider_fps.setRange(20, 60)
        self.slider_fps.setValue(self.server.target_fps)
        self.slider_fps.valueChanged.connect(self._on_fps_changed)
        fps_row.addWidget(self.slider_fps, 1)

        self.lbl_fps_val = QLabel(f"{self.server.target_fps} FPS")
        self.lbl_fps_val.setFixedWidth(50)
        self.lbl_fps_val.setStyleSheet("font-weight: bold; color: #111827;")
        fps_row.addWidget(self.lbl_fps_val)
        cfg_layout.addLayout(fps_row)

        # Quality Slider Row
        q_row = QHBoxLayout()
        q_row.setSpacing(12)
        lbl_q = QLabel("JPEG Quality:")
        lbl_q.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        lbl_q.setStyleSheet("color: #374151; min-width: 140px;")
        q_row.addWidget(lbl_q)

        self.slider_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(40, 95)
        self.slider_quality.setValue(self.server.quality)
        self.slider_quality.valueChanged.connect(self._on_quality_changed)
        q_row.addWidget(self.slider_quality, 1)

        self.lbl_quality_val = QLabel(f"{self.server.quality}%")
        self.lbl_quality_val.setFixedWidth(50)
        self.lbl_quality_val.setStyleSheet("font-weight: bold; color: #111827;")
        q_row.addWidget(self.lbl_quality_val)
        cfg_layout.addLayout(q_row)

        # Scale Factor (Resolution)
        scale_row = QHBoxLayout()
        scale_row.setSpacing(12)
        lbl_sc = QLabel("Resolution Scale:")
        lbl_sc.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        lbl_sc.setStyleSheet("color: #374151; min-width: 140px;")
        scale_row.addWidget(lbl_sc)

        self.combo_scale = QComboBox()
        self.combo_scale.addItem("100% (Native Full Resolution)", 1.0)
        self.combo_scale.addItem("75% (Balanced High Speed)", 0.75)
        self.combo_scale.addItem("50% (Ultra Low Bandwidth)", 0.50)
        self.combo_scale.currentIndexChanged.connect(self._on_scale_changed)
        scale_row.addWidget(self.combo_scale, 1)
        cfg_layout.addLayout(scale_row)

        # Touch Control Toggle
        self.chk_touch = QCheckBox("👆 Enable Remote Touch & Stylus Control (Control PC cursor from mobile screen)")
        self.chk_touch.setChecked(self.server.enable_touch)
        self.chk_touch.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.chk_touch.setStyleSheet("color: #111827; margin-top: 6px;")
        self.chk_touch.toggled.connect(self._on_touch_toggled)
        cfg_layout.addWidget(self.chk_touch)

        content_layout.addWidget(cfg_card)

        # Live Performance Stats Card
        stats_card = QFrame()
        stats_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 18px;")
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setSpacing(12)

        st_title = QLabel("📊 Live Stream Metrics")
        st_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        st_title.setStyleSheet("color: #111827;")
        stats_layout.addWidget(st_title)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(20)

        # FPS chip
        self.lbl_stat_fps = QLabel("⚡ 0 FPS")
        self.lbl_stat_fps.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_stat_fps.setStyleSheet("background-color: #F0FDF4; color: #166534; padding: 8px 16px; border-radius: 8px; border: 1px solid #BBF7D0;")
        metrics_row.addWidget(self.lbl_stat_fps)

        # Bitrate chip
        self.lbl_stat_bitrate = QLabel("📊 0.0 Mbps")
        self.lbl_stat_bitrate.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_stat_bitrate.setStyleSheet("background-color: #F5F3FF; color: #6D28D9; padding: 8px 16px; border-radius: 8px; border: 1px solid #DDD6FE;")
        metrics_row.addWidget(self.lbl_stat_bitrate)

        metrics_row.addStretch()
        stats_layout.addLayout(metrics_row)
        content_layout.addWidget(stats_card)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll, 1)

        self._widget = container

    def _populate_monitors(self):
        if not self.combo_monitors:
            return
        self.combo_monitors.blockSignals(True)
        self.combo_monitors.clear()
        monitors = self.server.get_monitors_list()
        for m in monitors:
            self.combo_monitors.addItem(m["name"], m["index"])
        self.combo_monitors.blockSignals(False)

    def _on_monitor_changed(self, idx: int):
        val = self.combo_monitors.currentData()
        if val is not None:
            self.server.selected_monitor_idx = int(val)

    def _on_fps_changed(self, val: int):
        self.server.target_fps = val
        if self.lbl_fps_val:
            self.lbl_fps_val.setText(f"{val} FPS")

    def _on_quality_changed(self, val: int):
        self.server.quality = val
        if self.lbl_quality_val:
            self.lbl_quality_val.setText(f"{val}%")

    def _on_scale_changed(self, idx: int):
        val = self.combo_scale.currentData()
        if val is not None:
            self.server.scale_factor = float(val)

    def _on_touch_toggled(self, checked: bool):
        self.server.enable_touch = checked

    def _toggle_power(self):
        if self.is_active:
            self.stop_service()
            self.state_changed.emit(self.module_id, False)
        else:
            self.start_service()
            self.state_changed.emit(self.module_id, True)

    def _on_stats_updated(self, fps: float, bitrate_mbps: float):
        if self.lbl_stat_fps:
            self.lbl_stat_fps.setText(f"⚡ {fps:.0f} FPS")
        if self.lbl_stat_bitrate:
            self.lbl_stat_bitrate.setText(f"📊 {bitrate_mbps:.1f} Mbps")

    def _on_client_connected(self, ip: str, model: str):
        if self.client_pill:
            count = len(self.server.get_connected_clients())
            self.client_pill.setText(f"📱 Mobile: {count} Connected ({model})")
            self.client_pill.setStyleSheet("color: #059669; background: #ECFDF5; border: 1px solid #A7F3D0; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;")

    def _on_client_disconnected(self, ip: str):
        if self.client_pill:
            count = len(self.server.get_connected_clients())
            if count == 0:
                self.client_pill.setText("📱 Mobile: 0 Connected")
                self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
            else:
                self.client_pill.setText(f"📱 Mobile: {count} Connected")
