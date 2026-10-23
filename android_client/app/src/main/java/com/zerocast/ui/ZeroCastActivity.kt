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
import com.zerocast.speedtest.SpeedTestManager
import com.zerocast.util.ZeroLinkConfig
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Button
import android.view.View
import android.content.IntentFilter
import android.os.BatteryManager

class ZeroCastActivity : AppCompatActivity() {

    companion object {
        val BITRATE_VALUES_KBPS = intArrayOf(
            80000, // 80 Mbps
            50000, // 50 Mbps
            35000, // 35 Mbps
            25000, // 25 Mbps
            18000, // 18 Mbps (Default)
            14000, // 14 Mbps
            10000, // 10 Mbps
            6000,  // 6 Mbps
            3000,  // 3 Mbps
            1500   // 1.5 Mbps
        )

        val BITRATE_LABELS = listOf(
            "80 Mbps (⚡ Extreme USB 3.0)",
            "50 Mbps (🔥 Master Quality)",
            "35 Mbps (💎 Crystal Clear)",
            "25 Mbps (🚀 High Performance)",
            "18 Mbps (✨ High Quality)",
            "14 Mbps (⚖️ Balanced)",
            "10 Mbps (📶 Standard)",
            "6 Mbps (⚡ Low Latency)",
            "3 Mbps (🍃 Ultra-Fast)",
            "1.5 Mbps (🔋 Battery Saver)"
        )
    }

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
        binding.switchStrictCbr.isChecked = ZeroLinkConfig.getCastStrictCbr(this)
        updateConnectionHint()
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
        ZeroLinkConfig.setCastStrictCbr(this, binding.switchStrictCbr.isChecked)
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
            "80 Mbps (⚡ Extreme USB 3.0 • Lossless Fidelity)",
            "50 Mbps (🔥 Master Quality • USB / Wi-Fi 6)",
            "35 Mbps (💎 Crystal Clear • Fast 5GHz / USB)",
            "25 Mbps (🚀 High Performance • 5GHz Wi-Fi)",
            "18 Mbps (✨ High Quality • Recommended)",
            "14 Mbps (⚖️ Balanced • Standard)",
            "10 Mbps (📶 Standard Wi-Fi)",
            "6 Mbps (⚡ Low Latency • Fast Response)",
            "3 Mbps (🍃 Ultra-Fast • Weak Wi-Fi / Hotspot)",
            "1.5 Mbps (🔋 Battery Saver • Low Bandwidth)"
        )
        val adapterBitrate = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, bitrateOptions)
        binding.spinnerBitrate.adapter = adapterBitrate
        binding.spinnerBitrate.setSelection(4)
    }

    private fun isUsbCablePluggedIn(): Boolean {
        return try {
            val ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
            val batteryStatus: Intent? = registerReceiver(null, ifilter)
            val chargePlug = batteryStatus?.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1) ?: -1
            chargePlug == BatteryManager.BATTERY_PLUGGED_USB
        } catch (_: Exception) {
            false
        }
    }

    private fun updateConnectionHint() {
        val ip = binding.etServerIp.text.toString().trim()
        val isUsb = ip == "127.0.0.1" || ip == "localhost"
        val hasPhysicalCable = isUsbCablePluggedIn()

        if (isUsb) {
            if (hasPhysicalCable) {
                binding.tvConnectionHint.text = "⚡ Connection Mode: Physical USB Cable (High-Speed ADB 127.0.0.1)"
                binding.tvConnectionHint.setTextColor(android.graphics.Color.parseColor("#0284C7"))
            } else {
                binding.tvConnectionHint.text = "⚠️ Connection Mode: Wireless ADB over Wi-Fi (No physical cable detected • Capped ~20 Mbps • Plug in USB cable for 50-80 Mbps)"
                binding.tvConnectionHint.setTextColor(android.graphics.Color.parseColor("#D97706"))
            }
        } else if (ip.isNotEmpty()) {
            binding.tvConnectionHint.text = "📡 Connection Mode: Direct Wi-Fi LAN (Local Network: $ip)"
            binding.tvConnectionHint.setTextColor(android.graphics.Color.parseColor("#059669"))
        } else {
            binding.tvConnectionHint.text = "⚠️ Please enter PC IP or tap 'USB Cable'"
            binding.tvConnectionHint.setTextColor(android.graphics.Color.parseColor("#D97706"))
        }
    }

    private fun setupListeners() {
        binding.btnBackToHub.setOnClickListener {
            finish()
        }

        binding.etServerIp.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                updateConnectionHint()
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })

        binding.btnModeUsb.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etServerIp.setText("127.0.0.1")
            binding.etPort.setText("8888")
            updateConnectionHint()
        }

        binding.btnModeWifi.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            if (binding.etServerIp.text.toString().trim() == "127.0.0.1") {
                val lastWifi = ZeroLinkConfig.getServerIp(this)
                if (lastWifi != "127.0.0.1" && lastWifi.isNotEmpty()) {
                    binding.etServerIp.setText(lastWifi)
                } else {
                    binding.etServerIp.setText("")
                }
            }
            updateConnectionHint()
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

        binding.btnSpeedTest.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            showSpeedTestDialog()
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

        val bitrateKbps = BITRATE_VALUES_KBPS.getOrElse(binding.spinnerBitrate.selectedItemPosition) { 18000 }

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
            putExtra(StreamForegroundService.EXTRA_USE_CBR, binding.switchStrictCbr.isChecked)
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
        val host = binding.etServerIp.text.toString().trim()
        val isLoopback = host == "127.0.0.1" || host == "localhost"
        val hasPhysicalCable = isUsbCablePluggedIn()

        if (streaming) {
            binding.btnToggleStream.text = "STOP STREAMING"
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.status_red))
            if (isLoopback && hasPhysicalCable) {
                binding.tvStatusBadge.text = "● LIVE (⚡ USB)"
                binding.tvMetricHint.text = "⚡ Live via Physical USB Cable (High-Speed ADB)"
            } else if (isLoopback) {
                binding.tvStatusBadge.text = "● LIVE (⚡ ADB Wi-Fi)"
                binding.tvMetricHint.text = "⚠️ Live via Wireless ADB over Wi-Fi (Capped ~20 Mbps)"
            } else {
                binding.tvStatusBadge.text = "● LIVE (📡 Wi-Fi)"
                binding.tvMetricHint.text = "📡 Live via Direct Wi-Fi LAN ($host)"
            }
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

    private fun showSpeedTestDialog() {
        val host = binding.etServerIp.text.toString().trim().ifEmpty { "127.0.0.1" }
        val dialogView = layoutInflater.inflate(R.layout.dialog_speed_test, null)
        val dialog = com.google.android.material.dialog.MaterialAlertDialogBuilder(this)
            .setView(dialogView)
            .create()

        val tvMediumBadge = dialogView.findViewById<TextView>(R.id.tvMediumBadge)
        val tvSpeedVal = dialogView.findViewById<TextView>(R.id.tvSpeedVal)
        val progressBar = dialogView.findViewById<ProgressBar>(R.id.progressBarSpeed)
        val tvPingVal = dialogView.findViewById<TextView>(R.id.tvPingVal)
        val tvJitterVal = dialogView.findViewById<TextView>(R.id.tvJitterVal)
        val tvRecommendation = dialogView.findViewById<TextView>(R.id.tvRecommendation)
        val btnApply = dialogView.findViewById<Button>(R.id.btnApplyRecommendation)
        val btnStart = dialogView.findViewById<Button>(R.id.btnStartTest)
        val btnClose = dialogView.findViewById<Button>(R.id.btnCloseDialog)

        val isUsb = host == "127.0.0.1" || host == "localhost"
        tvMediumBadge.text = if (isUsb) "⚡ USB CABLE" else "📡 WI-FI ($host)"
        tvMediumBadge.setTextColor(if (isUsb) android.graphics.Color.parseColor("#0284C7") else android.graphics.Color.parseColor("#059669"))

        var testManager: SpeedTestManager? = null

        btnStart.setOnClickListener {
            btnStart.isEnabled = false
            btnStart.text = "TESTING..."
            btnApply.visibility = View.GONE
            tvSpeedVal.text = "0.0"
            progressBar.progress = 0
            tvPingVal.text = "..."
            tvJitterVal.text = "..."
            tvRecommendation.text = "Measuring real-time latency and raw TCP throughput..."

            testManager = SpeedTestManager(host, 8890, object : SpeedTestManager.SpeedTestListener {
                override fun onPingCompleted(avgPingMs: Float, jitterMs: Float) {
                    tvPingVal.text = String.format("%.1f ms", avgPingMs)
                    tvJitterVal.text = String.format("%.1f ms", jitterMs)
                }

                override fun onProgress(progress: Float, currentMbps: Float) {
                    progressBar.progress = (progress * 100).toInt()
                    tvSpeedVal.text = String.format("%.1f", currentMbps)
                }

                override fun onCompleted(result: SpeedTestManager.SpeedTestResult) {
                    btnStart.isEnabled = true
                    btnStart.text = "RUN AGAIN"
                    progressBar.progress = 100
                    tvSpeedVal.text = String.format("%.1f", result.mbps)
                    tvRecommendation.text = result.recommendation
                    btnApply.visibility = View.VISIBLE
                    val label = BITRATE_LABELS.getOrElse(result.recommendedBitrateIndex) { "" }
                    btnApply.text = "Apply Optimal Bitrate ($label)"
                    btnApply.setOnClickListener {
                        if (result.recommendedBitrateIndex < binding.spinnerBitrate.count) {
                            binding.spinnerBitrate.setSelection(result.recommendedBitrateIndex)
                        }
                        dialog.dismiss()
                    }
                }

                override fun onError(message: String) {
                    btnStart.isEnabled = true
                    btnStart.text = "RETRY"
                    tvRecommendation.text = "❌ Error: $message\nEnsure PC Hub is running and port 8890 is reachable."
                }
            })
            testManager?.startTest()
        }

        btnClose.setOnClickListener {
            testManager?.cancel()
            dialog.dismiss()
        }

        dialog.setOnDismissListener {
            testManager?.cancel()
        }

        dialog.show()
        // Automatically start benchmark when dialog opens
        btnStart.performClick()
    }
}
