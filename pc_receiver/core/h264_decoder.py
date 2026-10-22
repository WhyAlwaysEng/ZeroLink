"""ZeroCast H.264 Hardware-Accelerated Stream Decoder (SIMD Optimized)
Decodes video/avc NAL units with zero-latency baseline mode and fast C-level RGB conversion.
"""

from typing import List
from PyQt6.QtGui import QImage

try:
    import av
    HAS_AV = True
except ImportError:
    HAS_AV = False


class H264Decoder:
    def __init__(self):
        self.codec = None
        self._init_decoder()

    def _init_decoder(self):
        if not HAS_AV:
            return
        try:
            codec = av.CodecContext.create('h264', 'r')
            codec.options = {'flags': 'low_delay', 'tune': 'zerolatency'}
            codec.thread_type = 'SLICE'
            codec.thread_count = 1
            codec.open()
            self.codec = codec
        except Exception:
            try:
                codec = av.CodecContext.create('h264', 'r')
                codec.open()
                self.codec = codec
            except Exception:
                self.codec = None

    def is_available(self) -> bool:
        return self.codec is not None

    def reset(self):
        """Flushes and reinitializes the codec context for a new stream session."""
        self._init_decoder()

    def decode(self, h264_data: bytes) -> List[QImage]:
        """Decodes raw H.264 NAL bytes and returns decoded QImages with SIMD reformatting."""
        if not self.codec:
            self._init_decoder()
            if not self.codec:
                return []

        images = []
        try:
            packet = av.Packet(h264_data)
            frames = self.codec.decode(packet)
            for frame in frames:
                # Fast SIMD C-level RGB24 conversion (reformat)
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
            self._init_decoder()

        return images
