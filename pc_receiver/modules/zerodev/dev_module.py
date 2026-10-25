"""ZeroLink Hub - ZeroDev Developer Console & Module Workshop
Allows developers to scaffold new modules for both PC and Android, probe ports,
and test cross-platform communication in real-time.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.parse
from typing import Optional, Dict, List

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QLineEdit, QComboBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QApplication, QSplitter
)

from core.base_module import BaseModule
from core.adb_helper import AdbManager
from modules.zerodev.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


class PortProbeWorker(QThread):
    result_ready = pyqtSignal(str, int, bool, float, str)

    def __init__(self, host: str, port: int, timeout: float = 2.0):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self):
        t0 = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.host, self.port))
            latency_ms = (time.time() - t0) * 1000.0
            info = "Open (TCP Handshake OK)"
            # Quick HTTP probe
            try:
                s.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
                resp = s.recv(128).decode("latin-1", errors="ignore")
                if resp.startswith("HTTP/"):
                    status_line = resp.split("\r\n")[0]
                    info = f"HTTP Service ({status_line})"
            except Exception:
                pass
            s.close()
            self.result_ready.emit(self.host, self.port, True, latency_ms, info)
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            self.result_ready.emit(self.host, self.port, False, latency_ms, str(e))
        finally:
            try:
                s.close()
            except Exception:
                pass


class ZeroDevModule(BaseModule):
    """Developer Console and Module Workshop for ZeroLink Ecosystem."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self.adb_manager = AdbManager()
        self._widget: Optional[QWidget] = None
        self._probe_worker: Optional[PortProbeWorker] = None

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
        self.status_changed.emit(self.module_id, f"Console Active ({self.port})")
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

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel(MODULE_ICON)
        icon_lbl.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        icon_lbl.setStyleSheet("color: #111827; background-color: #E5E7EB; padding: 4px 10px; border-radius: 6px;")
        header.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        t_lbl = QLabel(MODULE_NAME)
        t_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #111827;")
        title_col.addWidget(t_lbl)
        sub_lbl = QLabel("ZeroLink Ecosystem Module Workshop & Network Diagnostics Console")
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet("color: #6B7280;")
        title_col.addWidget(sub_lbl)
        header.addLayout(title_col)

        header.addStretch()

        self.status_pill = QLabel("● WORKSHOP READY")
        self.status_pill.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_pill.setStyleSheet("""
            background-color: #FFFFFF;
            color: #111827;
            border: 1px solid #D1D5DB;
            padding: 5px 12px;
            border-radius: 6px;
        """)
        header.addWidget(self.status_pill)
        layout.addLayout(header)

        # Tabs: 1) Module Generator, 2) Port & Socket Inspector, 3) Android Code Exporter
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                background-color: #FFFFFF;
            }
            QTabBar::tab {
                background-color: #F9FAFB;
                color: #4B5563;
                padding: 8px 18px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                border: 1px solid #E5E7EB;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #111827;
                font-weight: 700;
            }
        """)

        self.tabs.addTab(self._build_scaffolder_tab(), "⚡ Module Scaffolder")
        self.tabs.addTab(self._build_inspector_tab(), "◈ Port & Network Inspector")
        self.tabs.addTab(self._build_mobile_templates_tab(), "📱 Mobile Code Exporter")
        layout.addWidget(self.tabs, 1)

        return root

    # ==================== Tab 1: Module Scaffolder ====================

    def _build_scaffolder_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        desc = QLabel("Create a new ZeroLink ecosystem module skeleton with production-grade BaseModule structure.")
        desc.setFont(QFont("Segoe UI", 9))
        desc.setStyleSheet("color: #4B5563;")
        layout.addWidget(desc)

        form_grid = QVBoxLayout()
        form_grid.setSpacing(10)

        # Row 1: Name & ID
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Module Display Name:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_mod_name = QLineEdit("ZeroTerminal")
        self.txt_mod_name.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 10px; color: #111827;")
        col1.addWidget(self.txt_mod_name)
        r1.addLayout(col1, 1)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Module ID (Slug):", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_mod_id = QLineEdit("zeroterm")
        self.txt_mod_id.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 10px; color: #111827;")
        col2.addWidget(self.txt_mod_id)
        r1.addLayout(col2, 1)

        form_grid.addLayout(r1)

        # Row 2: Port, Icon & Pattern
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        col3 = QVBoxLayout()
        col3.addWidget(QLabel("Default Port:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_mod_port = QLineEdit("8897")
        self.txt_mod_port.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 10px; color: #111827;")
        col3.addWidget(self.txt_mod_port)
        r2.addLayout(col3)

        col4 = QVBoxLayout()
        col4.addWidget(QLabel("Icon Glyph:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_mod_glyph = QLineEdit(">_")
        self.txt_mod_glyph.setFixedWidth(80)
        self.txt_mod_glyph.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 10px; color: #111827; text-align: center;")
        col4.addWidget(self.txt_mod_glyph)
        r2.addLayout(col4)

        col5 = QVBoxLayout()
        col5.addWidget(QLabel("Architecture Pattern:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems([
            "PC Server (TCP/HTTP) ➔ Mobile Client",
            "Mobile Server (HTTP/TCP) ➔ PC Client",
            "Bidirectional WebSocket Peer Sync"
        ])
        self.cmb_pattern.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 5px 8px; color: #111827;")
        col5.addWidget(self.cmb_pattern)
        r2.addLayout(col5, 1)

        form_grid.addLayout(r2)

        # Row 3: Description
        r3 = QVBoxLayout()
        r3.addWidget(QLabel("Description:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_mod_desc = QLineEdit("Low-latency remote shell command runner and terminal bridge.")
        self.txt_mod_desc.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 10px; color: #111827;")
        r3.addWidget(self.txt_mod_desc)
        form_grid.addLayout(r3)

        layout.addLayout(form_grid)

        # Action Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_gen_pc = QPushButton("⚡ Generate PC Module Skeleton")
        self.btn_gen_pc.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_gen_pc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen_pc.setStyleSheet("""
            QPushButton {
                background-color: #111827;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton:hover {
                background-color: #1F2937;
            }
        """)
        self.btn_gen_pc.clicked.connect(self._generate_pc_module)
        btn_bar.addWidget(self.btn_gen_pc)

        self.btn_gen_android = QPushButton("📱 Preview Android Kotlin Code")
        self.btn_gen_android.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_gen_android.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen_android.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 7px 16px;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self.btn_gen_android.clicked.connect(self._preview_android_code)
        btn_bar.addWidget(self.btn_gen_android)

        self.btn_open_folder = QPushButton("📁 Open Modules Directory")
        self.btn_open_folder.setFont(QFont("Segoe UI", 9))
        self.btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #F3F4F6;
                color: #374151;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 7px 14px;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """)
        self.btn_open_folder.clicked.connect(self._open_modules_dir)
        btn_bar.addWidget(self.btn_open_folder)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # Output / Generated Code Box
        layout.addWidget(QLabel("Scaffolded Output Preview:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_scaffold_output = QTextEdit()
        self.txt_scaffold_output.setReadOnly(True)
        self.txt_scaffold_output.setFont(QFont("Consolas", 9))
        self.txt_scaffold_output.setStyleSheet("""
            QTextEdit {
                background-color: #111827;
                color: #F9FAFB;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        self.txt_scaffold_output.setPlaceholderText("Generated code or creation report will appear here...")
        layout.addWidget(self.txt_scaffold_output, 1)

        return tab

    def _generate_pc_module(self):
        m_id = self.txt_mod_id.text().strip().lower()
        m_name = self.txt_mod_name.text().strip()
        m_port = self.txt_mod_port.text().strip()
        m_glyph = self.txt_mod_glyph.text().strip()
        m_desc = self.txt_mod_desc.text().strip()

        if not m_id or not m_name or not m_port:
            QMessageBox.warning(self._widget, "Validation Error", "Please provide Module Name, ID, and Port.")
            return

        modules_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.join(modules_root, m_id)
        os.makedirs(target_dir, exist_ok=True)

        # 1. Write manifest.py
        manifest_content = f'''"""ZeroLink Hub - {m_name} Module Manifest"""

MODULE_ID = "{m_id}"
MODULE_NAME = "{m_name}"
MODULE_ICON = "{m_glyph}"
MODULE_DESCRIPTION = "{m_desc}"
MODULE_PORT = {m_port}
'''
        with open(os.path.join(target_dir, "manifest.py"), "w", encoding="utf-8") as f:
            f.write(manifest_content)

        # 2. Write module code
        class_name = "".join(w.capitalize() for w in m_name.split()) + "Module"
        module_content = f'''"""ZeroLink Hub - {m_name} Module
{m_desc}
"""

import socket
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit
)

from core.base_module import BaseModule
from modules.{m_id}.manifest import (
    MODULE_ID, MODULE_NAME, MODULE_ICON, MODULE_DESCRIPTION, MODULE_PORT
)


class {class_name}(BaseModule):
    """{m_name} Ecosystem Module."""

    def __init__(self, port: int = MODULE_PORT, local_ip: str = "127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.local_ip = local_ip
        self._widget: Optional[QWidget] = None
        self._server_socket: Optional[socket.socket] = None
        self._is_running = False

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
        self._is_active = True
        self._is_running = True
        
        # Start background listener thread
        threading.Thread(target=self._server_loop, daemon=True).start()

        self.state_changed.emit(self.module_id, True)
        self.status_changed.emit(self.module_id, f"Listening on port {self.port}")
        return True

    def stop_service(self) -> bool:
        self._is_active = False
        self._is_running = False
        try:
            if self._server_socket:
                self._server_socket.close()
        except Exception:
            pass
        self._server_socket = None
        self.state_changed.emit(self.module_id, False)
        self.status_changed.emit(self.module_id, "Stopped")
        return True

    def _server_loop(self):
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind(("0.0.0.0", self.port))
            self._server_socket.listen(5)
            while self._is_running:
                client, addr = self._server_socket.accept()
                threading.Thread(target=self._handle_client, args=(client, addr), daemon=True).start()
        except Exception:
            pass

    def _handle_client(self, client: socket.socket, addr):
        try:
            resp = json.dumps({"status": "ok", "module": self.module_id})
            http_resp = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(resp)}\r\nConnection: close\r\n\r\n{resp}".encode("utf-8")
            client.sendall(http_resp)
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._create_ui()
        return self._widget

    def _create_ui(self) -> QWidget:
        root = QWidget()
        root.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon_lbl = QLabel(MODULE_ICON)
        icon_lbl.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        header.addWidget(icon_lbl)

        title = QLabel(MODULE_NAME)
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        self.btn_toggle = QPushButton("Start Service")
        self.btn_toggle.setStyleSheet("background-color: #111827; color: #FFFFFF; padding: 6px 14px; border-radius: 6px;")
        self.btn_toggle.clicked.connect(lambda: self.start_service() if not self.is_active else self.stop_service())
        header.addWidget(self.btn_toggle)
        layout.addLayout(header)

        # Log or Content Viewport
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 10))
        self.txt_log.setStyleSheet("background-color: #111827; color: #F9FAFB; border-radius: 8px; padding: 10px;")
        self.txt_log.setText("Ready. Connect from mobile client to port " + str(self.port))
        layout.addWidget(self.txt_log, 1)

        return root
'''
        with open(os.path.join(target_dir, f"{m_id}_module.py"), "w", encoding="utf-8") as f:
            f.write(module_content)

        report = f"""✔ PC Module Skeleton created successfully!
Location: {target_dir}
Files Created:
  - manifest.py (ID={m_id}, Port={m_port})
  - {m_id}_module.py ({class_name})

Next Steps to hook into ZeroLink Hub:
1. Open pc_receiver/ui/main_window.py
2. Import module:
   from modules.{m_id}.{m_id}_module import {class_name}
3. In __init__, register:
   self.mod_{m_id} = {class_name}(port={m_port}, local_ip=self.local_ip, parent=self)
   self.module_manager.register_module(self.mod_{m_id})
4. Add to stacked widget and sidebar navigation!
"""
        self.txt_scaffold_output.setText(report)
        QMessageBox.information(self._widget, "Module Created", f"Module '{m_name}' created in:\n{target_dir}")

    def _open_modules_dir(self):
        modules_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.startfile(modules_root)

    def _preview_android_code(self):
        m_id = self.txt_mod_id.text().strip().lower()
        m_name = self.txt_mod_name.text().strip()
        m_port = self.txt_mod_port.text().strip()
        class_name = "".join(w.capitalize() for w in m_name.split()) + "Activity"

        kotlin_code = f"""// ==================== Android Activity Template: {class_name}.kt ====================
package com.zerocast.ui

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.zerocast.databinding.Activity{class_name}Binding
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.Socket
import kotlin.concurrent.thread

class {class_name} : AppCompatActivity() {{

    private lateinit var binding: Activity{class_name}Binding
    private val defaultPort = {m_port}

    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        binding = Activity{class_name}Binding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnConnect.setOnClickListener {{
            val host = binding.etHost.text.toString().trim().ifEmpty {{ "127.0.0.1" }}
            connectToPc(host, defaultPort)
        }}
    }}

    private fun connectToPc(host: String, port: Int) {{
        thread {{
            try {{
                val socket = Socket(host, port)
                val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
                val line = reader.readLine()
                socket.close()
                runOnUiThread {{
                    binding.tvLog.append("\\nConnected to PC: $line")
                    Toast.makeText(this, "Success: $line", Toast.LENGTH_SHORT).show()
                }}
            }} catch (e: Exception) {{
                runOnUiThread {{
                    binding.tvLog.append("\\nConnection error: ${{e.message}}")
                }}
            }}
        }}
    }}
}}

// ==================== AndroidManifest.xml Entry ====================
// <activity
//     android:name=".ui.{class_name}"
//     android:exported="true"
//     android:theme="@style/Theme.ZeroCast" />
"""
        self.txt_scaffold_output.setText(kotlin_code)
        self.tabs.setCurrentIndex(2)

    # ==================== Tab 2: Port & Network Inspector ====================

    def _build_inspector_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Top Bar: Host probe input
        probe_bar = QHBoxLayout()
        probe_bar.setSpacing(8)

        probe_bar.addWidget(QLabel("Target Host:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_probe_host = QLineEdit("127.0.0.1")
        self.txt_probe_host.setFixedWidth(130)
        self.txt_probe_host.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 5px 8px;")
        probe_bar.addWidget(self.txt_probe_host)

        probe_bar.addWidget(QLabel("Port:", styleSheet="font-size: 11px; font-weight: bold; color: #374151;"))
        self.txt_probe_port = QLineEdit("8888")
        self.txt_probe_port.setFixedWidth(80)
        self.txt_probe_port.setStyleSheet("background-color: #F9FAFB; border: 1px solid #D1D5DB; border-radius: 6px; padding: 5px 8px;")
        probe_bar.addWidget(self.txt_probe_port)

        self.btn_probe = QPushButton("Probe Socket")
        self.btn_probe.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_probe.setStyleSheet("background-color: #111827; color: #FFFFFF; border-radius: 6px; padding: 6px 14px;")
        self.btn_probe.clicked.connect(self._probe_single_port)
        probe_bar.addWidget(self.btn_probe)

        self.btn_probe_all = QPushButton("Probe All Ecosystem Ports")
        self.btn_probe_all.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.btn_probe_all.setStyleSheet("background-color: #F3F4F6; color: #111827; border: 1px solid #D1D5DB; border-radius: 6px; padding: 6px 14px;")
        self.btn_probe_all.clicked.connect(self._probe_all_ports)
        probe_bar.addWidget(self.btn_probe_all)

        probe_bar.addStretch()
        layout.addLayout(probe_bar)

        # Port Status Table
        self.table_ports = QTableWidget(0, 5)
        self.table_ports.setHorizontalHeaderLabels(["Module", "Port", "Status", "Latency", "Service Info"])
        self.table_ports.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_ports.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_ports.setShowGrid(False)
        self.table_ports.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #F9FAFB;
                padding: 6px 10px;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #E5E7EB;
            }
        """)
        layout.addWidget(self.table_ports, 1)

        # Quick preset rows
        self._populate_port_presets()

        return tab

    def _populate_port_presets(self):
        presets = [
            ("ZeroCast (Screen Mirror)", 8888),
            ("ZeroClip (Clipboard)", 8889),
            ("ZeroDrop (File Drop)", 8890),
            ("ZeroMix (Audio Deck)", 8891),
            ("ZeroDisplay (2nd Screen)", 8892),
            ("ZeroCam (4K Webcam)", 8893),
            ("ZeroPad (Macro Remote)", 8894),
            ("ZeroExplorer (File & Gallery)", 8896),
            ("ZeroDev (Dev Workshop)", 8897),
        ]
        self.table_ports.setRowCount(len(presets))
        for row, (mod_name, p) in enumerate(presets):
            self.table_ports.setItem(row, 0, QTableWidgetItem(f"  {mod_name}"))
            self.table_ports.setItem(row, 1, QTableWidgetItem(str(p)))
            self.table_ports.setItem(row, 2, QTableWidgetItem("○ UNPROBED"))
            self.table_ports.setItem(row, 3, QTableWidgetItem("--"))
            self.table_ports.setItem(row, 4, QTableWidgetItem("Click Probe to check"))

    def _probe_single_port(self):
        host = self.txt_probe_host.text().strip() or "127.0.0.1"
        try:
            port = int(self.txt_probe_port.text().strip())
        except ValueError:
            return

        self._run_probe(host, port)

    def _probe_all_ports(self):
        host = self.txt_probe_host.text().strip() or "127.0.0.1"
        for r in range(self.table_ports.rowCount()):
            p_str = self.table_ports.item(r, 1).text()
            try:
                p = int(p_str)
                self._run_probe(host, p, row_idx=r)
            except Exception:
                pass

    def _run_probe(self, host: str, port: int, row_idx: Optional[int] = None):
        worker = PortProbeWorker(host, port)
        def _on_done(h, p, ok, lat, info):
            target_row = row_idx
            if target_row is None:
                # Find or add row
                for r in range(self.table_ports.rowCount()):
                    if self.table_ports.item(r, 1).text() == str(p):
                        target_row = r
                        break
            if target_row is not None:
                status_item = QTableWidgetItem("● ACTIVE" if ok else "○ CLOSED")
                status_item.setForeground(QColor("#10B981" if ok else "#6B7280"))
                status_item.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                self.table_ports.setItem(target_row, 2, status_item)
                self.table_ports.setItem(target_row, 3, QTableWidgetItem(f"{lat:.1f} ms"))
                self.table_ports.setItem(target_row, 4, QTableWidgetItem(info))

        worker.result_ready.connect(_on_done)
        worker.start()

    # ==================== Tab 3: Mobile Code Exporter ====================

    def _build_mobile_templates_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet("background-color: #FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl = QLabel("Android Kotlin Templates for newly scaffolded modules:")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        layout.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋 Copy Code to Clipboard")
        btn_copy.setStyleSheet("background-color: #111827; color: #FFFFFF; padding: 6px 14px; border-radius: 6px; font-weight: bold;")
        btn_copy.clicked.connect(self._copy_android_template)
        btn_row.addWidget(btn_copy)

        btn_save = QPushButton("💾 Save Directly to android_client project")
        btn_save.setStyleSheet("background-color: #F3F4F6; color: #111827; border: 1px solid #D1D5DB; padding: 6px 14px; border-radius: 6px; font-weight: bold;")
        btn_save.clicked.connect(self._save_to_android_project)
        btn_row.addWidget(btn_save)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.txt_mobile_code = QTextEdit()
        self.txt_mobile_code.setFont(QFont("Consolas", 9))
        self.txt_mobile_code.setStyleSheet("background-color: #111827; color: #F9FAFB; border: 1px solid #374151; border-radius: 6px; padding: 8px;")
        layout.addWidget(self.txt_mobile_code, 1)

        # Initial sample template
        self.txt_mobile_code.setText("""// Android Module Scaffolding Template
// 1. In android_client/app/src/main/java/com/zerocast/ui/
//    Create: NewModuleActivity.kt
// 2. In android_client/app/src/main/res/layout/
//    Create: activity_new_module.xml
// 3. Register in AndroidManifest.xml:
//    <activity android:name=".ui.NewModuleActivity" android:exported="true" />
""")
        return tab

    def _copy_android_template(self):
        text = self.txt_mobile_code.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            QMessageBox.information(self._widget, "Copied", "Android template copied to clipboard!")

    def _save_to_android_project(self):
        m_id = self.txt_mod_id.text().strip().lower()
        m_name = self.txt_mod_name.text().strip()
        class_name = "".join(w.capitalize() for w in m_name.split()) + "Activity"

        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        android_ui_dir = os.path.join(root_dir, "android_client", "app", "src", "main", "java", "com", "zerocast", "ui")
        
        if os.path.exists(android_ui_dir):
            file_path = os.path.join(android_ui_dir, f"{class_name}.kt")
            code = self.txt_mobile_code.toPlainText()
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)
                QMessageBox.information(self._widget, "Saved", f"Created: {file_path}")
            except Exception as e:
                QMessageBox.warning(self._widget, "Save Error", f"Failed to write file: {e}")
        else:
            QMessageBox.warning(self._widget, "Project Not Found", "Could not find android_client UI directory.")
