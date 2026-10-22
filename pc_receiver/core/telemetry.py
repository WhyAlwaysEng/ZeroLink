"""ZeroCast Real-Time Performance Telemetry Calculator
Tracks FPS, bitrate (Mbps), frame size (KB), and latency (ms).
"""

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class TelemetryStats:
    fps: float = 0.0
    bitrate_mbps: float = 0.0
    latency_ms: float = 0.0
    last_frame_kb: float = 0.0
    total_frames: int = 0
    dropped_frames: int = 0


class TelemetryTracker:
    def __init__(self, window_seconds: float = 1.0):
        self.window_seconds = window_seconds
        self._frame_times = deque()      # timestamps of recent frames
        self._frame_bytes = deque()      # byte sizes of recent frames
        self._latencies = deque(maxlen=30)
        self._smoothed_fps = 0.0
        self.total_frames = 0
        self.dropped_frames = 0
        self.last_frame_kb = 0.0

    def record_frame(self, frame_bytes: int, sender_timestamp_us: int):
        now = time.time()
        self.total_frames += 1
        self.last_frame_kb = frame_bytes / 1024.0

        # Calculate latency in ms (sender clock vs local clock; fallback if out of sync)
        if sender_timestamp_us > 0:
            now_us = int(now * 1_000_000)
            diff_ms = (now_us - sender_timestamp_us) / 1000.0
            # If clocks are roughly aligned (0 to 10000ms), store latency
            if 0 <= diff_ms < 10000:
                self._latencies.append(diff_ms)

        self._frame_times.append(now)
        self._frame_bytes.append(frame_bytes)
        self._purge_old_entries(now)

    def _purge_old_entries(self, now: float):
        cutoff = now - self.window_seconds
        while self._frame_times and self._frame_times[0] < cutoff:
            self._frame_times.popleft()
            self._frame_bytes.popleft()

    def get_stats(self) -> TelemetryStats:
        now = time.time()
        self._purge_old_entries(now)

        count = len(self._frame_times)
        raw_fps = count / self.window_seconds if count > 0 else 0.0
        if self._smoothed_fps == 0.0:
            self._smoothed_fps = raw_fps
        else:
            self._smoothed_fps = 0.7 * self._smoothed_fps + 0.3 * raw_fps

        total_bytes = sum(self._frame_bytes)
        bitrate_mbps = (total_bytes * 8) / (self.window_seconds * 1_000_000)

        avg_latency = (sum(self._latencies) / len(self._latencies)) if self._latencies else 0.0

        return TelemetryStats(
            fps=round(self._smoothed_fps, 1),
            bitrate_mbps=round(bitrate_mbps, 2),
            latency_ms=round(avg_latency, 1),
            last_frame_kb=round(self.last_frame_kb, 1),
            total_frames=self.total_frames,
            dropped_frames=self.dropped_frames
        )

    def reset(self):
        self._frame_times.clear()
        self._frame_bytes.clear()
        self._latencies.clear()
        self._smoothed_fps = 0.0
        self.total_frames = 0
        self.dropped_frames = 0
        self.last_frame_kb = 0.0
