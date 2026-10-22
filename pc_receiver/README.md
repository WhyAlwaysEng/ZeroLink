# 🖥️ ZeroLink PC Receiver (Hub & Desktop Engine)

The desktop receiver application for **ZeroLink**, written in Python 3.10+ using **PyQt6**, **PyAV (FFmpeg C-bindings)**, and **pyvirtualcam**. Features a modular hub architecture supporting multiple tools (ZeroCast, ZeroDrop, ZeroClip, ZeroPad).

---

## ⚡ Features

- **H.264 Hardware Decoding**: Ultra-fast, zero-copy decode via PyAV directly to `QImage` RGB24.
- **Studio Jitter-Buffered Audio**: Plays 48,000 Hz 16-bit Stereo PCM with a dedicated ~200ms Jitter Buffer and zero-sample-loss alignment.
- **Audio Output Device Routing**: Select your preferred sound device (Headphones, Gaming Headset, External Monitors, or Speakers) directly from the header dropdown.
- **Virtual Camera Output**: Feeds the real-time mobile screen or phone camera directly into `OBS Virtual Camera` for seamless use in **Discord, Zoom, Google Meet, and OBS Studio**.
- **Auto ADB Tunneling**: Automatically discovers Android SDK `adb.exe` on Windows (even if not in system `PATH`), and automatically establishes `adb reverse tcp:8888 tcp:8888` for zero-configuration USB streaming.
- **Reverse Mouse & Keyboard Control**:
  - Left-click & drag on the mirror canvas injects taps and swipes onto the phone.
  - Typing on your PC keyboard sends key events (Backspace, Enter, Space, Tab, Esc) and characters directly to Android.
- **Telemetry HUD**: Real-time FPS, Bitrate (Mbps), Latency (ms), Resolution, and Frame Size.
- **One-Click Snapshot**: Captures uncompressed still frames to `Pictures/ZeroCast`.
- **Fullscreen Mode**: Toggle via `F11` or double-clicking the viewport canvas.

---

## 📦 Requirements & Prerequisites

- **OS**: Windows 10 / 11 (64-bit)
- **Python**: Python 3.10, 3.11, 3.12, or 3.13 (64-bit)
- **Optional for Virtual Camera**: [OBS Studio](https://obsproject.com/) installed (provides the Windows OBS Virtual Camera driver).

---

## 🚀 Installation & Running

1. **Open PowerShell / Command Prompt** in this directory:
   ```powershell
   cd pc_receiver
   ```

2. **(Recommended) Create a Virtual Environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Launch the Receiver**:
   ```powershell
   python main.py
   ```

---

## 🎥 Using Virtual Camera in Discord / Zoom / Teams

1. Connect your Android phone and start streaming (Screen or Rear/Front Camera).
2. Click **`[ 🎥 V-Cam: OFF ]`** in the top ribbon -> It will turn glowing green **`[ 🎥 V-Cam: ON ]`**.
3. Open **Discord**, **Zoom**, or **Google Meet**:
   - Go to **Settings** ➔ **Voice & Video** ➔ **Camera**.
   - Select **`OBS Virtual Camera`** from the camera dropdown list.
4. Your Android camera or screen is now broadcasting as your high-definition 60 FPS webcam!

---

## 🎧 Selecting Audio Output Devices

- In the top-right toolbar next to the volume slider, click the **Audio Output Dropdown**.
- ZeroCast automatically detects all plugged-in audio hardware (e.g. `Speakers (HyperX Cloud Stinger Core + 7.1)`, `Headphones (TV speaker)`).
- Click any device to switch audio output instantly without interrupting the stream.

---

## 📁 File Structure

```
pc_receiver/
├── core/
│   ├── protocol.py          # 16-Byte Binary Header Protocol
│   ├── server.py            # Async TCP Server (Video, Audio, Control backchannel)
│   ├── h264_decoder.py      # PyAV H.264 Zero-Latency Decoder
│   ├── audio_player.py      # Studio Jitter-Buffered QAudioSink with Device Routing
│   ├── virtual_cam.py       # OpenCV SIMD Letterbox & pyvirtualcam Engine
│   ├── input_controller.py  # Reverse Mouse & Keyboard ADB Injector
│   ├── adb_helper.py        # Automatic ADB & Port Reverse Tunneling Manager
│   ├── discovery.py         # UDP Broadcast Beacon for LAN Auto-Discovery (Port 8889)
│   └── telemetry.py         # Smoothed FPS, Bitrate & Latency Tracker
├── ui/
│   └── main_window.py       # Modern Glassmorphic Dark Window & Canvas Viewport
├── main.py                  # PC Receiver Entry Point
├── mock_sender.py           # Standalone Simulator for Testing
└── requirements.txt         # Python Package Dependencies
```
