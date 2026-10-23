"""ZeroLink Hub - ZeroDrop Module
AirDrop-like high-speed wireless & USB file transfers between PC and Android.
"""

import os
import subprocess
from typing import Optional, List
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QDateTime
from PyQt6.QtGui import QFont, QColor, QDragEnterEvent, QDropEvent, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QProgressBar, QScrollArea, QSizePolicy
)

from core.base_module import BaseModule
from core.file_transfer import FileTransferService
from modules.zerodrop.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, DEFAULT_PORT
)


class DropZoneWidget(QFrame):
    """Interactive drag & drop target area with clean dashed border."""
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(170)
        self._set_normal_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self.icon_lbl = QLabel("⇪")
        self.icon_lbl.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.icon_lbl.setStyleSheet("color: #111827; border: none;")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_lbl)

        self.title_lbl = QLabel("Drag & Drop Files Here")
        self.title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #111827; border: none;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)

        self.sub_lbl = QLabel("or click anywhere in this box to browse from your PC")
        self.sub_lbl.setFont(QFont("Segoe UI", 10))
        self.sub_lbl.setStyleSheet("color: #6B7280; border: none;")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub_lbl)

    def _set_normal_style(self):
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: #FFFFFF;
                border: 2px dashed #D1D5DB;
                border-radius: 12px;
            }
            DropZoneWidget:hover {
                background-color: #F9FAFB;
                border-color: #111827;
            }
        """)

    def _set_active_style(self):
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: #F3F4F6;
                border: 2px dashed #111827;
                border-radius: 12px;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active_style()

    def dragLeaveEvent(self, event):
        self._set_normal_style()

    def dropEvent(self, event: QDropEvent):
        self._set_normal_style()
        paths = []
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.exists(local_path):
                paths.append(local_path)
        if paths:
            self.files_dropped.emit(paths)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Send to Mobile")
            if files:
                self.files_dropped.emit(files)


class TransferItemCard(QFrame):
    """History entry card for sent/received files."""

    def __init__(self, filename: str, direction: str, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
            QFrame:hover {
                border-color: #9CA3AF;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        icon_text = "⤓" if direction == "RECEIVED" else "⤒"
        icon_lbl = QLabel(icon_text)
        icon_lbl.setFont(QFont("Segoe UI Symbol", 16))
        layout.addWidget(icon_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name_lbl = QLabel(filename)
        name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #111827;")
        info_col.addWidget(name_lbl)

        time_str = QDateTime.currentDateTime().toString("hh:mm:ss AP")
        meta_lbl = QLabel(f"{direction} • {time_str}")
        meta_lbl.setStyleSheet("color: #6B7280; font-size: 10px;")
        info_col.addWidget(meta_lbl)
        layout.addLayout(info_col, 1)

        btn_open = QPushButton("↗ Open File")
        btn_open.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #111827;
                color: #FFFFFF;
            }
        """)
        btn_open.clicked.connect(self._open_file)
        layout.addWidget(btn_open)

        btn_dir = QPushButton("⧉ Show in Folder")
        btn_dir.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #4B5563;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        btn_dir.clicked.connect(self._show_in_folder)
        layout.addWidget(btn_dir)

    def _open_file(self):
        if os.path.exists(self.file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.file_path))

    def _show_in_folder(self):
        folder = os.path.dirname(self.file_path)
        if os.path.exists(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


class ZeroDropModule(BaseModule):
    """Minimalist ZeroDrop Module for fast LAN/USB file transfers."""

    def __init__(self, port: int = DEFAULT_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip

        self.service = FileTransferService(port=self.port, parent=self)
        self.service.transfer_progress.connect(self._on_transfer_progress)
        self.service.transfer_completed.connect(self._on_transfer_completed)
        self.service.transfer_failed.connect(self._on_transfer_failed)
        self.service.client_count_changed.connect(self._on_client_count_changed)

        self._widget: Optional[QWidget] = None
        self.status_pill: Optional[QLabel] = None
        self.client_pill: Optional[QLabel] = None
        self.btn_power: Optional[QPushButton] = None

        self.progress_card: Optional[QFrame] = None
        self.progress_file_lbl: Optional[QLabel] = None
        self.progress_bar: Optional[QProgressBar] = None
        self.progress_speed_lbl: Optional[QLabel] = None

        self.history_layout: Optional[QVBoxLayout] = None

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
                self.status_pill.setText("● READY")
                self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
            if self.btn_power:
                self.btn_power.setText("⏻ Disable")
            self.status_changed.emit(self.module_id, "ZeroDrop service running")
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
                self.btn_power.setText("⏻ Enable")
            self.status_changed.emit(self.module_id, "ZeroDrop service stopped")
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

        self.btn_power = QPushButton("⏻ Disable" if self.is_active else "⏻ Enable")
        self.btn_power.clicked.connect(self._toggle_power)
        bar_layout.addWidget(self.btn_power)

        self.status_pill = QLabel("● READY" if self.is_active else "○ INACTIVE")
        self.status_pill.setStyleSheet("color: #111827; background-color: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;")
        bar_layout.addWidget(self.status_pill)

        self.client_pill = QLabel("⇄ Mobile: 0 Connected")
        self.client_pill.setStyleSheet("color: #4B5563; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px;")
        bar_layout.addWidget(self.client_pill)

        port_pill = QLabel(f"Port: {self.port}")
        port_pill.setStyleSheet("color: #4B5563; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-family: Consolas;")
        bar_layout.addWidget(port_pill)

        bar_layout.addStretch()

        btn_open_folder = QPushButton("⧉ Open ZeroDrop Folder")
        btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        btn_open_folder.clicked.connect(self._open_download_dir)
        bar_layout.addWidget(btn_open_folder)

        root_layout.addWidget(top_bar)

        # Content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        # Drag and Drop Zone
        drop_zone = DropZoneWidget()
        drop_zone.files_dropped.connect(self._send_files)
        content_layout.addWidget(drop_zone)

        # Transfer Progress Card (Hidden initially)
        self.progress_card = QFrame()
        self.progress_card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #111827;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        prog_l = QVBoxLayout(self.progress_card)
        prog_l.setSpacing(6)

        prog_header = QHBoxLayout()
        self.progress_file_lbl = QLabel("Transferring file...")
        self.progress_file_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.progress_file_lbl.setStyleSheet("color: #111827; border: none;")
        prog_header.addWidget(self.progress_file_lbl)

        prog_header.addStretch()

        self.progress_speed_lbl = QLabel("0.0 MB/s")
        self.progress_speed_lbl.setStyleSheet("color: #6B7280; font-size: 11px; border: none; font-family: Consolas;")
        prog_header.addWidget(self.progress_speed_lbl)
        prog_l.addLayout(prog_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #E5E7EB;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #111827;
                border-radius: 3px;
            }
        """)
        prog_l.addWidget(self.progress_bar)
        self.progress_card.setVisible(False)
        content_layout.addWidget(self.progress_card)

        # Transfer History Section
        history_header = QHBoxLayout()
        hist_title = QLabel("Transfer History")
        hist_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        hist_title.setStyleSheet("color: #111827;")
        history_header.addWidget(hist_title)

        history_header.addStretch()

        btn_clear_hist = QPushButton("Clear History")
        btn_clear_hist.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #6B7280;
                border: none;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #111827;
                text-decoration: underline;
            }
        """)
        btn_clear_hist.clicked.connect(self._clear_history)
        history_header.addWidget(btn_clear_hist)
        content_layout.addLayout(history_header)

        # Scrollable history list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        history_container = QWidget()
        self.history_layout = QVBoxLayout(history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(8)
        self.history_layout.addStretch()

        scroll.setWidget(history_container)
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

    def _open_download_dir(self):
        d = self.service.download_dir
        if os.path.exists(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _send_files(self, paths: List[str]):
        if not self.is_active:
            self.start_service()
        self.service.send_files_to_client(paths)

    def _on_client_count_changed(self, count: int):
        if self.client_pill:
            color = "#111827" if count > 0 else "#6B7280"
            weight = "700" if count > 0 else "400"
            icon = "●" if count > 0 else "○"
            self.client_pill.setText(f"{icon} Mobile: {count} Connected")
            self.client_pill.setStyleSheet(f"color: {color}; background: #F3F4F6; border: 1px solid #E5E7EB; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: {weight};")

    def _on_transfer_progress(self, filename: str, done: int, total: int, speed: float):
        if self.progress_card and not self.progress_card.isVisible():
            self.progress_card.setVisible(True)

        pct = int((done / total) * 100) if total > 0 else 0
        if self.progress_file_lbl:
            self.progress_file_lbl.setText(f"Transferring: {filename} ({pct}%)")
        if self.progress_speed_lbl:
            self.progress_speed_lbl.setText(f"{speed:.1f} MB/s")
        if self.progress_bar:
            self.progress_bar.setValue(pct)

    def _on_transfer_completed(self, filename: str, direction: str, file_path: str):
        if self.progress_card:
            self.progress_card.setVisible(False)

        if self.history_layout:
            card = TransferItemCard(filename, direction, file_path)
            self.history_layout.insertWidget(0, card)

    def _on_transfer_failed(self, filename: str, error: str):
        if self.progress_card:
            self.progress_card.setVisible(False)
        print(f"[ZeroDrop] Transfer failed: {filename} - {error}")

    def _clear_history(self):
        if not self.history_layout:
            return
        while self.history_layout.count() > 1:
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
