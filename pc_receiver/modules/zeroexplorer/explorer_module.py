"""ZeroLink Hub - ZeroExplorer Module
All-in-One Phone Gallery, Storage Explorer, Media Streamer & File Manager.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize, QTimer
from PyQt6.QtGui import QFont, QPixmap, QImage, QClipboard, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QSplitter, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
    QProgressBar, QFileDialog, QMessageBox, QApplication, QDialog
)

from core.base_module import BaseModule
from core.adb_helper import AdbManager
from modules.zeroexplorer.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


# ==================== Background Workers ====================

class StorageWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        url = f"http://{self.host}:{self.port}/api/storage"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.result_ready.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))


class GalleryWorker(QThread):
    result_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, host: str, port: int, album: Optional[str] = None):
        super().__init__()
        self.host = host
        self.port = port
        self.album = album

    def run(self):
        url = f"http://{self.host}:{self.port}/api/gallery/photos"
        if self.album:
            url += f"?album={urllib.parse.quote(self.album)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.result_ready.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))


class FilesWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, host: str, port: int, path: str):
        super().__init__()
        self.host = host
        self.port = port
        self.path = path

    def run(self):
        encoded = urllib.parse.quote(self.path)
        url = f"http://{self.host}:{self.port}/api/files/list?path={encoded}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.result_ready.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ThumbWorker(QThread):
    thumb_ready = pyqtSignal(int, QPixmap)

    def __init__(self, host: str, port: int, photo_id: int):
        super().__init__()
        self.host = host
        self.port = port
        self.photo_id = photo_id

    def run(self):
        url = f"http://{self.host}:{self.port}/api/media/thumb?id={self.photo_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw_bytes = resp.read()
                img = QImage.fromData(raw_bytes)
                if not img.isNull():
                    pix = QPixmap.fromImage(img)
                    self.thumb_ready.emit(self.photo_id, pix)
        except Exception:
            pass


class ZeroExplorerModule(BaseModule):
    """ZeroExplorer: Unified Media Gallery & Storage Manager for Phone."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self.adb_manager = AdbManager()
        self._widget: Optional[QWidget] = None
        self._is_active = False

        # State
        self.phone_host = "127.0.0.1"
        self.current_folder_path = "/storage/emulated/0"
        self.parent_folder_path = ""
        self.raw_files_list: List[Dict] = []
        self.gallery_items: List[Dict] = []
        self.selected_file_path = ""
        self.selected_photo_id: Optional[int] = None

        # Workers
        self._storage_worker: Optional[StorageWorker] = None
        self._gallery_worker: Optional[GalleryWorker] = None
        self._files_worker: Optional[FilesWorker] = None
        self._active_thumb_workers: List[ThumbWorker] = []

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
        self._is_active = True
        self.state_changed.emit(self.module_id, True)
        self.status_changed.emit(self.module_id, f"Client ready for port {self.port}")
        return True

    def stop_service(self) -> bool:
        self._is_active = False
        self.state_changed.emit(self.module_id, False)
        self.status_changed.emit(self.module_id, "Stopped")
        return True

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._create_ui()
            # Initial auto-connect
            QTimer.singleShot(1000, self.connect_and_sync)
        return self._widget

    def _create_ui(self) -> QWidget:
        root = QWidget()
        root.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # ==================== Top Header Row ====================
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel(MODULE_ICON)
        icon_lbl.setFont(QFont("Segoe UI Symbol", 20))
        icon_lbl.setStyleSheet("color: #111827;")
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_lbl = QLabel("ZeroExplorer")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #111827;")
        title_row.addWidget(title_lbl)

        badge_lbl = QLabel("ALL-IN-ONE")
        badge_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge_lbl.setStyleSheet("""
            background-color: #F3F4F6;
            color: #111827;
            padding: 2px 6px;
            border: 1px solid #D1D5DB;
            border-radius: 4px;
        """)
        title_row.addWidget(badge_lbl)
        title_row.addStretch()
        title_col.addLayout(title_row)

        desc_lbl = QLabel("Phone Gallery, Storage Explorer & Live File Manager (Port 8896)")
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setStyleSheet("color: #6B7280;")
        title_col.addWidget(desc_lbl)

        header_row.addLayout(title_col, 1)

        # Gateway IP row
        self.et_host_ip = QLineEdit("127.0.0.1")
        self.et_host_ip.setFixedWidth(130)
        self.et_host_ip.setFont(QFont("Segoe UI", 9))
        self.et_host_ip.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 5px 8px;
                color: #111827;
            }
            QLineEdit:focus {
                border-color: #111827;
            }
        """)
        header_row.addWidget(self.et_host_ip)

        self.btn_usb_mode = QPushButton("⌁ USB")
        self.btn_usb_mode.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_usb_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_usb_mode.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self.btn_usb_mode.clicked.connect(self._on_usb_mode_clicked)
        header_row.addWidget(self.btn_usb_mode)

        self.btn_connect = QPushButton("Sync / Refresh")
        self.btn_connect.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        self.btn_connect.clicked.connect(self.connect_and_sync)
        header_row.addWidget(self.btn_connect)

        self.status_badge = QLabel("○ IDLE")
        self.status_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_badge.setStyleSheet("""
            background-color: #FFFFFF;
            color: #4B5563;
            border: 1px solid #D1D5DB;
            padding: 5px 10px;
            border-radius: 6px;
        """)
        header_row.addWidget(self.status_badge)

        layout.addLayout(header_row)

        # ==================== Real Storage Breakdown Bar ====================
        storage_card = QFrame()
        storage_card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        s_layout = QVBoxLayout(storage_card)
        s_layout.setContentsMargins(10, 8, 10, 8)
        s_layout.setSpacing(6)

        s_header = QHBoxLayout()
        lbl_s_title = QLabel("Internal Storage")
        lbl_s_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_s_title.setStyleSheet("color: #111827; border: none;")
        s_header.addWidget(lbl_s_title)

        s_header.addStretch()

        self.lbl_storage_details = QLabel("Connect to view device storage")
        self.lbl_storage_details.setFont(QFont("Segoe UI", 9))
        self.lbl_storage_details.setStyleSheet("color: #4B5563; border: none;")
        s_header.addWidget(self.lbl_storage_details)
        s_layout.addLayout(s_header)

        self.storage_progress = QProgressBar()
        self.storage_progress.setFixedHeight(6)
        self.storage_progress.setTextVisible(False)
        self.storage_progress.setValue(0)
        self.storage_progress.setStyleSheet("""
            QProgressBar {
                background-color: #E5E7EB;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #111827;
                border-radius: 3px;
            }
        """)
        s_layout.addWidget(self.storage_progress)
        layout.addWidget(storage_card)

        # ==================== Main Dual Tabs ====================
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                background-color: #FFFFFF;
                top: -1px;
            }
            QTabBar::tab {
                background: #F3F4F6;
                color: #4B5563;
                font-family: 'Segoe UI';
                font-weight: 600;
                font-size: 11px;
                padding: 8px 20px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #E5E7EB;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #111827;
                border-bottom: 2px solid #111827;
            }
            QTabBar::tab:hover:!selected {
                background: #E5E7EB;
            }
        """)

        # Tab 1: Photo Gallery
        self.tab_gallery = self._build_gallery_tab()
        self.tabs.addTab(self.tab_gallery, "Photo Gallery")

        # Tab 2: Storage & Files
        self.tab_files = self._build_files_tab()
        self.tabs.addTab(self.tab_files, "Storage & Files")

        layout.addWidget(self.tabs, 1)

        return root

    def _build_gallery_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Filter and Actions Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.btn_alb_all = QPushButton("All Media")
        self.btn_alb_cam = QPushButton("Camera")
        self.btn_alb_shot = QPushButton("Screenshots")
        self.btn_alb_down = QPushButton("Downloads")

        for btn in [self.btn_alb_all, self.btn_alb_cam, self.btn_alb_shot, self.btn_alb_down]:
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #F9FAFB;
                    color: #374151;
                    border: 1px solid #E5E7EB;
                    border-radius: 6px;
                    padding: 5px 14px;
                }
                QPushButton:hover {
                    background-color: #F3F4F6;
                    color: #111827;
                }
            """)
            filter_row.addWidget(btn)

        self.btn_alb_all.clicked.connect(lambda: self.fetch_gallery(None))
        self.btn_alb_cam.clicked.connect(lambda: self.fetch_gallery("Camera"))
        self.btn_alb_shot.clicked.connect(lambda: self.fetch_gallery("Screenshots"))
        self.btn_alb_down.clicked.connect(lambda: self.fetch_gallery("Download"))

        filter_row.addStretch()

        self.btn_copy_image = QPushButton("Copy Image to Clipboard")
        self.btn_copy_image.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_copy_image.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_image.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        self.btn_copy_image.clicked.connect(self._on_copy_selected_image)
        filter_row.addWidget(self.btn_copy_image)

        layout.addLayout(filter_row)

        # Gallery Grid
        self.gallery_list = QListWidget()
        self.gallery_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery_list.setIconSize(QSize(130, 130))
        self.gallery_list.setGridSize(QSize(145, 160))
        self.gallery_list.setSpacing(10)
        self.gallery_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                background-color: #FFFFFF;
                padding: 8px;
            }
            QListWidget::item {
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 4px;
                color: #111827;
            }
            QListWidget::item:hover {
                background-color: #F9FAFB;
                border-color: #9CA3AF;
            }
            QListWidget::item:selected {
                background-color: #F3F4F6;
                border: 2px solid #111827;
                color: #111827;
            }
        """)
        self.gallery_list.itemClicked.connect(self._on_gallery_item_clicked)
        self.gallery_list.itemDoubleClicked.connect(self._on_gallery_item_double_clicked)
        layout.addWidget(self.gallery_list, 1)

        return tab

    def _build_files_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Top Path & Navigation Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.btn_up_folder = QPushButton("↑ Up")
        self.btn_up_folder.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_up_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up_folder.setStyleSheet("""
            QPushButton {
                background-color: #F9FAFB;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_up_folder.clicked.connect(self._on_navigate_up)
        top_bar.addWidget(self.btn_up_folder)

        self.txt_breadcrumb = QLineEdit(self.current_folder_path)
        self.txt_breadcrumb.setFont(QFont("Segoe UI", 9))
        self.txt_breadcrumb.setStyleSheet("""
            QLineEdit {
                background-color: #F9FAFB;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 10px;
                color: #111827;
            }
            QLineEdit:focus {
                border-color: #111827;
                background-color: #FFFFFF;
            }
        """)
        self.txt_breadcrumb.returnPressed.connect(lambda: self.fetch_files(self.txt_breadcrumb.text()))
        top_bar.addWidget(self.txt_breadcrumb, 1)

        lbl_sort = QLabel("Sort:")
        lbl_sort.setFont(QFont("Segoe UI", 9))
        lbl_sort.setStyleSheet("color: #4B5563;")
        top_bar.addWidget(lbl_sort)

        self.cmb_sort = QComboBox()
        self.cmb_sort.setFont(QFont("Segoe UI", 9))
        self.cmb_sort.addItems([
            "Size (Largest ➔ Smallest)",
            "Size (Smallest ➔ Largest)",
            "Date (Newest ➔ Oldest)",
            "Date (Oldest ➔ Newest)",
            "Name (A ➔ Z)",
            "Type"
        ])
        self.cmb_sort.setStyleSheet("""
            QComboBox {
                background-color: #F9FAFB;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 5px 10px;
                color: #111827;
            }
        """)
        self.cmb_sort.currentIndexChanged.connect(self._apply_sorting)
        top_bar.addWidget(self.cmb_sort)

        layout.addLayout(top_bar)

        # Splitter: Sidebar + Table + Inspector
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Left Quick Access Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 10, 10, 10)
        side_layout.setSpacing(6)

        lbl_fav = QLabel("QUICK ACCESS")
        lbl_fav.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl_fav.setStyleSheet("color: #6B7280; letter-spacing: 0.5px; border: none;")
        side_layout.addWidget(lbl_fav)

        self.list_favorites = QListWidget()
        self.list_favorites.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
            }
            QListWidget::item {
                padding: 7px 8px;
                border-radius: 6px;
                color: #374151;
            }
            QListWidget::item:hover {
                background-color: #F3F4F6;
                color: #111827;
            }
            QListWidget::item:selected {
                background-color: #E5E7EB;
                color: #111827;
                font-weight: bold;
            }
        """)
        fav_items = [
            ("Downloads", "/storage/emulated/0/Download"),
            ("Camera", "/storage/emulated/0/DCIM/Camera"),
            ("Screenshots", "/storage/emulated/0/Pictures/Screenshots"),
            ("Documents", "/storage/emulated/0/Documents"),
            ("Storage Root", "/storage/emulated/0")
        ]
        for name, path in fav_items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_favorites.addItem(item)
        self.list_favorites.itemClicked.connect(lambda item: self.fetch_files(item.data(Qt.ItemDataRole.UserRole)))
        side_layout.addWidget(self.list_favorites, 1)

        splitter.addWidget(sidebar)

        # 2. File Table
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(4)
        self.table_files.setHorizontalHeaderLabels(["Name", "Date Modified", "Type", "Size"])
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_files.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_files.setAlternatingRowColors(True)
        self.table_files.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                gridline-color: #F3F4F6;
            }
            QHeaderView::section {
                background-color: #F9FAFB;
                color: #374151;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #E5E7EB;
                padding: 6px 8px;
            }
            QTableWidget::item:selected {
                background-color: #F3F4F6;
                color: #111827;
            }
        """)
        self.table_files.itemClicked.connect(self._on_table_item_clicked)
        self.table_files.itemDoubleClicked.connect(self._on_table_item_double_clicked)
        splitter.addWidget(self.table_files)

        # 3. Right Quick Preview Inspector
        self.preview_pane = QFrame()
        self.preview_pane.setFixedWidth(220)
        self.preview_pane.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        p_layout = QVBoxLayout(self.preview_pane)
        p_layout.setContentsMargins(14, 14, 14, 14)
        p_layout.setSpacing(8)

        lbl_p_title = QLabel("INSPECTOR")
        lbl_p_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl_p_title.setStyleSheet("color: #6B7280; letter-spacing: 0.5px; border: none;")
        p_layout.addWidget(lbl_p_title)

        self.lbl_preview_name = QLabel("No item selected")
        self.lbl_preview_name.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_preview_name.setStyleSheet("color: #111827; border: none;")
        self.lbl_preview_name.setWordWrap(True)
        p_layout.addWidget(self.lbl_preview_name)

        self.lbl_preview_meta = QLabel("Select a file or photo to inspect details.")
        self.lbl_preview_meta.setFont(QFont("Segoe UI", 8))
        self.lbl_preview_meta.setStyleSheet("color: #6B7280; border: none;")
        self.lbl_preview_meta.setWordWrap(True)
        p_layout.addWidget(self.lbl_preview_meta)

        p_layout.addStretch()

        self.btn_download_file = QPushButton("Download to PC")
        self.btn_download_file.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_download_file.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_download_file.clicked.connect(self._on_download_selected_file)
        p_layout.addWidget(self.btn_download_file)

        splitter.addWidget(self.preview_pane)
        splitter.setSizes([160, 480, 200])

        layout.addWidget(splitter, 1)

        return tab

    # ==================== Actions & Data Sync ====================

    def _on_usb_mode_clicked(self):
        self.et_host_ip.setText("127.0.0.1")
        # Run adb forward
        success, msg = self.adb_manager.forward_port(self.port)
        if success:
            self.status_badge.setText("● USB TUNNEL ACTIVE")
        self.connect_and_sync()

    def connect_and_sync(self):
        host = self.et_host_ip.text().strip()
        if not host:
            host = "127.0.0.1"
        self.phone_host = host
        self.status_badge.setText("● SYNCING...")

        self.fetch_storage()
        self.fetch_gallery(None)
        self.fetch_files(self.current_folder_path)

    def fetch_storage(self):
        if self._storage_worker and self._storage_worker.isRunning():
            self._storage_worker.terminate()
        self._storage_worker = StorageWorker(self.phone_host, self.port)
        self._storage_worker.result_ready.connect(self._on_storage_received)
        self._storage_worker.error_occurred.connect(self._on_error)
        self._storage_worker.start()

    def _on_storage_received(self, data: dict):
        total_b = data.get("totalBytes", 0)
        used_b = data.get("usedBytes", 0)
        free_pct = data.get("freePercent", 0)
        used_pct = data.get("usedPercent", 0)

        total_gb = total_b / (1024 ** 3)
        used_gb = used_b / (1024 ** 3)

        self.lbl_storage_details.setText(f"{used_gb:.1f} GB / {total_gb:.1f} GB used ({free_pct}% Free)")
        self.storage_progress.setValue(used_pct)
        self.status_badge.setText("● CONNECTED")

    def fetch_gallery(self, album: Optional[str]):
        if self._gallery_worker and self._gallery_worker.isRunning():
            self._gallery_worker.terminate()
        self.gallery_list.clear()
        self._gallery_worker = GalleryWorker(self.phone_host, self.port, album)
        self._gallery_worker.result_ready.connect(self._on_gallery_received)
        self._gallery_worker.error_occurred.connect(self._on_error)
        self._gallery_worker.start()

    def _on_gallery_received(self, items: list):
        self.gallery_items = items
        self.gallery_list.clear()

        # Create placeholder items and start async thumb workers
        for itm in items:
            p_id = itm.get("id")
            name = itm.get("name", "Photo")
            album = itm.get("album", "")
            size_mb = itm.get("size", 0) / (1024 * 1024)

            list_item = QListWidgetItem(f"{name}\n{size_mb:.1f} MB")
            list_item.setData(Qt.ItemDataRole.UserRole, itm)
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.gallery_list.addItem(list_item)

            # Spawn thumb worker
            tw = ThumbWorker(self.phone_host, self.port, p_id)
            tw.thumb_ready.connect(self._on_thumb_ready)
            self._active_thumb_workers.append(tw)
            tw.start()

    def _on_thumb_ready(self, photo_id: int, pixmap: QPixmap):
        for i in range(self.gallery_list.count()):
            itm = self.gallery_list.item(i)
            data = itm.data(Qt.ItemDataRole.UserRole)
            if data and data.get("id") == photo_id:
                itm.setIcon(pixmap)
                break

    def fetch_files(self, path: str):
        if self._files_worker and self._files_worker.isRunning():
            self._files_worker.terminate()
        self._files_worker = FilesWorker(self.phone_host, self.port, path)
        self._files_worker.result_ready.connect(self._on_files_received)
        self._files_worker.error_occurred.connect(self._on_error)
        self._files_worker.start()

    def _on_files_received(self, data: dict):
        self.current_folder_path = data.get("currentPath", self.current_folder_path)
        self.parent_folder_path = data.get("parentPath", "")
        self.txt_breadcrumb.setText(self.current_folder_path)

        self.raw_files_list = data.get("files", [])
        self._apply_sorting()

    def _apply_sorting(self):
        sort_mode = self.cmb_sort.currentText()
        files = list(self.raw_files_list)

        if "Size (Largest ➔ Smallest)" in sort_mode:
            files.sort(key=lambda x: (not x.get("isDir", False), x.get("size", 0)), reverse=True)
        elif "Size (Smallest ➔ Largest)" in sort_mode:
            files.sort(key=lambda x: (x.get("isDir", False), x.get("size", 0)))
        elif "Date (Newest ➔ Oldest)" in sort_mode:
            files.sort(key=lambda x: x.get("date", 0), reverse=True)
        elif "Date (Oldest ➔ Newest)" in sort_mode:
            files.sort(key=lambda x: x.get("date", 0))
        elif "Name (A ➔ Z)" in sort_mode:
            files.sort(key=lambda x: (not x.get("isDir", False), x.get("name", "").lower()))
        elif "Type" in sort_mode:
            files.sort(key=lambda x: (not x.get("isDir", False), os.path.splitext(x.get("name", ""))[1].lower()))

        self.table_files.setRowCount(len(files))
        for row, f in enumerate(files):
            name = f.get("name", "")
            is_dir = f.get("isDir", False)
            size_b = f.get("size", 0)
            date_ms = f.get("date", 0)

            display_name = f"📁 {name}" if is_dir else f"📄 {name}"
            date_str = datetime.fromtimestamp(date_ms / 1000).strftime("%Y-%m-%d %H:%M") if date_ms > 0 else ""
            type_str = "Folder" if is_dir else os.path.splitext(name)[1].upper() or "File"
            size_str = "" if is_dir else (f"{size_b / (1024*1024):.1f} MB" if size_b > 1024*1024 else f"{size_b / 1024:.1f} KB")

            item_name = QTableWidgetItem(display_name)
            item_name.setData(Qt.ItemDataRole.UserRole, f)
            self.table_files.setItem(row, 0, item_name)
            self.table_files.setItem(row, 1, QTableWidgetItem(date_str))
            self.table_files.setItem(row, 2, QTableWidgetItem(type_str))
            self.table_files.setItem(row, 3, QTableWidgetItem(size_str))

    def _on_navigate_up(self):
        if self.parent_folder_path:
            self.fetch_files(self.parent_folder_path)

    def _on_table_item_clicked(self, item: QTableWidgetItem):
        f = self.table_files.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if f:
            self.selected_file_path = f.get("path", "")
            name = f.get("name", "")
            is_dir = f.get("isDir", False)
            size_b = f.get("size", 0)
            self.lbl_preview_name.setText(name)
            if is_dir:
                self.lbl_preview_meta.setText(f"Folder\nPath: {self.selected_file_path}")
            else:
                self.lbl_preview_meta.setText(f"File Size: {size_b / (1024*1024):.2f} MB\nPath: {self.selected_file_path}")

    def _on_table_item_double_clicked(self, item: QTableWidgetItem):
        f = self.table_files.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if f and f.get("isDir", False):
            self.fetch_files(f.get("path", ""))

    def _on_gallery_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.selected_photo_id = data.get("id")
            name = data.get("name", "")
            album = data.get("album", "")
            size_mb = data.get("size", 0) / (1024 * 1024)
            self.lbl_preview_name.setText(name)
            self.lbl_preview_meta.setText(f"Album: {album}\nSize: {size_mb:.2f} MB")

    def _on_gallery_item_double_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self._preview_full_image(data.get("id"), data.get("name", "Image"))

    def _preview_full_image(self, photo_id: int, title: str):
        url = f"http://{self.phone_host}:{self.port}/api/media/raw?id={photo_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()
                img = QImage.fromData(raw_bytes)
                if not img.isNull():
                    dlg = QDialog(self._widget)
                    dlg.setWindowTitle(f"ZeroExplorer - {title}")
                    dlg.resize(800, 600)
                    d_layout = QVBoxLayout(dlg)
                    lbl = QLabel()
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    pix = QPixmap.fromImage(img).scaled(780, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    lbl.setPixmap(pix)
                    d_layout.addWidget(lbl)
                    dlg.exec()
        except Exception as e:
            QMessageBox.warning(self._widget, "Preview Error", f"Could not load image: {e}")

    def _on_copy_selected_image(self):
        if not self.selected_photo_id:
            QMessageBox.information(self._widget, "Copy Image", "Please click on an image in the gallery first.")
            return

        url = f"http://{self.phone_host}:{self.port}/api/media/raw?id={self.selected_photo_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()
                img = QImage.fromData(raw_bytes)
                if not img.isNull():
                    pix = QPixmap.fromImage(img)
                    QApplication.clipboard().setPixmap(pix)
                    QMessageBox.information(self._widget, "Copied!", "Image copied to Windows Clipboard!\nYou can now press Ctrl + V in any application.")
        except Exception as e:
            QMessageBox.warning(self._widget, "Copy Error", f"Failed to copy image: {e}")

    def _on_download_selected_file(self):
        if not self.selected_file_path:
            QMessageBox.information(self._widget, "Download", "Please select a file to download.")
            return

        file_name = os.path.basename(self.selected_file_path)
        save_path, _ = QFileDialog.getSaveFileName(self._widget, "Save File to PC", file_name)
        if not save_path:
            return

        encoded = urllib.parse.quote(self.selected_file_path)
        url = f"http://{self.phone_host}:{self.port}/api/files/download?path={encoded}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=15) as resp, open(save_path, "wb") as f_out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f_out.write(chunk)
            QMessageBox.information(self._widget, "Downloaded", f"File saved successfully to:\n{save_path}")
        except Exception as e:
            QMessageBox.warning(self._widget, "Download Error", f"Failed to download: {e}")

    def _on_error(self, err: str):
        self.status_badge.setText("○ CONNECTION FAILED")
