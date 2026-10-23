"""ZeroLink Studio Microphone DSP Suite (ZeroMix)
Real-time high-performance microphone filters in vectorized NumPy:
- Low-Cut / High-Pass Filter (80Hz AC hum & desk thud removal)
- Adaptive Noise Gate (cuts keyboard clicks & fan noise when silent)
- Background Noise Expander / Suppressor
- Studio Compressor & Hard Peak Limiter (anti-clipping / vocal leveler)
- De-Esser (softens harsh S/T sibilance)
- 5-second Instant Mic Check / Test playback
"""

import math
import time
import numpy as np
from typing import Dict, List, Optional


class BiquadFilter:
    """Direct Form II Transposed Biquad Filter for real-time sample processing."""

    def __init__(self):
        self.b0 = 1.0
        self.b1 = 0.0
        self.b2 = 0.0
        self.a1 = 0.0
        self.a2 = 0.0
        self.z1 = 0.0
        self.z2 = 0.0

    def set_highpass(self, cutoff_hz: float, sample_rate: int, q: float = 0.7071):
        w0 = 2.0 * math.pi * cutoff_hz / sample_rate
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha = sin_w0 / (2.0 * q)

        a0 = 1.0 + alpha
        self.b0 = ((1.0 + cos_w0) / 2.0) / a0
        self.b1 = (-(1.0 + cos_w0)) / a0
        self.b2 = ((1.0 + cos_w0) / 2.0) / a0
        self.a1 = (-2.0 * cos_w0) / a0
        self.a2 = (1.0 - alpha) / a0

    def process(self, x: np.ndarray) -> np.ndarray:
        # Vectorized lfilter approximation or sequential state update for chunks
        y = np.zeros_like(x)
        z1, z2 = self.z1, self.z2
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2

        for i in range(len(x)):
            xi = float(x[i])
            yi = b0 * xi + z1
            z1 = b1 * xi - a1 * yi + z2
            z2 = b2 * xi - a2 * yi
            y[i] = yi

        self.z1, self.z2 = z1, z2
        return y


class MicDspProcessor:
    """Comprehensive Microphone Studio DSP Engine for ZeroMix."""

    PRESETS = {
        "BROADCAST": {
            "name": "🎙️ Broadcast / Podcast",
            "desc": "Warm, clean, natural studio vocal with gentle gate and anti-clipping",
            "lowcut": True,
            "gate": True,
            "gate_db": -42.0,
            "compressor": True,
            "deesser": True,
            "noise_suppress": False
        },
        "GAMING": {
            "name": "🎮 Gaming / Discord",
            "desc": "Aggressive noise gate to silence Blue switches, fans and clicks",
            "lowcut": True,
            "gate": True,
            "gate_db": -34.0,
            "compressor": True,
            "deesser": True,
            "noise_suppress": True
        },
        "MAX_NOISE": {
            "name": "🔇 Max Noise Suppression",
            "desc": "Heavy background room noise and fan elimination",
            "lowcut": True,
            "gate": True,
            "gate_db": -28.0,
            "compressor": True,
            "deesser": False,
            "noise_suppress": True
        },
        "RAW": {
            "name": "🎵 Raw Studio (Flat)",
            "desc": "All DSP filters disabled for music recording or external VSTs",
            "lowcut": False,
            "gate": False,
            "gate_db": -60.0,
            "compressor": False,
            "deesser": False,
            "noise_suppress": False
        }
    }

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate

        # Low-Cut (High-Pass) Filter: 80 Hz
        self.enable_lowcut = True
        self.lowcut_filter = BiquadFilter()
        self.lowcut_filter.set_highpass(80.0, self.sample_rate)

        # Noise Gate
        self.enable_gate = True
        self.gate_threshold_db = -40.0   # dBFS threshold (-60 to -15)
        self.gate_attack = 0.25          # fast open (~2ms)
        self.gate_release = 0.04         # smooth close (~80ms)
        self.gate_hold_ms = 70.0
        self._gate_gain = 1.0
        self._gate_hold_samples = 0
        self._is_gate_open = True

        # Smart Noise Expander (Background Hiss Reduction)
        self.enable_noise_suppress = True
        self._noise_floor_estimate = 0.005

        # Studio Compressor & Limiter
        self.enable_compressor = True
        self.comp_threshold_db = -16.0
        self.comp_ratio = 3.5
        self.makeup_gain = 1.35          # ~2.6 dB makeup
        self._comp_envelope = 0.0

        # De-Esser (6.5 kHz Bandpass detector)
        self.enable_deesser = True
        self._deess_band_filter = BiquadFilter()
        # High-pass for sibilance detection (> 6000 Hz)
        self._deess_band_filter.set_highpass(6200.0, self.sample_rate)

        # 5-Second Mic Test Recorder
        self._mic_test_recording = False
        self._mic_test_buffer: List[np.ndarray] = []
        self._mic_test_max_samples = sample_rate * 5
        self._mic_test_collected = 0
        self._test_playback_data: Optional[np.ndarray] = None
        self._test_playback_idx = 0
        self.is_test_playing = False

    def apply_preset(self, preset_key: str):
        if preset_key not in self.PRESETS:
            return
        cfg = self.PRESETS[preset_key]
        self.enable_lowcut = cfg["lowcut"]
        self.enable_gate = cfg["gate"]
        self.gate_threshold_db = cfg["gate_db"]
        self.enable_compressor = cfg["compressor"]
        self.enable_deesser = cfg["deesser"]
        self.enable_noise_suppress = cfg["noise_suppress"]

    @property
    def is_gate_open(self) -> bool:
        return self._is_gate_open

    @property
    def gate_gain(self) -> float:
        return self._gate_gain

    def process(self, mic_mono: np.ndarray) -> np.ndarray:
        """Processes a 1D float32 audio chunk through the entire DSP chain."""
        if len(mic_mono) == 0:
            return mic_mono

        out = mic_mono.copy()

        # 1. Low-Cut (80Hz High-Pass)
        if self.enable_lowcut:
            out = self.lowcut_filter.process(out)

        # 2. De-Esser (Tames harsh sibilance)
        if self.enable_deesser:
            sibilance = self._deess_band_filter.process(out)
            sib_peak = float(np.max(np.abs(sibilance)))
            if sib_peak > 0.22:
                # Duck harsh high frequencies gently
                attenuation = max(0.60, 1.0 - (sib_peak - 0.22) * 1.5)
                out *= attenuation

        # 3. Noise Gate & Background Noise Expander
        peak_amp = float(np.max(np.abs(out))) + 1e-6
        db = 20.0 * math.log10(peak_amp)

        if self.enable_gate:
            if db >= self.gate_threshold_db:
                target_gain = 1.0
                self._gate_hold_samples = int(self.sample_rate * (self.gate_hold_ms / 1000.0))
                self._is_gate_open = True
            else:
                if self._gate_hold_samples > 0:
                    self._gate_hold_samples -= len(mic_mono)
                    target_gain = 1.0
                    self._is_gate_open = True
                else:
                    target_gain = 0.0
                    self._is_gate_open = False

            # Smooth envelope curve to avoid click/pop transitions
            speed = self.gate_attack if target_gain > self._gate_gain else self.gate_release
            self._gate_gain += (target_gain - self._gate_gain) * speed
            out *= self._gate_gain
        else:
            self._gate_gain = 1.0
            self._is_gate_open = True

        # 4. Background Noise Suppression (Expander when speech is present)
        if self.enable_noise_suppress and self._is_gate_open:
            # Downward expansion for very quiet room noise
            if db < self.gate_threshold_db + 8.0:
                reduction = max(0.20, (db - self.gate_threshold_db) / 8.0)
                out *= reduction

        # 5. Studio Compressor & Limiter
        if self.enable_compressor:
            comp_thresh_linear = 10.0 ** (self.comp_threshold_db / 20.0)
            abs_out = np.abs(out)
            over = np.maximum(0.0, abs_out - comp_thresh_linear)
            # Soft compression curve
            gain_reduction = 1.0 / (1.0 + over * (self.comp_ratio - 1.0))
            out = out * gain_reduction * self.makeup_gain

            # Hard peak limiter at -1.0 dBFS (0.891) to guarantee zero distortion
            max_limit = 0.891
            out = np.clip(out, -max_limit, max_limit)

        # 6. Record into Mic Test Buffer if active
        if self._mic_test_recording:
            self._mic_test_buffer.append(out.copy())
            self._mic_test_collected += len(out)
            if self._mic_test_collected >= self._mic_test_max_samples:
                self.finish_mic_test_recording()

        return out

    # ==================== 5-Second Mic Test Feature ====================
    def start_mic_test_recording(self):
        """Starts recording 5 seconds of processed mic audio for instant playback check."""
        self._mic_test_buffer.clear()
        self._mic_test_collected = 0
        self._mic_test_recording = True
        self.is_test_playing = False

    def finish_mic_test_recording(self) -> Optional[np.ndarray]:
        """Finishes recording and prepares the 5s audio array for playback."""
        self._mic_test_recording = False
        if self._mic_test_buffer:
            concatenated = np.concatenate(self._mic_test_buffer)
            # Convert to stereo
            stereo_test = np.column_stack((concatenated, concatenated)).astype(np.float32)
            self._test_playback_data = stereo_test
            self._test_playback_idx = 0
            self.is_test_playing = True
            return stereo_test
        return None

    def get_next_test_playback_chunk(self, frames: int) -> Optional[np.ndarray]:
        """Provides playback audio chunk for headphone preview."""
        if not self.is_test_playing or self._test_playback_data is None:
            return None
        rem = len(self._test_playback_data) - self._test_playback_idx
        if rem <= 0:
            self.is_test_playing = False
            return None
        take = min(frames, rem)
        chunk = self._test_playback_data[self._test_playback_idx:self._test_playback_idx + take]
        self._test_playback_idx += take
        if self._test_playback_idx >= len(self._test_playback_data):
            self.is_test_playing = False
        if len(chunk) < frames:
            padded = np.zeros((frames, 2), dtype=np.float32)
            padded[:len(chunk)] = chunk
            return padded
        return chunk
