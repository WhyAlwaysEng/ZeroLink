# 🖥️ ZeroLink PC Receiver (Hub & Desktop Engine)

The desktop receiver application for **ZeroLink**, written in Python 3.10+ using **PyQt6**, **PyAV (FFmpeg C-bindings)**, **libdav1d (AV1 SIMD)**, and **pyvirtualcam**. Features a modular hub architecture supporting multiple integrated tools (**ZeroCast**, **ZeroCam**, **ZeroDisplay**, **ZeroDrop**, **ZeroClip**, **ZeroMix**, **ZeroPad**).

---

## ⚡ Features & Architecture

### 🎥 Next-Gen Multi-Codec Video Decoders
- **H.264 Hardware Decoder (`h264_decoder.py`)**:
  - Ultra-fast, zero-copy PyAV decode directly to `QImage` RGB24.
  - Zero-latency tuning with baseline slice threading and instant render.
- **H.265 / HEVC Low-Delay Decoder (`hevc_decoder.py`)**:
  - Multi-threaded slice decoding with `Flags.low_delay` and `Flags2.fast` arithmetic.
  - Benchmarked at > 800 FPS on PC CPU for effortless, stutter-free 1080p 60FPS playback.
- **AV1 High-Performance Decoder (`av1_decoder.py`)**:
  - Direct integration with **`libdav1d`**, the world's fastest AV1 software decoder powered by hand-crafted AVX2/NEON SIMD assembly.
  - Complete protocol isolation (`PacketHeader.TYPE_VIDEO_AV1 = 0x07`).
- **Frame Coalescing**:
  - Automatically coalesces multi-frame bursts to paint only the most recent frame, preventing Qt GUI event queue congestion during high-throughput action.

### 🎧 Studio Audio Engine with Device Routing
- **Studio Jitter-Buffered Audio (`audio_player.py`)**:
  - Plays 48,000 Hz 16-bit Stereo PCM with dynamic jitter buffer and zero-sample-loss alignment.
- **Instant Audio Output Routing**:
  - Switch playback sound between Gaming Headset, External Monitors, Headphones, or Desktop Speakers directly from the top navigation dropdown without interrupting the stream.

### 📹 Virtual Camera Integration
- Feeds the real-time mobile screen or phone camera directly into `OBS Virtual Camera` for seamless use in **Discord, Zoom, Google Meet, and OBS Studio**.

### 🔌 Intelligent Connection Manager
- **Auto ADB Tunneling (`adb_helper.py`)**:
  - Automatically detects Android SDK `adb.exe` on Windows (even if not in system `PATH`).
  - Sets up `adb reverse tcp:8888 tcp:8888` automatically for zero-configuration, rock-solid USB streaming.
- **LAN Auto-Discovery (`discovery.py`)**:
  - Listens on UDP port 8889 to auto-pair with mobile clients on the local Wi-Fi network.
- **Diagnostic Speed Test (`speedtest_server.py`)**:
  - Measures true TCP socket bandwidth, latency, and packet loss between PC and phone to recommend the optimal bitrate.

### 🖱️ Reverse Mouse & Keyboard Control
- Left-click and drag on the mirror canvas injects taps and swipes onto the phone.
- Typing on your physical PC keyboard sends characters and navigation keys (Backspace, Enter, Space, Tab, Esc) directly to Android.

---

## 📦 Requirements & Prerequisites

- **OS**: Windows 10 / 11 (64-bit)
- **Python**: Python 3.10, 3.11, 3.12, or 3.13 (64-bit)
- **Virtual Camera Support (Optional)**: [OBS Studio](https://obsproject.com/) installed (provides the Windows OBS Virtual Camera driver).

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

To compile a standalone `.exe`:
```powershell
pyinstaller ZeroLink.spec --noconfirm
```

---

## 🎥 Using Virtual Camera in Discord / Zoom / Teams

1. Connect your Android phone and start streaming in ZeroCast or ZeroCam.
2. Click **`[ ⛶ V-Cam: OFF ]`** in the top ribbon -> It will turn active **`[ ⛶ V-Cam: ON ]`**.
3. Open **Discord**, **Zoom**, or **Google Meet**:
   - Go to **Settings** ➔ **Voice & Video** ➔ **Camera**.
   - Select **`OBS Virtual Camera`** from the camera dropdown list.
4. Your Android camera or screen is now broadcasting as your high-definition 60 FPS webcam!

---

## 📁 Source Code Structure

```
pc_receiver/
├── core/
│   ├── protocol.py          # 16-Byte Binary Framing Protocol (AVC, HEVC, AV1)
│   ├── server.py            # Async TCP Server (Video, Audio, Control backchannel)
│   ├── h264_decoder.py      # PyAV H.264 Zero-Latency Decoder
│   ├── hevc_decoder.py      # PyAV H.265 Low-Delay SIMD Decoder
│   ├── av1_decoder.py       # libdav1d AV1 High-Performance SIMD Decoder
│   ├── audio_player.py      # Studio Jitter-Buffered QAudioSink with Device Routing
│   ├── audio_mixer.py       # Virtual Audio Routing & Voice FX Matrix
│   ├── virtual_cam.py       # OpenCV SIMD Letterbox & pyvirtualcam Engine
│   ├── input_controller.py  # Reverse Mouse & Keyboard ADB Injector
│   ├── adb_helper.py        # Automatic ADB & Port Reverse Tunneling Manager
│   ├── discovery.py         # UDP Broadcast Beacon for LAN Auto-Discovery (Port 8889)
│   ├── speedtest_server.py  # Network Speedtest & Diagnostics Engine
│   ├── telemetry.py         # Smoothed FPS, Bitrate & Latency Tracker
│   ├── base_module.py       # Abstract BaseModule Interface
│   └── module_manager.py    # Modular Suite Registry & Lifecycle Coordinator
├── modules/
│   ├── zerocast/            # Ultra-low latency screen & internal audio mirroring
│   ├── zerocam/             # Wireless mobile HD webcam studio
│   ├── zerodisplay/         # Secondary Windows monitor driver & display engine
│   ├── zerodrop/            # High-speed peer-to-peer LAN/USB file transfer
│   ├── zeroclip/            # Bidirectional cross-device clipboard sync
│   ├── zeromix/             # Virtual audio mixer & Voice FX
│   └── zeropad/             # Remote trackpad, presentation clicker & macro keys
├── ui/
│   ├── main_window.py       # Modular Hub Window & Sidebar Navigation
│   ├── dashboard_view.py    # Card-based overview with monochrome aesthetic
│   ├── connections_view.py  # USB ADB, Wi-Fi LAN & Speedtest Diagnostics UI
│   ├── speedtest_dialog.py  # Live animated speedtest modal
│   └── theme.py             # Minimal monochrome stylesheet & color constants
├── main.py                  # PC Receiver Entry Point
├── mock_sender.py           # Standalone Simulator for Automated Testing
├── ZeroLink.spec            # PyInstaller Standalone Executable Build Spec
└── requirements.txt         # Python Package Dependencies
```
