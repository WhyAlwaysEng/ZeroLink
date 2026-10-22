"""ZeroLink Hub - ZeroMix Module
Virtual Audio Mixer with Smart Auto-Ducking, Separate Monitoring & Mobile Sound Deck.
"""

import os
from typing import Optional, List, Dict
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QProgressBar, QScrollArea, QFileDialog,
    QComboBox, QCheckBox, QGridLayout, QSizePolicy
)

from core.base_module import BaseModule
from core.audio_mixer import AudioMixerEngine
from core.zeromix_service import ZeroMixService
from modules.zeromix.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, DEFAULT_PORT
)


class VUMeterWidget(QProgressBar):
    """Custom fast-rendering VU Level Meter with Green-Yellow-Red gradient."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setFixedHeight(8)
        self.setTextVisible(False)
        self.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E5E7EB;
                background-color: #F3F4F6;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #10B981, stop:0.7 #10B981, stop:0.85 #F59E0B, stop:1.0 #EF4444);
                border-radius: 3px;
            }
        """)


class ChannelStrip(QFrame):
    """Single mixer channel card with volume slider, VU meter, and mute button."""
    volume_changed = pyqtSignal(int)
    mute_toggled = pyqtSignal(bool)

    def __init__(self, title: str, glyph: str, initial_vol: int = 100, max_vol: int = 100, parent=None):
        super().__init__(parent)
        self.is_muted = False
        self.setStyleSheet("""
            ChannelStrip {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header: Glyph + Title + Mute
        hdr = QHBoxLayout()
        icon = QLabel(glyph)
        icon.setFont(QFont("Segoe UI Emoji", 14))
        hdr.addWidget(icon)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #111827;")
        hdr.addWidget(t_lbl)

        hdr.addStretch()

        self.btn_mute = QPushButton("MUTE")
        self.btn_mute.setFixedSize(56, 26)
        self.btn_mute.setStyleSheet(self._mute_style(False))
        self.btn_mute.clicked.connect(self._toggle_mute)
        hdr.addWidget(self.btn_mute)
        layout.addLayout(hdr)

        # VU Meter
        self.vu_meter = VUMeterWidget()
        layout.addWidget(self.vu_meter)

        # Volume control
        vol_box = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max_vol)
        self.slider.setValue(initial_vol)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #E5E7EB;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #111827;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #111827;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
        """)
        self.slider.valueChanged.connect(self._on_slider_changed)
        vol_box.addWidget(self.slider)

        self.lbl_vol = QLabel(f"{initial_vol}%")
        self.lbl_vol.setFixedWidth(44)
        self.lbl_vol.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_vol.setStyleSheet("color: #111827;")
        self.lbl_vol.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vol_box.addWidget(self.lbl_vol)
        layout.addLayout(vol_box)

    def _mute_style(self, muted: bool) -> str:
        if muted:
            return """
                QPushButton {
                    background-color: #EF4444;
                    color: #FFFFFF;
                    border: 1px solid #DC2626;
                    border-radius: 6px;
                    font-size: 10px;
                    font-weight: 700;
                }
            """
        return """
            QPushButton {
                background-color: #F3F4F6;
                color: #4B5563;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
                color: #111827;
            }
        """

    def _toggle_mute(self):
        self.is_muted = not self.is_muted
        self.btn_mute.setStyleSheet(self._mute_style(self.is_muted))
        self.btn_mute.setText("MUTED" if self.is_muted else "MUTE")
        self.mute_toggled.emit(self.is_muted)

    def _on_slider_changed(self, val: int):
        self.lbl_vol.setText(f"{val}%")
        self.volume_changed.emit(val)

    def set_vu_level(self, level: float):
        pct = int(min(1.0, max(0.0, level)) * 100)
        self.vu_meter.setValue(pct)

    def set_volume_externally(self, val: int):
        self.slider.blockSignals(True)
        self.slider.setValue(val)
        self.lbl_vol.setText(f"{val}%")
        self.slider.blockSignals(False)

    def set_mute_externally(self, muted: bool):
        self.is_muted = muted
        self.btn_mute.setStyleSheet(self._mute_style(muted))
        self.btn_mute.setText("MUTED" if muted else "MUTE")


class ZeroMixModule(BaseModule):
    """Minimalist ZeroMix Virtual Audio Mixer Module."""

    def __init__(self, port: int = DEFAULT_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip

        self.engine = AudioMixerEngine(parent=self)
        self.service = ZeroMixService(engine=self.engine, port=self.port, parent=self)

        self._widget: Optional[QWidget] = None
        self.status_pill: Optional[QLabel] = None
        self.client_pill: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None

        # Strips
        self.strip_mic: Optional[ChannelStrip] = None
        self.strip_music: Optional[ChannelStrip] = None
        self.strip_sound: Optional[ChannelStrip] = None

        # Ducking widgets
        self.chk_ducking: Optional[QCheckBox] = None
        self.slider_duck_level: Optional[QSlider] = None
        self.lbl_duck_level: Optional[QLabel] = None
        self.lbl_duck_status: Optional[QLabel] = None

        # Device combos
        self.combo_mic: Optional[QComboBox] = None
        self.combo_monitor: Optional[QComboBox] = None
        self.combo_broadcast: Optional[QComboBox] = None

        # Soundboard grid
        self.soundboard_layout: Optional[QGridLayout] = None

        # Wire engine signals
        self.lbl_phone_cast_status: Optional[QLabel] = None
        self.engine.levels_updated.connect(self._on_levels_updated)
        self.engine.ducking_state_changed.connect(self._on_ducking_changed)
        self.engine.soundboard_list_changed.connect(self._refresh_soundboard_ui)
        self.engine.phone_stream_status_changed.connect(self._on_phone_stream_status_changed)
        self.service.client_count_changed.connect(self._on_client_count_changed)

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
        ok1 = self.engine.start()
        ok2 = self.service.start()
        if ok1 or ok2:
            self._is_active = True
            if self.status_pill:
                self.status_pill.setText("● MIXER ACTIVE")
                self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("Disable Mixer")
            self.status_changed.emit(self.module_id, "ZeroMix engine running")
            return True
        return False

    def stop_service(self) -> bool:
        if not self._is_active:
            return True
        self.engine.stop()
        self.service.stop()
        self._is_active = False
        if self.status_pill:
            self.status_pill.setText("○ INACTIVE")
            self.status_pill.setStyleSheet("color: #6B7280; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        if self.btn_power:
            self.btn_power.setText("Enable Mixer")
        self.status_changed.emit(self.module_id, "ZeroMix engine stopped")
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

        self.btn_power = QPushButton("Disable Mixer" if self.is_active else "Enable Mixer")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● MIXER ACTIVE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("📱 Mobile: 0 Connected")
        self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        port_pill = QLabel(f"Port: {self.port}")
        port_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-family: Consolas;")
        bar_layout.addWidget(port_pill)

        bar_layout.addStretch()
        root_layout.addWidget(top_bar)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 20, 24, 24)
        content_layout.setSpacing(16)

        # Device Selection Card
        dev_card = QFrame()
        dev_card.setStyleSheet("QFrame { background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 12px; }")
        dev_layout = QHBoxLayout(dev_card)
        dev_layout.setSpacing(14)

        # Inputs and outputs list
        inputs, outputs = self.engine.get_device_lists()

        # Mic Device
        col_mic = QVBoxLayout()
        col_mic.addWidget(QLabel("🎤 Microphone Input:", styleSheet="font-size: 11px; font-weight: bold; color: #111827;"))
        self.combo_mic = QComboBox()
        for d in inputs:
            self.combo_mic.addItem(f"{d['name'][:30]}", d["index"])
        self._select_combo_data(self.combo_mic, self.engine.input_mic_device)
        self.combo_mic.currentIndexChanged.connect(self._on_devices_changed)
        col_mic.addWidget(self.combo_mic)
        dev_layout.addLayout(col_mic, 1)

        # Monitor Device
        col_mon = QVBoxLayout()
        col_mon.addWidget(QLabel("🎧 Monitor (Your Headphones):", styleSheet="font-size: 11px; font-weight: bold; color: #111827;"))
        self.combo_monitor = QComboBox()
        for d in outputs:
            self.combo_monitor.addItem(f"{d['name'][:30]}", d["index"])
        self._select_combo_data(self.combo_monitor, self.engine.output_monitor_device)
        self.combo_monitor.currentIndexChanged.connect(self._on_devices_changed)
        col_mon.addWidget(self.combo_monitor)
        dev_layout.addLayout(col_mon, 1)

        # Broadcast Device
        col_bc = QVBoxLayout()
        col_bc.addWidget(QLabel("📡 Virtual Mic (Discord/Game Output):", styleSheet="font-size: 11px; font-weight: bold; color: #111827;"))
        self.combo_broadcast = QComboBox()
        self.combo_broadcast.addItem("None (Monitor Only)", -1)
        for d in outputs:
            self.combo_broadcast.addItem(f"{d['name'][:30]}", d["index"])
        self._select_combo_data(self.combo_broadcast, self.engine.output_broadcast_device)
        self.combo_broadcast.currentIndexChanged.connect(self._on_devices_changed)
        col_bc.addWidget(self.combo_broadcast)
        dev_layout.addLayout(col_bc, 1)

        content_layout.addWidget(dev_card)

        # Channels Section (3 Stems)
        stems_layout = QHBoxLayout()
        stems_layout.setSpacing(14)

        # Mic Channel
        self.strip_mic = ChannelStrip("Microphone", "🎤", initial_vol=100, max_vol=150)
        self.strip_mic.volume_changed.connect(lambda v: self.engine.set_mic_volume(v))
        self.strip_mic.mute_toggled.connect(lambda m: self.engine.set_mic_mute(m))

        chk_hear_mic = QCheckBox("Hear myself in headphones")
        chk_hear_mic.setChecked(self.engine.monitor_mic)
        chk_hear_mic.setStyleSheet("color: #6B7280; font-size: 11px;")
        chk_hear_mic.toggled.connect(lambda on: self.engine.set_monitor_mic(on))
        self.strip_mic.layout().addWidget(chk_hear_mic)
        stems_layout.addWidget(self.strip_mic, 1)

        # Strip Music / Phone Cast
        self.strip_music = ChannelStrip("Phone Cast / Music", "📱", initial_vol=80, max_vol=100)
        self.strip_music.volume_changed.connect(lambda v: self.engine.set_music_volume(v))
        self.strip_music.mute_toggled.connect(lambda m: self.engine.set_music_mute(m))

        self.lbl_phone_cast_status = QLabel("● Phone Cast: Ready")
        self.lbl_phone_cast_status.setStyleSheet("color: #6B7280; font-size: 10px; font-weight: 600; padding: 2px 0;")
        self.strip_music.layout().addWidget(self.lbl_phone_cast_status)

        # Music file loader
        music_btn_row = QHBoxLayout()
        btn_open_music = QPushButton("📁 PC Music")
        btn_open_music.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_open_music.clicked.connect(self._pick_music_file)
        music_btn_row.addWidget(btn_open_music)

        btn_stop_music = QPushButton("⏹ Stop")
        btn_stop_music.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_stop_music.clicked.connect(self.engine.stop_music)
        music_btn_row.addWidget(btn_stop_music)
        self.strip_music.layout().addLayout(music_btn_row)
        stems_layout.addWidget(self.strip_music, 1)

        # Soundboard Channel
        self.strip_sound = ChannelStrip("Soundboard", "🔊", initial_vol=90, max_vol=100)
        self.strip_sound.volume_changed.connect(lambda v: self.engine.set_soundboard_volume(v))
        self.strip_sound.mute_toggled.connect(lambda m: self.engine.set_soundboard_mute(m))

        btn_stop_snd = QPushButton("⏹ Stop Sound")
        btn_stop_snd.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_stop_snd.clicked.connect(self.engine.stop_sound)
        self.strip_sound.layout().addWidget(btn_stop_snd)
        stems_layout.addWidget(self.strip_sound, 1)

        content_layout.addLayout(stems_layout)

        # Smart Auto-Ducking Card
        duck_card = QFrame()
        duck_card.setStyleSheet("QFrame { background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px; }")
        duck_l = QVBoxLayout(duck_card)
        duck_l.setSpacing(10)

        duck_hdr = QHBoxLayout()
        self.chk_ducking = QCheckBox("🦆 Enable Smart Auto-Ducking (Auto-Lower Music When Speaking)")
        self.chk_ducking.setChecked(self.engine.ducking_enabled)
        self.chk_ducking.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.chk_ducking.setStyleSheet("color: #111827;")
        self.chk_ducking.toggled.connect(self._on_ducking_toggled)
        duck_hdr.addWidget(self.chk_ducking)

        duck_hdr.addStretch()

        self.lbl_duck_status = QLabel("● IDLE")
        self.lbl_duck_status.setStyleSheet("color: #6B7280; font-size: 10px; font-weight: 700; background: #F3F4F6; padding: 3px 8px; border-radius: 4px;")
        duck_hdr.addWidget(self.lbl_duck_status)
        duck_l.addLayout(duck_hdr)

        duck_sub = QLabel("Automatically reduces background music and soundboard volume whenever your microphone detects speech, and smoothly fades it back when silent.")
        duck_sub.setStyleSheet("color: #6B7280; font-size: 11px; border: none;")
        duck_l.addWidget(duck_sub)

        # Ducking level slider
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Reduce Music Down To:", styleSheet="color: #111827; font-size: 11px; font-weight: bold;"))

        self.slider_duck_level = QSlider(Qt.Orientation.Horizontal)
        self.slider_duck_level.setRange(0, 80)
        self.slider_duck_level.setValue(int(self.engine.ducking_level * 100))
        self.slider_duck_level.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #E5E7EB; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #111827; border-radius: 3px; }
            QSlider::handle:horizontal { background: #FFFFFF; border: 2px solid #111827; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
        """)
        self.slider_duck_level.valueChanged.connect(self._on_duck_level_changed)
        slider_row.addWidget(self.slider_duck_level)

        self.lbl_duck_level = QLabel(f"{int(self.engine.ducking_level * 100)}%")
        self.lbl_duck_level.setFixedWidth(40)
        self.lbl_duck_level.setStyleSheet("font-weight: bold; color: #111827; font-size: 11px;")
        slider_row.addWidget(self.lbl_duck_level)
        duck_l.addLayout(slider_row)

        content_layout.addWidget(duck_card)

        # Soundboard Library Card
        snd_card = QFrame()
        snd_card.setStyleSheet("QFrame { background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 16px; }")
        snd_l = QVBoxLayout(snd_card)
        snd_l.setSpacing(12)

        snd_hdr = QHBoxLayout()
        snd_title = QLabel("Soundboard Library")
        snd_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        snd_title.setStyleSheet("color: #111827;")
        snd_hdr.addWidget(snd_title)

        snd_hdr.addStretch()

        btn_add_sound = QPushButton("➕ Add Sound File (.mp3, .wav)")
        btn_add_sound.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #374151; }
        """)
        btn_add_sound.clicked.connect(self._add_sound_file)
        snd_hdr.addWidget(btn_add_sound)
        snd_l.addLayout(snd_hdr)

        snd_hint = QLabel("💡 Add sounds here. Open ZeroMix on your phone and press 'Refresh' to trigger them wirelessly into your PC mix!")
        snd_hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        snd_l.addWidget(snd_hint)

        # Soundboard Grid
        self.soundboard_container = QWidget()
        self.soundboard_layout = QGridLayout(self.soundboard_container)
        self.soundboard_layout.setContentsMargins(0, 4, 0, 4)
        self.soundboard_layout.setSpacing(8)
        snd_l.addWidget(self.soundboard_container)

        self._refresh_soundboard_ui()
        content_layout.addWidget(snd_card)

        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll, 1)

        self._widget = container

    def _select_combo_data(self, combo: QComboBox, data_val: Optional[int]):
        if data_val is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == data_val:
                combo.setCurrentIndex(i)
                break

    def _toggle_power(self):
        if self.is_active:
            self.stop_service()
            self.state_changed.emit(self.module_id, False)
        else:
            self.start_service()
            self.state_changed.emit(self.module_id, True)

    def _on_devices_changed(self):
        mic_idx = self.combo_mic.currentData() if self.combo_mic else None
        mon_idx = self.combo_monitor.currentData() if self.combo_monitor else None
        bc_idx = self.combo_broadcast.currentData() if self.combo_broadcast else None
        if bc_idx == -1:
            bc_idx = None
        self.engine.set_devices(mic_idx, mon_idx, bc_idx)

    def _pick_music_file(self):
        path, _ = QFileDialog.getOpenFileName(self._widget, "Select Music Track", "", "Audio Files (*.mp3 *.wav *.ogg *.m4a *.flac)")
        if path:
            self.engine.play_music_file(path)

    def _add_sound_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self._widget, "Select Soundboard Audio", "", "Audio Files (*.mp3 *.wav *.ogg *.m4a *.flac)")
        for p in paths:
            self.engine.add_sound_file(p)

    def _refresh_soundboard_ui(self):
        if not self.soundboard_layout:
            return
        # Clear existing
        while self.soundboard_layout.count() > 0:
            item = self.soundboard_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items = self.engine.soundboard_items
        if not items:
            lbl_empty = QLabel("No sounds added yet. Click 'Add Sound File' above to add memes and sound effects.")
            lbl_empty.setStyleSheet("color: #9CA3AF; font-size: 11px; padding: 12px;")
            self.soundboard_layout.addWidget(lbl_empty, 0, 0)
            return

        for idx, item in enumerate(items):
            row = idx // 3
            col = idx % 3
            card = self._create_sound_tile(item)
            self.soundboard_layout.addWidget(card, row, col)

    def _create_sound_tile(self, item: Dict) -> QWidget:
        tile = QFrame()
        tile.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 6px;
            }
            QFrame:hover {
                border-color: #111827;
                background-color: #F3F4F6;
            }
        """)
        l = QHBoxLayout(tile)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(8)

        lbl = QLabel(f"🔊 {item['name'][:20]}")
        lbl.setStyleSheet("color: #111827; font-size: 11px; font-weight: 600; border: none;")
        l.addWidget(lbl, 1)

        btn_play = QPushButton("▶ Play")
        btn_play.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #374151; }
        """)
        btn_play.clicked.connect(lambda _, sid=item["id"]: self.engine.play_sound(sid))
        l.addWidget(btn_play)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #9CA3AF;
                border: none;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { color: #EF4444; }
        """)
        btn_del.clicked.connect(lambda _, sid=item["id"]: self.engine.remove_sound(sid))
        l.addWidget(btn_del)
        return tile

    def _on_ducking_toggled(self, checked: bool):
        val = self.slider_duck_level.value() if self.slider_duck_level else 20
        self.engine.set_ducking_config(checked, val)

    def _on_duck_level_changed(self, val: int):
        if self.lbl_duck_level:
            self.lbl_duck_level.setText(f"{val}%")
        enabled = self.chk_ducking.isChecked() if self.chk_ducking else True
        self.engine.set_ducking_config(enabled, val)

    def _on_ducking_changed(self, is_ducking: bool, factor: float):
        if self.lbl_duck_status:
            if is_ducking:
                pct = int((1.0 - factor) * 100)
                self.lbl_duck_status.setText(f"🦆 DUCKING (-{pct}%)")
                self.lbl_duck_status.setStyleSheet("color: #FFFFFF; font-size: 10px; font-weight: 700; background: #EF4444; padding: 3px 8px; border-radius: 4px;")
            else:
                self.lbl_duck_status.setText("● IDLE")
                self.lbl_duck_status.setStyleSheet("color: #6B7280; font-size: 10px; font-weight: 700; background: #F3F4F6; padding: 3px 8px; border-radius: 4px;")

    def _on_levels_updated(self, mic_lvl: float, music_lvl: float, snd_lvl: float):
        if self.strip_mic:
            self.strip_mic.set_vu_level(mic_lvl)
        if self.strip_music:
            self.strip_music.set_vu_level(music_lvl)
        if self.strip_sound:
            self.strip_sound.set_vu_level(snd_lvl)

    def _on_client_count_changed(self, count: int):
        if self.client_pill:
            color = "#111827" if count > 0 else "#6B7280"
            weight = "700" if count > 0 else "400"
            self.client_pill.setText(f"📱 Mobile: {count} Connected")
            self.client_pill.setStyleSheet(f"color: {color}; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: {weight};")

    def _on_phone_stream_status_changed(self, is_active: bool):
        if self.lbl_phone_cast_status:
            if is_active:
                self.lbl_phone_cast_status.setText("● Phone Cast: Streaming")
                self.lbl_phone_cast_status.setStyleSheet("color: #10B981; font-size: 10px; font-weight: 700; padding: 2px 0;")
            else:
                self.lbl_phone_cast_status.setText("● Phone Cast: Ready")
                self.lbl_phone_cast_status.setStyleSheet("color: #6B7280; font-size: 10px; font-weight: 600; padding: 2px 0;")
