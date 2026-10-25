"""ZeroCast ADB Helper
Locates adb.exe automatically across system PATH and standard Android SDK installation directories,
detects connected devices, and manages port reverse tunnels.
"""

import os
import shutil
import subprocess
from typing import Optional, List, Tuple


def find_adb_path() -> Optional[str]:
    """Locates adb executable on the machine."""
    # 1. Check if adb is directly in system PATH
    adb_in_path = shutil.which("adb")
    if adb_in_path:
        return adb_in_path

    # 2. Check Android Studio / SDK standard locations on Windows
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_appdata, r"Android\Sdk\platform-tools\adb.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), r"Android\platform-tools\adb.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), r"AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        r"C:\platform-tools\adb.exe",
    ]

    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if android_home:
        candidates.insert(0, os.path.join(android_home, r"platform-tools\adb.exe"))

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


class AdbManager:
    def __init__(self):
        self.adb_path = find_adb_path()

    def refresh(self):
        self.adb_path = find_adb_path()

    def is_available(self) -> bool:
        return self.adb_path is not None and os.path.isfile(self.adb_path)

    def is_wireless_device(self, serial: str) -> bool:
        """Returns True if the ADB device serial indicates a Wireless Debugging connection over Wi-Fi."""
        return "._tcp" in serial or ":" in serial or serial.startswith("adb-")

    def get_connection_type(self) -> str:
        """Returns 'USB', 'WIRELESS_ADB', or 'NONE'."""
        devices = self.get_devices()
        if not devices:
            return "NONE"
        for serial, state in devices:
            if state == "device":
                if self.is_wireless_device(serial):
                    return "WIRELESS_ADB"
                return "USB"
        return "NONE"

    def get_devices(self) -> List[Tuple[str, str]]:
        """Returns list of (serial_id, state) e.g. [('device_serial', 'device')]."""
        if not self.is_available():
            return []
        try:
            res = subprocess.run(
                [self.adb_path, "devices"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            devices = []
            for line in res.stdout.strip().splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    devices.append((parts[0], parts[1]))
            return devices
        except Exception:
            return []

    ECOSYSTEM_REVERSE_PORTS = [8886, 8888, 8889, 8890, 8891, 8892, 8893, 8894, 8895, 8897]

    def reverse_ecosystem_ports(self) -> Tuple[bool, str]:
        """Reverses all ports required by the ZeroLink ecosystem modules for seamless USB ADB mode."""
        if not self.is_available():
            return False, "ADB was not found."
        devices = self.get_devices()
        if not devices:
            return False, "No device connected."
        success_count = 0
        for port in self.ECOSYSTEM_REVERSE_PORTS:
            ok, _ = self.reverse_port(port)
            if ok:
                success_count += 1
        return success_count > 0, f"Successfully reversed {success_count} ecosystem ports via ADB."

    def reverse_port(self, port: int = 8888) -> Tuple[bool, str]:
        """Runs 'adb reverse tcp:<port> tcp:<port>' to allow Android to connect via 127.0.0.1."""
        if not self.is_available():
            return False, "ADB was not found on your system."

        devices = self.get_devices()
        if not devices:
            return False, "No Android device detected. Please connect phone via USB and allow USB Debugging."

        try:
            cmd = [self.adb_path, "reverse", f"tcp:{port}", f"tcp:{port}"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if res.returncode == 0:
                return True, f"USB tunnel active! Port {port} forwarded successfully."
            else:
                err = res.stderr.strip() or res.stdout.strip()
                return False, f"ADB error: {err}"
        except Exception as e:
            return False, f"Failed to execute ADB: {e}"

    def forward_port(self, port: int = 8896) -> Tuple[bool, str]:
        """Runs 'adb forward tcp:<port> tcp:<port>' to allow PC to connect to Android server via 127.0.0.1."""
        if not self.is_available():
            return False, "ADB was not found."
        try:
            cmd = [self.adb_path, "forward", f"tcp:{port}", f"tcp:{port}"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if res.returncode == 0:
                return True, f"Port {port} forwarded successfully."
            else:
                return False, res.stderr.strip() or res.stdout.strip()
        except Exception as e:
            return False, str(e)
