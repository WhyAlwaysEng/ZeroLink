"""ZeroLink PC Hub - GitHub Releases Auto-Update Engine
Checks https://api.github.com/repos/WhyAlwaysEng/ZeroLink/releases/latest
Runs in a background thread to prevent UI freezing.
"""

import re
import json
import urllib.request
import urllib.error
from typing import Optional, Tuple
from PyQt6.QtCore import QThread, pyqtSignal

CURRENT_VERSION = "1.2.3"
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
    """Background worker to check for new GitHub releases."""
    update_available = pyqtSignal(str, str, str)  # tag_name, html_url, release_notes
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
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status != 200:
                    self.no_update.emit(self.is_manual)
                    return

                data = json.loads(resp.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").strip()
                html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
                body = data.get("body", "No release notes provided.")

                remote_v = parse_version(tag_name)
                local_v = parse_version(self.current_version)

                if remote_v > local_v:
                    self.update_available.emit(tag_name, html_url, body)
                else:
                    self.no_update.emit(self.is_manual)

        except urllib.error.HTTPError:
            self.no_update.emit(self.is_manual)
        except Exception as e:
            self.check_failed.emit(str(e), self.is_manual)
