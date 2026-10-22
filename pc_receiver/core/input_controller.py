"""ZeroCast Reverse Control & Mouse Input Controller
Injects mouse clicks, swipes, and key events directly to the Android device.
Uses ultra-fast ADB shell input when connected, with socket fallback.
"""

import subprocess
import threading
from typing import Optional, Tuple
from core.adb_helper import AdbManager


class InputController:
    def __init__(self, adb_manager: AdbManager):
        self.adb_manager = adb_manager
        self.screen_width = 1080
        self.screen_height = 2400
        self.last_press_pos: Optional[Tuple[int, int]] = None

        self._query_phone_resolution()

    def _query_phone_resolution(self):
        """Asks ADB for physical device screen resolution."""
        if not self.adb_manager.is_available():
            return

        def _worker():
            try:
                cmd = [self.adb_manager.adb_path, "shell", "wm", "size"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                # Output format: "Physical size: 1080x2400"
                for line in res.stdout.splitlines():
                    if "size:" in line:
                        parts = line.split(":")[-1].strip().split("x")
                        if len(parts) == 2:
                            self.screen_width = int(parts[0])
                            self.screen_height = int(parts[1])
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def handle_mouse_event(self, action: str, norm_x: float, norm_y: float):
        """Translates normalized [0.0, 1.0] coordinates and sends touch to Android."""
        if not self.adb_manager.is_available():
            return

        target_x = int(norm_x * self.screen_width)
        target_y = int(norm_y * self.screen_height)

        if action == "DOWN":
            self.last_press_pos = (target_x, target_y)
        elif action == "UP":
            if self.last_press_pos:
                x1, y1 = self.last_press_pos
                dx = abs(target_x - x1)
                dy = abs(target_y - y1)
                if dx < 15 and dy < 15:
                    # Tap
                    self._run_adb_async(["shell", "input", "tap", str(target_x), str(target_y)])
                else:
                    # Swipe
                    self._run_adb_async(["shell", "input", "swipe", str(x1), str(y1), str(target_x), str(target_y), "150"])
            self.last_press_pos = None

    def send_touch_event(self, action: str, norm_x: float, norm_y: float):
        self.handle_mouse_event(action, norm_x, norm_y)

    def send_back_key(self):
        self._run_adb_async(["shell", "input", "keyevent", "4"])

    def send_home_key(self):
        self._run_adb_async(["shell", "input", "keyevent", "3"])

    def send_keyevent(self, keycode: int):
        """Sends an Android keycode (e.g. 66 for Enter, 67 for Backspace)."""
        self._run_adb_async(["shell", "input", "keyevent", str(keycode)])

    def send_key_event(self, keycode: int):
        self.send_keyevent(keycode)

    def send_text(self, text: str):
        """Sends typed characters directly to the Android device."""
        if not text:
            return
        # Escape spaces and shell-sensitive characters for adb shell input text
        escaped = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>").replace("\"", "\\\"").replace("'", "\\'")
        self._run_adb_async(["shell", "input", "text", escaped])

    def _run_adb_async(self, args):
        def _exec():
            try:
                cmd = [self.adb_manager.adb_path] + args
                subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                pass

        threading.Thread(target=_exec, daemon=True).start()
