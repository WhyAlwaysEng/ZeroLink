"""ZeroCast PC Receiver - High-Performance Virtual Camera Engine
Streams the live mobile screen or phone camera directly into a system Virtual Camera.
Applications like Discord, Zoom, Google Meet, and OBS can select 'OBS Virtual Camera'
to use the Android phone as a high-definition 60FPS webcam or presentation source.
"""

import queue
import threading
import time
import cv2
import numpy as np
from PyQt6.QtGui import QImage

try:
    import pyvirtualcam
    HAS_VIRTUALCAM = True
except ImportError:
    HAS_VIRTUALCAM = False


class VirtualCameraManager:
    def __init__(self, target_width: int = 1280, target_height: int = 720, fps: int = 30):
        self.target_width = target_width
        self.target_height = target_height
        self.fps = fps
        self.is_active = False
        self.device_name = "None"

        self._cam = None
        self._thread = None
        self._queue = queue.Queue(maxsize=2)

    @staticmethod
    def is_supported() -> bool:
        return HAS_VIRTUALCAM

    def start(self) -> bool:
        if not HAS_VIRTUALCAM or self.is_active:
            return False

        try:
            self._cam = pyvirtualcam.Camera(
                width=self.target_width,
                height=self.target_height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.RGB
            )
            self.device_name = str(self._cam.device)
            self.is_active = True

            self._thread = threading.Thread(target=self._worker, daemon=True, name="ZeroCast-VirtualCam")
            self._thread.start()
            return True
        except Exception as e:
            self.device_name = f"Error: {e}"
            self.stop()
            return False

    def send_qimage(self, image: QImage):
        """Alias for push_frame."""
        self.push_frame(image)

    def push_frame(self, image: QImage):
        """Pushes a QImage frame into the virtual camera queue asynchronously."""
        if not self.is_active or image.isNull():
            return

        try:
            # Ensure RGB888 format
            rgb_img = image
            if image.format() != QImage.Format.Format_RGB888:
                rgb_img = image.convertToFormat(QImage.Format.Format_RGB888)

            ptr = rgb_img.bits()
            ptr.setsize(rgb_img.sizeInBytes())
            src_arr = np.frombuffer(ptr, np.uint8).reshape((rgb_img.height(), rgb_img.width(), 3))

            # Letterbox scale to target 16:9 canvas using ultra-fast OpenCV SIMD
            h, w = src_arr.shape[:2]
            scale = min(self.target_width / w, self.target_height / h)
            nw, nh = int(w * scale), int(h * scale)

            resized = cv2.resize(src_arr, (nw, nh), interpolation=cv2.INTER_LINEAR)
            canvas = np.zeros((self.target_height, self.target_width, 3), dtype=np.uint8)
            x = (self.target_width - nw) // 2
            y = (self.target_height - nh) // 2
            canvas[y:y+nh, x:x+nw] = resized

            # Non-blocking push; drop older frame if consumer is behind
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            self._queue.put_nowait(canvas)
        except Exception:
            pass

    def _worker(self):
        while self.is_active and self._cam:
            try:
                frame = self._queue.get(timeout=0.1)
                if frame is None or not self.is_active:
                    break
                self._cam.send(frame)
                self._cam.sleep_until_next_frame()
            except queue.Empty:
                continue
            except Exception:
                break

    def stop(self):
        self.is_active = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=0.2)
            except Exception:
                pass
            self._thread = None
        if self._cam:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None
        self.device_name = "None"
