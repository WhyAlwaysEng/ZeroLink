# 📱 ZeroLink Android Client (Mobile Hub & Engine)

Native Android client and modular dashboard for **ZeroLink**, built with **Kotlin**, **Android SDK 35**, **MediaProjection**, **MediaCodec (Hardware GPU)**, and **AudioPlaybackCapture**. Offers a unified hub screen to navigate between modules (ZeroCast, ZeroDrop, ZeroClip, ZeroPad).

---

## ⚡ Features

- **MediaCodec H.264 GPU Encoding**:
  - Encodes native display directly via hardware surface (`COLOR_FormatSurface`).
  - Strict `AVCProfileBaseline` (no B-frames) for zero-buffer decode latency.
  - Prepends SPS/PPS sequence parameters to every keyframe for instant sync.
- **Dynamic Orientation Switching**:
  - Listens to `DisplayManager.DisplayListener`.
  - Automatically re-negotiates encoder dimensions on-the-fly when rotating between Portrait (1080×2400) and Landscape (2400×1080).
- **Internal Device Audio Capture**:
  - Captures game and media sound directly via `AudioPlaybackCapture` (Android 10+).
  - Streams raw 48,000 Hz 16-bit Stereo PCM chunks to PC with 500ms internal hardware buffer.
- **Dynamic Adaptive Bitrate (ABR)**:
  - Continuously monitors socket queue congestion.
  - Automatically throttles bitrate down during Wi-Fi packet drops and smoothly restores it when network recovers.
- **Floating Performance Overlay HUD**:
  - Floats live CPU %, RAM %, and Battery Temp on the phone screen.
  - Tap once to collapse into an ultra-minimalist Ghost Dot (`●`).
  - Drag to reposition anywhere freely.
- **Auto-Dim Screen Saver**:
  - Dims phone display backlight to 1% while streaming to eliminate phone heating and save 40–50% battery. PC mirror remains 100% vibrant.
- **UDP LAN Auto-Discovery**:
  - Broadcasts discovery packets on port 8889 to instantly locate the PC receiver without typing IP addresses.

---

## 📋 Requirements

- **Minimum Android Version**: Android 10 (API 29) or higher (Required for `AudioPlaybackCapture`).
- **Target Android Version**: Android 15 (API 35).
- **Hardware**: Any Android device with hardware H.264 video encoder (Snapdragon, MediaTek, Exynos, Google Tensor).
- **JDK**: Java 17.
- **Gradle**: 8.10.2+.

---

## 🛠️ Building & Installing

### Method 1: Using Gradle & ADB (Command Line)
1. Ensure your phone has **USB Debugging** enabled in Developer Options.
2. Connect your phone via USB cable or wireless ADB.
3. Open terminal in the `android_client` directory:
   ```bash
   cd android_client

   # Build debug APK
   ./gradlew assembleDebug

   # Install directly to attached device
   adb install -r app/build/outputs/apk/debug/app-debug.apk
   ```

### Method 2: Using Android Studio
1. Open Android Studio.
2. Select **Open** and choose the `android_client/` folder.
3. Let Gradle sync dependencies.
4. Select your connected device and click **Run (Shift+F10)**.

---

## 🔒 Permissions & Privacy

ZeroCast requests only essential permissions necessary for streaming:
- **`FOREGROUND_SERVICE_MEDIA_PROJECTION`**: Required to capture your display.
- **`RECORD_AUDIO`**: Required by Android to capture internal playback audio.
- **`SYSTEM_ALERT_WINDOW`**: Optional; allows the Floating Performance HUD to float over other apps while gaming.
- **`CAMERA`**: Optional; only accessed if you switch capture source to Rear/Front Camera.

---

## 📁 Source Code Structure

```
android_client/
├── app/
│   ├── src/main/
│   │   ├── java/com/zerocast/
│   │   │   ├── capture/
│   │   │   │   ├── ScreenCaptureH264Manager.kt  # MediaCodec H.264 Baseline GPU Encoder
│   │   │   │   ├── ScreenCaptureManager.kt      # MJPEG ImageReader Fallback
│   │   │   │   ├── AudioCaptureManager.kt       # AudioPlaybackCapture 48kHz PCM
│   │   │   │   └── CameraCaptureManager.kt      # Camera2 Video Feed
│   │   │   ├── network/
│   │   │   │   ├── StreamSender.kt              # Async Socket Transmitter with ABR
│   │   │   │   └── NetworkDiscovery.kt          # UDP LAN Auto-Discovery Client
│   │   │   ├── protocol/
│   │   │   │   └── PacketHeader.kt              # 16-Byte Binary Framing Header
│   │   │   ├── service/
│   │   │   │   ├── StreamForegroundService.kt   # Dynamic Rotation & MediaProjection Service
│   │   │   │   └── FloatingOverlayService.kt    # Floating Performance HUD (CPU/RAM/Temp)
│   │   │   └── ui/
│   │   │       └── MainActivity.kt              # Material 3 Setup & Mode Controller
│   │   ├── res/                                 # Layouts, Drawables & Themes
│   │   └── AndroidManifest.xml
│   └── build.gradle.kts
├── gradle/
└── build.gradle.kts
```
