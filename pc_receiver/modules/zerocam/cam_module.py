"""ZeroLink Hub - ZeroCam Module
Wireless HD/4K mobile camera receiver with Virtual Webcam bridging for Discord, OBS, and Zoom.
"""

import os
import time
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QCheckBox, QComboBox, QScrollArea, QFileDialog
)

from core.base_module import BaseModule
from core.cam_server import CamServer
from core.adb_helper import AdbManager
from modules.zerocam.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


class ZeroCamModule(BaseModule):
    """ZeroCam Module: Wireless Mobile Webcam & OBS Virtual Camera Feeder."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self.adb_manager = AdbManager()
        self.server = CamServer(port=self.port, parent=self)

        self._widget: Optional[QWidget] = None
        self._is_active = False

        # Latest frame for snapshot
        self._last_qimage: Optional[QImage] = None

        # UI elements
        self.status_pill: Optional[QLabel] = None
        self.client_pill: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None
        self.preview_lbl: Optional[QLabel] = None
        self.btn_vcam_toggle: Optional[QPushButton] = None
        self.lbl_vcam_status: Optional[QLabel] = None
        self.lbl_stat_fps: Optional[QLabel] = None
        self.lbl_stat_bitrate: Optional[QLabel] = None

        # Wire server signals
        self.server.stats_updated.connect(self._on_stats_updated)
        self.server.frame_ready.connect(self._on_frame_ready)
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
                self.status_pill.setText("● WEBCAM SERVER ACTIVE")
                self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("Disable Cam Server")
            self.status_changed.emit(self.module_id, "ZeroCam server running")
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
            self.btn_power.setText("Enable Cam Server")
        self.status_changed.emit(self.module_id, "ZeroCam server stopped")
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

        self.btn_power = QPushButton("Disable Cam Server" if self.is_active else "Enable Cam Server")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● WEBCAM SERVER ACTIVE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("📱 Camera: Offline")
        self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        bar_layout.addStretch()

        port_info = QLabel(f"Port: {self.port} • IP: {self.local_ip}")
        port_info.setStyleSheet("color: #6B7280; font-size: 11px;")
        bar_layout.addWidget(port_info)

        root_layout.addWidget(top_bar)

        # Scrollable Viewport
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(28, 20, 28, 24)
        content_layout.setSpacing(20)

        # Left Column: Video Viewport Preview
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        preview_card = QFrame()
        preview_card.setStyleSheet("background-color: #000000; border-radius: 12px; border: 1px solid #E5E7EB;")
        p_layout = QVBoxLayout(preview_card)
        p_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_lbl = QLabel("📷 Waiting for Camera Stream...")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: bold;")
        self.preview_lbl.setMinimumSize(640, 380)
        p_layout.addWidget(self.preview_lbl)
        left_col.addWidget(preview_card, 1)

        # Snapshot & Quick actions below preview
        snap_row = QHBoxLayout()
        btn_snapshot = QPushButton("📸 Take Photo Snapshot")
        btn_snapshot.setStyleSheet("padding: 8px 16px; font-weight: bold; background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px;")
        btn_snapshot.clicked.connect(self._take_snapshot)
        snap_row.addWidget(btn_snapshot)

        self.lbl_snap_status = QLabel("")
        self.lbl_snap_status.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        snap_row.addWidget(self.lbl_snap_status)
        snap_row.addStretch()
        left_col.addLayout(snap_row)

        content_layout.addLayout(left_col, 3)

        # Right Column: Controls & Virtual Webcam Setup
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Card 1: Virtual Camera Feeder
        vcam_card = QFrame()
        vcam_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        vc_layout = QVBoxLayout(vcam_card)
        vc_layout.setSpacing(12)

        vc_title = QLabel("🎥 Virtual Webcam (Discord / OBS / Zoom)")
        vc_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        vc_title.setStyleSheet("color: #111827;")
        vc_layout.addWidget(vc_title)

        vc_desc = QLabel("Exposes your phone camera as a native Windows USB Webcam so any app can select it as video input.")
        vc_desc.setFont(QFont("Segoe UI", 10))
        vc_desc.setStyleSheet("color: #6B7280;")
        vc_desc.setWordWrap(True)
        vc_layout.addWidget(vc_desc)

        self.btn_vcam_toggle = QPushButton("Start Virtual Webcam")
        self.btn_vcam_toggle.setCheckable(True)
        self.btn_vcam_toggle.setStyleSheet("""
            QPushButton {
                background-color: #111827; color: #FFFFFF; border-radius: 6px;
                padding: 8px 14px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #374151; }
        """)
        self.btn_vcam_toggle.toggled.connect(self._on_vcam_toggled)
        vc_layout.addWidget(self.btn_vcam_toggle)

        self.lbl_vcam_status = QLabel("○ Virtual Camera: Offline")
        self.lbl_vcam_status.setStyleSheet("color: #6B7280; font-size: 11px;")
        vc_layout.addWidget(self.lbl_vcam_status)
        right_col.addWidget(vcam_card)

        # Card 2: Phone Camera Controls
        ctrl_card = QFrame()
        ctrl_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        c_layout = QVBoxLayout(ctrl_card)
        c_layout.setSpacing(12)

        c_title = QLabel("📱 Mobile Camera Controls")
        c_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        c_title.setStyleSheet("color: #111827;")
        c_layout.addWidget(c_title)

        btn_row = QHBoxLayout()
        btn_switch = QPushButton("🔄 Switch Front / Back")
        btn_switch.setStyleSheet("padding: 6px 12px; font-size: 11px; font-weight: 600;")
        btn_switch.clicked.connect(lambda: self.server.send_control_command({"action": "SWITCH_CAMERA"}))
        btn_row.addWidget(btn_switch)

        btn_torch = QPushButton("💡 Toggle Torch / Flash")
        btn_torch.setStyleSheet("padding: 6px 12px; font-size: 11px; font-weight: 600;")
        btn_torch.clicked.connect(lambda: self.server.send_control_command({"action": "TOGGLE_TORCH"}))
        btn_row.addWidget(btn_torch)
        c_layout.addLayout(btn_row)

        # Resolution dropdown
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Stream Resolution:", styleSheet="font-size: 11px; font-weight: bold; min-width: 110px;"))
        combo_res = QComboBox()
        combo_res.addItem("720p HD (1280x720 • Smooth 30-60 FPS Recommended)", (1280, 720))
        combo_res.addItem("1080p Full HD (1920x1080 • High Detail)", (1920, 1080))
        combo_res.addItem("4K Ultra HD (3840x2160 • Studio / USB Cable)", (3840, 2160))
        combo_res.currentIndexChanged.connect(lambda idx: self._on_remote_res_changed(combo_res.currentData()))
        res_row.addWidget(combo_res)
        c_layout.addLayout(res_row)

        # Quality dropdown
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("JPEG Quality:", styleSheet="font-size: 11px; font-weight: bold; min-width: 110px;"))
        combo_q = QComboBox()
        combo_q.addItem("65% (Fast & Smooth 30-60 FPS • ~50KB/f Recommended)", 65)
        combo_q.addItem("80% (High Clarity • ~120KB/f)", 80)
        combo_q.addItem("95% (Maximum Crystal Clarity • ~800KB/f USB Cable)", 95)
        combo_q.currentIndexChanged.connect(lambda idx: self.server.send_control_command({"action": "SET_QUALITY", "quality": combo_q.currentData()}))
        q_row.addWidget(combo_q)
        c_layout.addLayout(q_row)

        # Zoom slider
        z_row = QHBoxLayout()
        z_row.addWidget(QLabel("Camera Zoom:", styleSheet="font-size: 11px; font-weight: bold; min-width: 110px;"))
        slider_zoom = QSlider(Qt.Orientation.Horizontal)
        slider_zoom.setRange(0, 100)
        slider_zoom.setValue(0)
        slider_zoom.valueChanged.connect(lambda val: self.server.send_control_command({"action": "SET_ZOOM", "zoom": val / 100.0}))
        z_row.addWidget(slider_zoom)
        c_layout.addLayout(z_row)

        right_col.addWidget(ctrl_card)

        # Card: USB Cable Direct Link (0ms Latency)
        usb_card = QFrame()
        usb_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        u_layout = QVBoxLayout(usb_card)
        u_layout.setSpacing(8)

        u_title = QLabel("⚡ USB Cable High-Speed Mode")
        u_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        u_title.setStyleSheet("color: #111827;")
        u_layout.addWidget(u_title)

        u_desc = QLabel("Plug phone via USB for rock-solid 60 FPS without Wi-Fi interference. Click button below to activate tunnel:")
        u_desc.setFont(QFont("Segoe UI", 10))
        u_desc.setStyleSheet("color: #6B7280;")
        u_desc.setWordWrap(True)
        u_layout.addWidget(u_desc)

        btn_usb_tunnel = QPushButton("⚡ Activate USB Cable Tunnel (Port 8893)")
        btn_usb_tunnel.setStyleSheet("""
            QPushButton {
                background-color: #0284C7; color: #FFFFFF; border-radius: 6px;
                padding: 7px 12px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0369A1; }
        """)
        lbl_usb_status = QLabel("Tip: After clicking, select '⚡ USB Cable (127.0.0.1)' on your phone.")
        lbl_usb_status.setStyleSheet("color: #6B7280; font-size: 10px;")

        def _on_usb_click():
            if not self.adb_manager.is_available():
                lbl_usb_status.setText("❌ ADB not detected. Please enable USB Debugging.")
                lbl_usb_status.setStyleSheet("color: #DC2626; font-size: 10px; font-weight: bold;")
                return
            ok, msg = self.adb_manager.reverse_port(self.port)
            if ok:
                lbl_usb_status.setText("✅ USB Tunnel Active! On your phone, connect to 127.0.0.1.")
                lbl_usb_status.setStyleSheet("color: #059669; font-size: 10px; font-weight: bold;")
            else:
                lbl_usb_status.setText(f"❌ {msg}")
                lbl_usb_status.setStyleSheet("color: #DC2626; font-size: 10px;")

        btn_usb_tunnel.clicked.connect(_on_usb_click)
        u_layout.addWidget(btn_usb_tunnel)
        u_layout.addWidget(lbl_usb_status)
        right_col.addWidget(usb_card)

        # Card 3: Image Adjustments & Mirroring
        adj_card = QFrame()
        adj_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px;")
        a_layout = QVBoxLayout(adj_card)
        a_layout.setSpacing(10)

        a_title = QLabel("🎨 Video Adjustments & Enhancer")
        a_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        a_title.setStyleSheet("color: #111827;")
        a_layout.addWidget(a_title)

        chk_mirror = QCheckBox("🪞 Mirror Camera (Flip Horizontal)")
        chk_mirror.setChecked(self.server.flip_horizontal)
        chk_mirror.toggled.connect(lambda checked: setattr(self.server, "flip_horizontal", checked))
        a_layout.addWidget(chk_mirror)

        chk_flip_v = QCheckBox("Flip Vertical")
        chk_flip_v.setChecked(self.server.flip_vertical)
        chk_flip_v.toggled.connect(lambda checked: setattr(self.server, "flip_vertical", checked))
        a_layout.addWidget(chk_flip_v)

        # Orientation / Rotation Control
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Orientation:", styleSheet="font-size: 11px; font-weight: bold; min-width: 100px;"))
        btn_rotate = QPushButton("🔄 Rotate +90°")
        btn_rotate.setStyleSheet("padding: 5px 12px; font-size: 11px; font-weight: 600;")
        lbl_rot_status = QLabel("Auto (0°)")
        lbl_rot_status.setStyleSheet("color: #6B7280; font-size: 10px;")

        def _cycle_rotation():
            self.server.manual_rotation = (self.server.manual_rotation + 90) % 360
            lbl_rot_status.setText(f"Manual Offset: +{self.server.manual_rotation}°")

        btn_rotate.clicked.connect(_cycle_rotation)
        rot_row.addWidget(btn_rotate)
        rot_row.addWidget(lbl_rot_status)
        rot_row.addStretch()
        a_layout.addLayout(rot_row)

        # Detail Enhancer / Sharpness
        sh_row = QHBoxLayout()
        sh_row.addWidget(QLabel("Detail Sharpness:", styleSheet="font-size: 11px; font-weight: bold; min-width: 100px;"))
        slider_sharp = QSlider(Qt.Orientation.Horizontal)
        slider_sharp.setRange(0, 150)
        slider_sharp.setValue(int(self.server.sharpness * 100))
        slider_sharp.valueChanged.connect(lambda val: setattr(self.server, "sharpness", val / 100.0))
        sh_row.addWidget(slider_sharp)
        a_layout.addLayout(sh_row)

        # Saturation
        sat_row = QHBoxLayout()
        sat_row.addWidget(QLabel("Color Vibrancy:", styleSheet="font-size: 11px; font-weight: bold; min-width: 100px;"))
        slider_sat = QSlider(Qt.Orientation.Horizontal)
        slider_sat.setRange(50, 200)
        slider_sat.setValue(int(self.server.saturation * 100))
        slider_sat.valueChanged.connect(lambda val: setattr(self.server, "saturation", val / 100.0))
        sat_row.addWidget(slider_sat)
        a_layout.addLayout(sat_row)

        # Brightness
        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Brightness:", styleSheet="font-size: 11px; font-weight: bold; min-width: 100px;"))
        slider_bright = QSlider(Qt.Orientation.Horizontal)
        slider_bright.setRange(-50, 50)
        slider_bright.setValue(self.server.brightness)
        slider_bright.valueChanged.connect(lambda val: setattr(self.server, "brightness", val))
        b_row.addWidget(slider_bright)
        a_layout.addLayout(b_row)

        # Contrast
        co_row = QHBoxLayout()
        co_row.addWidget(QLabel("Contrast:", styleSheet="font-size: 11px; font-weight: bold; min-width: 100px;"))
        slider_contrast = QSlider(Qt.Orientation.Horizontal)
        slider_contrast.setRange(50, 150)
        slider_contrast.setValue(int(self.server.contrast * 100))
        slider_contrast.valueChanged.connect(lambda val: setattr(self.server, "contrast", val / 100.0))
        co_row.addWidget(slider_contrast)
        a_layout.addLayout(co_row)
        a_layout.addLayout(co_row)

        right_col.addWidget(adj_card)

        # Card 4: Metrics
        m_card = QFrame()
        m_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 14px;")
        m_layout = QHBoxLayout(m_card)
        m_layout.setSpacing(12)

        self.lbl_stat_fps = QLabel("⚡ 0 FPS")
        self.lbl_stat_fps.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_stat_fps.setStyleSheet("color: #059669;")
        m_layout.addWidget(self.lbl_stat_fps)

        self.lbl_stat_bitrate = QLabel("📊 0.0 Mbps")
        self.lbl_stat_bitrate.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_stat_bitrate.setStyleSheet("color: #7C3AED;")
        m_layout.addWidget(self.lbl_stat_bitrate)
        m_layout.addStretch()
        right_col.addWidget(m_card)

        right_col.addStretch()
        content_layout.addLayout(right_col, 2)

        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll, 1)

        self._widget = container

    def _on_frame_ready(self, q_img: QImage):
        self._last_qimage = q_img
        if self.preview_lbl:
            target_size = self.preview_lbl.size()
            if target_size.width() <= 10 or target_size.height() <= 10:
                target_size = self.preview_lbl.minimumSize()
            pix = QPixmap.fromImage(q_img)
            self.preview_lbl.setPixmap(
                pix.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
            )

    def _on_remote_res_changed(self, res_tuple):
        if not res_tuple:
            return
        w, h = res_tuple
        self.server._vcam_w = w
        self.server._vcam_h = h
        self.server.send_control_command({"action": "SET_RESOLUTION", "width": w, "height": h})

    def _on_vcam_toggled(self, checked: bool):
        if checked:
            ok = self.server.start_virtual_camera(width=self.server._vcam_w, height=self.server._vcam_h, fps=30)
            if ok:
                self.btn_vcam_toggle.setText("Stop Virtual Webcam")
                self.btn_vcam_toggle.setStyleSheet("background-color: #DC2626; color: #FFFFFF; border-radius: 6px; padding: 8px 14px; font-weight: bold;")
                self.lbl_vcam_status.setText(f"● Active: Broadcasting {self.server._vcam_w}x{self.server._vcam_h} to Discord / OBS")
                self.lbl_vcam_status.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
            else:
                self.btn_vcam_toggle.setChecked(False)
                self.lbl_vcam_status.setText("❌ Failed to initialize Virtual Camera driver.")
                self.lbl_vcam_status.setStyleSheet("color: #DC2626; font-size: 11px;")
        else:
            self.server.stop_virtual_camera()
            self.btn_vcam_toggle.setText("Start Virtual Webcam")
            self.btn_vcam_toggle.setStyleSheet("background-color: #111827; color: #FFFFFF; border-radius: 6px; padding: 8px 14px; font-weight: bold;")
            self.lbl_vcam_status.setText("○ Virtual Camera: Offline")
            self.lbl_vcam_status.setStyleSheet("color: #6B7280; font-size: 11px;")

    def _take_snapshot(self):
        if not self._last_qimage:
            return
        pic_dir = os.path.join(os.path.expanduser("~"), "Pictures", "ZeroCam")
        os.makedirs(pic_dir, exist_ok=True)
        fname = f"snapshot_{int(time.time())}.jpg"
        fpath = os.path.join(pic_dir, fname)
        self._last_qimage.save(fpath, "JPG", 95)
        self.lbl_snap_status.setText(f"✅ Saved to {fname}")

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
            is_usb = ip.strip() in ("127.0.0.1", "localhost", "::1")
            mode = "⚡ USB" if is_usb else "📡 Wi-Fi"
            self.client_pill.setText(f"📱 Cam: Connected via {mode} ({model})")
            if is_usb:
                self.client_pill.setStyleSheet("color: #0284C7; background: #F0F9FF; border: 1px solid #BAE6FD; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;")
            else:
                self.client_pill.setStyleSheet("color: #059669; background: #ECFDF5; border: 1px solid #A7F3D0; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;")

    def _on_client_disconnected(self, ip: str):
        if self.client_pill:
            self.client_pill.setText("📱 Camera: Offline")
            self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        if self.preview_lbl:
            self.preview_lbl.clear()
            self.preview_lbl.setText("📷 Waiting for Camera Stream...")
