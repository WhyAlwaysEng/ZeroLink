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
    QFrame, QSlider, QCheckBox, QComboBox, QScrollArea, QFileDialog,
    QTabWidget, QSizePolicy
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
                self.btn_power.setText("⏻ Disable Cam Server")
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
            self.btn_power.setText("⏻ Enable Cam Server")
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

        self.btn_power = QPushButton("⏻ Disable Cam Server" if self.is_active else "⏻ Enable Cam Server")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● WEBCAM SERVER ACTIVE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("◉ Camera: Offline")
        self.client_pill.setStyleSheet("color: #4B5563; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        bar_layout.addStretch()

        port_info = QLabel(f"Port: {self.port} • IP: {self.local_ip}")
        port_info.setStyleSheet("color: #4B5563; font-size: 11px;")
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

        self.preview_lbl = QLabel("◉ Waiting for Camera Stream...")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: bold;")
        self.preview_lbl.setMinimumSize(440, 248)
        self.preview_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        p_layout.addWidget(self.preview_lbl)
        left_col.addWidget(preview_card, 1)

        # Snapshot & Quick actions below preview
        snap_row = QHBoxLayout()
        btn_snapshot = QPushButton("⧇ Photo Snapshot")
        btn_snapshot.setStyleSheet("padding: 6px 14px; font-size: 11px; font-weight: bold; background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px;")
        btn_snapshot.clicked.connect(self._take_snapshot)
        snap_row.addWidget(btn_snapshot)

        self.lbl_snap_status = QLabel("")
        self.lbl_snap_status.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        snap_row.addWidget(self.lbl_snap_status)
        snap_row.addStretch()

        self.lbl_stat_fps = QLabel("0 FPS")
        self.lbl_stat_fps.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_stat_fps.setStyleSheet("color: #111827; background: #E5E7EB; padding: 3px 8px; border-radius: 4px;")
        snap_row.addWidget(self.lbl_stat_fps)

        self.lbl_stat_bitrate = QLabel("0.0 Mbps")
        self.lbl_stat_bitrate.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_stat_bitrate.setStyleSheet("color: #4B5563; background: #F3F4F6; padding: 3px 8px; border-radius: 4px;")
        snap_row.addWidget(self.lbl_stat_bitrate)

        left_col.addLayout(snap_row)

        content_layout.addLayout(left_col, 3)

        # Right Column: Tabbed Controls (Ultra-Compact, Fits on All Screens)
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                background-color: #FFFFFF;
                padding: 10px;
            }
            QTabBar::tab {
                background: #F3F4F6;
                color: #4B5563;
                padding: 6px 12px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 11px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #111827;
                color: #FFFFFF;
            }
        """)

        # Tab 1: 4K Framing & Virtual Cam
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(4, 4, 4, 4)
        tab1_layout.setSpacing(10)

        # Virtual Cam Section
        vc_box = QFrame()
        vc_box.setStyleSheet("background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px;")
        vc_layout = QVBoxLayout(vc_box)
        vc_layout.setSpacing(6)

        self.btn_vcam_toggle = QPushButton("Start Virtual Webcam")
        self.btn_vcam_toggle.setCheckable(True)
        self.btn_vcam_toggle.setStyleSheet("""
            QPushButton {
                background-color: #111827; color: #FFFFFF; border-radius: 6px;
                padding: 7px 12px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #374151; }
        """)
        self.btn_vcam_toggle.toggled.connect(self._on_vcam_toggled)
        vc_layout.addWidget(self.btn_vcam_toggle)

        self.lbl_vcam_status = QLabel("○ Virtual Camera: Offline")
        self.lbl_vcam_status.setStyleSheet("color: #6B7280; font-size: 10px;")
        vc_layout.addWidget(self.lbl_vcam_status)

        v_res_row = QHBoxLayout()
        v_res_row.addWidget(QLabel("VCam Output Res:", styleSheet="font-size: 10px; font-weight: bold; min-width: 100px;"))
        combo_vcam_res = QComboBox()
        combo_vcam_res.addItem("1080p Full HD (Discord/Zoom Standard)", (1920, 1080))
        combo_vcam_res.addItem("4K Ultra HD (Full Canvas)", (3840, 2160))
        combo_vcam_res.addItem("720p HD (Low Bandwidth)", (1280, 720))
        def _on_vcam_res_changed(idx):
            data = combo_vcam_res.currentData()
            if data:
                self.server._vcam_w, self.server._vcam_h = data
                if self.server.enable_virtual_cam:
                    self.server.start_virtual_camera(self.server._vcam_w, self.server._vcam_h, 30)
        combo_vcam_res.currentIndexChanged.connect(_on_vcam_res_changed)
        v_res_row.addWidget(combo_vcam_res)
        vc_layout.addLayout(v_res_row)
        tab1_layout.addWidget(vc_box)

        # 4K Digital Framing & Crop Studio
        cr_box = QFrame()
        cr_box.setStyleSheet("background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px;")
        cr_layout = QVBoxLayout(cr_box)
        cr_layout.setSpacing(6)

        chk_crop = QCheckBox("✂️ Enable 4K Framing & Lossless Crop (ePTZ)")
        chk_crop.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        chk_crop.setChecked(self.server.crop_enabled)
        chk_crop.toggled.connect(lambda checked: setattr(self.server, "crop_enabled", checked))
        cr_layout.addWidget(chk_crop)

        # Zoom
        zoom_row = QHBoxLayout()
        lbl_zoom_val = QLabel("1.0x (Wide)")
        lbl_zoom_val.setStyleSheet("font-size: 10px; font-weight: bold; min-width: 80px; color: #111827;")
        zoom_row.addWidget(lbl_zoom_val)
        slider_crop_zoom = QSlider(Qt.Orientation.Horizontal)
        slider_crop_zoom.setRange(100, 350)
        slider_crop_zoom.setValue(int(self.server.crop_zoom * 100))
        def _on_zoom_changed(val):
            z = val / 100.0
            self.server.crop_zoom = z
            lbl_zoom_val.setText(f"{z:.1f}x ({'Wide' if z <= 1.05 else 'Cropped'})")
        slider_crop_zoom.valueChanged.connect(_on_zoom_changed)
        zoom_row.addWidget(slider_crop_zoom)
        cr_layout.addLayout(zoom_row)

        # Pan
        pan_row = QHBoxLayout()
        pan_row.addWidget(QLabel("Pan (Left/Right):", styleSheet="font-size: 10px; font-weight: bold; min-width: 80px;"))
        slider_crop_pan = QSlider(Qt.Orientation.Horizontal)
        slider_crop_pan.setRange(-100, 100)
        slider_crop_pan.setValue(int(self.server.crop_pan * 100))
        slider_crop_pan.valueChanged.connect(lambda val: setattr(self.server, "crop_pan", val / 100.0))
        pan_row.addWidget(slider_crop_pan)
        cr_layout.addLayout(pan_row)

        # Tilt
        tilt_row = QHBoxLayout()
        tilt_row.addWidget(QLabel("Tilt (Up/Down):", styleSheet="font-size: 10px; font-weight: bold; min-width: 80px;"))
        slider_crop_tilt = QSlider(Qt.Orientation.Horizontal)
        slider_crop_tilt.setRange(-100, 100)
        slider_crop_tilt.setValue(int(self.server.crop_tilt * 100))
        slider_crop_tilt.valueChanged.connect(lambda val: setattr(self.server, "crop_tilt", val / 100.0))
        tilt_row.addWidget(slider_crop_tilt)
        cr_layout.addLayout(tilt_row)

        # Presets
        preset_row = QHBoxLayout()
        btn_preset_wide = QPushButton("Full Wide (1.0x)")
        btn_preset_wide.setStyleSheet("padding: 3px 6px; font-size: 10px;")
        def _apply_wide():
            chk_crop.setChecked(False)
            slider_crop_zoom.setValue(100)
            slider_crop_pan.setValue(0)
            slider_crop_tilt.setValue(0)
        btn_preset_wide.clicked.connect(_apply_wide)
        preset_row.addWidget(btn_preset_wide)

        btn_preset_bust = QPushButton("Bust Shot (1.4x)")
        btn_preset_bust.setStyleSheet("padding: 3px 6px; font-size: 10px;")
        def _apply_bust():
            chk_crop.setChecked(True)
            slider_crop_zoom.setValue(140)
            slider_crop_pan.setValue(0)
            slider_crop_tilt.setValue(-10)
        btn_preset_bust.clicked.connect(_apply_bust)
        preset_row.addWidget(btn_preset_bust)

        btn_preset_face = QPushButton("Face (2.0x)")
        btn_preset_face.setStyleSheet("padding: 3px 6px; font-size: 10px;")
        def _apply_face():
            chk_crop.setChecked(True)
            slider_crop_zoom.setValue(200)
            slider_crop_pan.setValue(0)
            slider_crop_tilt.setValue(-15)
        btn_preset_face.clicked.connect(_apply_face)
        preset_row.addWidget(btn_preset_face)

        btn_reset_crop = QPushButton("↺ Reset")
        btn_reset_crop.setStyleSheet("padding: 3px 6px; font-size: 10px;")
        btn_reset_crop.clicked.connect(_apply_wide)
        preset_row.addWidget(btn_reset_crop)
        cr_layout.addLayout(preset_row)
        tab1_layout.addWidget(cr_box)

        tab1_layout.addStretch()
        tabs.addTab(tab1, "✂️ 4K Studio & VCam")

        # Tab 2: Mobile Camera Controls
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(4, 4, 4, 4)
        tab2_layout.setSpacing(8)

        btn_row = QHBoxLayout()
        btn_switch = QPushButton("↻ Switch Front / Back")
        btn_switch.setStyleSheet("padding: 5px 10px; font-size: 11px; font-weight: 600;")
        btn_switch.clicked.connect(lambda: self.server.send_control_command({"action": "SWITCH_CAMERA"}))
        btn_row.addWidget(btn_switch)

        btn_torch = QPushButton("◈ Toggle Torch / Flash")
        btn_torch.setStyleSheet("padding: 5px 10px; font-size: 11px; font-weight: 600;")
        btn_torch.clicked.connect(lambda: self.server.send_control_command({"action": "TOGGLE_TORCH"}))
        btn_row.addWidget(btn_torch)
        tab2_layout.addLayout(btn_row)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Stream Resolution:", styleSheet="font-size: 10px; font-weight: bold; min-width: 100px;"))
        combo_res = QComboBox()
        combo_res.addItem("1080p Full HD (1920x1080 • Smooth 60 FPS)", (1920, 1080))
        combo_res.addItem("4K Ultra HD (3840x2160 • Studio / USB Cable)", (3840, 2160))
        combo_res.addItem("720p HD (1280x720 • Fast)", (1280, 720))
        combo_res.currentIndexChanged.connect(lambda idx: self._on_remote_res_changed(combo_res.currentData()))
        res_row.addWidget(combo_res)
        tab2_layout.addLayout(res_row)

        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("Stream Quality:", styleSheet="font-size: 10px; font-weight: bold; min-width: 100px;"))
        combo_q = QComboBox()
        combo_q.addItem("82% (True Color High Clarity • Recommended)", 82)
        combo_q.addItem("95% (Maximum Studio Clarity)", 95)
        combo_q.addItem("65% (Fast Low Bandwidth)", 65)
        combo_q.currentIndexChanged.connect(lambda idx: self.server.send_control_command({"action": "SET_QUALITY", "quality": combo_q.currentData()}))
        q_row.addWidget(combo_q)
        tab2_layout.addLayout(q_row)

        z_row = QHBoxLayout()
        z_row.addWidget(QLabel("Camera Lens Zoom:", styleSheet="font-size: 10px; font-weight: bold; min-width: 100px;"))
        slider_zoom = QSlider(Qt.Orientation.Horizontal)
        slider_zoom.setRange(0, 100)
        slider_zoom.setValue(0)
        slider_zoom.valueChanged.connect(lambda val: self.server.send_control_command({"action": "SET_ZOOM", "zoom": val / 100.0}))
        z_row.addWidget(slider_zoom)
        tab2_layout.addLayout(z_row)

        tab2_layout.addStretch()
        tabs.addTab(tab2, "📱 Mobile Camera")

        # Tab 3: Adjustments & USB Link
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.setContentsMargins(4, 4, 4, 4)
        tab3_layout.setSpacing(6)

        chk_mirror = QCheckBox("Mirror Camera (Flip Horizontal)")
        chk_mirror.setChecked(self.server.flip_horizontal)
        chk_mirror.toggled.connect(lambda checked: setattr(self.server, "flip_horizontal", checked))
        tab3_layout.addWidget(chk_mirror)

        chk_flip_v = QCheckBox("Flip Vertical")
        chk_flip_v.setChecked(self.server.flip_vertical)
        chk_flip_v.toggled.connect(lambda checked: setattr(self.server, "flip_vertical", checked))
        tab3_layout.addWidget(chk_flip_v)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Orientation:", styleSheet="font-size: 10px; font-weight: bold; min-width: 90px;"))
        btn_rotate = QPushButton("↻ Rotate +90°")
        btn_rotate.setStyleSheet("padding: 3px 8px; font-size: 10px;")
        lbl_rot_status = QLabel("Auto (0°)")
        lbl_rot_status.setStyleSheet("color: #6B7280; font-size: 10px;")
        def _cycle_rotation():
            self.server.manual_rotation = (self.server.manual_rotation + 90) % 360
            lbl_rot_status.setText(f"+{self.server.manual_rotation}°")
        btn_rotate.clicked.connect(_cycle_rotation)
        rot_row.addWidget(btn_rotate)
        rot_row.addWidget(lbl_rot_status)
        rot_row.addStretch()
        tab3_layout.addLayout(rot_row)

        sh_row = QHBoxLayout()
        sh_row.addWidget(QLabel("Detail Sharpness:", styleSheet="font-size: 10px; font-weight: bold; min-width: 90px;"))
        slider_sharp = QSlider(Qt.Orientation.Horizontal)
        slider_sharp.setRange(0, 150)
        slider_sharp.setValue(int(self.server.sharpness * 100))
        slider_sharp.valueChanged.connect(lambda val: setattr(self.server, "sharpness", val / 100.0))
        sh_row.addWidget(slider_sharp)
        tab3_layout.addLayout(sh_row)

        sat_row = QHBoxLayout()
        sat_row.addWidget(QLabel("Color Vibrancy:", styleSheet="font-size: 10px; font-weight: bold; min-width: 90px;"))
        slider_sat = QSlider(Qt.Orientation.Horizontal)
        slider_sat.setRange(50, 200)
        slider_sat.setValue(int(self.server.saturation * 100))
        slider_sat.valueChanged.connect(lambda val: setattr(self.server, "saturation", val / 100.0))
        sat_row.addWidget(slider_sat)
        tab3_layout.addLayout(sat_row)

        # USB Tunnel Box
        usb_box = QFrame()
        usb_box.setStyleSheet("background: #F3F4F6; border-radius: 6px; padding: 6px;")
        u_box_layout = QVBoxLayout(usb_box)
        u_box_layout.setSpacing(4)
        btn_usb_tunnel = QPushButton("⌁ Activate USB Cable Tunnel (Port 8893)")
        btn_usb_tunnel.setStyleSheet("background: #111827; color: #FFFFFF; font-size: 10px; font-weight: bold; padding: 5px 10px; border-radius: 4px;")
        lbl_usb_status = QLabel("USB Mode: Connect phone to 127.0.0.1 for 0ms delay")
        lbl_usb_status.setStyleSheet("color: #4B5563; font-size: 9px;")
        def _on_usb_click():
            if not self.adb_manager.is_available():
                lbl_usb_status.setText("ADB not detected.")
                return
            ok, msg = self.adb_manager.reverse_port(self.port)
            if ok:
                lbl_usb_status.setText("USB Tunnel Active! Select 127.0.0.1 on phone.")
            else:
                lbl_usb_status.setText(f"{msg}")
        btn_usb_tunnel.clicked.connect(_on_usb_click)
        u_box_layout.addWidget(btn_usb_tunnel)
        u_box_layout.addWidget(lbl_usb_status)
        tab3_layout.addWidget(usb_box)

        tab3_layout.addStretch()
        tabs.addTab(tab3, "🎨 Tuning & Link")

        right_col.addWidget(tabs)
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
        self.server.send_control_command({"action": "SET_RESOLUTION", "width": w, "height": h})

    def _on_vcam_toggled(self, checked: bool):
        if checked:
            ok = self.server.start_virtual_camera(width=self.server._vcam_w, height=self.server._vcam_h, fps=30)
            if ok:
                self.btn_vcam_toggle.setText("Stop Virtual Webcam")
                self.btn_vcam_toggle.setStyleSheet("background-color: #DC2626; color: #FFFFFF; border-radius: 6px; padding: 8px 14px; font-weight: bold;")
                self.lbl_vcam_status.setText(f"● Active: Broadcasting {self.server._vcam_w}x{self.server._vcam_h} to Discord / OBS")
                self.lbl_vcam_status.setStyleSheet("color: #111827; font-size: 11px; font-weight: bold;")
            else:
                self.btn_vcam_toggle.setChecked(False)
                self.lbl_vcam_status.setText("Failed to initialize Virtual Camera driver.")
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
        self.lbl_snap_status.setText(f"Saved to {fname}")

    def _toggle_power(self):
        if self.is_active:
            self.stop_service()
            self.state_changed.emit(self.module_id, False)
        else:
            self.start_service()
            self.state_changed.emit(self.module_id, True)

    def _on_stats_updated(self, fps: float, bitrate_mbps: float):
        if self.lbl_stat_fps:
            self.lbl_stat_fps.setText(f"{fps:.0f} FPS")
        if self.lbl_stat_bitrate:
            self.lbl_stat_bitrate.setText(f"{bitrate_mbps:.1f} Mbps")

    def _on_client_connected(self, ip: str, model: str):
        if self.client_pill:
            is_usb = ip.strip() in ("127.0.0.1", "localhost", "::1")
            mode = "⌁ USB" if is_usb else "◫ Wi-Fi"
            self.client_pill.setText(f"◎ Cam: Connected via {mode} ({model})")
            self.client_pill.setStyleSheet("color: #111827; background: #F3F4F6; border: 1px solid #D1D5DB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold;")

    def _on_client_disconnected(self, ip: str):
        if self.client_pill:
            self.client_pill.setText("◎ Camera: Offline")
            self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        if self.preview_lbl:
            self.preview_lbl.clear()
            self.preview_lbl.setText("◎ Waiting for Camera Stream...")
