"""ZeroLink Audio FX - Real-Time Voice Changer & DSP Modulator
Low-latency real-time voice processing in NumPy for ZeroMix.
Includes: Walkie-Talkie Radio, Deep Broadcast, Helium Chipmunk, Cyborg Robot, and Stadium Echo.
"""

import math
import numpy as np
from typing import List, Dict


class GranularPitchShifter:
    """Vectorized real-time granular pitch shifter using dual circular delay heads and Hann crossfading."""

    def __init__(self, sample_rate: int = 48000, grain_size_ms: float = 45.0):
        self.sample_rate = sample_rate
        self.grain_size = max(64, int(sample_rate * grain_size_ms / 1000.0))
        self.buf_len = self.grain_size * 4
        self.buffer = np.zeros(self.buf_len, dtype=np.float32)
        self.write_pos = 0
        self.phase = 0.0

    def reset(self):
        self.buffer.fill(0)
        self.write_pos = 0
        self.phase = 0.0

    def process(self, chunk: np.ndarray, semitones: float) -> np.ndarray:
        if abs(semitones) < 0.1:
            return chunk

        ratio = 2.0 ** (semitones / 12.0)
        N = len(chunk)
        G = self.grain_size
        buf_len = self.buf_len

        delta = 1.0 - ratio
        phases = (self.phase + delta * np.arange(N, dtype=np.float32)) % G
        phases2 = (phases + G * 0.5) % G
        self.phase = float((self.phase + delta * N) % G)

        wp = (self.write_pos + np.arange(N)) % buf_len
        self.buffer[wp] = chunk
        self.write_pos = int((self.write_pos + N) % buf_len)

        r1 = (wp - phases.astype(np.int32)) % buf_len
        r2 = (wp - phases2.astype(np.int32)) % buf_len

        w = 0.5 * (1.0 - np.cos(2.0 * np.pi * phases / G))
        out = (w * self.buffer[r1] + (1.0 - w) * self.buffer[r2]).astype(np.float32)
        return out


class VoiceFxProcessor:
    """Real-time Voice Effects Processor for ZeroMix."""

    AVAILABLE_EFFECTS = [
        {"id": "OFF", "name": "Normal Voice", "icon": "🎙️", "desc": "Clean natural microphone audio"},
        {"id": "RADIO", "name": "Walkie-Talkie", "icon": "📻", "desc": "Military tactical radio with bandpass & warmth"},
        {"id": "DEEP", "name": "Deep Broadcast", "icon": "🦁", "desc": "Deep resonant radio announcer / monster bass"},
        {"id": "CHIPMUNK", "name": "Helium Chipmunk", "icon": "🐿️", "desc": "High pitch helium fun banter"},
        {"id": "ROBOT", "name": "Cyborg Robot", "icon": "🤖", "desc": "Sci-Fi robotic cybernetic ring modulator"},
        {"id": "ECHO", "name": "Stadium Echo", "icon": "🏟️", "desc": "Concert stadium acoustic delay"},
    ]

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.current_effect = "OFF"

        # Pitch shifter
        self.pitch_shifter = GranularPitchShifter(sample_rate=sample_rate, grain_size_ms=45.0)

        # Robot modulator carrier phase
        self._robot_phase = 0.0

        # Echo circular buffer (up to 500ms)
        self.echo_buf_len = int(sample_rate * 0.5)
        self.echo_buffer = np.zeros(self.echo_buf_len, dtype=np.float32)
        self.echo_write_pos = 0

        # Radio filter state
        self._radio_hp_prev = 0.0
        self._radio_lp_prev = 0.0

    def set_effect(self, effect_id: str):
        effect_id = effect_id.upper().strip()
        valid_ids = [e["id"] for e in self.AVAILABLE_EFFECTS]
        if effect_id in valid_ids:
            self.current_effect = effect_id
        else:
            self.current_effect = "OFF"

    def get_current_effect(self) -> str:
        return self.current_effect

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """Processes a 1D mono float32 chunk. Returns processed 1D float32 chunk."""
        if self.current_effect == "OFF" or len(chunk) == 0:
            return chunk

        if self.current_effect == "RADIO":
            return self._apply_walkie_talkie(chunk)
        elif self.current_effect == "DEEP":
            return self._apply_deep_broadcast(chunk)
        elif self.current_effect == "CHIPMUNK":
            return self._apply_helium_chipmunk(chunk)
        elif self.current_effect == "ROBOT":
            return self._apply_robot_cyborg(chunk)
        elif self.current_effect == "ECHO":
            return self._apply_stadium_echo(chunk)

        return chunk

    def _apply_walkie_talkie(self, chunk: np.ndarray) -> np.ndarray:
        """Military Walkie-Talkie: Bandpass 400Hz-3200Hz, soft saturation, and gentle analog static."""
        dt = 1.0 / self.sample_rate
        N = len(chunk)

        # 1. High-pass filter ~400Hz
        rc_hp = 1.0 / (2.0 * math.pi * 400.0)
        alpha_hp = rc_hp / (rc_hp + dt)
        hp = np.zeros_like(chunk)
        prev_in = 0.0
        prev_out = self._radio_hp_prev
        for i in range(N):
            cur_in = chunk[i]
            prev_out = alpha_hp * (prev_out + cur_in - prev_in)
            prev_in = cur_in
            hp[i] = prev_out
        self._radio_hp_prev = prev_out

        # 2. Low-pass filter ~3200Hz
        rc_lp = 1.0 / (2.0 * math.pi * 3200.0)
        alpha_lp = dt / (rc_lp + dt)
        lp = np.zeros_like(hp)
        prev_lp = self._radio_lp_prev
        for i in range(N):
            prev_lp += alpha_lp * (hp[i] - prev_lp)
            lp[i] = prev_lp
        self._radio_lp_prev = prev_lp

        # 3. Warm saturation & drive
        driven = np.tanh(lp * 2.8) * 0.85

        # 4. Subtle radio background hiss
        noise = np.random.normal(0.0, 0.0015, N).astype(np.float32)
        return (driven + noise).astype(np.float32)

    def _apply_deep_broadcast(self, chunk: np.ndarray) -> np.ndarray:
        """Deep Radio Host: -4.0 semitones pitch shift with warm low-frequency punch."""
        shifted = self.pitch_shifter.process(chunk, semitones=-4.0)
        # Boost low presence
        return (shifted * 1.15).astype(np.float32)

    def _apply_helium_chipmunk(self, chunk: np.ndarray) -> np.ndarray:
        """Helium Chipmunk: +5.0 semitones pitch shift."""
        return self.pitch_shifter.process(chunk, semitones=+5.0)

    def _apply_robot_cyborg(self, chunk: np.ndarray) -> np.ndarray:
        """Robotic Ring Modulator with 65Hz carrier wave and comb metallic resonance."""
        N = len(chunk)
        dt = 1.0 / self.sample_rate
        t = self._robot_phase + np.arange(N, dtype=np.float32) * dt
        self._robot_phase = float((self._robot_phase + N * dt) % 1.0)

        # 65 Hz Sine Carrier
        carrier = np.sin(2.0 * np.pi * 65.0 * t).astype(np.float32)
        modulated = chunk * carrier

        # Blend ring modulation with metallic resonance
        return (0.75 * modulated + 0.25 * chunk).astype(np.float32)

    def _apply_stadium_echo(self, chunk: np.ndarray) -> np.ndarray:
        """Concert Stadium Echo: 180ms delay line with 0.4 feedback."""
        N = len(chunk)
        delay_samples = int(self.sample_rate * 0.18)
        buf_len = self.echo_buf_len
        out = np.zeros_like(chunk)

        wp = (self.echo_write_pos + np.arange(N)) % buf_len
        rp = (wp - delay_samples) % buf_len

        delayed = self.echo_buffer[rp]
        mixed = chunk + delayed * 0.4
        self.echo_buffer[wp] = mixed
        self.echo_write_pos = int((self.echo_write_pos + N) % buf_len)

        out[:] = chunk * 0.8 + delayed * 0.45
        return out
