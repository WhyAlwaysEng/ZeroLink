# 📱 ZeroLink Android Client (Mobile Hub & Engine)

Native Android client and modular dashboard for **ZeroLink**, built with **Kotlin**, **Android SDK 35**, **MediaProjection**, **MediaCodec (Hardware GPU)**, and **AudioPlaybackCapture**. Provides a unified hub screen to launch and manage modules (**ZeroCast**, **ZeroCam**, **ZeroDisplay**, **ZeroDrop**, **ZeroClip**, **ZeroMix**, **ZeroPad**).

---

## ⚡ Features & Next-Gen Video Pipelines

### 🎥 Multi-Codec Hardware Acceleration
- **Codec Auto-Probing (`CodecProbeHelper`)**:
  - Dynamically inspects `MediaCodecList` on boot to detect hardware encoding capabilities for **H.264 (AVC)**, **H.265 (HEVC)**, and **AV1**.
  - Dynamically enables codec choices in the UI dropdown based on true device hardware capability.
- **H.264 (AVC Baseline)**:
  - Universal hardware compatibility across all Android devices.
  - Strict `AVCProfileBaseline` (no B-frames, zero lookahead latency).
  - SPS/PPS NAL sequence headers injected into every keyframe for instant sync.
- **H.265 / HEVC (Deep Hardware Tuned)**:
  - Up to 50% bandwidth efficiency compared to H.264.
  - **`KEY_COMPLEXITY = 0`**: Forces Qualcomm/MediaTek hardware encoders into fastest motion estimation mode to eliminate high-motion frame stalls.
  - **Progressive Intra-Refresh (`KEY_INTRA_REFRESH_PERIOD`)**: Spreads keyframe data smoothly across frames, eliminating periodic 400KB I-frame stutter.
  - **Sample Adaptive Offset (SAO) Bypass**: Disables heavy GPU in-loop filters (`vendor.qcom-ext-enc-caps.sao.enable = 0`).
  - **QP Clamping**: Limits Quantization Parameters between 18 and 36 to prevent sudden size fluctuations.
  - **Dynamic Bitrate Scaling (× 0.70)**: Automatically scales target bitrate to avoid network buffer bloat while delivering crystal-clear visual fidelity.
- **AV1 (AOMedia Video 1)**:
  - Modern next-gen codec support for devices equipped with AV1 hardware encoders (Snapdragon 8 Gen 3+, Dimensity 9300+, Google Tensor G4+).

### 🚀 Resilient Low-Latency Networking (`StreamSender`)
- **Fast Adaptive Bitrate (ABR)**:
  - Queue depth triggers congestion scaling early at **8 frames (~133ms at 60 FPS)** instead of waiting for full buffer saturation.
  - Bitrate immediately steps down during Wi-Fi packet drops and smoothly restores when clear.
- **Instant Keyframe Resync (`onFrameDropped`)**:
  - If network stalls force the 40-frame safety queue to drop a packet, an instantaneous sync I-frame (`requestKeyFrame()`) is automatically generated to heal the stream without visual corruption.

### 🔊 Internal Device Audio Capture
- Captures internal game and media sound directly via `AudioPlaybackCapture` (Android 10+).
- Streams raw 48,000 Hz 16-bit Stereo PCM chunks to PC with hardware jitter compensation.

### 📱 Mobile Quality-of-Life Tools
- **Dynamic Orientation Switching**: Automatically detects orientation changes (`DisplayManager.DisplayListener`) and reconfigures encoder resolution on-the-fly.
- **Floating Performance Overlay HUD**: Floats real-time CPU %, RAM %, and Battery Temp on screen; tap to collapse to a discreet dot (`●`).
- **Auto-Dim Screen Saver**: Reduces phone display brightness to 1% while streaming to keep the device cool and save battery without dimming the PC mirror.
- **UDP LAN Auto-Discovery**: Automatically broadcasts beacons on port 8889 to connect to the PC without manually typing IP addresses.

---

## 📋 Requirements

- **Minimum Android Version**: Android 10 (API 29) or higher (Required for `AudioPlaybackCapture`).
- **Target Android Version**: Android 15 (API 35).
- **Hardware**: Android device with hardware video encoding support (Qualcomm Snapdragon, MediaTek Dimensity, Exynos, Google Tensor).
- **JDK**: Java 17.
- **Gradle**: 8.10.2+.

---

## 🛠️ Building & Installing

### Command Line (Gradle & ADB)
1. Ensure your phone has **USB Debugging** enabled in Developer Options.
2. Connect your phone via USB cable or Wi-Fi ADB.
3. Open terminal in the `android_client` directory:
   ```bash
   cd android_client

   # Build debug APK
   ./gradlew assembleDebug

   # Install directly to attached device
   adb install -r app/build/outputs/apk/debug/app-debug.apk
   ```

### Android Studio
1. Open Android Studio.
2. Select **Open** and choose the `android_client/` folder.
3. Let Gradle sync dependencies.
4. Select your connected device and click **Run (Shift+F10)**.

---

## 🔒 Permissions & Privacy

ZeroLink requests only the permissions strictly required for its features:
- **`FOREGROUND_SERVICE_MEDIA_PROJECTION`**: Required to capture screen content.
- **`RECORD_AUDIO`**: Required by Android to capture internal playback audio.
- **`SYSTEM_ALERT_WINDOW`**: Optional; allows the Performance HUD to float over other apps while gaming.
- **`CAMERA`**: Optional; only accessed when using the ZeroCam module.

---

## 📁 Source Code Structure

```
android_client/
├── app/
│   ├── src/main/
│   │   ├── java/com/zerocast/
│   │   │   ├── capture/
│   │   │   │   ├── ScreenCaptureH264Manager.kt  # MediaCodec H.264 Baseline Encoder
│   │   │   │   ├── ScreenCaptureHevcManager.kt  # MediaCodec H.265 Low-Complexity Realtime Encoder
│   │   │   │   ├── ScreenCaptureManager.kt      # MJPEG Fallback
│   │   │   │   ├── AudioCaptureManager.kt       # AudioPlaybackCapture 48kHz PCM
│   │   │   │   └── CameraCaptureManager.kt      # CameraX Video Feed
│   │   │   ├── network/
│   │   │   │   ├── StreamSender.kt              # Async Socket Transmitter with Fast ABR & Resync
│   │   │   │   └── NetworkDiscovery.kt          # UDP LAN Auto-Discovery Client
│   │   │   ├── protocol/
│   │   │   │   └── PacketHeader.kt              # 16-Byte Binary Framing Header (AVC/HEVC/AV1)
│   │   │   ├── service/
│   │   │   │   ├── StreamForegroundService.kt   # Dynamic Rotation & MediaProjection Service
│   │   │   │   └── FloatingOverlayService.kt    # Floating Performance HUD (CPU/RAM/Temp)
│   │   │   ├── util/
│   │   │   │   ├── CodecProbeHelper.kt          # MediaCodecList Hardware Capability Prober
│   │   │   │   └── ZeroLinkConfig.kt            # SharedPreferences Storage Manager
│   │   │   └── ui/
│   │   │       ├── MainActivity.kt              # Hub Dashboard (Modules selector)
│   │   │       └── ZeroCastActivity.kt          # Dedicated ZeroCast stream controller
│   │   ├── res/                                 # Layouts, Drawables & Themes
│   │   └── AndroidManifest.xml
│   └── build.gradle.kts
├── gradle/
└── build.gradle.kts
```
