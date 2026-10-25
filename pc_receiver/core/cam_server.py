"""ZeroCam Streaming Server
Receives wireless HD/4K camera streams from Android mobile devices and bridges into
OBS Virtual Camera / DirectShow virtual webcam for Discord, OBS, Zoom, and Teams.
"""

import json
import socket
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

try:
    import pyvirtualcam
    HAS_PYVIRTUALCAM = True
except ImportError:
    HAS_PYVIRTUALCAM = False


class CamServer(QObject):
    """ZeroCam TCP Server: Mobile wireless camera receiver and PC Virtual Webcam feeder."""

    client_connected = pyqtSignal(str, str)     # ip, model
    client_disconnected = pyqtSignal(str)       # ip
    clients_updated = pyqtSignal()
    stats_updated = pyqtSignal(float, float)    # fps, bitrate_mbps
    frame_ready = pyqtSignal(QImage)            # Render-ready QImage for PC GUI

    MAGIC = b"ZCAM"  # 4-byte header magic

    def __init__(self, port: int = 8893, parent=None):
        super().__init__(parent)
        self.port = port
        self.is_running = False

        # Virtual Webcam Feeder (Default Full HD 1080p)
        self.enable_virtual_cam = False
        self._vcam: Optional[object] = None
        self._vcam_w = 1920
        self._vcam_h = 1080
        self._vcam_fps = 30

        # Video adjustments
        self.flip_horizontal = True     # Mirror camera (standard for webcams)
        self.flip_vertical = False
        self.rotation_degrees = 0       # 0, 90, 180, 270
        self.manual_rotation = 0        # 0, 90, 180, 270 manual override offset
        self.brightness = 0             # -100 to 100
        self.contrast = 1.0             # 0.5 to 2.0
        self.sharpness = 0.5            # 0.0 to 1.5 Detail enhancer / unsharp mask
        self.saturation = 1.15          # 0.5 to 2.0 Color vibrancy booster

        # 4K Digital Framing / Lossless ePTZ (Pan-Tilt-Zoom)
        self.crop_enabled = False
        self.crop_zoom = 1.0            # 1.0x to 4.0x
        self.crop_pan = 0.0             # -1.0 (left) to +1.0 (right)
        self.crop_tilt = 0.0            # -1.0 (up) to +1.0 (down)

        # Hardware H.264 Decoder
        self._h264_decoder = None

        # Sockets & threads
        self._server_sock: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()
        self._active_client: Optional[socket.socket] = None
        self._client_info: Optional[Dict] = None

        # Stats
        self.fps = 0.0
        self.bitrate_mbps = 0.0
        self._frame_count = 0
        self._bytes_received = 0
        self._last_stat_time = time.time()

    def start(self) -> bool:
        if self.is_running:
            return True

        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._server_sock.bind(("0.0.0.0", self.port))
            self._server_sock.listen(2)
            self.is_running = True

            self._server_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._server_thread.start()

            print(f"[ZeroCam] Server started on port {self.port}")
            return True
        except Exception as e:
            print(f"[ZeroCam] Start error: {e}")
            self.stop()
            return False

    def stop(self):
        self.is_running = False
        self.stop_virtual_camera()

        with self._lock:
            if self._active_client:
                try:
                    self._active_client.close()
                except Exception:
                    pass
                self._active_client = None
                self._client_info = None

        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        self.fps = 0.0
        self.bitrate_mbps = 0.0
        self.stats_updated.emit(0.0, 0.0)
        self.clients_updated.emit()
        print("[ZeroCam] Server stopped.")

    def start_virtual_camera(self, width: int = 1280, height: int = 720, fps: int = 30) -> bool:
        """Initializes pyvirtualcam to expose ZeroCam to Discord / Zoom / OBS."""
        if not HAS_PYVIRTUALCAM:
            return False

        try:
            self.stop_virtual_camera()
            self._vcam_w = width
            self._vcam_h = height
            self._vcam_fps = fps
            self._vcam = pyvirtualcam.Camera(width=width, height=height, fps=fps, fmt=pyvirtualcam.PixelFormat.BGR)
            self.enable_virtual_cam = True
            print(f"[ZeroCam] Virtual Camera started: {self._vcam.device} ({width}x{height} @ {fps}fps)")
            return True
        except Exception as e:
            print(f"[ZeroCam] Virtual Camera start failed: {e}")
            self._vcam = None
            self.enable_virtual_cam = False
            return False

    def stop_virtual_camera(self):
        self.enable_virtual_cam = False
        if self._vcam:
            try:
                self._vcam.close()
            except Exception:
                pass
            self._vcam = None
            print("[ZeroCam] Virtual Camera closed.")

    def _listen_loop(self):
        while self.is_running and self._server_sock:
            try:
                client_sock, addr = self._server_sock.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                ip = addr[0]

                info = {
                    "addr": f"{addr[0]}:{addr[1]}",
                    "ip": ip,
                    "model": "Android Camera Client",
                    "connected_at": time.time(),
                    "mode": "Wireless 4K Webcam"
                }

                with self._lock:
                    if self._active_client:
                        try:
                            self._active_client.close()
                        except Exception:
                            pass
                    self._active_client = client_sock
                    self._client_info = info

                print(f"[ZeroCam] Mobile camera connected from {addr}")
                self.client_connected.emit(ip, info["model"])
                self.clients_updated.emit()

                # Handle camera stream frames
                self._handle_camera_stream(client_sock)
            except Exception:
                break

    def _handle_camera_stream(self, client_sock: socket.socket):
        """Reads incoming [ZCAM][Length][Timestamp][JPEG/Frame] packets."""
        magic_buf = bytearray(4)
        if self._h264_decoder:
            self._h264_decoder.reset()

        while self.is_running:
            try:
                # Read 4 bytes MAGIC
                magic_read = self._recv_exact(client_sock, 4)
                if not magic_read:
                    break

                # Support both binary packet and text JSON handshake
                if magic_read == self.MAGIC:
                    # Read length (4B), timestamp (8B), rotation (2B), flags (2B) = 16B
                    header = self._recv_exact(client_sock, 16)
                    if not header:
                        break
                    payload_len, timestamp, rotation_deg, flags = struct.unpack("!IQhh", header)

                    if payload_len <= 0 or payload_len > 15 * 1024 * 1024:
                        continue

                    # Read frame payload
                    frame_data = self._recv_exact(client_sock, payload_len)
                    if not frame_data:
                        break

                    if flags & 0x01:
                        # Hardware H.264 NAL Unit stream (Ultra-Low Latency, Crystal Clarity)
                        self._process_h264_frame(frame_data, rotation_deg)
                    else:
                        # Classic MJPEG stream
                        self._process_camera_frame(frame_data, rotation_deg)

                    self._frame_count += 1
                    self._bytes_received += (20 + payload_len)

                elif magic_read.startswith(b"{"):
                    # JSON line handshake
                    rest_of_line = b""
                    while not rest_of_line.endswith(b"\n"):
                        ch = client_sock.recv(1)
                        if not ch:
                            break
                        rest_of_line += ch
                    full_json = magic_read + rest_of_line
                    try:
                        msg = json.loads(full_json.decode("utf-8").strip())
                        model = msg.get("model") or msg.get("device_model")
                        with self._lock:
                            if self._client_info and model:
                                self._client_info["model"] = model
                        self.clients_updated.emit()
                    except Exception:
                        pass

                # Stats update every 1 second
                now = time.time()
                if now - self._last_stat_time >= 1.0:
                    dt = now - self._last_stat_time
                    self.fps = self._frame_count / dt
                    self.bitrate_mbps = (self._bytes_received * 8.0) / (dt * 1_000_000.0)
                    self.stats_updated.emit(self.fps, self.bitrate_mbps)
                    self._frame_count = 0
                    self._bytes_received = 0
                    self._last_stat_time = now

            except Exception:
                break

        with self._lock:
            if self._active_client == client_sock:
                self._active_client = None
                self._client_info = None

        self.client_disconnected.emit(client_sock.getpeername()[0] if client_sock else "")
        self.clients_updated.emit()

    def _recv_exact(self, sock: socket.socket, num_bytes: int) -> Optional[bytes]:
        """Utility to read exact byte length from TCP socket stream."""
        view = bytearray(num_bytes)
        received = 0
        while received < num_bytes:
            n = sock.recv_into(memoryview(view)[received:])
            if n == 0:
                return None
            received += n
        return bytes(view)

    def _post_process_and_emit(self, bgr: np.ndarray, rotation_deg: int = 0):
        """Unified post-processing pipeline: rotation, mirroring, color enhancement, VCam feeder, and GUI preview."""
        # Combine auto sensor rotation with manual override
        effective_rot = (rotation_deg + self.manual_rotation + self.rotation_degrees) % 360
        if effective_rot == 90:
            bgr = cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
        elif effective_rot == 180:
            bgr = cv2.rotate(bgr, cv2.ROTATE_180)
        elif effective_rot == 270:
            bgr = cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Image transforms
        if self.flip_horizontal:
            bgr = cv2.flip(bgr, 1)
        if self.flip_vertical:
            bgr = cv2.flip(bgr, 0)

        # Brightness / Contrast
        if self.contrast != 1.0 or self.brightness != 0:
            bgr = cv2.convertScaleAbs(bgr, alpha=self.contrast, beta=self.brightness)

        # Detail Enhancer & Sharpness Booster (Unsharp Mask)
        if self.sharpness > 0:
            gaussian = cv2.GaussianBlur(bgr, (0, 0), 2.0)
            bgr = cv2.addWeighted(bgr, 1.0 + self.sharpness, gaussian, -self.sharpness, 0)

        # Saturation Booster
        if self.saturation != 1.0:
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * self.saturation, 0, 255)
            bgr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # 4K Digital Framing / Lossless ePTZ (Pan-Tilt-Zoom Crop)
        if self.crop_enabled and self.crop_zoom > 1.01:
            orig_h, orig_w = bgr.shape[:2]
            crop_w = int(orig_w / self.crop_zoom)
            crop_h = int(orig_h / self.crop_zoom)

            max_pan = (orig_w - crop_w) // 2
            max_tilt = (orig_h - crop_h) // 2

            offset_x = int(self.crop_pan * max_pan)
            offset_y = int(self.crop_tilt * max_tilt)

            center_x = (orig_w // 2) + offset_x
            center_y = (orig_h // 2) + offset_y

            x1 = max(0, min(orig_w - crop_w, center_x - (crop_w // 2)))
            y1 = max(0, min(orig_h - crop_h, center_y - (crop_h // 2)))

            bgr = bgr[y1:y1 + crop_h, x1:x1 + crop_w]

        # Feed Virtual Camera (Discord / OBS / Zoom)
        if self.enable_virtual_cam and self._vcam:
            try:
                # Resize to target virtual cam dimensions with smooth anti-aliased interpolation
                h, w = bgr.shape[:2]
                if w != self._vcam_w or h != self._vcam_h:
                    v_frame = cv2.resize(bgr, (self._vcam_w, self._vcam_h), interpolation=cv2.INTER_LINEAR)
                else:
                    v_frame = bgr
                self._vcam.send(v_frame)
            except Exception:
                pass

        # Convert to QImage for PC Hub display
        h, w, ch = bgr.shape
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        bytes_per_line = ch * w
        q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self.frame_ready.emit(q_img)

    def _process_camera_frame(self, frame_bytes: bytes, rotation_deg: int = 0):
        """Decodes, filters, and broadcasts JPEG frame to GUI and Virtual Webcam."""
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return
        self._post_process_and_emit(bgr, rotation_deg)

    def _process_h264_frame(self, nal_bytes: bytes, rotation_deg: int = 0):
        """Hardware H.264 stream processor: decodes NAL units with PyAV in < 1ms."""
        if not self._h264_decoder:
            from core.h264_decoder import H264Decoder
            self._h264_decoder = H264Decoder()

        bgr_frames = self._h264_decoder.decode_to_bgr(nal_bytes)
        for bgr in bgr_frames:
            if bgr is not None and bgr.size > 0:
                self._post_process_and_emit(bgr, rotation_deg)

    def send_control_command(self, cmd: Dict):
        """Sends command JSON (e.g. switch camera, toggle flash) to the phone."""
        with self._lock:
            sock = self._active_client

        if sock:
            try:
                payload = (json.dumps(cmd) + "\n").encode("utf-8")
                sock.sendall(payload)
            except Exception as e:
                print(f"[ZeroCam] send_control_command error: {e}")

    def get_connected_clients(self) -> List[Dict]:
        with self._lock:
            if self._client_info:
                return [dict(self._client_info)]
        return []

    def disconnect_client(self, addr: str):
        with self._lock:
            if self._active_client:
                try:
                    self._active_client.close()
                except Exception:
                    pass
                self._active_client = None
                self._client_info = None
        self.clients_updated.emit()
