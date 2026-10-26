"""ZeroLink PC Hub - One-Click Auto-Update Dialog (Monochrome Minimalist Edition)
"""

import os
import sys
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QFont, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame, QMessageBox, QApplication
)

from core.updater import CURRENT_VERSION, UpdateDownloadWorker, apply_update_and_restart


class UpdateDialog(QDialog):
    """Modern modal dialog allowing 1-click in-place update with download progress."""

    def __init__(
        self,
        tag_name: str,
        html_url: str,
        release_notes: str,
        zip_url: str = "",
        zip_size: int = 0,
        parent=None
    ):
        super().__init__(parent)
        self.tag_name = tag_name
        self.html_url = html_url
        self.release_notes = release_notes
        self.zip_url = zip_url
        self.zip_size = zip_size
        self.download_worker: UpdateDownloadWorker = None

        self.setWindowTitle(f"ZeroLink Update — {tag_name}")
        self.setFixedSize(500, 440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #0E0E0E;
                color: #FFFFFF;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QLabel {
                color: #DDDDDD;
            }
            QTextEdit {
                background-color: #161616;
                color: #CCCCCC;
                border: 1px solid #2B2B2B;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
                line-height: 1.5;
            }
            QProgressBar {
                background-color: #1A1A1A;
                border: 1px solid #333333;
                border-radius: 4px;
                height: 8px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background-color: #FFFFFF;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3A3A3A;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2D2D2D;
                border-color: #555555;
            }
            QPushButton#btn_primary {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #FFFFFF;
            }
            QPushButton#btn_primary:hover {
                background-color: #D6D6D6;
                border-color: #D6D6D6;
            }
            QPushButton#btn_primary:disabled {
                background-color: #444444;
                color: #888888;
                border-color: #444444;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Section
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        lbl_header = QLabel("NEW VERSION AVAILABLE")
        lbl_header.setStyleSheet("color: #888888; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        title_box.addWidget(lbl_header)

        ver_text = f"v{CURRENT_VERSION}  →  <span style='color:#FFFFFF; font-weight:bold;'>{self.tag_name}</span>"
        lbl_version = QLabel(ver_text)
        lbl_version.setStyleSheet("font-size: 18px; color: #AAAAAA;")
        lbl_version.setTextFormat(Qt.TextFormat.RichText)
        title_box.addWidget(lbl_version)

        header_layout.addLayout(title_box)
        header_layout.addStretch()

        badge = QLabel("READY TO INSTALL")
        badge.setStyleSheet("color: #FFFFFF; background-color: #222222; border: 1px solid #444444; border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: 700;")
        header_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_layout)

        # Release Notes Label & Box
        lbl_notes_title = QLabel("What's New:")
        lbl_notes_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #888888; text-transform: uppercase;")
        layout.addWidget(lbl_notes_title)

        self.txt_notes = QTextEdit()
        self.txt_notes.setReadOnly(True)
        self.txt_notes.setPlainText(self.release_notes.strip() or "No detailed changelog provided.")
        layout.addWidget(self.txt_notes, stretch=1)

        # Progress Section (Initially hidden)
        self.progress_frame = QFrame()
        p_layout = QVBoxLayout(self.progress_frame)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(6)

        self.lbl_progress_status = QLabel("Preparing download...")
        self.lbl_progress_status.setStyleSheet("font-size: 11px; color: #AAAAAA;")
        p_layout.addWidget(self.lbl_progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        p_layout.addWidget(self.progress_bar)
        self.progress_frame.setVisible(False)
        layout.addWidget(self.progress_frame)

        # Action Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)

        self.btn_browser = QPushButton("Open GitHub")
        self.btn_browser.clicked.connect(self._on_open_browser)
        self.btn_layout.addWidget(self.btn_browser)

        self.btn_layout.addStretch()

        self.btn_cancel = QPushButton("Later")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_layout.addWidget(self.btn_cancel)

        self.btn_update = QPushButton("Update Now")
        self.btn_update.setObjectName("btn_primary")
        if not self.zip_url:
            self.btn_update.setEnabled(False)
            self.btn_update.setToolTip("No Windows zip release asset detected.")
        else:
            self.btn_update.clicked.connect(self._on_start_update)
        self.btn_layout.addWidget(self.btn_update)

        layout.addLayout(self.btn_layout)

    def _on_open_browser(self):
        QDesktopServices.openUrl(QUrl(self.html_url))

    def _on_cancel(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
        self.reject()

    def _on_start_update(self):
        if not self.zip_url:
            return

        self.btn_update.setEnabled(False)
        self.btn_cancel.setText("Cancel")
        self.progress_frame.setVisible(True)
        self.lbl_progress_status.setText("Connecting to download server...")

        self.download_worker = UpdateDownloadWorker(
            download_url=self.zip_url,
            total_size=self.zip_size,
            parent=self
        )
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.failed.connect(self._on_download_failed)
        self.download_worker.start()

    def _on_download_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            dl_mb = downloaded / (1024 * 1024)
            tot_mb = total / (1024 * 1024)
            self.lbl_progress_status.setText(f"Downloading update: {dl_mb:.1f} MB / {tot_mb:.1f} MB ({pct}%)")
        else:
            dl_mb = downloaded / (1024 * 1024)
            self.lbl_progress_status.setText(f"Downloading update: {dl_mb:.1f} MB...")

    def _on_download_finished(self, zip_path: str):
        self.lbl_progress_status.setText("Download complete! Applying update...")
        self.progress_bar.setValue(100)

        is_frozen = getattr(sys, "frozen", False)
        if not is_frozen:
            QMessageBox.information(
                self,
                "Development Mode",
                f"Update archive downloaded successfully to:\n{zip_path}\n\n"
                "Auto-replace is disabled when running in source developer mode."
            )
            self.accept()
            return

        # Trigger in-place update and exit
        applied = apply_update_and_restart(zip_path)
        if applied:
            self.lbl_progress_status.setText("Restarting ZeroLink in 2 seconds...")
            QTimer.singleShot(1500, lambda: QApplication.quit())
        else:
            self._on_download_failed("Could not launch updater script.")

    def _on_download_failed(self, error_msg: str):
        self.progress_frame.setVisible(False)
        self.btn_update.setEnabled(True)
        self.btn_cancel.setText("Close")
        QMessageBox.warning(
            self,
            "Update Failed",
            f"Could not complete the automatic update:\n{error_msg}\n\n"
            "You can still download the release manually from GitHub."
        )
