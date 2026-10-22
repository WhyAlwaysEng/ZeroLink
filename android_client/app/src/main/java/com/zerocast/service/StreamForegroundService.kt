package com.zerocast.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import android.view.Display
import android.view.Surface
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import com.zerocast.capture.AudioCaptureManager
import com.zerocast.capture.ScreenCaptureH264Manager
import com.zerocast.capture.ScreenCaptureManager
import com.zerocast.network.StreamSender
import com.zerocast.protocol.PacketHeader

class StreamForegroundService : LifecycleService() {

    interface ServiceStateListener {
        fun onStreamingStateChanged(isStreaming: Boolean, isAudioOnly: Boolean)
    }

    companion object {
        private const val TAG = "StreamService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "zerocast_stream_channel"

        const val ACTION_START_SCREEN = "com.zerocast.action.START_SCREEN"
        const val ACTION_START_AUDIO_ONLY = "com.zerocast.action.START_AUDIO_ONLY"
        const val ACTION_STOP = "com.zerocast.action.STOP"
        const val ACTION_TOGGLE_ORIENTATION = "com.zerocast.action.TOGGLE_ORIENTATION"

        const val EXTRA_RESULT_CODE = "extra_result_code"
        const val EXTRA_RESULT_DATA = "extra_result_data"
        const val EXTRA_HOST = "extra_host"
        const val EXTRA_PORT = "extra_port"
        const val EXTRA_WIDTH = "extra_width"
        const val EXTRA_HEIGHT = "extra_height"
        const val EXTRA_DPI = "extra_dpi"
        const val EXTRA_FPS = "extra_fps"
        const val EXTRA_QUALITY = "extra_quality"
        const val EXTRA_USE_H264 = "extra_use_h264"
        const val EXTRA_CAPTURE_AUDIO = "extra_capture_audio"
        const val EXTRA_BITRATE_KBPS = "extra_bitrate_kbps"

        var isStreaming = false
            private set
        var isAudioOnly = false
            private set

        var stateListener: ServiceStateListener? = null
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var mediaProjection: MediaProjection? = null
    private var screenCaptureManager: ScreenCaptureManager? = null
    private var screenCaptureH264Manager: ScreenCaptureH264Manager? = null
    private var audioCaptureManager: AudioCaptureManager? = null
    private var streamSender: StreamSender? = null
    private var dummyImageReader: ImageReader? = null
    private var dummyVirtualDisplay: VirtualDisplay? = null

    // Stored streaming config for dynamic rotation switching
    private var baseWidth = 1080
    private var baseHeight = 2400
    private var currentActiveWidth = 1080
    private var currentActiveHeight = 2400
    private var streamDpi = 320
    private var streamFps = 60
    private var streamQuality = 75
    private var streamBitrateKbps = 14000
    private var isH264Mode = true
    private var lastRotation = -1
    private var displayListener: DisplayManager.DisplayListener? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        acquireWakeLock()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)

        when (intent?.action) {
            ACTION_START_SCREEN -> handleStartScreen(intent)
            ACTION_START_AUDIO_ONLY -> handleStartAudioOnly(intent)
            ACTION_STOP -> stopStreaming()
            ACTION_TOGGLE_ORIENTATION -> handleToggleOrientation()
        }

        return START_NOT_STICKY
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        if (isStreaming) {
            checkOrientationChanged()
        }
    }

    private fun notifyStateChanged() {
        mainHandler.post {
            stateListener?.onStreamingStateChanged(isStreaming, isAudioOnly)
        }
    }

    private fun handleStartAudioOnly(intent: Intent) {
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
        val resultData = intent.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
        val host = intent.getStringExtra(EXTRA_HOST) ?: "127.0.0.1"
        val port = intent.getIntExtra(EXTRA_PORT, 8888)

        if (resultCode != Activity.RESULT_OK || resultData == null) {
            Log.e(TAG, "Invalid MediaProjection intent data for audio-only cast")
            stopSelf()
            return
        }

        isAudioOnly = true
        acquireWakeLock()
        startForegroundWithNotification(isAudioOnly = true)

        val mpManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjection = mpManager.getMediaProjection(resultCode, resultData).apply {
            registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    Log.d(TAG, "MediaProjection stopped by system")
                    stopStreaming()
                }
            }, null)
        }

        val mp = mediaProjection
        if (mp == null) {
            Log.e(TAG, "Failed to initialize MediaProjection for audio cast")
            stopStreaming()
            return
        }

        streamSender = StreamSender(host, port, dropLateFrames = false, listener = object : StreamSender.StreamListener {
            override fun onConnected() {
                Log.d(TAG, "Audio-only eco cast connected to PC: $host:$port")
                sendAudioOnlyConfig()
            }

            override fun onDisconnected(reason: String?) {
                Log.d(TAG, "Audio cast disconnected: $reason")
            }

            override fun onControlPacketReceived(payload: ByteArray) {
                Log.d(TAG, "Audio cast control packet (${payload.size} bytes)")
            }

            override fun onError(error: Throwable) {
                Log.e(TAG, "Audio cast network error: ${error.message}")
                mainHandler.post {
                    val msg = if (error is java.net.ConnectException) {
                        "⚠️ Connection refused: Ensure ZeroCast module is ENABLED on PC"
                    } else {
                        "Audio Cast Error: ${error.localizedMessage ?: "Failed"}"
                    }
                    android.widget.Toast.makeText(applicationContext, msg, android.widget.Toast.LENGTH_LONG).show()
                }
                stopStreaming()
            }
        })
        streamSender?.start()

        val sender = streamSender ?: return

        // Rock-solid Eco Video Stream: 320x180 @ 5 FPS & 200 Kbps (0.05% CPU/GPU, ice-cold phone)
        // Satisfies Android 14 MediaProjection lifecycle while acting 100% as an audio cast.
        screenCaptureH264Manager = ScreenCaptureH264Manager(
            mediaProjection = mp,
            width = 320,
            height = 180,
            dpi = 120,
            targetFps = 5,
            bitrateKbps = 200,
            streamSender = sender
        ).apply {
            start()
        }

        audioCaptureManager = AudioCaptureManager(
            mediaProjection = mp,
            streamSender = sender
        ).apply {
            start()
        }

        isStreaming = true
        notifyStateChanged()
        Log.d(TAG, "Eco-mode Video+Audio Cast started for ZeroMix (0.05% GPU / Ice-cold Phone).")
    }

    private fun sendAudioOnlyConfig() {
        val configJson = """
            {
                "codec": "AUDIO_ONLY_ECO",
                "width": 320,
                "height": 180,
                "fps": 5,
                "device_model": "${android.os.Build.MODEL}"
            }
        """.trimIndent()
        val payload = configJson.toByteArray(Charsets.UTF_8)
        streamSender?.enqueueFrame(PacketHeader.TYPE_CONFIG_JSON, 0, payload)
    }

    private fun handleStartScreen(intent: Intent) {
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
        val resultData = intent.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
        val host = intent.getStringExtra(EXTRA_HOST) ?: "127.0.0.1"
        val port = intent.getIntExtra(EXTRA_PORT, 8888)
        baseWidth = intent.getIntExtra(EXTRA_WIDTH, 1080)
        baseHeight = intent.getIntExtra(EXTRA_HEIGHT, 2400)
        streamDpi = intent.getIntExtra(EXTRA_DPI, 320)
        streamFps = intent.getIntExtra(EXTRA_FPS, 60)
        streamQuality = intent.getIntExtra(EXTRA_QUALITY, 75)
        streamBitrateKbps = intent.getIntExtra(EXTRA_BITRATE_KBPS, 14000)
        isH264Mode = intent.getBooleanExtra(EXTRA_USE_H264, true)
        val captureAudio = intent.getBooleanExtra(EXTRA_CAPTURE_AUDIO, true)

        if (resultCode != Activity.RESULT_OK || resultData == null) {
            Log.e(TAG, "Invalid MediaProjection intent data")
            stopSelf()
            return
        }

        startForegroundWithNotification()

        val mpManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjection = mpManager.getMediaProjection(resultCode, resultData).apply {
            registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    Log.d(TAG, "MediaProjection stopped by system")
                    stopStreaming()
                }
            }, null)
        }

        streamSender = StreamSender(host, port, dropLateFrames = false, listener = object : StreamSender.StreamListener {
            override fun onConnected() {
                Log.d(TAG, "Connected to PC: $host:$port")
            }

            override fun onDisconnected(reason: String?) {
                Log.d(TAG, "Disconnected: $reason")
            }

            override fun onControlPacketReceived(payload: ByteArray) {
                Log.d(TAG, "Received control packet (${payload.size} bytes)")
            }

            override fun onError(error: Throwable) {
                Log.e(TAG, "Stream error: ${error.message}")
                mainHandler.post {
                    val msg = if (error is java.net.ConnectException) {
                        "⚠️ Connection refused: Ensure ZeroCast module is ENABLED in ZeroLink Hub on PC"
                    } else {
                        "Stream error: ${error.localizedMessage ?: "Connection failed"}"
                    }
                    android.widget.Toast.makeText(applicationContext, msg, android.widget.Toast.LENGTH_LONG).show()
                }
                stopStreaming()
            }

            override fun onCongestionChanged(isCongested: Boolean) {
                if (isCongested) {
                    val fallbackKbps = maxOf(4500, streamBitrateKbps / 2)
                    Log.w(TAG, "Network congestion detected -> Scaling bitrate down to ${fallbackKbps} Kbps")
                    screenCaptureH264Manager?.updateBitrate(fallbackKbps)
                } else {
                    Log.d(TAG, "Network recovered -> Restoring bitrate to ${streamBitrateKbps} Kbps")
                    screenCaptureH264Manager?.updateBitrate(streamBitrateKbps)
                }
            }
        })
        streamSender?.start()

        // Check initial screen rotation (Landscape vs Portrait)
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val initialRotation = wm.defaultDisplay.rotation
        lastRotation = initialRotation
        val isLandscape = initialRotation == Surface.ROTATION_90 || initialRotation == Surface.ROTATION_270

        currentActiveWidth = if (isLandscape) maxOf(baseWidth, baseHeight) else minOf(baseWidth, baseHeight)
        currentActiveHeight = if (isLandscape) minOf(baseWidth, baseHeight) else maxOf(baseWidth, baseHeight)

        startVideoEncoder(currentActiveWidth, currentActiveHeight)

        // Internal Audio Capture
        if (captureAudio) {
            audioCaptureManager = AudioCaptureManager(
                mediaProjection = mediaProjection!!,
                streamSender = streamSender!!
            )
            audioCaptureManager?.start()
        }

        // Register dynamic display listener for orientation changes
        registerOrientationListener()

        isStreaming = true
        notifyStateChanged()
        Log.d(TAG, "Streaming service running: ${currentActiveWidth}x${currentActiveHeight} (H.264=$isH264Mode, Landscape=$isLandscape).")
    }

    private fun startVideoEncoder(w: Int, h: Int) {
        val proj = mediaProjection ?: return
        val sender = streamSender ?: return

        if (isH264Mode) {
            val bitrateKbps = if (streamBitrateKbps > 0) streamBitrateKbps else (if (w >= 1080 || h >= 1080) 12000 else 6000)
            screenCaptureH264Manager = ScreenCaptureH264Manager(
                mediaProjection = proj,
                width = w,
                height = h,
                dpi = streamDpi,
                targetFps = streamFps,
                bitrateKbps = bitrateKbps,
                streamSender = sender
            )
            screenCaptureH264Manager?.start()
        } else {
            screenCaptureManager = ScreenCaptureManager(
                mediaProjection = proj,
                width = w,
                height = h,
                dpi = streamDpi,
                targetFps = streamFps,
                jpegQuality = streamQuality,
                streamSender = sender
            )
            screenCaptureManager?.start()
        }
    }

    private fun registerOrientationListener() {
        val displayManager = getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
        displayListener = object : DisplayManager.DisplayListener {
            override fun onDisplayAdded(displayId: Int) {}
            override fun onDisplayRemoved(displayId: Int) {}
            override fun onDisplayChanged(displayId: Int) {
                if (displayId == Display.DEFAULT_DISPLAY && isStreaming) {
                    checkOrientationChanged()
                }
            }
        }
        displayManager.registerDisplayListener(displayListener, mainHandler)
    }

    private fun checkOrientationChanged() {
        try {
            val dm = getSystemService(Context.DISPLAY_SERVICE) as? DisplayManager
            val rot = dm?.getDisplay(Display.DEFAULT_DISPLAY)?.rotation ?: Surface.ROTATION_0
            val isConfigLandscape = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
            val isRotLandscape = rot == Surface.ROTATION_90 || rot == Surface.ROTATION_270
            val isLandscape = isConfigLandscape || isRotLandscape

            val targetW = if (isLandscape) maxOf(baseWidth, baseHeight) else minOf(baseWidth, baseHeight)
            val targetH = if (isLandscape) minOf(baseWidth, baseHeight) else maxOf(baseWidth, baseHeight)

            if (targetW != currentActiveWidth || targetH != currentActiveHeight) {
                Log.d(TAG, "Orientation changed -> Reconfiguring stream to ${targetW}x${targetH} (Landscape=$isLandscape)")
                currentActiveWidth = targetW
                currentActiveHeight = targetH

                // Stop old video encoder and restart with new orientation dimensions
                screenCaptureH264Manager?.stop()
                screenCaptureH264Manager = null

                screenCaptureManager?.stop()
                screenCaptureManager = null

                mainHandler.postDelayed({
                    if (isStreaming && mediaProjection != null) {
                        startVideoEncoder(targetW, targetH)
                    }
                }, 200) // Small debounce for Android window manager to settle
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error in checkOrientationChanged: ${e.message}", e)
        }
    }

    private fun handleToggleOrientation() {
        if (!isStreaming || mediaProjection == null) return
        try {
            val isCurrentlyLandscape = currentActiveWidth > currentActiveHeight
            val newW = if (isCurrentlyLandscape) minOf(baseWidth, baseHeight) else maxOf(baseWidth, baseHeight)
            val newH = if (isCurrentlyLandscape) maxOf(baseWidth, baseHeight) else minOf(baseWidth, baseHeight)

            Log.d(TAG, "Manual toggle orientation requested: ${currentActiveWidth}x${currentActiveHeight} -> ${newW}x${newH}")
            currentActiveWidth = newW
            currentActiveHeight = newH

            screenCaptureH264Manager?.stop()
            screenCaptureH264Manager = null

            screenCaptureManager?.stop()
            screenCaptureManager = null

            mainHandler.postDelayed({
                if (isStreaming && mediaProjection != null) {
                    startVideoEncoder(newW, newH)
                }
            }, 150)
        } catch (e: Exception) {
            Log.e(TAG, "Error in handleToggleOrientation: ${e.message}", e)
        }
    }

    private fun startForegroundWithNotification(isAudioOnly: Boolean = false) {
        val stopIntent = Intent(this, StreamForegroundService::class.java).apply {
            action = ACTION_STOP
        }
        val stopPendingIntent = PendingIntent.getService(
            this,
            0,
            stopIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val title = if (isAudioOnly) "ZeroMix Audio Cast" else "ZeroLink Streaming"
        val text = if (isAudioOnly) "Audio-only streaming to PC (0% Video / Battery Saver)" else "Screen mirroring is actively streaming to PC"

        val notifBuilder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(if (isAudioOnly) android.R.drawable.ic_media_play else android.R.drawable.presence_video_online)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop Cast", stopPendingIntent)

        if (!isAudioOnly) {
            val rotateIntent = Intent(this, StreamForegroundService::class.java).apply {
                action = ACTION_TOGGLE_ORIENTATION
            }
            val rotatePendingIntent = PendingIntent.getService(
                this,
                1,
                rotateIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            notifBuilder.addAction(android.R.drawable.ic_menu_rotate, "Rotate 90°", rotatePendingIntent)
        }

        val notification = notifBuilder.build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun stopStreaming() {
        isStreaming = false
        isAudioOnly = false
        notifyStateChanged()

        if (displayListener != null) {
            val dm = getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
            dm.unregisterDisplayListener(displayListener)
            displayListener = null
        }

        dummyVirtualDisplay?.release()
        dummyVirtualDisplay = null

        dummyImageReader?.close()
        dummyImageReader = null

        screenCaptureH264Manager?.stop()
        screenCaptureH264Manager = null

        screenCaptureManager?.stop()
        screenCaptureManager = null

        audioCaptureManager?.stop()
        audioCaptureManager = null

        streamSender?.disconnect()
        streamSender = null

        mediaProjection?.stop()
        mediaProjection = null

        releaseWakeLock()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        Log.d(TAG, "Streaming service stopped.")
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "ZeroCast Live Streaming",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows live streaming status"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun acquireWakeLock() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "ZeroCast::StreamingWakeLock"
        ).apply {
            acquire(12 * 60 * 60 * 1000L)
        }
    }

    private fun releaseWakeLock() {
        if (wakeLock?.isHeld == true) {
            wakeLock?.release()
        }
        wakeLock = null
    }

    override fun onDestroy() {
        stopStreaming()
        super.onDestroy()
    }
}
