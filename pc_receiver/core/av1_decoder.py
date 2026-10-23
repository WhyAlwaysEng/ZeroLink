"""ZeroCast AV1 Hardware-Accelerated Stream Decoder (SIMD Optimized)
Decodes video/av1 frames with zero-latency baseline mode and fast C-level RGB conversion.
Runs in total isolation from H.264 decoder.
"""

from typing import List
import numpy as np
from PyQt6.QtGui import QImage

try:
    import av
    HAS_AV = True
except ImportError:
    HAS_AV = False


class Av1Decoder:
    def __init__(self):
        self.codec = None
        self._init_decoder()

    def _init_decoder(self):
        if not HAS_AV:
            return
        # Prefer libdav1d (VideoLAN ultra-fast SIMD AV1 decoder) with zero-latency
        for codec_name in ('libdav1d', 'av1_cuvid', 'av1'):
            try:
                codec = av.CodecContext.create(codec_name, 'r')
                codec.flags |= av.codec.context.Flags.low_delay
                codec.open()
                self.codec = codec
                break
            except Exception:
                continue

    def is_available(self) -> bool:
        return self.codec is not None

    def reset(self):
        """Flushes and reinitializes the codec context for a new stream session."""
        self._init_decoder()

    def decode(self, av1_data: bytes) -> List[QImage]:
        """Decodes raw AV1 bytes and returns decoded QImages with SIMD reformatting."""
        if not self.codec:
            self._init_decoder()
            if not self.codec:
                return []

        images = []
        try:
            packet = av.Packet(av1_data)
            frames = self.codec.decode(packet)
            for frame in frames:
                rgb = frame.reformat(format='rgb24')
                plane = rgb.planes[0]

                qimg = QImage(
                    plane,
                    rgb.width,
                    rgb.height,
                    plane.line_size,
                    QImage.Format.Format_RGB888
                ).copy()
                images.append(qimg)
        except Exception:
            pass

        return images

    def decode_to_bgr(self, av1_data: bytes) -> List[np.ndarray]:
        """Decodes raw AV1 bytes and returns decoded OpenCV BGR numpy arrays."""
        if not self.codec:
            self._init_decoder()
            if not self.codec:
                return []

        bgr_frames = []
        try:
            packet = av.Packet(av1_data)
            frames = self.codec.decode(packet)
            for frame in frames:
                bgr = frame.to_ndarray(format='bgr24')
                bgr_frames.append(bgr)
        except Exception:
            pass

        return bgr_frames
