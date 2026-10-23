"""ZeroLink Hub - ZeroExplorer Download Manager & Progress Queue
Displays live 0-100% itemized file download progress, speed, ETA, and quick file/folder actions.
"""

import os
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread, QUrl
from PyQt6.QtGui import QFont, QColor, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QFrame, QMessageBox, QApplication, QSizePolicy
)


class DownloadTask(QThread):
    """Background file downloader with chunked transfer, live speed, and ETA calculation."""
    progress = pyqtSignal(int, int, float)   # downloaded_bytes, total_bytes, speed_bps
    finished = pyqtSignal(bool, str)        # success, result_path_or_error

    def __init__(self, task_id: str, download_url: str, save_path: str, display_name: str, file_type: str = "file"):
        super().__init__()
        self.task_id = task_id
        self.download_url = download_url
        self.save_path = save_path
        self.display_name = display_name
        self.file_type = file_type.lower()  # "video", "image", "doc", "file"
        self.status = "queued"              # "queued", "downloading", "completed", "error", "cancelled"
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.speed_bps = 0.0
        self.error_message = ""
        self._is_cancelled = False
        self.start_time = 0.0

    def cancel(self):
        self._is_cancelled = True
        self.status = "cancelled"

    def run(self):
        self.status = "downloading"
        self.start_time = time.time()
        last_calc_time = self.start_time
        last_calc_bytes = 0

        try:
            req = urllib.request.Request(self.download_url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.total_bytes = int(resp.headers.get("Content-Length", 0))
                self.downloaded_bytes = 0

                # Ensure parent directory exists
                os.makedirs(os.path.dirname(os.path.abspath(self.save_path)), exist_ok=True)

                with open(self.save_path, "wb") as f_out:
                    while not self._is_cancelled:
                        chunk = resp.read(131072)  # 128 KB
                        if not chunk:
                            break
                        f_out.write(chunk)
                        self.downloaded_bytes += len(chunk)

                        now = time.time()
                        dt = now - last_calc_time
                        if dt >= 0.25:  # Update speed and progress every 250ms
                            self.speed_bps = (self.downloaded_bytes - last_calc_bytes) / dt
                            last_calc_time = now
                            last_calc_bytes = self.downloaded_bytes
                            self.progress.emit(self.downloaded_bytes, self.total_bytes, self.speed_bps)

                if self._is_cancelled:
                    self.status = "cancelled"
                    if os.path.exists(self.save_path):
                        try:
                            os.remove(self.save_path)
                        except Exception:
                            pass
                    self.finished.emit(False, "Download cancelled by user")
                else:
                    self.status = "completed"
                    self.progress.emit(self.downloaded_bytes, self.total_bytes, 0.0)
                    self.finished.emit(True, self.save_path)

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            self.finished.emit(False, str(e))


class DownloadItemWidget(QFrame):
    """Sleek item card for an individual download task with a 0-100% progress bar."""
    retry_requested = pyqtSignal(str)   # task_id
    cancelled = pyqtSignal(str)         # task_id

    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self.task = task

        self.setStyleSheet("""
            DownloadItemWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 12px 14px;
            }
            DownloadItemWidget:hover {
                border-color: #D1D5DB;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Top Row: Icon + File Name + Percent Badge + Cancel / Actions
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # Icon / Badge by file type
        glyph = "📄"
        type_badge = "FILE"
        if "video" in self.task.file_type or self.task.display_name.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
            glyph = "🎬"
            type_badge = "VIDEO"
        elif "image" in self.task.file_type or "photo" in self.task.file_type or self.task.display_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
            glyph = "🖼"
            type_badge = "PHOTO"
        elif self.task.display_name.lower().endswith((".pdf", ".doc", ".docx", ".txt", ".zip", ".apk")):
            glyph = "📦" if self.task.display_name.lower().endswith((".zip", ".apk")) else "📄"
            type_badge = self.task.display_name.split(".")[-1].upper()

        self.lbl_icon = QLabel(glyph)
        self.lbl_icon.setFont(QFont("Segoe UI Emoji", 16))
        top_row.addWidget(self.lbl_icon)

        # Name & Subtitle
        name_col = QVBoxLayout()
        name_col.setSpacing(2)

        self.lbl_name = QLabel(self.task.display_name)
        self.lbl_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #111827;")
        self.lbl_name.setToolTip(f"{self.task.display_name}\nTarget: {self.task.save_path}")
        name_col.addWidget(self.lbl_name)

        self.lbl_target = QLabel(os.path.basename(os.path.dirname(self.task.save_path)) + "/" + os.path.basename(self.task.save_path))
        self.lbl_target.setFont(QFont("Segoe UI", 9))
        self.lbl_target.setStyleSheet("color: #6B7280;")
        name_col.addWidget(self.lbl_target)

        top_row.addLayout(name_col, 1)

        # Status / Percent Badge
        self.lbl_percent = QLabel("0%")
        self.lbl_percent.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_percent.setStyleSheet("color: #111827; min-width: 45px;")
        self.lbl_percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.lbl_percent)

        # Action Buttons Container
        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #4B5563;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #FEE2E2;
                color: #DC2626;
                border-color: #FCA5A5;
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        top_row.addWidget(self.btn_cancel)

        # Completed Actions: Open File & Open Folder (Initially Hidden)
        self.btn_open = QPushButton("▶ Open")
        self.btn_open.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        self.btn_open.clicked.connect(self._on_open_file)
        self.btn_open.setVisible(False)
        top_row.addWidget(self.btn_open)

        self.btn_folder = QPushButton("📁 Folder")
        self.btn_folder.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_folder.clicked.connect(self._on_open_folder)
        self.btn_folder.setVisible(False)
        top_row.addWidget(self.btn_folder)

        layout.addLayout(top_row)

        # Middle: Progress Bar (0-100%)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(7)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #F3F4F6;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #111827;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Bottom Row: Live Stats (Size downloaded / Total • Speed • ETA)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)

        self.lbl_stats = QLabel("Connecting...")
        self.lbl_stats.setFont(QFont("Segoe UI", 9))
        self.lbl_stats.setStyleSheet("color: #6B7280;")
        stats_row.addWidget(self.lbl_stats, 1)

        self.lbl_speed = QLabel("")
        self.lbl_speed.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.lbl_speed.setStyleSheet("color: #111827;")
        stats_row.addWidget(self.lbl_speed)

        layout.addLayout(stats_row)

        # Wire Task signals
        self.task.progress.connect(self._on_task_progress)
        self.task.finished.connect(self._on_task_finished)

    def _on_cancel_clicked(self):
        self.task.cancel()
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelling...")
        self.cancelled.emit(self.task.task_id)

    def _on_open_file(self):
        if os.path.exists(self.task.save_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.task.save_path))

    def _on_open_folder(self):
        folder = os.path.dirname(os.path.abspath(self.task.save_path))
        if os.path.exists(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_task_progress(self, downloaded: int, total: int, speed_bps: float):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(min(100, max(0, pct)))
            self.lbl_percent.setText(f"{pct}%")

            mb_down = downloaded / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            self.lbl_stats.setText(f"{mb_down:.1f} MB of {mb_tot:.1f} MB")

            # Speed & ETA
            if speed_bps > 0:
                mb_s = speed_bps / (1024 * 1024)
                rem_bytes = max(0, total - downloaded)
                rem_sec = int(rem_bytes / speed_bps)
                if rem_sec >= 60:
                    eta_str = f"~{rem_sec // 60}m {rem_sec % 60}s left"
                else:
                    eta_str = f"~{rem_sec}s left"
                self.lbl_speed.setText(f"⚡ {mb_s:.1f} MB/s • {eta_str}")
            else:
                self.lbl_speed.setText("")
        else:
            # Stream with unknown Content-Length
            mb_down = downloaded / (1024 * 1024)
            self.progress_bar.setRange(0, 0)  # indeterminate animation
            self.lbl_stats.setText(f"Downloaded {mb_down:.1f} MB")
            if speed_bps > 0:
                mb_s = speed_bps / (1024 * 1024)
                self.lbl_speed.setText(f"⚡ {mb_s:.1f} MB/s")

    def _on_task_finished(self, success: bool, msg: str):
        self.btn_cancel.setVisible(False)

        if success:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #ECFDF5; border: none; border-radius: 3px; }
                QProgressBar::chunk { background-color: #059669; border-radius: 3px; }
            """)
            self.lbl_percent.setText("100%")
            self.lbl_percent.setStyleSheet("color: #059669; font-weight: bold; min-width: 45px;")

            size_mb = 0.0
            if os.path.exists(self.task.save_path):
                size_mb = os.path.getsize(self.task.save_path) / (1024 * 1024)

            self.lbl_stats.setText(f"✔ Completed ({size_mb:.1f} MB)")
            self.lbl_stats.setStyleSheet("color: #059669; font-weight: 600;")
            self.lbl_speed.setText("")

            self.btn_open.setVisible(True)
            self.btn_folder.setVisible(True)
        else:
            self.progress_bar.setStyleSheet("""
                QProgressBar { background-color: #FEF2F2; border: none; border-radius: 3px; }
                QProgressBar::chunk { background-color: #DC2626; border-radius: 3px; }
            """)
            if self.task.status == "cancelled":
                self.lbl_stats.setText("✖ Cancelled by user")
                self.lbl_stats.setStyleSheet("color: #6B7280;")
            else:
                self.lbl_stats.setText(f"⚠ Failed: {msg}")
                self.lbl_stats.setStyleSheet("color: #DC2626;")
            self.lbl_speed.setText("")


class DownloadManagerDialog(QDialog):
    """Floating & itemized Download Manager for ZeroExplorer with 0-100% item progress list."""
    active_count_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ZeroExplorer - Download Manager")
        self.resize(560, 480)
        self.setMinimumSize(420, 320)
        self.setStyleSheet("background-color: #F9FAFB;")

        self.tasks: Dict[str, DownloadTask] = {}
        self.item_widgets: Dict[str, DownloadItemWidget] = {}

        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        # Header: Title + Active Badge + Clear + Open Folder
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel("📥")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 15))
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)

        title = QLabel("Downloads & Transfers")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #111827;")
        title_col.addWidget(title)

        self.lbl_summary = QLabel("0 active downloads")
        self.lbl_summary.setFont(QFont("Segoe UI", 9))
        self.lbl_summary.setStyleSheet("color: #6B7280;")
        title_col.addWidget(self.lbl_summary)

        header_row.addLayout(title_col, 1)

        self.btn_clear_done = QPushButton("Clear Finished")
        self.btn_clear_done.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_clear_done.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_done.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #4B5563;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
                color: #111827;
            }
        """)
        self.btn_clear_done.clicked.connect(self.clear_completed)
        header_row.addWidget(self.btn_clear_done)

        self.btn_open_dest = QPushButton("📁 Downloads")
        self.btn_open_dest.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_open_dest.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_dest.setStyleSheet("""
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
        self.btn_open_dest.clicked.connect(self._open_default_downloads)
        header_row.addWidget(self.btn_open_dest)

        root_layout.addLayout(header_row)

        # Scroll Area for Download Items
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                background-color: #F3F4F6;
            }
        """)

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #F3F4F6;")
        self.items_layout = QVBoxLayout(self.container)
        self.items_layout.setContentsMargins(10, 10, 10, 10)
        self.items_layout.setSpacing(10)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty State Placeholder
        self.empty_placeholder = QWidget()
        empty_layout = QVBoxLayout(self.empty_placeholder)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setContentsMargins(20, 60, 20, 60)
        empty_layout.setSpacing(8)

        empty_icon = QLabel("📥")
        empty_icon.setFont(QFont("Segoe UI Emoji", 28))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_txt = QLabel("No active or recent downloads")
        empty_txt.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        empty_txt.setStyleSheet("color: #4B5563;")
        empty_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_txt)

        empty_sub = QLabel("Files, photos, and videos downloaded from ZeroExplorer\nwill show 0-100% itemized progress here.")
        empty_sub.setFont(QFont("Segoe UI", 9))
        empty_sub.setStyleSheet("color: #9CA3AF;")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_sub)

        self.items_layout.addWidget(self.empty_placeholder)

        self.scroll.setWidget(self.container)
        root_layout.addWidget(self.scroll, 1)

    def add_download(self, download_url: str, save_path: str, display_name: str, file_type: str = "file") -> DownloadTask:
        """Adds a new download item to the queue and starts background transfer."""
        task_id = f"dl_{int(time.time() * 1000)}_{len(self.tasks)}"
        task = DownloadTask(task_id, download_url, save_path, display_name, file_type)

        self.empty_placeholder.setVisible(False)

        item_widget = DownloadItemWidget(task, parent=self.container)
        self.tasks[task_id] = task
        self.item_widgets[task_id] = item_widget

        # Insert at the top of the list so newest download is first
        self.items_layout.insertWidget(0, item_widget)

        # Wire finished signal to update summary count
        task.finished.connect(lambda _, __: self._update_summary())

        # Start downloading
        task.start()

        self._update_summary()

        # Pop up and bring download window to front
        self.show()
        self.raise_()
        self.activateWindow()

        return task

    def clear_completed(self):
        """Removes all finished, cancelled, or failed items from the view."""
        to_remove = []
        for t_id, task in self.tasks.items():
            if task.status in ["completed", "cancelled", "error"]:
                to_remove.append(t_id)

        for t_id in to_remove:
            widget = self.item_widgets.pop(t_id, None)
            if widget:
                self.items_layout.removeWidget(widget)
                widget.deleteLater()
            self.tasks.pop(t_id, None)

        if not self.tasks:
            self.empty_placeholder.setVisible(True)

        self._update_summary()

    def get_active_count(self) -> int:
        return sum(1 for t in self.tasks.values() if t.status in ["downloading", "queued"])

    def _update_summary(self):
        active = self.get_active_count()
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == "completed")

        if active > 0:
            self.lbl_summary.setText(f"{active} downloading • {completed} of {total} completed")
        elif total > 0:
            self.lbl_summary.setText(f"All {total} downloads finished ({completed} successful)")
        else:
            self.lbl_summary.setText("0 active downloads")

        self.active_count_changed.emit(active)

    def _open_default_downloads(self):
        dest = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(dest):
            dest = os.path.expanduser("~")
        QDesktopServices.openUrl(QUrl.fromLocalFile(dest))

    def closeEvent(self, event):
        # Don't destroy ongoing tasks, just hide window
        self.hide()
        event.ignore()
