package com.zerocast.ui

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.util.DisplayMetrics
import android.view.HapticFeedbackConstants
import android.view.WindowManager
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.zerocast.R
import com.zerocast.capture.CameraCaptureManager
import com.zerocast.databinding.ActivityMainBinding
import com.zerocast.network.NetworkDiscovery
import com.zerocast.network.StreamSender
import com.zerocast.service.FloatingOverlayService
import com.zerocast.service.StreamForegroundService

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var isStreaming = false

    private var cameraManager: CameraCaptureManager? = null
    private var cameraStreamSender: StreamSender? = null
    private var discovery: NetworkDiscovery? = null

    // Native screen resolution detected at runtime
    private var nativeWidth = 1080
    private var nativeHeight = 2400
    private var nativeDpi = 420

    private val mediaProjectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            startScreenStreamService(result.resultCode, result.data!!)
        } else {
            Toast.makeText(this, "Screen capture permission denied", Toast.LENGTH_SHORT).show()
            updateUiState(false)
        }
    }

    private val overlayPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        if (Settings.canDrawOverlays(this)) {
            binding.switchFloatingOverlay.isChecked = true
            startOverlayService()
        } else {
            binding.switchFloatingOverlay.isChecked = false
            Toast.makeText(this, "Overlay permission not granted", Toast.LENGTH_SHORT).show()
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val cameraGranted = permissions[Manifest.permission.CAMERA] ?: false
        if (cameraGranted && (binding.rbCameraBack.isChecked || binding.rbCameraFront.isChecked)) {
            startCameraStream()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        detectNativeScreenSize()
        setupSpinners()
        setupListeners()
    }

    private fun detectNativeScreenSize() {
        val metrics = DisplayMetrics()
        windowManager.defaultDisplay.getRealMetrics(metrics)

        val w = metrics.widthPixels
        val h = metrics.heightPixels
        val isPortrait = h > w

        nativeWidth = if (isPortrait) minOf(w, h) else maxOf(w, h)
        nativeHeight = if (isPortrait) maxOf(w, h) else minOf(w, h)
        nativeDpi = metrics.densityDpi

        binding.tvNativeBadge.text = "${nativeWidth}x${nativeHeight}"
    }

    private fun setupSpinners() {
        // Calculate scaled dimensions keeping the exact aspect ratio of the phone screen
        val ratio = nativeHeight.toFloat() / nativeWidth.toFloat()

        val h720 = ((720 * ratio).toInt() and 1.inv())
        val h540 = ((540 * ratio).toInt() and 1.inv())

        val resolutions = listOf(
            "📱 Native (${nativeWidth}x${nativeHeight}) • 1:1 Pixel Match",
            "🌟 1080p (${nativeWidth}x${nativeHeight}) Full HD",
            "⚖️ 720p (720x${h720}) Balanced",
            "🚀 540p (540x${h540}) Ultra-Fast"
        )
        val resAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, resolutions)
        binding.spinnerResolution.adapter = resAdapter
        binding.spinnerResolution.setSelection(0) // Default to Native Screen!

        val fpsOptions = listOf(
            "60 FPS (Ultra-Smooth)",
            "45 FPS (Smooth Balanced)",
            "30 FPS (Power Saver)",
            "15 FPS (Ultra Low Data)"
        )
        val fpsAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, fpsOptions)
        binding.spinnerFps.adapter = fpsAdapter
        binding.spinnerFps.setSelection(0)

        // Bitrate Presets
        val bitrateOptions = listOf(
            "30 Mbps (Ultra Extreme • USB)",
            "20 Mbps (Ultra Crisp • Fast Wi-Fi)",
            "14 Mbps (High Quality • Recommended)",
            "10 Mbps (Balanced)",
            "6 Mbps (Bandwidth Saver)"
        )
        val bitrateAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, bitrateOptions)
        binding.spinnerBitrate.adapter = bitrateAdapter
        binding.spinnerBitrate.setSelection(2) // 14 Mbps default
    }

    private fun setupListeners() {
        // Floating Performance HUD Switch
        binding.switchFloatingOverlay.isChecked = FloatingOverlayService.isOverlayRunning
        binding.switchFloatingOverlay.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                if (!Settings.canDrawOverlays(this)) {
                    Toast.makeText(this, "Please enable 'Display over other apps' for ZeroCast HUD", Toast.LENGTH_LONG).show()
                    val intent = Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")
                    )
                    overlayPermissionLauncher.launch(intent)
                } else {
                    startOverlayService()
                }
            } else {
                stopOverlayService()
            }
        }
        // Quick Connection Modes
        binding.btnModeUsb.setOnClickListener {
            binding.etServerIp.setText("127.0.0.1")
            binding.etPort.setText("8888")
            binding.tvConnectionHint.text = "⚡ USB Mode Active: Zero-latency connection via 127.0.0.1:8888"
            binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this, R.color.status_green))
            Toast.makeText(this, "USB Mode Selected (127.0.0.1:8888)", Toast.LENGTH_SHORT).show()
        }

        binding.btnModeWifi.setOnClickListener {
            binding.tvConnectionHint.text = "📡 Wi-Fi Mode: Scanning for PC..."
            binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this, R.color.accent_blue))
            triggerAutoDiscovery()
        }

        // LAN Auto-Discovery
        binding.btnAutoDiscover.setOnClickListener {
            triggerAutoDiscovery()
        }

        // Audio permission check on toggle
        binding.chkAudio.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                permissionLauncher.launch(arrayOf(Manifest.permission.RECORD_AUDIO))
            }
        }

        // Start / Stop Action Button
        binding.btnToggleStream.setOnClickListener { view ->
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            if (isStreaming) {
                stopStream()
            } else {
                startStream()
            }
        }
    }

    private fun triggerAutoDiscovery() {
        Toast.makeText(this, "Scanning local Wi-Fi for ZeroCast PC...", Toast.LENGTH_SHORT).show()
        binding.tvConnectionHint.text = "🔍 Scanning Wi-Fi LAN for PC (Port 8889)..."
        binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this, R.color.accent_blue))
        discovery?.stopDiscovery()
        discovery = NetworkDiscovery { ip, port ->
            binding.etServerIp.setText(ip)
            binding.etPort.setText(port.toString())
            binding.tvConnectionHint.text = "✅ Found PC at $ip:$port! Ready to stream."
            binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this, R.color.status_green))
            Toast.makeText(this, "Connected to PC: $ip:$port", Toast.LENGTH_SHORT).show()
        }
        discovery?.startDiscovery()
    }

    private fun startStream() {
        val ip = binding.etServerIp.text.toString().trim()
        val portStr = binding.etPort.text.toString().trim()

        if (ip.isEmpty() || portStr.isEmpty()) {
            Toast.makeText(this, "Please enter valid PC IP and Port", Toast.LENGTH_SHORT).show()
            return
        }

        if (binding.chkAudio.isChecked && ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionLauncher.launch(arrayOf(Manifest.permission.RECORD_AUDIO))
            return
        }

        if (binding.rbScreen.isChecked) {
            val mpManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            mediaProjectionLauncher.launch(mpManager.createScreenCaptureIntent())
        } else {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA))
            } else {
                startCameraStream()
            }
        }
    }

    private fun startScreenStreamService(resultCode: Int, data: Intent) {
        val (width, height) = getSelectedDimensions()
        val fps = when (binding.spinnerFps.selectedItemPosition) {
            0 -> 60
            1 -> 45
            2 -> 30
            3 -> 15
            else -> 60
        }
        val bitrateKbps = when (binding.spinnerBitrate.selectedItemPosition) {
            0 -> 30000
            1 -> 20000
            2 -> 14000
            3 -> 10000
            4 -> 6000
            else -> 14000
        }
        val host = binding.etServerIp.text.toString().trim()
        val port = binding.etPort.text.toString().trim().toIntOrNull() ?: 8888
        val useH264 = binding.rbH264.isChecked
        val captureAudio = binding.chkAudio.isChecked

        val serviceIntent = Intent(this, StreamForegroundService::class.java).apply {
            action = StreamForegroundService.ACTION_START_SCREEN
            putExtra(StreamForegroundService.EXTRA_RESULT_CODE, resultCode)
            putExtra(StreamForegroundService.EXTRA_RESULT_DATA, data)
            putExtra(StreamForegroundService.EXTRA_HOST, host)
            putExtra(StreamForegroundService.EXTRA_PORT, port)
            putExtra(StreamForegroundService.EXTRA_WIDTH, width)
            putExtra(StreamForegroundService.EXTRA_HEIGHT, height)
            putExtra(StreamForegroundService.EXTRA_DPI, nativeDpi)
            putExtra(StreamForegroundService.EXTRA_FPS, fps)
            putExtra(StreamForegroundService.EXTRA_BITRATE_KBPS, bitrateKbps)
            putExtra(StreamForegroundService.EXTRA_USE_H264, useH264)
            putExtra(StreamForegroundService.EXTRA_CAPTURE_AUDIO, captureAudio)
        }

        ContextCompat.startForegroundService(this, serviceIntent)
        updateUiState(true)
    }

    private fun startOverlayService() {
        val intent = Intent(this, FloatingOverlayService::class.java).apply {
            action = FloatingOverlayService.ACTION_START_OVERLAY
        }
        startService(intent)
    }

    private fun stopOverlayService() {
        val intent = Intent(this, FloatingOverlayService::class.java).apply {
            action = FloatingOverlayService.ACTION_STOP_OVERLAY
        }
        startService(intent)
    }

    private fun startCameraStream() {
        val (width, height) = getSelectedDimensions()
        val host = binding.etServerIp.text.toString().trim()
        val port = binding.etPort.text.toString().trim().toIntOrNull() ?: 8888
        val useFront = binding.rbCameraFront.isChecked

        cameraStreamSender = StreamSender(host, port, dropLateFrames = true)
        cameraStreamSender?.start()

        cameraManager = CameraCaptureManager(
            context = this,
            lifecycleOwner = this,
            useFrontCamera = useFront,
            targetWidth = width,
            targetHeight = height,
            jpegQuality = 80,
            streamSender = cameraStreamSender!!
        )
        cameraManager?.start()

        updateUiState(true)
    }

    private fun stopStream() {
        val stopIntent = Intent(this, StreamForegroundService::class.java).apply {
            action = StreamForegroundService.ACTION_STOP
        }
        startService(stopIntent)

        cameraManager?.stop()
        cameraManager = null
        cameraStreamSender?.disconnect()
        cameraStreamSender = null

        discovery?.stopDiscovery()
        discovery = null

        updateUiState(false)
    }

    private fun updateUiState(streaming: Boolean) {
        isStreaming = streaming
        if (streaming) {
            if (binding.switchDimScreen.isChecked) {
                window.attributes = window.attributes.apply { screenBrightness = 0.01f }
            }
            binding.btnToggleStream.text = "⏹ STOP STREAMING"
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.status_red))
            binding.tvStatusBadge.text = "● STREAMING (H.264)"
            binding.tvStatusBadge.setTextColor(ContextCompat.getColor(this, R.color.status_red))
            val codecInfo = if (binding.rbH264.isChecked) "H.264 Hardware 60 FPS" else "MJPEG"
            binding.tvMetricHint.text = "Active: $codecInfo • Sound: ${if (binding.chkAudio.isChecked) "ON" else "OFF"}"
            binding.tvMetricHint.setTextColor(ContextCompat.getColor(this, R.color.status_green))
        } else {
            window.attributes = window.attributes.apply { screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE }
            binding.btnToggleStream.text = "▶ START STREAMING (H.264)"
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.primary))
            binding.tvStatusBadge.text = "● READY"
            binding.tvStatusBadge.setTextColor(ContextCompat.getColor(this, R.color.status_green))
            binding.tvMetricHint.text = "Zero-Latency Pipeline • Tap Start to Cast Screen"
            binding.tvMetricHint.setTextColor(ContextCompat.getColor(this, R.color.text_tertiary))
        }
    }

    private fun getSelectedDimensions(): Pair<Int, Int> {
        val ratio = nativeHeight.toFloat() / nativeWidth.toFloat()
        return when (binding.spinnerResolution.selectedItemPosition) {
            0 -> Pair(nativeWidth, nativeHeight) // 100% Native Resolution!
            1 -> Pair(nativeWidth, nativeHeight) // 1080p
            2 -> Pair(720, (720 * ratio).toInt() and 1.inv()) // 720p
            3 -> Pair(540, (540 * ratio).toInt() and 1.inv()) // 540p
            else -> Pair(nativeWidth, nativeHeight)
        }
    }

    override fun onDestroy() {
        if (isStreaming) {
            stopStream()
        }
        super.onDestroy()
    }
}
