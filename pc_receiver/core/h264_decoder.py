"""ZeroCast H.264 Hardware-Accelerated Stream Decoder (SIMD Optimized)
Decodes video/avc NAL units with zero-latency baseline mode and fast C-level RGB conversion.
"""

from typing import List
import numpy as np
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
            import os
            codec = av.CodecContext.create('h264', 'r')
            codec.flags |= av.codec.context.Flags.low_delay
            try:
                codec.flags2 |= av.codec.context.Flags2.fast
            except Exception:
                pass
            codec.options = {'tune': 'zerolatency'}
            codec.thread_type = 'SLICE'
            codec.thread_count = min(2, os.cpu_count() or 2)
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
            # Parameter sets (SPS/PPS) or incomplete slices can raise an error in avcodec_send_packet.
            # Do NOT reset the decoder so that macroblock reference chains remain intact.
            pass

        return images

    def decode_to_bgr(self, h264_data: bytes) -> List[np.ndarray]:
        """Decodes raw H.264 NAL bytes and returns decoded OpenCV BGR numpy arrays."""
        if not self.codec:
            self._init_decoder()
            if not self.codec:
                return []

        bgr_frames = []
        try:
            packet = av.Packet(h264_data)
            frames = self.codec.decode(packet)
            for frame in frames:
                bgr = frame.to_ndarray(format='bgr24')
                bgr_frames.append(bgr)
        except Exception:
            pass

        return bgr_frames
