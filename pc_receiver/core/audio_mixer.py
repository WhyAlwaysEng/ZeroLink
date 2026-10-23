"""ZeroLink Audio Mixer Engine (ZeroMix)
Real-time audio mixer with Smart Auto-Ducking, Separate Monitoring,
Soundboard playback, and dual-output routing (Headphones Monitor + Virtual Mic Broadcast).
"""

import os
import time
import math
import threading
import collections
from typing import Optional, List, Dict, Tuple
import numpy as np
import sounddevice as sd
import av
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from core.voice_fx import VoiceFxProcessor


class AudioMixerEngine(QObject):
    levels_updated = pyqtSignal(float, float, float)     # mic_level (0..1), music_level, soundboard_level
    ducking_state_changed = pyqtSignal(bool, float)       # is_ducking, current_duck_multiplier
    soundboard_list_changed = pyqtSignal()
    sound_playback_changed = pyqtSignal(str, bool)        # sound_name, is_playing
    playback_state_changed = pyqtSignal(bool, str)        # is_music_playing, current_track_name
    phone_stream_status_changed = pyqtSignal(bool)
    volume_changed = pyqtSignal(str, int)                 # channel ("mic", "music", "soundboard"), pct
    mute_changed = pyqtSignal(str, bool)                  # channel, muted
    ducking_config_changed = pyqtSignal(bool, int)        # enabled, level_pct
    voice_effect_changed = pyqtSignal(str)                # effect_id e.g. "OFF", "RADIO", "DEEP", ...
    state_changed = pyqtSignal()

    def __init__(self, sample_rate: int = 48000, block_size: int = 512, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.is_running = False

        # Devices (indexes into sounddevice)
        self.input_mic_device: Optional[int] = None
        self.output_monitor_device: Optional[int] = None      # Headphones
        self.output_broadcast_device: Optional[int] = None    # Virtual Mic / Cable

        # Channel volumes (0.0 to 1.5) and mutes
        self.vol_mic = 1.0
        self.vol_music = 0.8
        self.vol_soundboard = 0.9

        self.mute_mic = False
        self.mute_music = False
        self.mute_soundboard = False

        # Monitoring flags (what user hears in their own headphones)
        self.monitor_mic = False          # False = don't echo own voice
        self.monitor_music = True
        self.monitor_soundboard = True
        self.mute_monitor = False         # Master monitor mute toggle (useful when testing in Discord)

        # Smart Auto-Ducking Configuration
        self.ducking_enabled = True
        self.ducking_level = 0.20         # Reduce music to 20%
        self.voice_threshold_db = -32.0   # dB threshold to trigger ducking
        self.duck_attack = 0.35           # Speed of fading down (fast)
        self.duck_release = 0.05          # Speed of fading back up (smooth)
        self._current_duck_factor = 1.0
        self._is_ducking = False

        # Real-time Voice FX Processor
        self.voice_fx = VoiceFxProcessor(sample_rate=self.sample_rate)

        # Audio Buffers & Playback state
        self._lock = threading.Lock()
        self._phone_buffer = bytearray()
        self._phone_prebuffering = True
        self._last_phone_audio_time: float = 0.0
        self._phone_streaming_active: bool = False

        self._music_data: Optional[np.ndarray] = None     # shape: (N, 2), float32
        self._music_idx: int = 0
        self._is_music_playing = False
        self._current_track_name = ""

        self._sound_data: Optional[np.ndarray] = None     # shape: (N, 2), float32
        self._sound_idx: int = 0
        self._is_sound_playing = False
        self._current_sound_name = ""

        # Soundboard Library storage
        self.soundboard_dir = os.path.join(os.path.expanduser("~"), ".zerolink", "sounds")
        os.makedirs(self.soundboard_dir, exist_ok=True)
        self.soundboard_items: List[Dict] = []
        self._load_soundboard_library()

        # Audio streams
        self._in_stream: Optional[sd.InputStream] = None
        self._out_monitor_stream: Optional[sd.OutputStream] = None
        self._out_broadcast_stream: Optional[sd.OutputStream] = None

        # Output ring queues for non-blocking PortAudio callbacks (low-latency queue)
        self._out_lock = threading.Lock()
        self._monitor_queue = collections.deque(maxlen=4)
        self._broadcast_queue = collections.deque(maxlen=4)

        # Level smoothing for VU meters
        self._peak_mic = 0.0
        self._peak_music = 0.0
        self._peak_sound = 0.0

        # Auto-detect default devices
        self._init_default_devices()

    def _init_default_devices(self):
        try:
            apis = sd.query_hostapis()
            wasapi_idx = next((i for i, a in enumerate(apis) if "WASAPI" in a["name"].upper()), None)
            devices = sd.query_devices()

            if wasapi_idx is not None:
                wasapi_info = apis[wasapi_idx]
                def_in = wasapi_info.get("default_input")
                def_out = wasapi_info.get("default_output")
                if def_in is not None and def_in >= 0:
                    self.input_mic_device = int(def_in)
                if def_out is not None and def_out >= 0:
                    self.output_monitor_device = int(def_out)
                target_devices = [(i, d) for i, d in enumerate(devices) if d.get("hostapi") == wasapi_idx]
            else:
                defaults = sd.default.device
                if defaults[0] is not None and defaults[0] >= 0:
                    self.input_mic_device = int(defaults[0])
                if defaults[1] is not None and defaults[1] >= 0:
                    self.output_monitor_device = int(defaults[1])
                target_devices = list(enumerate(devices))

            # Auto-detect Virtual Cable / AudioRelay for broadcast
            for idx, dev in target_devices:
                name = dev.get("name", "").lower()
                if dev.get("max_output_channels", 0) > 0:
                    if "cable input" in name or "virtual" in name or "line out" in name:
                        self.output_broadcast_device = idx
                        break
        except Exception as e:
            print(f"[ZeroMix] Device init warning: {e}")

    def get_device_lists(self) -> Tuple[List[Dict], List[Dict]]:
        """Returns (input_devices, output_devices) available on the host system.
        Filters for active Windows WASAPI endpoints to show only real, connected, active devices.
        """
        inputs = []
        outputs = []
        try:
            apis = sd.query_hostapis()
            wasapi_idx = next((i for i, a in enumerate(apis) if "WASAPI" in a["name"].upper()), None)

            devices = sd.query_devices()
            target_devices = []
            if wasapi_idx is not None:
                target_devices = [(i, d) for i, d in enumerate(devices) if d.get("hostapi") == wasapi_idx]
            if not target_devices:
                target_devices = list(enumerate(devices))

            seen_in_names = set()
            seen_out_names = set()

            for idx, dev in target_devices:
                raw_name = dev.get("name", f"Device {idx}")
                clean_name = raw_name.encode("ascii", "replace").decode("ascii").strip()

                # Filter out system driver proxies / broken endpoints
                clean_lower = clean_name.lower()
                if "@system32" in clean_lower or "sound mapper" in clean_lower or "primary sound" in clean_lower:
                    continue

                in_ch = dev.get("max_input_channels", 0)
                out_ch = dev.get("max_output_channels", 0)

                if in_ch > 0 and clean_name not in seen_in_names:
                    seen_in_names.add(clean_name)
                    inputs.append({"index": idx, "name": clean_name, "channels": in_ch})
                if out_ch > 0 and clean_name not in seen_out_names:
                    seen_out_names.add(clean_name)
                    outputs.append({"index": idx, "name": clean_name, "channels": out_ch})
        except Exception as e:
            print(f"[ZeroMix] Error querying devices: {e}")
        return inputs, outputs

    def _monitor_out_callback(self, outdata, frames, time_info, status):
        if getattr(self, "mute_monitor", False):
            outdata.fill(0)
            return
        with self._out_lock:
            if self._monitor_queue:
                chunk = self._monitor_queue.popleft()
                if len(chunk) == frames:
                    outdata[:] = chunk
                    return
                elif len(chunk) > frames:
                    outdata[:] = chunk[:frames]
                    self._monitor_queue.appendleft(chunk[frames:])
                    return
        outdata.fill(0)

    def _broadcast_out_callback(self, outdata, frames, time_info, status):
        with self._out_lock:
            if self._broadcast_queue:
                chunk = self._broadcast_queue.popleft()
                if len(chunk) == frames:
                    outdata[:] = chunk
                    return
                elif len(chunk) > frames:
                    outdata[:] = chunk[:frames]
                    self._broadcast_queue.appendleft(chunk[frames:])
                    return
        outdata.fill(0)

    def start(self) -> bool:
        if self.is_running:
            return True

        try:
            # Setup output monitor stream (Headphones) using non-blocking low-latency callback
            if self.output_monitor_device is not None:
                try:
                    dev_info = sd.query_devices(self.output_monitor_device)
                    m_sr = int(dev_info.get("default_samplerate", self.sample_rate))
                    if m_sr <= 0:
                        m_sr = self.sample_rate
                    self._out_monitor_stream = sd.OutputStream(
                        samplerate=m_sr,
                        blocksize=self.block_size,
                        device=self.output_monitor_device,
                        channels=2,
                        dtype='float32',
                        latency='low',
                        callback=self._monitor_out_callback
                    )
                    self._out_monitor_stream.start()
                except Exception as e:
                    print(f"[ZeroMix] Warning: Monitor output stream failed: {e}")
                    self._out_monitor_stream = None

            # Setup output broadcast stream (Virtual Cable / Discord Mic)
            if self.output_broadcast_device is not None:
                try:
                    dev_info = sd.query_devices(self.output_broadcast_device)
                    b_sr = int(dev_info.get("default_samplerate", self.sample_rate))
                    if b_sr <= 0:
                        b_sr = self.sample_rate
                    ch = min(2, max(1, dev_info.get("max_output_channels", 2)))
                    self._out_broadcast_stream = sd.OutputStream(
                        samplerate=b_sr,
                        blocksize=self.block_size,
                        device=self.output_broadcast_device,
                        channels=ch,
                        dtype='float32',
                        latency='low',
                        callback=self._broadcast_out_callback
                    )
                    self._out_broadcast_stream.start()
                except Exception:
                    self._out_broadcast_stream = None

            # Setup input mic stream
            if self.input_mic_device is not None:
                try:
                    dev_info = sd.query_devices(self.input_mic_device)
                    in_sr = int(dev_info.get("default_samplerate", self.sample_rate))
                    if in_sr <= 0:
                        in_sr = self.sample_rate
                    self._in_stream = sd.InputStream(
                        samplerate=in_sr,
                        blocksize=self.block_size,
                        device=self.input_mic_device,
                        channels=1,
                        dtype='float32',
                        latency='low',
                        callback=self._audio_callback
                    )
                    self._in_stream.start()
                except Exception as e:
                    print(f"[ZeroMix] Warning: Input mic stream failed: {e}")
                    self._in_stream = None

            if self._in_stream is None:
                # If no mic, still run a clock generator thread to mix music & soundboard
                self._clock_thread = threading.Thread(target=self._clock_loop, daemon=True)
                self._clock_thread.start()

            self.is_running = True
            return True
        except Exception as e:
            print(f"[ZeroMix] Start failed: {e}")
            self.stop()
            return False

    def stop(self) -> bool:
        self.is_running = False
        with self._out_lock:
            self._monitor_queue.clear()
            self._broadcast_queue.clear()

        try:
            if self._in_stream:
                self._in_stream.stop()
                self._in_stream.close()
                self._in_stream = None
        except Exception:
            pass

        try:
            if self._out_monitor_stream:
                self._out_monitor_stream.stop()
                self._out_monitor_stream.close()
                self._out_monitor_stream = None
        except Exception:
            pass

        try:
            if self._out_broadcast_stream:
                self._out_broadcast_stream.stop()
                self._out_broadcast_stream.close()
                self._out_broadcast_stream = None
        except Exception:
            pass

        self.levels_updated.emit(0.0, 0.0, 0.0)
        return True

    def _clock_loop(self):
        """Runs mixing loop when no input mic device is active."""
        empty_in = np.zeros((self.block_size, 1), dtype=np.float32)
        interval = self.block_size / float(self.sample_rate)
        while self.is_running and self._in_stream is None:
            t0 = time.time()
            self._process_mix(empty_in)
            elapsed = time.time() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice callback triggered for every audio block."""
        if not self.is_running:
            return
        self._process_mix(indata)

    def _process_mix(self, mic_chunk: np.ndarray):
        frames = len(mic_chunk)

        # 1. Process Microphone Channel
        # mic_chunk is shape (frames, 1)
        mic_mono = mic_chunk[:, 0]
        peak_mic = float(np.max(np.abs(mic_mono))) if len(mic_mono) > 0 else 0.0

        # Calculate dB
        db_mic = 20.0 * math.log10(peak_mic + 1e-6)

        # Ducking Logic
        if self.ducking_enabled and not self.mute_mic:
            if db_mic >= self.voice_threshold_db:
                target_duck = self.ducking_level
                is_ducking = True
            else:
                target_duck = 1.0
                is_ducking = False

            # Smooth exponential attack/release
            speed = self.duck_attack if target_duck < self._current_duck_factor else self.duck_release
            self._current_duck_factor += (target_duck - self._current_duck_factor) * speed
            if self._is_ducking != is_ducking:
                self._is_ducking = is_ducking
                self.ducking_state_changed.emit(is_ducking, self._current_duck_factor)
        else:
            self._current_duck_factor = 1.0
            if self._is_ducking:
                self._is_ducking = False
                self.ducking_state_changed.emit(False, 1.0)

        # Apply Real-Time Voice FX
        processed_mono = self.voice_fx.process(mic_mono)

        # Scale mic audio
        effective_mic = 0.0 if self.mute_mic else self.vol_mic
        mic_stereo = np.column_stack((processed_mono * effective_mic, processed_mono * effective_mic))

        # 2. Process Music / Phone Cast Channel
        music_stereo = np.zeros((frames, 2), dtype=np.float32)
        has_phone_audio = False

        with self._lock:
            # 2a. Priority: Incoming Live Phone Cast Audio from ZeroCast
            needed_bytes = frames * 4
            target_prebuffer = int(self.sample_rate * 4 * 0.080)  # 80ms jitter absorption
            if self._phone_prebuffering:
                if len(self._phone_buffer) >= target_prebuffer:
                    self._phone_prebuffering = False

            if not self._phone_prebuffering:
                if len(self._phone_buffer) >= needed_bytes:
                    raw_bytes = bytes(self._phone_buffer[:needed_bytes])
                    del self._phone_buffer[:needed_bytes]
                    int16_arr = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)
                    music_stereo[:] = int16_arr.astype(np.float32) / 32768.0
                    has_phone_audio = True
                elif len(self._phone_buffer) == 0:
                    self._phone_prebuffering = True

            # 2b. Secondary: Local Music File Playback
            if not has_phone_audio and self._is_music_playing and self._music_data is not None:
                rem = len(self._music_data) - self._music_idx
                take = min(frames, rem)
                if take > 0:
                    chunk = self._music_data[self._music_idx:self._music_idx + take]
                    music_stereo[:take] = chunk
                    self._music_idx += take
                if self._music_idx >= len(self._music_data):
                    self._is_music_playing = False
                    self.playback_state_changed.emit(False, self._current_track_name)

        # Check phone stream indicator
        now_t = time.time()
        is_phone_active = (now_t - self._last_phone_audio_time) < 0.6
        if self._phone_streaming_active != is_phone_active:
            self._phone_streaming_active = is_phone_active
            self.phone_stream_status_changed.emit(is_phone_active)

        effective_music = 0.0 if self.mute_music else (self.vol_music * self._current_duck_factor)
        music_stereo *= effective_music
        peak_music = float(np.max(np.abs(music_stereo))) if len(music_stereo) > 0 else 0.0

        # 3. Process Soundboard Channel
        sound_stereo = np.zeros((frames, 2), dtype=np.float32)
        with self._lock:
            if self._is_sound_playing and self._sound_data is not None:
                rem = len(self._sound_data) - self._sound_idx
                take = min(frames, rem)
                if take > 0:
                    chunk = self._sound_data[self._sound_idx:self._sound_idx + take]
                    sound_stereo[:take] = chunk
                    self._sound_idx += take
                if self._sound_idx >= len(self._sound_data):
                    self._is_sound_playing = False
                    self.sound_playback_changed.emit(self._current_sound_name, False)

        effective_sound = 0.0 if self.mute_soundboard else self.vol_soundboard
        sound_stereo *= effective_sound
        peak_sound = float(np.max(np.abs(sound_stereo))) if len(sound_stereo) > 0 else 0.0

        # 4. Generate Master Mixes
        # Broadcast Mix (Sent to Discord / Virtual Mic): Mic + Music + Soundboard
        broadcast_mix = mic_stereo + music_stereo + sound_stereo
        np.clip(broadcast_mix, -1.0, 1.0, out=broadcast_mix)

        # Monitor Mix (User's Headphones):
        monitor_mic_chunk = mic_stereo if self.monitor_mic else np.zeros_like(mic_stereo)
        monitor_music_chunk = music_stereo if self.monitor_music else np.zeros_like(music_stereo)
        monitor_sound_chunk = sound_stereo if self.monitor_soundboard else np.zeros_like(sound_stereo)
        monitor_mix = monitor_mic_chunk + monitor_music_chunk + monitor_sound_chunk
        np.clip(monitor_mix, -1.0, 1.0, out=monitor_mix)

        # Push to output ring queues for callback streams
        with self._out_lock:
            self._monitor_queue.append(monitor_mix.copy())
            self._broadcast_queue.append(broadcast_mix.copy())

        # Update VU meter levels with gentle decay
        self._peak_mic = max(peak_mic, self._peak_mic * 0.85)
        self._peak_music = max(peak_music, self._peak_music * 0.85)
        self._peak_sound = max(peak_sound, self._peak_sound * 0.85)

        self.levels_updated.emit(
            min(1.0, self._peak_mic),
            min(1.0, self._peak_music),
            min(1.0, self._peak_sound)
        )

    def write_phone_pcm(self, pcm_data: bytes):
        """Receives live 16-bit stereo PCM audio streamed from Android phone via ZeroCast."""
        if not self.is_running or not pcm_data:
            return
        with self._lock:
            self._phone_buffer.extend(pcm_data)
            # 150ms backlog cap prevents runaway latency while absorbing Wi-Fi jitter seamlessly
            max_bytes = int(self.sample_rate * 4 * 0.150)
            if len(self._phone_buffer) > max_bytes:
                excess = len(self._phone_buffer) - max_bytes
                excess = (excess // 4) * 4
                del self._phone_buffer[:excess]
            self._last_phone_audio_time = time.time()

    # Audio file decoding using PyAV
    def load_audio(self, file_path: str) -> Optional[np.ndarray]:
        """Decodes an MP3/WAV/FLAC file into float32 stereo numpy array at self.sample_rate."""
        if not os.path.exists(file_path):
            return None
        try:
            container = av.open(file_path)
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format='fltp', layout='stereo', rate=self.sample_rate)

            frames = []
            for packet in container.demux(stream):
                for frame in packet.decode():
                    for resampled in resampler.resample(frame):
                        frames.append(resampled.to_ndarray())

            if frames:
                # Concatenate channels along time dimension
                stacked = np.concatenate(frames, axis=1).T  # Shape: (samples, 2)
                return stacked.astype(np.float32)
        except Exception as e:
            print(f"[ZeroMix] Failed to decode audio '{file_path}': {e}")
        return None

    # Music Channel Controls
    def play_music_file(self, file_path: str):
        data = self.load_audio(file_path)
        if data is not None:
            with self._lock:
                self._music_data = data
                self._music_idx = 0
                self._is_music_playing = True
                self._current_track_name = os.path.basename(file_path)
            self.playback_state_changed.emit(True, self._current_track_name)

    def pause_music(self):
        with self._lock:
            self._is_music_playing = False
        self.playback_state_changed.emit(False, self._current_track_name)

    def resume_music(self):
        with self._lock:
            if self._music_data is not None:
                self._is_music_playing = True
        self.playback_state_changed.emit(True, self._current_track_name)

    def stop_music(self):
        with self._lock:
            self._is_music_playing = False
            self._music_idx = 0
        self.playback_state_changed.emit(False, "")

    # Soundboard Management
    def _load_soundboard_library(self):
        self.soundboard_items.clear()
        if not os.path.exists(self.soundboard_dir):
            return
        files = sorted(os.listdir(self.soundboard_dir))
        for idx, f in enumerate(files):
            if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                path = os.path.join(self.soundboard_dir, f)
                base_name, _ = os.path.splitext(f)
                self.soundboard_items.append({
                    "id": f"snd_{idx}",
                    "name": base_name.replace("_", " "),
                    "filename": f,
                    "path": path
                })

    def add_sound_file(self, source_path: str) -> Optional[Dict]:
        """Copies an audio file to soundboard directory and re-indexes."""
        if not os.path.exists(source_path):
            return None
        import shutil
        fname = os.path.basename(source_path)
        dest_path = os.path.join(self.soundboard_dir, fname)
        shutil.copy2(source_path, dest_path)
        self._load_soundboard_library()
        self.soundboard_list_changed.emit()
        for item in self.soundboard_items:
            if item["filename"] == fname:
                return item
        return None

    def remove_sound(self, sound_id: str) -> bool:
        for item in list(self.soundboard_items):
            if item["id"] == sound_id:
                try:
                    if os.path.exists(item["path"]):
                        os.remove(item["path"])
                except Exception:
                    pass
                self._load_soundboard_library()
                self.soundboard_list_changed.emit()
                return True
        return False

    def play_sound(self, sound_id_or_name: str):
        target = None
        for item in self.soundboard_items:
            if item["id"] == sound_id_or_name or item["name"] == sound_id_or_name:
                target = item
                break
        if not target:
            return

        data = self.load_audio(target["path"])
        if data is not None:
            with self._lock:
                self._sound_data = data
                self._sound_idx = 0
                self._is_sound_playing = True
                self._current_sound_name = target["name"]
            self.sound_playback_changed.emit(target["name"], True)

    def stop_sound(self):
        with self._lock:
            self._is_sound_playing = False
            self._sound_idx = 0
        self.sound_playback_changed.emit("", False)

    # Configuration Setters
    def set_devices(self, mic_idx: Optional[int], monitor_idx: Optional[int], broadcast_idx: Optional[int]):
        mic_idx = None if mic_idx is not None and mic_idx < 0 else mic_idx
        monitor_idx = None if monitor_idx is not None and monitor_idx < 0 else monitor_idx
        broadcast_idx = None if broadcast_idx is not None and broadcast_idx < 0 else broadcast_idx
        was_running = self.is_running
        if was_running:
            self.stop()
        self.input_mic_device = mic_idx
        self.output_monitor_device = monitor_idx
        self.output_broadcast_device = broadcast_idx
        if was_running:
            self.start()

    def set_monitor_mute(self, muted: bool):
        self.mute_monitor = muted
        self.state_changed.emit()

    def set_mic_volume(self, pct: int):
        self.vol_mic = max(0.0, min(1.5, pct / 100.0))
        self.volume_changed.emit("mic", pct)
        self.state_changed.emit()

    def set_music_volume(self, pct: int):
        self.vol_music = max(0.0, min(1.0, pct / 100.0))
        self.volume_changed.emit("music", pct)
        self.state_changed.emit()

    def set_soundboard_volume(self, pct: int):
        self.vol_soundboard = max(0.0, min(1.0, pct / 100.0))
        self.volume_changed.emit("soundboard", pct)
        self.state_changed.emit()

    def set_mic_mute(self, muted: bool):
        self.mute_mic = muted
        self.mute_changed.emit("mic", muted)
        self.state_changed.emit()

    def set_music_mute(self, muted: bool):
        self.mute_music = muted
        self.mute_changed.emit("music", muted)
        self.state_changed.emit()

    def set_soundboard_mute(self, muted: bool):
        self.mute_soundboard = muted
        self.mute_changed.emit("soundboard", muted)
        self.state_changed.emit()

    def set_voice_effect(self, effect_id: str):
        """Sets real-time voice changer effect ('OFF', 'RADIO', 'DEEP', 'CHIPMUNK', 'ROBOT', 'ECHO')."""
        self.voice_fx.set_effect(effect_id)
        current = self.voice_fx.get_current_effect()
        self.voice_effect_changed.emit(current)
        self.state_changed.emit()

    def get_voice_effect(self) -> str:
        return self.voice_fx.get_current_effect()

    def set_monitor_mic(self, enabled: bool):
        self.monitor_mic = enabled
        self.state_changed.emit()

    def set_ducking_config(self, enabled: bool, duck_level_pct: int, threshold_db: float = -32.0):
        self.ducking_enabled = enabled
        self.ducking_level = max(0.0, min(0.8, duck_level_pct / 100.0))
        self.voice_threshold_db = threshold_db
        self.ducking_config_changed.emit(enabled, duck_level_pct)
        self.state_changed.emit()
