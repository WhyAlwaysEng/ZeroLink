"""ZeroLink Hub - ZeroClip Module
Ultra-fast bi-directional clipboard sync between PC and mobile devices.
"""

import time
from typing import Optional, List, Dict
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QCheckBox, QTextEdit, QScrollArea, QSizePolicy,
    QGraphicsDropShadowEffect, QApplication
)

from core.base_module import BaseModule
from core.clipboard_service import ClipboardService
from modules.zeroclip.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, DEFAULT_PORT
)


class ClipHistoryCard(QFrame):
    """Card representing a single synced clipboard item."""
    copy_requested = pyqtSignal(str)

    def __init__(self, text: str, source: str, timestamp: float, parent=None):
        super().__init__(parent)
        self.text_content = text
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 10px;
            }
            QFrame:hover {
                border-color: #9CA3AF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Meta row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        source_pill = QLabel(f"From {source}")
        source_color = "#111827" if source == "PHONE" else "#4B5563"
        source_bg = "#F3F4F6"
        source_pill.setStyleSheet(f"""
            color: {source_color};
            background-color: {source_bg};
            border: 1px solid #E5E7EB;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        """)
        meta_row.addWidget(source_pill)

        time_str = QDateTime.fromSecsSinceEpoch(int(timestamp)).toString("hh:mm:ss AP")
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        meta_row.addWidget(time_lbl)

        meta_row.addStretch()

        btn_copy = QPushButton("Copy")
        btn_copy.setFixedWidth(56)
        btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #111827;
                color: #FFFFFF;
            }
        """)
        btn_copy.clicked.connect(lambda: self.copy_requested.emit(self.text_content))
        meta_row.addWidget(btn_copy)

        layout.addLayout(meta_row)

        # Content preview
        preview_text = text if len(text) <= 300 else (text[:297] + "...")
        content_lbl = QLabel(preview_text)
        content_lbl.setWordWrap(True)
        content_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_lbl.setStyleSheet("color: #111827; font-size: 12px; font-family: Segoe UI, Consolas;")
        layout.addWidget(content_lbl)


class ZeroClipModule(BaseModule):
    """Minimalist ZeroClip Module for shared clipboard."""

    def __init__(self, port: int = DEFAULT_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip

        self.service = ClipboardService(port=self.port, parent=self)
        self.service.clip_received.connect(self._on_clip_received)
        self.service.client_count_changed.connect(self._on_client_count_changed)

        self._widget: Optional[QWidget] = None
        self.status_pill: Optional[QLabel] = None
        self.client_pill: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None
        self.chk_sync: Optional[QCheckBox] = None

        self.history_items: List[Dict] = []
        self.history_container: Optional[QWidget] = None
        self.history_layout: Optional[QVBoxLayout] = None
        self.current_clip_box: Optional[QTextEdit] = None
        self.current_source_lbl: Optional[QLabel] = None

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
        ok = self.service.start()
        if ok:
            self._is_active = True
            if self.status_pill:
                self.status_pill.setText("● SYNC ACTIVE")
                self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("Disable Module")
            self.status_changed.emit(self.module_id, "ZeroClip service running")
        return ok

    def stop_service(self) -> bool:
        if not self._is_active:
            return True
        ok = self.service.stop()
        if ok:
            self._is_active = False
            if self.status_pill:
                self.status_pill.setText("○ INACTIVE")
                self.status_pill.setStyleSheet("color: #6B7280; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("Enable Module")
            self.status_changed.emit(self.module_id, "ZeroClip service stopped")
        return ok

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

        # Header bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #FFFFFF; border-bottom: 1px solid #E5E7EB;")
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(18, 10, 18, 10)
        bar_layout.setSpacing(10)

        self.btn_power = QPushButton("Disable Module" if self.is_active else "Enable Module")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● SYNC ACTIVE" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("📱 Mobile: 0 Connected")
        self.client_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        port_pill = QLabel(f"Port: {self.port}")
        port_pill.setStyleSheet("color: #6B7280; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-family: Consolas;")
        bar_layout.addWidget(port_pill)

        bar_layout.addStretch()

        self.chk_sync = QCheckBox("Auto Sync")
        self.chk_sync.setChecked(True)
        self.chk_sync.setStyleSheet("color: #374151; font-size: 11px; font-weight: 600;")
        self.chk_sync.toggled.connect(self._on_sync_toggled)
        bar_layout.addWidget(self.chk_sync)

        btn_clear = QPushButton("Clear History")
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #374151;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        btn_clear.clicked.connect(self._clear_history)
        bar_layout.addWidget(btn_clear)

        root_layout.addWidget(top_bar)

        # Content Area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        # Active Clipboard Card
        active_card = QFrame()
        active_card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
        """)
        card_l = QVBoxLayout(active_card)
        card_l.setContentsMargins(16, 14, 16, 14)
        card_l.setSpacing(10)

        card_header = QHBoxLayout()
        title_lbl = QLabel("📋 Active Clipboard")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827; border: none;")
        card_header.addWidget(title_lbl)

        self.current_source_lbl = QLabel("System Clipboard")
        self.current_source_lbl.setStyleSheet("color: #6B7280; font-size: 11px; border: none;")
        card_header.addWidget(self.current_source_lbl)

        card_header.addStretch()

        btn_copy_active = QPushButton("Copy to Clipboard")
        btn_copy_active.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #000000;
            }
        """)
        btn_copy_active.clicked.connect(self._copy_active_text)
        card_header.addWidget(btn_copy_active)

        card_l.addLayout(card_header)

        self.current_clip_box = QTextEdit()
        self.current_clip_box.setPlaceholderText("Copied text from PC or phone will appear here in real-time...")
        self.current_clip_box.setFixedHeight(90)
        self.current_clip_box.setStyleSheet("""
            QTextEdit {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
                color: #111827;
            }
        """)
        card_l.addWidget(self.current_clip_box)

        content_layout.addWidget(active_card)

        # History Section Title
        sec_title = QLabel("Sync History")
        sec_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        sec_title.setStyleSheet("color: #111827;")
        content_layout.addWidget(sec_title)

        # Scrollable History List
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(8)
        self.history_layout.addStretch()

        scroll.setWidget(self.history_container)
        content_layout.addWidget(scroll, 1)

        root_layout.addWidget(content_widget, 1)
        self._widget = container

    def _toggle_power(self):
        if self.is_active:
            self.stop_service()
            self.state_changed.emit(self.module_id, False)
        else:
            self.start_service()
            self.state_changed.emit(self.module_id, True)

    def _on_sync_toggled(self, checked: bool):
        self.service.sync_enabled = checked

    def _on_client_count_changed(self, count: int):
        if self.client_pill:
            color = "#111827" if count > 0 else "#6B7280"
            weight = "700" if count > 0 else "400"
            self.client_pill.setText(f"📱 Mobile: {count} Connected")
            self.client_pill.setStyleSheet(f"color: {color}; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: {weight};")

    def _on_clip_received(self, text: str, source: str, timestamp: float):
        if self.current_clip_box:
            self.current_clip_box.setPlainText(text)
        if self.current_source_lbl:
            self.current_source_lbl.setText(f"Last updated from {source}")

        # Add to history card list
        if self.history_layout:
            card = ClipHistoryCard(text, source, timestamp)
            card.copy_requested.connect(self._copy_text_to_clipboard)
            # Insert at top (index 0)
            self.history_layout.insertWidget(0, card)

    def _copy_active_text(self):
        if not self.current_clip_box:
            return
        txt = self.current_clip_box.toPlainText()
        if txt:
            self._copy_text_to_clipboard(txt)

    def _copy_text_to_clipboard(self, text: str):
        clip = QApplication.clipboard()
        if clip:
            clip.setText(text)

    def _clear_history(self):
        if not self.history_layout:
            return
        while self.history_layout.count() > 1:
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
