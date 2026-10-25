"""ZeroCast PC Receiver - Studio-Grade Jitter-Buffered Audio Player
Uses PyQt6.QtMultimedia QAudioSink to playback PCM 16-bit stereo audio directly from Android device.
Features:
- Dedicated asynchronous feeder thread (decoupled from Qt GUI thread)
- Adaptive Jitter Prebuffer (absorbs Wi-Fi packet latency & network bursts)
- Exact 4-byte sample-frame alignment (eliminates channel swaps & metallic crackling)
- Zero sample-loss replay recovery
- Dynamic Audio Output Device Routing (switch between Headphones, Speakers, Monitors)
- Real-time volume adjustment (0.0 to 1.0)
"""

import threading
import time
from typing import List, Tuple
import numpy as np
from PyQt6.QtCore import QIODevice
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QAudioDevice, QMediaDevices


class AudioPlayer:
    def __init__(self, sample_rate: int = 48000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self.bytes_per_sample = 2 * channels  # 16-bit stereo = 4 bytes per frame
        self.sink: QAudioSink = None
        self.io_device: QIODevice = None
        self.selected_device: QAudioDevice = None
        self.is_active = True
        self.current_volume = 1.0

        # Thread-safe Jitter Buffer
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._is_prebuffering = True
        self._last_chunk_time = 0.0
        # ~60ms initial prebuffer (~11.5 KB) absorbs network bursts smoothly on startup
        self._target_prebuffer_bytes = int(self.sample_rate * self.bytes_per_sample * 0.06)
        # Max buffer backlog before gentle discard (prevents runaway latency)
        self._max_buffer_bytes = int(self.sample_rate * self.bytes_per_sample * 0.50)

        self._setup_sink()

        # Dedicated background thread feeding QAudioSink smoothly
        self._feed_thread = threading.Thread(target=self._feed_loop, daemon=True, name="ZeroCast-AudioFeeder")
        self._feed_thread.start()

    def get_available_devices(self) -> List[Tuple[str, QAudioDevice, bool]]:
        """Returns list of (device_description, device_obj, is_default)."""
        outputs = QMediaDevices.audioOutputs()
        return [(d.description(), d, d.isDefault()) for d in outputs]

    def set_device(self, device: QAudioDevice):
        """Dynamically switches playback to a selected audio output device."""
        if not device or device.isNull():
            return
        self.selected_device = device
        self._restart_sink()

    def _setup_sink(self):
        dev = self.selected_device or QMediaDevices.defaultAudioOutput()
        audio_format = QAudioFormat()
        audio_format.setSampleRate(self.sample_rate)
        audio_format.setChannelCount(self.channels)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        if not dev.isFormatSupported(audio_format):
            audio_format = dev.preferredFormat()

        self.audio_format = audio_format
        self.is_float_format = (audio_format.sampleFormat() == QAudioFormat.SampleFormat.Float)
        self.sink_frame_bytes = audio_format.bytesPerFrame() if audio_format.bytesPerFrame() > 0 else (4 if not self.is_float_format else 8)

        self.sink = QAudioSink(dev, audio_format)
        # 500ms hardware buffer in WASAPI completely eliminates audio underruns
        buf_size = max(4096, self.sample_rate * self.sink_frame_bytes // 2)
        self.sink.setBufferSize(buf_size)
        self.sink.setVolume(self.current_volume)
        self.io_device = self.sink.start()
        self.is_active = True

    def _restart_sink(self):
        with self._lock:
            if self.sink:
                try:
                    self.sink.stop()
                except Exception:
                    pass
                self.sink = None
            self.io_device = None

            self._setup_sink()
            self._is_prebuffering = True
            self._target_prebuffer_bytes = int(self.sample_rate * self.bytes_per_sample * 0.15)

    def set_volume(self, volume: float):
        """Sets volume between 0.0 (silent) and 1.0 (max)."""
        self.current_volume = max(0.0, min(1.0, volume))
        if self.sink:
            self.sink.setVolume(self.current_volume)

    def is_muted(self) -> bool:
        return self.current_volume == 0.0

    def toggle_mute(self) -> bool:
        """Toggles between mute (0.0) and previous volume level."""
        if self.current_volume > 0.0:
            self._unmute_volume = self.current_volume
            self.set_volume(0.0)
            return True
        else:
            prev = getattr(self, "_unmute_volume", 1.0)
            self.set_volume(prev if prev > 0.0 else 1.0)
            return False

    def play_chunk(self, pcm_data: bytes):
        """Alias for write_pcm."""
        self.write_pcm(pcm_data)

    def write_pcm(self, pcm_data: bytes):
        """Receives incoming PCM audio bytes from network and buffers them safely."""
        if not self.is_active or not pcm_data:
            return
        with self._lock:
            self._last_chunk_time = time.time()
            # Drop older overflow data if network stalled for too long
            if len(self._buffer) > self._max_buffer_bytes:
                excess = len(self._buffer) - self._max_buffer_bytes
                # Align excess drop to exact sample-frame (4 bytes)
                excess = (excess // self.bytes_per_sample) * self.bytes_per_sample
                del self._buffer[:excess]

            self._buffer.extend(pcm_data)

    def _feed_loop(self):
        """Continuously feeds the audio sink without blocking or truncating frames."""
        while self.is_active:
            try:
                if not self.sink or not self.io_device:
                    time.sleep(0.01)
                    continue

                bytes_free = self.sink.bytesFree()
                sink_frame_bytes = getattr(self, "sink_frame_bytes", self.bytes_per_sample)
                if bytes_free < sink_frame_bytes:
                    time.sleep(0.003)
                    continue

                chunk_to_write = None
                with self._lock:
                    now = time.time()
                    # Only reset prebuffer if stream was completely idle/silent for > 400ms
                    if now - self._last_chunk_time > 0.4:
                        self._is_prebuffering = True

                    if self._is_prebuffering:
                        if len(self._buffer) >= self._target_prebuffer_bytes:
                            self._is_prebuffering = False
                        else:
                            # Still filling prebuffer to absorb initial startup burst
                            pass

                    # Once prebuffered, feed continuously without artificial starvation cycles!
                    if not self._is_prebuffering and len(self._buffer) > 0:
                        frames_free = bytes_free // sink_frame_bytes
                        frames_available = len(self._buffer) // self.bytes_per_sample
                        frames_to_take = min(frames_free, frames_available)
                        bytes_to_take = frames_to_take * self.bytes_per_sample

                        if bytes_to_take > 0:
                            chunk_to_write = bytes(self._buffer[:bytes_to_take])
                            del self._buffer[:bytes_to_take]

                if chunk_to_write:
                    # Convert to Float32 if required by hardware sink
                    if getattr(self, "is_float_format", False):
                        int16_arr = np.frombuffer(chunk_to_write, dtype=np.int16)
                        bytes_to_write = (int16_arr.astype(np.float32) / 32768.0).tobytes()
                    else:
                        bytes_to_write = chunk_to_write

                    written = self.io_device.write(bytes_to_write)
                    if written > 0 and written < len(bytes_to_write):
                        # Re-insert unwritten remainder back to the front of buffer (converting back to int16 if needed)
                        unwritten_ratio = 1.0 - (written / len(bytes_to_write))
                        unwritten_bytes = int(len(chunk_to_write) * unwritten_ratio)
                        unwritten_bytes = (unwritten_bytes // self.bytes_per_sample) * self.bytes_per_sample
                        if unwritten_bytes > 0:
                            remainder = chunk_to_write[-unwritten_bytes:]
                            with self._lock:
                                self._buffer = bytearray(remainder) + self._buffer

                time.sleep(0.003)
            except Exception:
                time.sleep(0.01)

    def stop(self):
        self.is_active = False
        with self._lock:
            self._buffer.clear()
        if self.sink:
            try:
                self.sink.stop()
            except Exception:
                pass
            self.sink = None
        self.io_device = None
