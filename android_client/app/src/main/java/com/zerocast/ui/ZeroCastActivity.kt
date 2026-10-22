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
import com.zerocast.databinding.ActivityZerocastBinding
import com.zerocast.network.NetworkDiscovery
import com.zerocast.network.StreamSender
import com.zerocast.service.FloatingOverlayService
import com.zerocast.service.StreamForegroundService
import com.zerocast.util.ZeroLinkConfig

class ZeroCastActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZerocastBinding
    private var isStreaming = false

    private var cameraManager: CameraCaptureManager? = null
    private var cameraStreamSender: StreamSender? = null
    private var discovery: NetworkDiscovery? = null

    private var nativeWidth = 1080
    private var nativeHeight = 2400
    private var nativeDpi = 420

    private val recordAudioLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            launchScreenCapture()
        } else {
            Toast.makeText(this, "Audio permission denied. Casting screen without audio.", Toast.LENGTH_SHORT).show()
            launchScreenCapture()
        }
    }

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
        binding = ActivityZerocastBinding.inflate(layoutInflater)
        setContentView(binding.root)

        detectNativeScreenSize()
        setupSpinners()
        restoreSettings()
        setupListeners()
    }

    private fun restoreSettings() {
        val ip = ZeroLinkConfig.getServerIp(this)
        binding.etServerIp.setText(ip)
        val port = ZeroLinkConfig.getCastPort(this)
        binding.etPort.setText(port.toString())

        val resIdx = ZeroLinkConfig.getCastResolution(this)
        if (resIdx < binding.spinnerResolution.count) {
            binding.spinnerResolution.setSelection(resIdx)
        }

        val fpsIdx = ZeroLinkConfig.getCastFps(this)
        if (fpsIdx < binding.spinnerFps.count) {
            binding.spinnerFps.setSelection(fpsIdx)
        }

        val bitrateIdx = ZeroLinkConfig.getCastBitrate(this)
        if (bitrateIdx < binding.spinnerBitrate.count) {
            binding.spinnerBitrate.setSelection(bitrateIdx)
        }

        binding.chkAudio.isChecked = ZeroLinkConfig.getCastAudio(this)
        binding.switchDimScreen.isChecked = ZeroLinkConfig.getCastDimScreen(this)
    }

    private fun saveSettings() {
        ZeroLinkConfig.setServerIp(this, binding.etServerIp.text.toString().trim())
        val port = binding.etPort.text.toString().trim().toIntOrNull() ?: 8888
        ZeroLinkConfig.setCastPort(this, port)
        ZeroLinkConfig.setCastResolution(this, binding.spinnerResolution.selectedItemPosition)
        ZeroLinkConfig.setCastFps(this, binding.spinnerFps.selectedItemPosition)
        ZeroLinkConfig.setCastBitrate(this, binding.spinnerBitrate.selectedItemPosition)
        ZeroLinkConfig.setCastAudio(this, binding.chkAudio.isChecked)
        ZeroLinkConfig.setCastDimScreen(this, binding.switchDimScreen.isChecked)
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
        val ratio = nativeHeight.toFloat() / nativeWidth.toFloat()
        val h720 = ((720 * ratio).toInt() and 1.inv())
        val h540 = ((540 * ratio).toInt() and 1.inv())

        val resolutions = listOf(
            "Native (${nativeWidth}x${nativeHeight}) • 1:1 Pixel Match",
            "1080p (${nativeWidth}x${nativeHeight}) Full HD",
            "720p (720x${h720}) Balanced",
            "540p (540x${h540}) Ultra-Fast"
        )
        val adapterRes = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, resolutions)
        binding.spinnerResolution.adapter = adapterRes

        val fpsOptions = listOf(
            "60 FPS (Ultra Smooth)",
            "30 FPS (Battery Saver)"
        )
        val adapterFps = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, fpsOptions)
        binding.spinnerFps.adapter = adapterFps

        val bitrateOptions = listOf(
            "20 Mbps (Ultra-High Quality • Local Wi-Fi / USB)",
            "14 Mbps (Balanced • Default)",
            "8 Mbps (Low Latency / Weak Wi-Fi)",
            "4 Mbps (Ultra-Fast / Hotspot)"
        )
        val adapterBitrate = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, bitrateOptions)
        binding.spinnerBitrate.adapter = adapterBitrate
        binding.spinnerBitrate.setSelection(1)
    }

    private fun setupListeners() {
        binding.btnBackToHub.setOnClickListener {
            finish()
        }

        binding.btnModeUsb.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etServerIp.setText("127.0.0.1")
            binding.etPort.setText("8888")
            binding.tvConnectionHint.text = "⚡ USB Active: Zero-latency via 127.0.0.1:8888"
            binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
        }

        binding.btnModeWifi.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.tvConnectionHint.text = "📡 Wi-Fi Mode: Ensure phone & PC are on the same Wi-Fi"
            binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
        }

        binding.btnAutoDiscover.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.tvConnectionHint.text = "🔍 Scanning LAN for ZeroLink Hub..."
            discovery = NetworkDiscovery { ip, port ->
                binding.etServerIp.setText(ip)
                binding.etPort.setText(port.toString())
                binding.tvConnectionHint.text = "✅ Found ZeroLink Hub: $ip:$port"
                binding.tvConnectionHint.setTextColor(ContextCompat.getColor(this@ZeroCastActivity, R.color.text_primary))
            }
            discovery?.startDiscovery()
        }

        binding.switchFloatingOverlay.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                if (!Settings.canDrawOverlays(this)) {
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

        binding.btnToggleStream.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            if (!isStreaming) {
                startStreamFlow()
            } else {
                stopStreamService()
            }
        }
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

    private fun startStreamFlow() {
        saveSettings()
        if (binding.rbCameraBack.isChecked || binding.rbCameraFront.isChecked) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA))
                return
            }
            startCameraStream()
        } else {
            if (binding.chkAudio.isChecked &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                recordAudioLauncher.launch(Manifest.permission.RECORD_AUDIO)
            } else {
                launchScreenCapture()
            }
        }
    }

    private fun launchScreenCapture() {
        val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjectionLauncher.launch(projectionManager.createScreenCaptureIntent())
    }

    private fun startScreenStreamService(resultCode: Int, data: Intent) {
        val host = binding.etServerIp.text.toString().trim()
        val port = binding.etPort.text.toString().trim().toIntOrNull() ?: 8888
        val fps = if (binding.spinnerFps.selectedItemPosition == 0) 60 else 30

        val bitrateKbps = when (binding.spinnerBitrate.selectedItemPosition) {
            0 -> 20000
            1 -> 14000
            2 -> 8000
            else -> 4000
        }

        val dimScreen = binding.switchDimScreen.isChecked
        val (w, h) = getTargetDimensions()

        val serviceIntent = Intent(this, StreamForegroundService::class.java).apply {
            action = StreamForegroundService.ACTION_START_SCREEN
            putExtra(StreamForegroundService.EXTRA_RESULT_CODE, resultCode)
            putExtra(StreamForegroundService.EXTRA_RESULT_DATA, data)
            putExtra(StreamForegroundService.EXTRA_HOST, host)
            putExtra(StreamForegroundService.EXTRA_PORT, port)
            putExtra(StreamForegroundService.EXTRA_WIDTH, w)
            putExtra(StreamForegroundService.EXTRA_HEIGHT, h)
            putExtra(StreamForegroundService.EXTRA_DPI, nativeDpi)
            putExtra(StreamForegroundService.EXTRA_FPS, fps)
            putExtra(StreamForegroundService.EXTRA_QUALITY, 80)
            putExtra(StreamForegroundService.EXTRA_USE_H264, true)
            putExtra(StreamForegroundService.EXTRA_CAPTURE_AUDIO, binding.chkAudio.isChecked)
            putExtra(StreamForegroundService.EXTRA_BITRATE_KBPS, bitrateKbps)
        }

        if (dimScreen) {
            setScreenBrightness(0.01f)
        }

        ContextCompat.startForegroundService(this, serviceIntent)
        updateUiState(true)
    }

    private fun setScreenBrightness(brightness: Float) {
        val lp = window.attributes
        lp.screenBrightness = brightness
        window.attributes = lp
    }

    private fun startCameraStream() {
        val host = binding.etServerIp.text.toString().trim()
        val port = binding.etPort.text.toString().trim().toIntOrNull() ?: 8888
        val useFront = binding.rbCameraFront.isChecked

        val sender = StreamSender(host, port, dropLateFrames = true)
        cameraStreamSender = sender
        sender.start()

        cameraManager = CameraCaptureManager(
            context = this,
            lifecycleOwner = this,
            useFrontCamera = useFront,
            targetWidth = 1280,
            targetHeight = 720,
            jpegQuality = 75,
            streamSender = sender
        )
        cameraManager?.start()
        updateUiState(true)
    }

    private fun stopStreamService() {
        val serviceIntent = Intent(this, StreamForegroundService::class.java).apply {
            action = StreamForegroundService.ACTION_STOP
        }
        startService(serviceIntent)

        cameraManager?.stop()
        cameraManager = null
        cameraStreamSender?.disconnect()
        cameraStreamSender = null

        setScreenBrightness(WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE)
        updateUiState(false)
    }

    private fun updateUiState(streaming: Boolean) {
        isStreaming = streaming
        if (streaming) {
            binding.btnToggleStream.text = "STOP STREAMING"
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.status_red))
            binding.tvStatusBadge.text = "● LIVE"
            binding.tvMetricHint.text = "Streaming to ZeroLink Hub"
        } else {
            binding.btnToggleStream.text = "START STREAMING"
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.primary))
            binding.tvStatusBadge.text = "● READY"
            binding.tvMetricHint.text = "Zero-Latency GPU Pipeline • Ready"
        }
    }

    private fun getTargetDimensions(): Pair<Int, Int> {
        val ratio = nativeHeight.toFloat() / nativeWidth.toFloat()
        return when (binding.spinnerResolution.selectedItemPosition) {
            0, 1 -> Pair(nativeWidth, nativeHeight)
            2 -> Pair(720, ((720 * ratio).toInt() and 1.inv()))
            else -> Pair(540, ((540 * ratio).toInt() and 1.inv()))
        }
    }

    override fun onResume() {
        super.onResume()
        // 1. Sync streaming state with active background service
        val isServiceStreaming = StreamForegroundService.isStreaming && !StreamForegroundService.isAudioOnly
        updateUiState(isServiceStreaming)

        // 2. Register listener for background state changes
        StreamForegroundService.stateListener = object : StreamForegroundService.ServiceStateListener {
            override fun onStreamingStateChanged(streaming: Boolean, audioOnly: Boolean) {
                runOnUiThread {
                    updateUiState(streaming && !audioOnly)
                }
            }
        }
    }

    override fun onPause() {
        super.onPause()
        saveSettings()
    }

    override fun onDestroy() {
        super.onDestroy()
        saveSettings()
        StreamForegroundService.stateListener = null
        discovery?.stopDiscovery()
    }
}
