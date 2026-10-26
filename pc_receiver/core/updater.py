"""ZeroLink PC Hub - GitHub Releases Auto-Update Engine
Checks https://api.github.com/repos/WhyAlwaysEng/ZeroLink/releases/latest
Downloads updates with real-time progress and applies them in-place automatically.
"""

import os
import sys
import re
import json
import tempfile
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Tuple
from PyQt6.QtCore import QThread, pyqtSignal

CURRENT_VERSION = "1.2.5"
GITHUB_REPO = "WhyAlwaysEng/ZeroLink"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """Extract integer version components from string like 'v1.0.1' -> (1, 0, 1)."""
    clean = re.sub(r"[^\d.]", "", ver_str.strip())
    parts = []
    for part in clean.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0, 0, 0)


class UpdateCheckWorker(QThread):
    """Background worker to check for new GitHub releases and extract assets."""
    # tag_name, html_url, release_notes, zip_url, zip_size
    update_available = pyqtSignal(str, str, str, str, int)
    no_update = pyqtSignal(bool)                  # is_manual
    check_failed = pyqtSignal(str, bool)          # error_message, is_manual

    def __init__(self, current_version: str = CURRENT_VERSION, is_manual: bool = False, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.is_manual = is_manual

    def run(self):
        try:
            req = urllib.request.Request(
                API_URL,
                headers={
                    "User-Agent": f"ZeroLink-PC-Hub/{self.current_version}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status != 200:
                    self.no_update.emit(self.is_manual)
                    return

                data = json.loads(resp.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").strip()
                html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
                body = data.get("body", "No release notes provided.")

                setup_url = ""
                setup_size = 0
                zip_url = ""
                zip_size = 0
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    url = asset.get("browser_download_url", "")
                    size = asset.get("size", 0)
                    if name.endswith(".exe") and "setup" in name:
                        setup_url = url
                        setup_size = size
                    elif name.endswith(".zip") and ("windows" in name or "zerolink" in name):
                        zip_url = url
                        zip_size = size

                # Prefer modern Inno Setup installer over manual zip
                primary_url = setup_url or zip_url
                primary_size = setup_size or zip_size

                remote_v = parse_version(tag_name)
                local_v = parse_version(self.current_version)

                if remote_v > local_v:
                    self.update_available.emit(tag_name, html_url, body, primary_url, primary_size)
                else:
                    self.no_update.emit(self.is_manual)

        except urllib.error.HTTPError:
            self.no_update.emit(self.is_manual)
        except Exception as e:
            self.check_failed.emit(str(e), self.is_manual)


class UpdateDownloadWorker(QThread):
    """Downloads release archive in background with chunked progress."""
    progress = pyqtSignal(int, int)   # downloaded_bytes, total_bytes
    finished = pyqtSignal(str)        # downloaded_file_path
    failed = pyqtSignal(str)          # error_message

    def __init__(self, download_url: str, total_size: int = 0, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.total_size = total_size
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), "ZeroLink_Update")
            os.makedirs(temp_dir, exist_ok=True)
            is_exe = self.download_url.lower().split("?")[0].endswith(".exe")
            file_name = "ZeroLink_Setup.exe" if is_exe else "ZeroLink_Latest.zip"
            save_path = os.path.join(temp_dir, file_name)

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "ZeroLink-AutoUpdater"}
            )

            downloaded = 0
            chunk_size = 256 * 1024

            with urllib.request.urlopen(req, timeout=15.0) as resp, open(save_path, "wb") as f:
                content_len = resp.headers.get("Content-Length")
                if content_len:
                    self.total_size = int(content_len)

                while not self._is_cancelled:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, self.total_size)

            if self._is_cancelled:
                try:
                    if os.path.exists(save_path):
                        os.remove(save_path)
                except Exception:
                    pass
                return

            self.finished.emit(save_path)

        except Exception as e:
            self.failed.emit(str(e))


def apply_update_and_restart(file_path: str) -> bool:
    """Applies update in-place:
    - If file is an Inno Setup installer (.exe), executes it with /SILENT.
    - If file is a zip archive (.zip), extracts it over target directory.
    """
    is_frozen = getattr(sys, "frozen", False)
    target_dir = os.path.dirname(os.path.abspath(sys.executable if is_frozen else sys.argv[0]))

    if not is_frozen:
        print(f"[AutoUpdate] Development source mode: file downloaded to {file_path}")
        return False

    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    # 1. Native Inno Setup Installer upgrade
    if file_path.lower().endswith(".exe"):
        try:
            # /SILENT /SP- runs quietly, /CLOSEAPPLICATIONS closes old process cleanly
            cmd = f'"{file_path}" /SILENT /SP- /CLOSEAPPLICATIONS'
            subprocess.Popen(cmd, shell=True, creationflags=flags)
            return True
        except Exception as e:
            print(f"[AutoUpdate] Failed to run installer: {e}")
            return False

    # 2. Portable Zip fallback
    update_dir = os.path.dirname(file_path)
    bat_path = os.path.join(update_dir, "apply_update.bat")

    bat_content = f"""@echo off
setlocal enabledelayedexpansion
title ZeroLink Updater
echo ===================================================
echo   Updating ZeroLink to Latest Version...
echo ===================================================
echo.
echo [1/3] Waiting for current instance to exit...
timeout /t 2 /nobreak >nul
taskkill /f /im ZeroLink.exe >nul 2>&1

echo [2/3] Extracting new package...
tar -xf "{file_path}" -C "{target_dir}"
if %errorlevel% neq 0 (
    echo Extraction failed with tar. Retrying with PowerShell...
    powershell -Command "Expand-Archive -Path '{file_path}' -DestinationPath '{target_dir}' -Force"
)

echo [3/3] Relaunching ZeroLink...
start "" "{os.path.join(target_dir, 'ZeroLink.exe')}"

echo Update complete! Cleaning up...
ping 127.0.0.1 -n 3 >nul
del "{file_path}" >nul 2>&1
(goto) 2>nul & del "%~f0"
"""

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=flags)
    return True
