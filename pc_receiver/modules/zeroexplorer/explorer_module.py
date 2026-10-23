"""ZeroLink Hub - ZeroExplorer Module
All-in-One Phone Gallery, Storage Explorer, Media Streamer & File Manager.
"""

import os
import sys
from typing import Optional, List, Dict
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QSplitter, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
    QProgressBar, QScrollArea, QFileDialog, QMessageBox, QMenu
)

from core.base_module import BaseModule
from modules.zeroexplorer.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


class ZeroExplorerModule(BaseModule):
    """ZeroExplorer: Unified Media Gallery & Storage Manager for Phone."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self._widget: Optional[QWidget] = None
        self._is_active = False

        # State
        self.phone_ip = "127.0.0.1"
        self.current_folder_path = "/storage/emulated/0"
        self.favorites: List[str] = [
            "/storage/emulated/0/Download",
            "/storage/emulated/0/DCIM/Camera",
            "/storage/emulated/0/Pictures/Screenshots",
            "/storage/emulated/0/Documents"
        ]

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
        self.status_changed.emit(self.module_id, f"Listening on port {self.port}")
        return True

    def stop_service(self) -> bool:
        self._is_active = False
        self.state_changed.emit(self.module_id, False)
        self.status_changed.emit(self.module_id, "Stopped")
        return True

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._create_ui()
        return self._widget

    def _create_ui(self) -> QWidget:
        root = QWidget()
        root.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # ==================== Top Header ====================
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel(MODULE_ICON)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 20))
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

        desc_lbl = QLabel("High-speed Phone Gallery, Storage Explorer, Media Streamer & File Manager")
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setStyleSheet("color: #6B7280;")
        title_col.addWidget(desc_lbl)

        header_row.addLayout(title_col, 1)

        # Status and Controls
        self.status_badge = QLabel("● READY")
        self.status_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_badge.setStyleSheet("""
            background-color: #FFFFFF;
            color: #111827;
            border: 1px solid #D1D5DB;
            padding: 4px 10px;
            border-radius: 6px;
        """)
        header_row.addWidget(self.status_badge)

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
                border-color: #9CA3AF;
            }
        """)
        self.btn_refresh.clicked.connect(self._on_refresh)
        header_row.addWidget(self.btn_refresh)

        layout.addLayout(header_row)

        # ==================== Storage Breakdown Bar ====================
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
        self.lbl_storage_title = QLabel("Internal Storage Usage")
        self.lbl_storage_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_storage_title.setStyleSheet("color: #111827; border: none;")
        s_header.addWidget(self.lbl_storage_title)

        s_header.addStretch()

        self.lbl_storage_details = QLabel("68.4 GB / 128 GB (46% Free)")
        self.lbl_storage_details.setFont(QFont("Segoe UI", 9))
        self.lbl_storage_details.setStyleSheet("color: #4B5563; border: none;")
        s_header.addWidget(self.lbl_storage_details)
        s_layout.addLayout(s_header)

        self.storage_progress = QProgressBar()
        self.storage_progress.setFixedHeight(6)
        self.storage_progress.setTextVisible(False)
        self.storage_progress.setValue(54)
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
        self.tabs.addTab(self.tab_gallery, "🖼️ Photo Gallery")

        # Tab 2: Files & Storage Explorer
        self.tab_files = self._build_files_tab()
        self.tabs.addTab(self.tab_files, "📂 Files & Storage")

        layout.addWidget(self.tabs, 1)

        return root

    def _build_gallery_tab(self) -> QWidget:
        """Builds the Photo Gallery viewport."""
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Filter and Search Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.btn_alb_all = QPushButton("All Media")
        self.btn_alb_cam = QPushButton("📷 Camera")
        self.btn_alb_shot = QPushButton("📱 Screenshots")
        self.btn_alb_down = QPushButton("📥 Downloads")

        for btn in [self.btn_alb_all, self.btn_alb_cam, self.btn_alb_shot, self.btn_alb_down]:
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #F9FAFB;
                    color: #374151;
                    border: 1px solid #E5E7EB;
                    border-radius: 6px;
                    padding: 5px 12px;
                }
                QPushButton:hover {
                    background-color: #F3F4F6;
                    color: #111827;
                }
            """)
            filter_row.addWidget(btn)

        filter_row.addStretch()

        self.btn_copy_image = QPushButton("📋 Copy Image to Clipboard")
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
        filter_row.addWidget(self.btn_copy_image)

        layout.addLayout(filter_row)

        # Recent Strip Label
        lbl_recent = QLabel("RECENT MEDIA (Taken Today / Recent)")
        lbl_recent.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl_recent.setStyleSheet("color: #6B7280; letter-spacing: 0.5px;")
        layout.addWidget(lbl_recent)

        # Gallery placeholder / grid
        self.gallery_list = QListWidget()
        self.gallery_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery_list.setIconSize(QSize(120, 120))
        self.gallery_list.setGridSize(QSize(140, 150))
        self.gallery_list.setSpacing(10)
        self.gallery_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #F3F4F6;
                border-radius: 8px;
                background-color: #FFFFFF;
            }
            QListWidget::item {
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 4px;
                text-align: center;
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
        layout.addWidget(self.gallery_list, 1)

        return tab

    def _build_files_tab(self) -> QWidget:
        """Builds the Files & Storage Explorer viewport."""
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ==================== Top Breadcrumbs & Actions Row ====================
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
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        top_bar.addWidget(self.btn_up_folder)

        # Breadcrumbs bar
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
        top_bar.addWidget(self.txt_breadcrumb, 1)

        # Sort Dropdown
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
        top_bar.addWidget(self.cmb_sort)

        # In-Place Action Buttons
        self.btn_new_folder = QPushButton("+ New Folder")
        self.btn_new_folder.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_new_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_folder.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        top_bar.addWidget(self.btn_new_folder)

        self.btn_upload = QPushButton("⇪ Upload to Phone")
        self.btn_upload.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_upload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_upload.setStyleSheet("""
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
        top_bar.addWidget(self.btn_upload)

        layout.addLayout(top_bar)

        # ==================== Splitter: Sidebar + File Table + Preview ====================
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Left Favorites Sidebar
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
                padding: 6px 8px;
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
        for fav in ["📥 Downloads", "📷 Camera Roll", "📱 Screenshots", "📄 Documents", "💾 Storage Root"]:
            self.list_favorites.addItem(fav)
        side_layout.addWidget(self.list_favorites, 1)

        splitter.addWidget(sidebar)

        # 2. Center File Table
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
        splitter.addWidget(self.table_files)

        # 3. Right Quick Preview Pane
        self.preview_pane = QFrame()
        self.preview_pane.setFixedWidth(210)
        self.preview_pane.setStyleSheet("""
            QFrame {
                background-color: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        p_layout = QVBoxLayout(self.preview_pane)
        p_layout.setContentsMargins(12, 12, 12, 12)
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

        self.lbl_preview_meta = QLabel("Select a file to inspect details, preview text, or stream video.")
        self.lbl_preview_meta.setFont(QFont("Segoe UI", 8))
        self.lbl_preview_meta.setStyleSheet("color: #6B7280; border: none;")
        self.lbl_preview_meta.setWordWrap(True)
        p_layout.addWidget(self.lbl_preview_meta)

        p_layout.addStretch()

        self.btn_download_file = QPushButton("⬇ Download to PC")
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
        p_layout.addWidget(self.btn_download_file)

        splitter.addWidget(self.preview_pane)
        splitter.setSizes([160, 480, 180])

        layout.addWidget(splitter, 1)

        return tab

    def _on_refresh(self):
        """Simulates or performs refresh of folder and gallery items."""
        self.status_badge.setText("● SYNCING...")
        QTimer.singleShot(600, lambda: self.status_badge.setText("● READY"))
