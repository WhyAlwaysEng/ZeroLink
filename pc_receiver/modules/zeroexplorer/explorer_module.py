"""ZeroLink Hub - ZeroExplorer Module
All-in-One Phone Gallery, Storage Explorer, Media Streamer & File Manager.
Featuring Pro Image Viewer (Zoom & Pan), Full Video Player (Timeline & Snap Frame),
and Clear File Explorer with Instant Filter & Category Badges.
"""

import os
import sys
import time
import json
import queue
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize, QTimer, QUrl, QPointF
from PyQt6.QtGui import (
    QFont, QPixmap, QImage, QClipboard, QDesktopServices, QIcon,
    QColor, QPainter, QTransform, QKeySequence, QShortcut
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QSplitter, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
    QProgressBar, QFileDialog, QMessageBox, QApplication, QDialog,
    QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QMenu
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.base_module import BaseModule
from core.adb_helper import AdbManager
from modules.zeroexplorer.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)
from modules.zeroexplorer.download_manager import DownloadManagerDialog


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


class MediaWorker(QThread):
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, host: str, port: int, media_type: str = "all", album: Optional[str] = None, offset: int = 0, limit: int = 80):
        super().__init__()
        self.host = host
        self.port = port
        self.media_type = media_type
        self.album = album
        self.offset = offset
        self.limit = limit

    def run(self):
        params = [f"type={self.media_type}", f"offset={self.offset}", f"limit={self.limit}"]
        if self.album:
            params.append(f"album={urllib.parse.quote(self.album)}")
        query_str = "&".join(params)
        url = f"http://{self.host}:{self.port}/api/gallery/media?{query_str}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.result_ready.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))


class FilesWorker(QThread):
    result_ready = pyqtSignal(int, dict)
    error_occurred = pyqtSignal(int, str)

    def __init__(self, host: str, port: int, path: str, request_id: int = 0):
        super().__init__()
        self.host = host
        self.port = port
        self.path = path
        self.request_id = request_id

    def run(self):
        encoded = urllib.parse.quote(self.path)
        url = f"http://{self.host}:{self.port}/api/files/list?path={encoded}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.result_ready.emit(self.request_id, data)
        except Exception as e:
            self.error_occurred.emit(self.request_id, str(e))


class ThumbQueueWorker(QThread):
    thumb_ready = pyqtSignal(int, QPixmap)

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port
        self._queue = queue.Queue()
        self._is_cancelled = False
        self._is_paused = False
        self._enqueued_ids = set()

    def add_items(self, items: List[Dict]):
        for itm in items:
            p_id = itm.get("id")
            if p_id is not None and p_id not in self._enqueued_ids:
                self._enqueued_ids.add(p_id)
                self._queue.put(itm)

    def set_paused(self, paused: bool):
        self._is_paused = paused

    def clear(self):
        self._enqueued_ids.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break

    def cancel(self):
        self._is_cancelled = True
        self.clear()

    def run(self):
        while not self._is_cancelled:
            if self._is_paused:
                time.sleep(0.08)
                continue

            try:
                itm = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            p_id = itm.get("id")
            is_video = itm.get("type") == "video"
            type_param = "video" if is_video else "image"
            url = f"http://{self.host}:{self.port}/api/media/thumb?id={p_id}&type={type_param}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    raw_bytes = resp.read()
                    img = QImage.fromData(raw_bytes)
                    if not img.isNull():
                        # Format into a clean 120x120 centered thumbnail
                        scaled = img.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        canvas = QPixmap(120, 120)
                        canvas.fill(QColor(0, 0, 0, 0))
                        painter = QPainter(canvas)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        x = (120 - scaled.width()) // 2
                        y = (120 - scaled.height()) // 2
                        painter.drawImage(x, y, scaled)
                        painter.end()
                        self.thumb_ready.emit(p_id, canvas)
            except Exception:
                pass
            time.sleep(0.01)


class FileDownloadWorker(QThread):
    """Background file downloader with chunked transfer and progress reporting."""
    progress = pyqtSignal(int, int)   # downloaded_bytes, total_bytes
    finished = pyqtSignal(bool, str)  # success, message/path

    def __init__(self, download_url: str, save_path: str):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            req = urllib.request.Request(self.download_url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_len = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(self.save_path, "wb") as f_out:
                    while not self._is_cancelled:
                        chunk = resp.read(131072)  # 128 KB
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total_len)

                if self._is_cancelled:
                    if os.path.exists(self.save_path):
                        try:
                            os.remove(self.save_path)
                        except Exception:
                            pass
                    self.finished.emit(False, "Download cancelled")
                else:
                    self.finished.emit(True, self.save_path)
        except Exception as e:
            self.finished.emit(False, str(e))


# ==================== Pro Interactive Image Viewer Dialog ====================

class ProImageViewerDialog(QDialog):
    """Pro Image Viewer with Mouse Wheel Zoom, Click-Drag Pan, 1:1 vs Fit, and Next/Prev."""

    def __init__(self, host: str, port: int, media_list: List[Dict], initial_index: int, parent=None, explorer_module=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.explorer_module = explorer_module
        self.media_list = [m for m in media_list if m.get("type") == "image"]
        self.current_index = initial_index
        self.current_pixmap: Optional[QPixmap] = None
        self.rotation_angle = 0

        self.setWindowTitle("ZeroExplorer Image Viewer")
        self.resize(1000, 720)
        self.setStyleSheet("background-color: #111827; color: #FFFFFF;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        # Top Toolbar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.lbl_title = QLabel("Loading image...")
        self.lbl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet("color: #F9FAFB;")
        top_bar.addWidget(self.lbl_title, 1)

        self.btn_fit = QPushButton("Fit")
        self.btn_original = QPushButton("1:1")
        self.btn_rot_left = QPushButton("↶ Rotate")
        self.btn_rot_right = QPushButton("↷ Rotate")
        self.btn_copy = QPushButton("📋 Copy")
        self.btn_save = QPushButton("⬇ Save")

        for b in [self.btn_fit, self.btn_original, self.btn_rot_left, self.btn_rot_right, self.btn_copy, self.btn_save]:
            b.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #1F2937;
                    color: #F9FAFB;
                    border: 1px solid #374151;
                    border-radius: 6px;
                    padding: 5px 12px;
                }
                QPushButton:hover {
                    background-color: #374151;
                    border-color: #6B7280;
                }
            """)
            top_bar.addWidget(b)

        self.btn_fit.clicked.connect(self._fit_to_view)
        self.btn_original.clicked.connect(self._reset_to_100)
        self.btn_rot_left.clicked.connect(lambda: self._rotate_image(-90))
        self.btn_rot_right.clicked.connect(lambda: self._rotate_image(90))
        self.btn_copy.clicked.connect(self._copy_image)
        self.btn_save.clicked.connect(self._save_image)

        layout.addLayout(top_bar)

        # Main Graphics View for Smooth Zoom & Pan
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setStyleSheet("background-color: #0B0D13; border: 1px solid #1F2937; border-radius: 8px;")
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        layout.addWidget(self.view, 1)

        # Bottom Bar: Next / Prev Navigation
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.btn_prev = QPushButton("◀ Previous (Left Arrow)")
        self.btn_next = QPushButton("Next (Right Arrow) ▶")

        for b in [self.btn_prev, self.btn_next]:
            b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #1F2937;
                    color: #FFFFFF;
                    border: 1px solid #374151;
                    border-radius: 6px;
                    padding: 7px 18px;
                }
                QPushButton:hover {
                    background-color: #374151;
                }
            """)

        self.btn_prev.clicked.connect(self._prev_image)
        self.btn_next.clicked.connect(self._next_image)

        bottom_bar.addWidget(self.btn_prev)
        bottom_bar.addStretch()

        self.lbl_hint = QLabel("Tip: Mouse wheel to Zoom • Click & Drag to Pan")
        self.lbl_hint.setFont(QFont("Segoe UI", 9))
        self.lbl_hint.setStyleSheet("color: #9CA3AF;")
        bottom_bar.addWidget(self.lbl_hint)

        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_next)
        layout.addLayout(bottom_bar)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._prev_image)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._next_image)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

        # Override wheel event for zoom
        self.view.wheelEvent = self._on_view_wheel

        # Load first image
        self._load_current_image()

    def _on_view_wheel(self, event):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 0.85
        self.view.scale(factor, factor)

    def _load_current_image(self):
        if not self.media_list or self.current_index < 0 or self.current_index >= len(self.media_list):
            return

        itm = self.media_list[self.current_index]
        p_id = itm.get("id")
        name = itm.get("name", "Image")
        size_mb = itm.get("size", 0) / (1024 * 1024)

        self.lbl_title.setText(f"[{self.current_index + 1} / {len(self.media_list)}]  {name}  ({size_mb:.2f} MB)")
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < len(self.media_list) - 1)

        url = f"http://{self.host}:{self.port}/api/media/raw?id={p_id}&type=image&download=false"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()
                img = QImage.fromData(raw_bytes)
                if not img.isNull():
                    self.current_pixmap = QPixmap.fromImage(img)
                    self.rotation_angle = 0
                    self._update_display_pixmap()
                    self._fit_to_view()
        except Exception as e:
            self.lbl_title.setText(f"Error loading {name}: {e}")

    def _update_display_pixmap(self):
        if not self.current_pixmap:
            return
        t = QTransform().rotate(self.rotation_angle)
        rotated = self.current_pixmap.transformed(t, Qt.TransformationMode.SmoothTransformation)
        self.pixmap_item.setPixmap(rotated)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

    def _rotate_image(self, degrees: int):
        self.rotation_angle = (self.rotation_angle + degrees) % 360
        self._update_display_pixmap()

    def _fit_to_view(self):
        if not self.pixmap_item.pixmap().isNull():
            self.view.resetTransform()
            self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _reset_to_100(self):
        self.view.resetTransform()

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _next_image(self):
        if self.current_index < len(self.media_list) - 1:
            self.current_index += 1
            self._load_current_image()

    def _copy_image(self):
        if self.current_pixmap:
            QApplication.clipboard().setPixmap(self.current_pixmap)
            QMessageBox.information(self, "Copied", "Image copied to Windows Clipboard!")

    def _save_image(self):
        if not self.media_list or self.current_index < 0:
            return
        itm = self.media_list[self.current_index]
        p_id = itm.get("id")
        name = itm.get("name", "photo.jpg")
        default_dir = os.path.join(os.path.expanduser("~"), "Pictures")
        if not os.path.exists(default_dir):
            default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        default_path = os.path.join(default_dir, name)
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Image to PC", default_path, "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)")
        if not save_path:
            return

        dl_url = f"http://{self.host}:{self.port}/api/media/raw?id={p_id}&type=image&download=true"
        if getattr(self, "explorer_module", None):
            self.explorer_module.start_download(dl_url, save_path, name, "image")
            self.btn_save.setText("✔ Added")
            QTimer.singleShot(3000, lambda: self.btn_save.setText("⬇ Save"))
        elif self.current_pixmap:
            self.current_pixmap.save(save_path)
            QMessageBox.information(self, "Saved", f"Image saved successfully to:\n{save_path}")


# ==================== Pro Video Player Dialog ====================

class ProVideoPlayerDialog(QDialog):
    """Pro Video Player with HTTP Range seeking, Timeline Scrubber, Snap Frame, Speed & Fullscreen."""

    def __init__(self, stream_url: str, title: str, duration_ms: int = 0, parent=None, explorer_module=None):
        super().__init__(parent)
        self.stream_url = stream_url
        self.title = title
        self.duration_ms = duration_ms
        self.explorer_module = explorer_module
        self.is_user_scrubbing = False

        self.setWindowTitle(f"ZeroExplorer Video Player - {title}")
        self.resize(960, 660)
        self.setStyleSheet("background-color: #0B0D13; color: #FFFFFF;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        # Video Viewport Widget
        self.video_widget = QVideoWidget(self)
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 8px;")
        layout.addWidget(self.video_widget, 1)

        # Multimedia Player
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        # Timeline Scrubber Row
        time_row = QHBoxLayout()
        time_row.setSpacing(10)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.lbl_time.setStyleSheet("color: #E5E7EB;")
        time_row.addWidget(self.lbl_time)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #374151;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #FFFFFF;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        time_row.addWidget(self.seek_slider, 1)

        layout.addLayout(time_row)

        # Controls Row: Play/Pause, Rewind, Forward, Speed, Volume, Snap Frame, Fullscreen
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.btn_play = QPushButton("❚❚ Pause")
        self.btn_play.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl_row.addWidget(self.btn_play)

        self.btn_skip_back = QPushButton("-5s")
        self.btn_skip_fwd = QPushButton("+5s")
        for b in [self.btn_skip_back, self.btn_skip_fwd]:
            b.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #1F2937;
                    color: #FFFFFF;
                    border: 1px solid #374151;
                    border-radius: 6px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #374151;
                }
            """)
            ctrl_row.addWidget(b)

        self.btn_skip_back.clicked.connect(lambda: self._skip(-5000))
        self.btn_skip_fwd.clicked.connect(lambda: self._skip(5000))

        # Speed Dropdown
        self.cmb_speed = QComboBox()
        self.cmb_speed.setFont(QFont("Segoe UI", 9))
        self.cmb_speed.addItems(["1.0x", "1.25x", "1.5x", "2.0x", "0.75x"])
        self.cmb_speed.setStyleSheet("""
            QComboBox {
                background-color: #1F2937;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 5px 8px;
            }
        """)
        self.cmb_speed.currentIndexChanged.connect(self._on_speed_changed)
        ctrl_row.addWidget(self.cmb_speed)

        ctrl_row.addStretch()

        # Volume
        lbl_vol = QLabel("Vol:")
        lbl_vol.setFont(QFont("Segoe UI", 9))
        lbl_vol.setStyleSheet("color: #9CA3AF;")
        ctrl_row.addWidget(lbl_vol)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(85)
        self.vol_slider.setFixedWidth(80)
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #374151;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #E5E7EB;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
        """)
        self.vol_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))
        ctrl_row.addWidget(self.vol_slider)

        # Snap Frame Button (Bonus)
        self.btn_snap = QPushButton("📸 Snap Frame")
        self.btn_snap.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_snap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_snap.setStyleSheet("""
            QPushButton {
                background-color: #1F2937;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #374151;
            }
        """)
        self.btn_snap.clicked.connect(self._snap_frame)
        ctrl_row.addWidget(self.btn_snap)

        # Save Full Video Button
        self.btn_save_video = QPushButton("💾 Save Video to PC")
        self.btn_save_video.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_save_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_video.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #FFFFFF;
                border: 1px solid #10B981;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #9CA3AF;
                border-color: #4B5563;
            }
        """)
        self.btn_save_video.clicked.connect(self._save_video_to_pc)
        ctrl_row.addWidget(self.btn_save_video)

        self.btn_fs = QPushButton("Fullscreen (F)")
        self.btn_fs.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_fs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fs.setStyleSheet("""
            QPushButton {
                background-color: #1F2937;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #374151;
            }
        """)
        self.btn_fs.clicked.connect(self._toggle_fullscreen)
        ctrl_row.addWidget(self.btn_fs)

        self.btn_ext = QPushButton("⚡ Play in Windows Player")
        self.btn_ext.setToolTip("Stream and open in Windows default video player (VLC, Movies & TV) with native GPU decoding")
        self.btn_ext.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_ext.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ext.setStyleSheet("""
            QPushButton {
                background-color: #1F2937;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #374151;
            }
        """)
        self.btn_ext.clicked.connect(self._open_in_external)
        ctrl_row.addWidget(self.btn_ext)

        layout.addLayout(ctrl_row)

        # Wire Player events
        self.player.positionChanged.connect(self._on_player_position)
        self.player.durationChanged.connect(self._on_player_duration)
        self.player.playbackStateChanged.connect(self._on_playback_state)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._skip(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._skip(5000))
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self._toggle_fullscreen)

        # Start playback
        self.player.setSource(QUrl(self.stream_url))
        self.player.play()

    def _open_in_external(self):
        self.player.pause()
        self.btn_ext.setText("⏳ Opening in Player...")
        self.btn_ext.setEnabled(False)

        def _worker():
            try:
                temp_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "ZeroLink_Cache")
                os.makedirs(temp_dir, exist_ok=True)
                clean_name = self.title if self.title.lower().endswith((".mp4", ".mkv", ".mov", ".avi", ".webm")) else f"{self.title}.mp4"
                cached_path = os.path.join(temp_dir, clean_name)
                if not os.path.exists(cached_path) or os.path.getsize(cached_path) == 0:
                    req = urllib.request.Request(self.stream_url, headers={"User-Agent": "ZeroLink-PC"})
                    with urllib.request.urlopen(req, timeout=30) as resp, open(cached_path, "wb") as f_out:
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            f_out.write(chunk)
                os.startfile(cached_path)
            except Exception:
                try:
                    QDesktopServices.openUrl(QUrl(self.stream_url))
                except Exception:
                    pass
            finally:
                QTimer.singleShot(0, lambda: self.btn_ext.setText("⚡ Play in Windows Player"))
                QTimer.singleShot(0, lambda: self.btn_ext.setEnabled(True))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def closeEvent(self, event):
        try:
            self.player.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("❚❚ Pause")
        else:
            self.btn_play.setText("▶ Play")

    def _skip(self, ms: int):
        new_pos = max(0, min(self.player.duration(), self.player.position() + ms))
        self.player.setPosition(new_pos)

    def _on_player_position(self, pos: int):
        if not self.is_user_scrubbing and self.player.duration() > 0:
            val = int((pos / self.player.duration()) * 1000)
            self.seek_slider.setValue(val)
        self._update_time_label(pos, self.player.duration())

    def _on_player_duration(self, dur: int):
        self._update_time_label(self.player.position(), dur)

    def _update_time_label(self, pos: int, dur: int):
        pos_s = pos // 1000
        dur_s = max(0, dur // 1000)
        cur_str = f"{pos_s // 60:02d}:{pos_s % 60:02d}"
        tot_str = f"{dur_s // 60:02d}:{dur_s % 60:02d}"
        self.lbl_time.setText(f"{cur_str} / {tot_str}")

    def _on_seek_pressed(self):
        self.is_user_scrubbing = True

    def _on_seek_released(self):
        self.is_user_scrubbing = False
        ratio = self.seek_slider.value() / 1000.0
        target_pos = int(ratio * self.player.duration())
        self.player.setPosition(target_pos)

    def _on_speed_changed(self):
        txt = self.cmb_speed.currentText().replace("x", "")
        rate = float(txt) if txt else 1.0
        self.player.setPlaybackRate(rate)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.btn_fs.setText("Fullscreen (F)")
        else:
            self.showFullScreen()
            self.btn_fs.setText("Exit Fullscreen (F)")

    def _snap_frame(self):
        pix = self.video_widget.grab()
        if not pix.isNull():
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Video Frame", "snapshot.png", "PNG Image (*.png)")
            if save_path:
                pix.save(save_path)
                QMessageBox.information(self, "Snapshot Saved", f"Frame snapshot saved to:\n{save_path}")

    def _save_video_to_pc(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Videos")
        if not os.path.exists(default_dir):
            default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        base_name = self.title.strip()
        if not base_name.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
            base_name += ".mp4"
        default_path = os.path.join(default_dir, base_name)
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Video to PC", default_path, "Video Files (*.mp4 *.mov *.mkv *.webm);;All Files (*.*)")
        if not save_path:
            return

        dl_url = self.stream_url
        if "download=" in dl_url:
            dl_url = dl_url.replace("download=false", "download=true")
        else:
            sep = "&" if "?" in dl_url else "?"
            dl_url += f"{sep}download=true"

        if getattr(self, "explorer_module", None):
            self.explorer_module.start_download(dl_url, save_path, base_name, "video")
            self.btn_save_video.setText("✔ Added to Downloads")
            QTimer.singleShot(3000, lambda: self.btn_save_video.setText("💾 Save Video to PC"))
            return

        self.btn_save_video.setEnabled(False)
        self.btn_save_video.setText("💾 Connecting...")

        self._dl_worker = FileDownloadWorker(dl_url, save_path)

        def _on_prog(dl, total):
            if total > 0:
                pct = int((dl / total) * 100)
                mb_dl = dl / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                self.btn_save_video.setText(f"💾 Saving {pct}% ({mb_dl:.1f}/{mb_tot:.1f} MB)")
            else:
                mb_dl = dl / (1024 * 1024)
                self.btn_save_video.setText(f"💾 Saving {mb_dl:.1f} MB...")

        def _on_done(ok, msg):
            self.btn_save_video.setEnabled(True)
            if ok:
                self.btn_save_video.setText("✔ Video Saved!")
                QTimer.singleShot(4000, lambda: self.btn_save_video.setText("💾 Save Video to PC"))
                reply = QMessageBox.information(
                    self,
                    "Video Saved Successfully",
                    f"Video file has been downloaded and saved to:\n{msg}",
                    QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok
                )
                if reply == QMessageBox.StandardButton.Open:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(msg)))
            else:
                self.btn_save_video.setText("💾 Save Video to PC")
                QMessageBox.warning(self, "Download Error", f"Failed to save video:\n{msg}")

        self._dl_worker.progress.connect(_on_prog)
        self._dl_worker.finished.connect(_on_done)
        self._dl_worker.start()

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)


# ==================== Main ZeroExplorer Module ====================

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
        self.active_media_filter = "all"  # all, photos, videos
        self.active_album_filter: Optional[str] = None
        self.selected_file_path = ""
        self.selected_item_data: Optional[Dict] = None
        self._gallery_item_map: Dict[int, QListWidgetItem] = {}

        # Workers
        self._storage_worker: Optional[StorageWorker] = None
        self._media_worker: Optional[MediaWorker] = None
        self._files_worker: Optional[FilesWorker] = None
        self._thumb_queue_worker: Optional[ThumbQueueWorker] = None

        # Pagination & Gallery State (100 items per page)
        self.gallery_page = 1
        self.gallery_page_size = 100
        self.gallery_total = 0
        self.gallery_total_pages = 1
        self.is_loading_media = False

        # Pre-create Clean Placeholders
        self._image_placeholder = self._create_placeholder_icon(is_video=False)
        self._video_placeholder = self._create_placeholder_icon(is_video=True)

        # Download Manager & 0-100% Progress Queue
        self.download_manager = DownloadManagerDialog(parent=None)
        self.download_manager.active_count_changed.connect(self._on_download_active_count_changed)
        self.btn_downloads: Optional[QPushButton] = None

    def _create_placeholder_icon(self, is_video: bool) -> QIcon:
        pix = QPixmap(120, 120)
        pix.fill(QColor("#F3F4F6"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#E5E7EB"))
        painter.drawRoundedRect(1, 1, 118, 118, 6, 6)
        painter.setPen(QColor("#9CA3AF"))
        font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(font)
        glyph = "▶" if is_video else "▤"
        painter.drawText(0, 0, 120, 120, int(Qt.AlignmentFlag.AlignCenter), glyph)
        painter.end()
        return QIcon(pix)

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
        self.connect_and_sync()
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

        desc_lbl = QLabel("Phone Gallery, 4K Video Player, Storage Explorer & File Manager")
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setStyleSheet("color: #6B7280;")
        title_col.addWidget(desc_lbl)

        header_row.addLayout(title_col, 1)

        # Host IP & Mode
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

        self.btn_downloads = QPushButton("📥 Downloads")
        self.btn_downloads.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_downloads.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_downloads.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self.btn_downloads.clicked.connect(self.show_download_manager)
        header_row.addWidget(self.btn_downloads)

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

        # Tab 1: Media Gallery (Photos & Videos)
        self.tab_gallery = self._build_gallery_tab()
        self.tabs.addTab(self.tab_gallery, "Media Gallery (Photos & Videos)")

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

        # Filters Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.btn_type_all = QPushButton("All Media")
        self.btn_type_photos = QPushButton("Photos")
        self.btn_type_videos = QPushButton("Videos")

        self.btn_alb_cam = QPushButton("Camera")
        self.btn_alb_shot = QPushButton("Screenshots")
        self.btn_alb_down = QPushButton("Downloads")

        media_btns = [self.btn_type_all, self.btn_type_photos, self.btn_type_videos,
                      self.btn_alb_cam, self.btn_alb_shot, self.btn_alb_down]

        for btn in media_btns:
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

        self.btn_type_all.clicked.connect(lambda: self._set_media_filter("all", None))
        self.btn_type_photos.clicked.connect(lambda: self._set_media_filter("photos", None))
        self.btn_type_videos.clicked.connect(lambda: self._set_media_filter("videos", None))
        self.btn_alb_cam.clicked.connect(lambda: self._set_media_filter("all", "Camera"))
        self.btn_alb_shot.clicked.connect(lambda: self._set_media_filter("all", "Screenshots"))
        self.btn_alb_down.clicked.connect(lambda: self._set_media_filter("all", "Download"))

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

        # Gallery Grid View
        self.gallery_list = QListWidget()
        self.gallery_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery_list.setIconSize(QSize(120, 120))
        self.gallery_list.setGridSize(QSize(142, 178))
        self.gallery_list.setSpacing(10)
        self.gallery_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery_list.setUniformItemSizes(False)
        self.gallery_list.setWordWrap(True)
        self.gallery_list.setMovement(QListWidget.Movement.Static)
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
                padding: 6px;
                margin: 2px;
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
        self.gallery_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gallery_list.customContextMenuRequested.connect(self._show_gallery_context_menu)
        layout.addWidget(self.gallery_list, 1)

        # ==================== Page-by-Page Pagination Bar (100 items/page) ====================
        page_bar = QHBoxLayout()
        page_bar.setContentsMargins(4, 6, 4, 4)
        page_bar.setSpacing(8)

        self.lbl_page_info = QLabel("Showing 0 – 0 of 0 items")
        self.lbl_page_info.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.lbl_page_info.setStyleSheet("color: #374151;")
        page_bar.addWidget(self.lbl_page_info)

        page_bar.addStretch()

        page_btn_style = """
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
                border-color: #9CA3AF;
            }
            QPushButton:disabled {
                background-color: #F9FAFB;
                color: #9CA3AF;
                border-color: #E5E7EB;
            }
        """

        self.btn_page_first = QPushButton("⏮ First")
        self.btn_page_first.setStyleSheet(page_btn_style)
        self.btn_page_first.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_first.clicked.connect(self._go_first_page)
        page_bar.addWidget(self.btn_page_first)

        self.btn_page_prev = QPushButton("◀ Prev")
        self.btn_page_prev.setStyleSheet(page_btn_style)
        self.btn_page_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_prev.clicked.connect(self._go_prev_page)
        page_bar.addWidget(self.btn_page_prev)

        self.lbl_page_badge = QLabel("Page 1 / 1")
        self.lbl_page_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.lbl_page_badge.setStyleSheet("""
            background-color: #111827;
            color: #FFFFFF;
            border-radius: 6px;
            padding: 5px 14px;
        """)
        self.lbl_page_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_bar.addWidget(self.lbl_page_badge)

        self.btn_page_next = QPushButton("Next ▶")
        self.btn_page_next.setStyleSheet(page_btn_style)
        self.btn_page_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_next.clicked.connect(self._go_next_page)
        page_bar.addWidget(self.btn_page_next)

        self.btn_page_last = QPushButton("Last ⏭")
        self.btn_page_last.setStyleSheet(page_btn_style)
        self.btn_page_last.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_last.clicked.connect(self._go_last_page)
        page_bar.addWidget(self.btn_page_last)

        layout.addLayout(page_bar)

        return tab

    def _build_files_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Top Bar: Navigation, Path, Filter, Sort
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

        # Real-time Search Box
        self.txt_search_filter = QLineEdit()
        self.txt_search_filter.setPlaceholderText("Filter files...")
        self.txt_search_filter.setFixedWidth(160)
        self.txt_search_filter.setFont(QFont("Segoe UI", 9))
        self.txt_search_filter.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 10px;
                color: #111827;
            }
        """)
        self.txt_search_filter.textChanged.connect(self._apply_sorting_and_filter)
        top_bar.addWidget(self.txt_search_filter)

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
            "Category"
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
        self.cmb_sort.currentIndexChanged.connect(self._apply_sorting_and_filter)
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
            ("Movies & Video", "/storage/emulated/0/Movies"),
            ("Storage Root", "/storage/emulated/0")
        ]
        for name, path in fav_items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_favorites.addItem(item)
        self.list_favorites.itemClicked.connect(lambda item: self.fetch_files(item.data(Qt.ItemDataRole.UserRole)))
        side_layout.addWidget(self.list_favorites, 1)

        splitter.addWidget(sidebar)

        # 2. Spacious, Clean File Table
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(4)
        self.table_files.setHorizontalHeaderLabels(["Name", "Type / Category", "Date Modified", "Size"])
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table_files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table_files.setColumnWidth(1, 110)
        self.table_files.setColumnWidth(2, 140)
        self.table_files.setColumnWidth(3, 100)
        self.table_files.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_files.setShowGrid(False)
        self.table_files.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                selection-background-color: #F3F4F6;
                selection-color: #111827;
            }
            QHeaderView::section {
                background-color: #F9FAFB;
                color: #4B5563;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #E5E7EB;
                padding: 8px 10px;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #F9FAFB;
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

        self.lbl_preview_meta = QLabel("Select a file or media to inspect details.")
        self.lbl_preview_meta.setFont(QFont("Segoe UI", 8))
        self.lbl_preview_meta.setStyleSheet("color: #6B7280; border: none;")
        self.lbl_preview_meta.setWordWrap(True)
        p_layout.addWidget(self.lbl_preview_meta)

        p_layout.addStretch()

        self.btn_open_preview = QPushButton("Open / Stream")
        self.btn_open_preview.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_open_preview.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 7px 14px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        self.btn_open_preview.clicked.connect(self._on_open_current_selection)
        p_layout.addWidget(self.btn_open_preview)

        self.btn_download_file = QPushButton("Download to PC")
        self.btn_download_file.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
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

        # Spacebar shortcut to Quick Look
        QShortcut(QKeySequence(Qt.Key.Key_Space), self.table_files, self._on_open_current_selection)

        return tab

    # ==================== Actions & Data Sync ====================

    def _on_usb_mode_clicked(self):
        self.et_host_ip.setText("127.0.0.1")
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
        self.fetch_media(self.active_media_filter, self.active_album_filter)
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

    def _set_media_filter(self, media_type: str, album: Optional[str]):
        self.active_media_filter = media_type
        self.active_album_filter = album
        self.gallery_page = 1
        self._load_gallery_page(1)

    def _go_first_page(self):
        if self.gallery_page > 1:
            self._load_gallery_page(1)

    def _go_prev_page(self):
        if self.gallery_page > 1:
            self._load_gallery_page(self.gallery_page - 1)

    def _go_next_page(self):
        if self.gallery_page < self.gallery_total_pages:
            self._load_gallery_page(self.gallery_page + 1)

    def _go_last_page(self):
        if self.gallery_page < self.gallery_total_pages:
            self._load_gallery_page(self.gallery_total_pages)

    def _load_gallery_page(self, page_num: int):
        self.gallery_page = max(1, page_num)
        offset = (self.gallery_page - 1) * self.gallery_page_size
        self.fetch_media(self.active_media_filter, self.active_album_filter, offset=offset)

    def fetch_media(self, media_type: str, album: Optional[str], offset: int = 0):
        if self._media_worker and self._media_worker.isRunning():
            self._media_worker.terminate()

        # Clear items and jump scroll to top for fresh page
        self.gallery_list.clear()
        self._gallery_item_map.clear()
        self.gallery_list.verticalScrollBar().setValue(0)

        if self._thumb_queue_worker:
            self._thumb_queue_worker.clear()

        self.lbl_page_info.setText("Loading media from device...")

        if not self._thumb_queue_worker or not self._thumb_queue_worker.isRunning():
            self._thumb_queue_worker = ThumbQueueWorker(self.phone_host, self.port)
            self._thumb_queue_worker.thumb_ready.connect(self._on_thumb_ready)
            self._thumb_queue_worker.start()

        self._media_worker = MediaWorker(
            self.phone_host, self.port, media_type, album,
            offset=offset, limit=self.gallery_page_size
        )
        self._media_worker.result_ready.connect(self._on_media_received)
        self._media_worker.error_occurred.connect(self._on_error)
        self._media_worker.start()

    def _on_media_received(self, data):
        if isinstance(data, dict):
            items = data.get("items", [])
            self.gallery_total = data.get("total", len(items))
            offset = data.get("offset", 0)
        else:
            items = data if isinstance(data, list) else []
            self.gallery_total = len(items)
            offset = 0

        self.gallery_items = items
        self.gallery_list.clear()
        self._gallery_item_map.clear()

        for itm in items:
            p_id = itm.get("id")
            name = itm.get("name", "Media")
            is_video = itm.get("type") == "video"
            dur_ms = itm.get("duration", 0)
            size_mb = itm.get("size", 0) / (1024 * 1024)

            # Format clean truncated name
            clean_name = name
            if len(clean_name) > 16:
                base, ext = os.path.splitext(clean_name)
                if len(base) > 10:
                    clean_name = f"{base[:8]}…{base[-3:]}{ext}"
                else:
                    clean_name = clean_name[:14] + "…"

            if is_video and dur_ms > 0:
                s = dur_ms // 1000
                badge_str = f"▶ {s // 60:02d}:{s % 60:02d}"
            else:
                badge_str = f"{size_mb:.1f} MB"

            text = f"{clean_name}\n{badge_str}"

            # Always initialize with placeholder so item sizeHint is honored and doesn't collapse
            placeholder = self._video_placeholder if is_video else self._image_placeholder
            list_item = QListWidgetItem(placeholder, text)
            list_item.setSizeHint(QSize(130, 168))
            list_item.setData(Qt.ItemDataRole.UserRole, itm)
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.gallery_list.addItem(list_item)
            if p_id is not None:
                self._gallery_item_map[p_id] = list_item

        # Compute page boundaries
        self.gallery_total_pages = max(1, (self.gallery_total + self.gallery_page_size - 1) // self.gallery_page_size) if self.gallery_total > 0 else 1
        self.gallery_page = (offset // self.gallery_page_size) + 1

        if len(items) > 0:
            start_num = offset + 1
            end_num = offset + len(items)
            self.lbl_page_info.setText(f"Showing {start_num:,} – {end_num:,} of {self.gallery_total:,} items")
        else:
            self.lbl_page_info.setText(f"0 of {self.gallery_total:,} items")

        self.lbl_page_badge.setText(f"Page {self.gallery_page} / {self.gallery_total_pages}")

        # Update button enable states
        self.btn_page_first.setEnabled(self.gallery_page > 1)
        self.btn_page_prev.setEnabled(self.gallery_page > 1)
        self.btn_page_next.setEnabled(self.gallery_page < self.gallery_total_pages)
        self.btn_page_last.setEnabled(self.gallery_page < self.gallery_total_pages)

        # Enqueue thumbnails for this page of 100 items
        if items and self._thumb_queue_worker:
            self._thumb_queue_worker.add_items(items)

    def _on_thumb_ready(self, photo_id: int, pixmap: QPixmap):
        itm = self._gallery_item_map.get(photo_id)
        if itm and not pixmap.isNull():
            itm.setIcon(QIcon(pixmap))

    def fetch_files(self, path: str):
        self._files_request_seq = getattr(self, "_files_request_seq", 0) + 1
        req_id = self._files_request_seq

        # Show immediate feedback so the UI never feels frozen
        self.txt_breadcrumb.setText(path)
        self.table_files.setRowCount(1)
        loading_item = QTableWidgetItem(f"  ⏳ Loading folder contents ({os.path.basename(path) or path})...")
        loading_item.setForeground(QColor("#6B7280"))
        self.table_files.setItem(0, 0, loading_item)
        self.table_files.setItem(0, 1, QTableWidgetItem("--"))
        self.table_files.setItem(0, 2, QTableWidgetItem(""))
        self.table_files.setItem(0, 3, QTableWidgetItem(""))
        QApplication.processEvents()

        self._files_worker = FilesWorker(self.phone_host, self.port, path, request_id=req_id)
        self._files_worker.result_ready.connect(self._on_files_received)
        self._files_worker.error_occurred.connect(self._on_files_error)
        self._files_worker.start()

    def _on_files_received(self, req_id: int, data: dict):
        if req_id != getattr(self, "_files_request_seq", 0):
            return

        self.current_folder_path = data.get("currentPath", self.current_folder_path)
        self.parent_folder_path = data.get("parentPath", "")
        self.txt_breadcrumb.setText(self.current_folder_path)

        self.raw_files_list = data.get("files", [])
        self._apply_sorting_and_filter()

    def _on_files_error(self, req_id: int, err: str):
        if req_id != getattr(self, "_files_request_seq", 0):
            return
        self.table_files.setRowCount(1)
        err_item = QTableWidgetItem(f"  ⚠ Failed to load folder: {err}")
        err_item.setForeground(QColor("#EF4444"))
        self.table_files.setItem(0, 0, err_item)

    def _apply_sorting_and_filter(self):
        query = self.txt_search_filter.text().strip().lower()
        sort_mode = self.cmb_sort.currentText()

        files = [f for f in self.raw_files_list if query in f.get("name", "").lower()]

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
        elif "Category" in sort_mode:
            files.sort(key=lambda x: (not x.get("isDir", False), x.get("category", "")))

        # Batch insertion with updates disabled for instant rendering
        self.table_files.setUpdatesEnabled(False)
        self.table_files.blockSignals(True)
        try:
            self.table_files.setRowCount(len(files))
            for row, f in enumerate(files):
                name = f.get("name", "")
                is_dir = f.get("isDir", False)
                cat = f.get("category", "file").upper()
                size_b = f.get("size", 0)
                date_ms = f.get("date", 0)

                display_name = f"  {name}"
                date_str = datetime.fromtimestamp(date_ms / 1000).strftime("%Y-%m-%d %H:%M") if date_ms > 0 else ""

                if is_dir:
                    type_str = "FOLDER"
                    size_str = "--"
                else:
                    type_str = cat
                    if size_b >= 1024 ** 3:
                        size_str = f"{size_b / (1024 ** 3):.2f} GB"
                    elif size_b >= 1024 ** 2:
                        size_str = f"{size_b / (1024 ** 2):.1f} MB"
                    else:
                        size_str = f"{size_b / 1024:.0f} KB"

                item_name = QTableWidgetItem(display_name)
                item_name.setData(Qt.ItemDataRole.UserRole, f)
                item_name.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold if is_dir else QFont.Weight.Normal))

                item_type = QTableWidgetItem(type_str)
                item_type.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                item_type.setForeground(QColor("#6B7280" if is_dir else "#111827"))

                self.table_files.setItem(row, 0, item_name)
                self.table_files.setItem(row, 1, item_type)
                self.table_files.setItem(row, 2, QTableWidgetItem(date_str))
                self.table_files.setItem(row, 3, QTableWidgetItem(size_str))
        finally:
            self.table_files.setUpdatesEnabled(True)
            self.table_files.blockSignals(False)

    def _on_navigate_up(self):
        if self.parent_folder_path:
            self.fetch_files(self.parent_folder_path)

    def _on_table_item_clicked(self, item: QTableWidgetItem):
        f = self.table_files.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if f:
            self.selected_item_data = f
            self.selected_file_path = f.get("path", "")
            name = f.get("name", "")
            is_dir = f.get("isDir", False)
            cat = f.get("category", "file").upper()
            size_b = f.get("size", 0)
            self.lbl_preview_name.setText(name)
            if is_dir:
                self.lbl_preview_meta.setText(f"Folder\nPath: {self.selected_file_path}")
                self.btn_open_preview.setText("Open Folder")
            else:
                self.lbl_preview_meta.setText(f"Category: {cat}\nSize: {size_b / (1024*1024):.2f} MB\nPath: {self.selected_file_path}")
                if cat in ["VIDEO", "IMAGE"]:
                    self.btn_open_preview.setText("Play / Stream" if cat == "VIDEO" else "View Image")
                elif cat in ["DOCUMENT", "DOC", "PDF"] or name.lower().endswith((".pdf", ".docx", ".doc", ".xlsx", ".txt", ".json")):
                    self.btn_open_preview.setText("Open Document / PDF")
                else:
                    self.btn_open_preview.setText("Inspect File")

    def _on_table_item_double_clicked(self, item: QTableWidgetItem):
        f = self.table_files.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if f:
            if f.get("isDir", False):
                self.fetch_files(f.get("path", ""))
            else:
                self._open_file_item(f)

    def _on_gallery_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.selected_item_data = data
            self.selected_file_path = ""  # Clear file tree selection to prioritize gallery item
            name = data.get("name", "")
            is_video = data.get("type") == "video"
            album = data.get("album", "")
            size_mb = data.get("size", 0) / (1024 * 1024)
            self.lbl_preview_name.setText(name)
            if is_video:
                dur_s = data.get("duration", 0) // 1000
                self.lbl_preview_meta.setText(f"Video ({dur_s//60:02d}:{dur_s%60:02d})\nAlbum: {album}\nSize: {size_mb:.2f} MB")
                self.btn_open_preview.setText("Play Video ▶")
                self.btn_download_file.setText("💾 Save Video to PC")
            else:
                self.lbl_preview_meta.setText(f"Photo\nAlbum: {album}\nSize: {size_mb:.2f} MB")
                self.btn_open_preview.setText("View Image")
                self.btn_download_file.setText("💾 Save Photo to PC")

    def _show_gallery_context_menu(self, pos):
        item = self.gallery_list.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self.selected_item_data = data
        self._on_gallery_item_clicked(item)

        menu = QMenu(self._widget)
        is_video = data.get("type") == "video"
        act_open = menu.addAction("▶ Play Video" if is_video else "👁 View Image")
        act_save = menu.addAction("💾 Save to PC...")
        act_ext = None
        if is_video:
            act_ext = menu.addAction("⚡ Play in Windows Player (VLC / Movies)")

        chosen = menu.exec(self.gallery_list.mapToGlobal(pos))
        if chosen == act_open:
            self._open_media_item(data)
        elif chosen == act_save:
            self._on_download_selected_file()
        elif is_video and chosen == act_ext:
            p_id = data.get("id")
            url = f"http://{self.phone_host}:{self.port}/api/media/raw?id={p_id}&type=video&download=false"
            QDesktopServices.openUrl(QUrl(url))

    def _on_gallery_item_double_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self._open_media_item(data)

    def _on_open_current_selection(self):
        if not self.selected_item_data:
            return
        if self.selected_item_data.get("isDir", False):
            self.fetch_files(self.selected_item_data.get("path", ""))
        elif "duration" in self.selected_item_data:
            self._open_media_item(self.selected_item_data)
        else:
            self._open_file_item(self.selected_item_data)

    def _open_media_item(self, item_data: Dict):
        if getattr(self, "_is_opening_dialog", False):
            return
        self._is_opening_dialog = True

        try:
            is_video = item_data.get("type") == "video"
            p_id = item_data.get("id")
            name = item_data.get("name", "Media")

            if is_video:
                if self._thumb_queue_worker:
                    self._thumb_queue_worker.set_paused(True)
                try:
                    stream_url = f"http://{self.phone_host}:{self.port}/api/media/raw?id={p_id}&type=video&download=false"
                    dur_ms = item_data.get("duration", 0)
                    dlg = ProVideoPlayerDialog(stream_url, name, dur_ms, parent=self._widget, explorer_module=self)
                    dlg.exec()
                finally:
                    if self._thumb_queue_worker:
                        self._thumb_queue_worker.set_paused(False)
            else:
                # Find index in current gallery photo list
                photos_only = [m for m in self.gallery_items if m.get("type") == "image"]
                idx = 0
                for i, p in enumerate(photos_only):
                    if p.get("id") == p_id:
                        idx = i
                        break
                dlg = ProImageViewerDialog(self.phone_host, self.port, photos_only, idx, parent=self._widget, explorer_module=self)
                dlg.exec()
        finally:
            self._is_opening_dialog = False

    def _open_file_item(self, file_data: Dict):
        if getattr(self, "_is_opening_dialog", False):
            return
        self._is_opening_dialog = True

        try:
            cat = file_data.get("category", "")
            path = file_data.get("path", "")
            name = file_data.get("name", "")

            if cat == "video":
                if self._thumb_queue_worker:
                    self._thumb_queue_worker.set_paused(True)
                try:
                    encoded = urllib.parse.quote(path)
                    stream_url = f"http://{self.phone_host}:{self.port}/api/files/download?path={encoded}&download=false"
                    dlg = ProVideoPlayerDialog(stream_url, name, parent=self._widget, explorer_module=self)
                    dlg.exec()
                finally:
                    if self._thumb_queue_worker:
                        self._thumb_queue_worker.set_paused(False)
            elif cat == "image":
                encoded = urllib.parse.quote(path)
                img_list = [{"id": 0, "name": name, "type": "image"}]
                dlg = ProImageViewerDialog(self.phone_host, self.port, img_list, 0, parent=self._widget, explorer_module=self)
                dlg.exec()
            elif cat in ["document", "doc"] or name.lower().endswith((".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".txt", ".json", ".log", ".csv")):
                encoded = urllib.parse.quote(path)
                temp_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "ZeroLink_Cache")
                os.makedirs(temp_dir, exist_ok=True)
                cached_path = os.path.join(temp_dir, name)
                url = f"http://{self.phone_host}:{self.port}/api/files/download?path={encoded}&download=false"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
                    with urllib.request.urlopen(req, timeout=15) as resp, open(cached_path, "wb") as f_out:
                        f_out.write(resp.read())
                    QDesktopServices.openUrl(QUrl.fromLocalFile(cached_path))
                except Exception as e:
                    QMessageBox.warning(self._widget, "Error", f"Failed to open document: {e}")
        finally:
            self._is_opening_dialog = False

    def _on_copy_selected_image(self):
        if not self.selected_item_data or self.selected_item_data.get("type") != "image":
            QMessageBox.information(self._widget, "Copy Image", "Please select a photo in the gallery first.")
            return

        p_id = self.selected_item_data.get("id")
        url = f"http://{self.phone_host}:{self.port}/api/media/raw?id={p_id}&type=image&download=false"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZeroLink-PC"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()
                img = QImage.fromData(raw_bytes)
                if not img.isNull():
                    pix = QPixmap.fromImage(img)
                    QApplication.clipboard().setPixmap(pix)
                    QMessageBox.information(self._widget, "Copied!", "Photo copied to Windows Clipboard!\nYou can now press Ctrl + V in any application.")
        except Exception as e:
            QMessageBox.warning(self._widget, "Copy Error", f"Failed to copy image: {e}")

    def show_download_manager(self):
        self.download_manager.show()
        self.download_manager.raise_()
        self.download_manager.activateWindow()

    def _on_download_active_count_changed(self, active_count: int):
        if not self.btn_downloads:
            return
        if active_count > 0:
            self.btn_downloads.setText(f"📥 Downloads ({active_count})")
            self.btn_downloads.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #FFFFFF;
                    border: 1px solid #10B981;
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
            """)
        else:
            self.btn_downloads.setText("📥 Downloads")
            self.btn_downloads.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #111827;
                    border: 1px solid #D1D5DB;
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #F3F4F6;
                }
            """)

    def start_download(self, url: str, save_path: str, display_name: str, file_type: str = "file"):
        """Enqueues a download into the Download Manager with 0-100% item progress tracking."""
        return self.download_manager.add_download(url, save_path, display_name, file_type)

    def _on_download_selected_file(self):
        # Case 1: File Explorer selection
        if getattr(self, "selected_file_path", None):
            file_name = os.path.basename(self.selected_file_path)
            default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            default_path = os.path.join(default_dir, file_name)
            save_path, _ = QFileDialog.getSaveFileName(self._widget, "Save File to PC", default_path, "All Files (*.*)")
            if not save_path:
                return
            encoded = urllib.parse.quote(self.selected_file_path)
            url = f"http://{self.phone_host}:{self.port}/api/files/download?path={encoded}"
            self._start_download_with_feedback(url, save_path, file_name, file_type="file")
            return

        # Case 2: Media Gallery selection (Photo or Video)
        if getattr(self, "selected_item_data", None):
            p_id = self.selected_item_data.get("id")
            name = self.selected_item_data.get("name", "Media")
            is_video = self.selected_item_data.get("type") == "video"
            type_param = "video" if is_video else "image"
            default_dir = os.path.join(os.path.expanduser("~"), "Videos" if is_video else "Pictures")
            if not os.path.exists(default_dir):
                default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            default_path = os.path.join(default_dir, name)
            filter_str = "Video Files (*.mp4 *.mov *.mkv *.webm);;All Files (*.*)" if is_video else "Image Files (*.jpg *.png *.webp);;All Files (*.*)"
            save_path, _ = QFileDialog.getSaveFileName(self._widget, f"Save {'Video' if is_video else 'Image'} to PC", default_path, filter_str)
            if not save_path:
                return
            url = f"http://{self.phone_host}:{self.port}/api/media/raw?id={p_id}&type={type_param}&download=true"
            self._start_download_with_feedback(url, save_path, name, file_type="video" if is_video else "image")
            return

        QMessageBox.information(self._widget, "Download", "Please select a photo, video, or file to download.")

    def _start_download_with_feedback(self, url: str, save_path: str, display_name: str, file_type: str = "file"):
        self.start_download(url, save_path, display_name, file_type)
        self.btn_download_file.setText("✔ Added to Downloads")
        QTimer.singleShot(2500, lambda: self.btn_download_file.setText("💾 Download to PC"))

    def _on_error(self, err: str):
        self.status_badge.setText("○ CONNECTION FAILED")
