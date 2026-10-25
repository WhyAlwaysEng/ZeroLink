"""ZeroLink - Centralized Application Settings Manager
Persists PC settings to ~/.zerolink/settings.json
"""

import os
import json
import sys
from typing import Optional

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".zerolink")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "ZeroDrop")


class AppSettings:
    """Singleton settings manager for ZeroLink Hub."""
    _instance: Optional['AppSettings'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._data = {
            "download_dir": DEFAULT_DOWNLOAD_DIR,
            "close_to_tray": True,
            "start_minimized": False,
            "auto_copy_otp": True,
            "notify_popup": True,
        }
        self.load()

    def load(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self._data.update(loaded)
        except Exception as e:
            print(f"[Settings] Error loading config: {e}")

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
        except Exception as e:
            print(f"[Settings] Error saving config: {e}")

    @property
    def download_dir(self) -> str:
        d = self._data.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        return d if d else DEFAULT_DOWNLOAD_DIR

    @download_dir.setter
    def download_dir(self, value: str):
        self._data["download_dir"] = value
        self.save()

    @property
    def close_to_tray(self) -> bool:
        return self._data.get("close_to_tray", True)

    @close_to_tray.setter
    def close_to_tray(self, value: bool):
        self._data["close_to_tray"] = value
        self.save()

    @property
    def start_minimized(self) -> bool:
        return self._data.get("start_minimized", False)

    @start_minimized.setter
    def start_minimized(self, value: bool):
        self._data["start_minimized"] = value
        self.save()

    @property
    def auto_copy_otp(self) -> bool:
        return self._data.get("auto_copy_otp", True)

    @auto_copy_otp.setter
    def auto_copy_otp(self, value: bool):
        self._data["auto_copy_otp"] = value
        self.save()

    @property
    def notify_popup(self) -> bool:
        return self._data.get("notify_popup", True)

    @notify_popup.setter
    def notify_popup(self, value: bool):
        self._data["notify_popup"] = value
        self.save()
