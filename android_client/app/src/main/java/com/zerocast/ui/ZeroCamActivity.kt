package com.zerocast.ui

import android.Manifest
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Matrix
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.HapticFeedbackConstants
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroCamBinding
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.lifecycleScope
import com.zerocast.network.ConnectionState
import com.zerocast.network.EcosystemConnectionManager
import com.zerocast.network.NetworkDiscovery
import kotlinx.coroutines.flow.collectLatest
import com.zerocast.util.ZeroLinkConfig
import com.zerocast.capture.CameraH264Encoder
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class ZeroCamActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ZeroCam"
        private const val DEFAULT_PORT = 8893
    }

    private lateinit var binding: ActivityZeroCamBinding

    private var cameraProvider: ProcessCameraProvider? = null
    private var camera: Camera? = null
    private var cameraExecutor: ExecutorService? = null

    private var useFrontCamera = false
    private var isTorchOn = false
    private var isStreaming = false

    private var targetWidth = 1920
    private var targetHeight = 1080
    private var jpegQuality = 82

    private var h264Encoder: CameraH264Encoder? = null
    private var useH264Hardware = false // Default to Turbo JPEG Safe Mode (never green), toggleable to H.264

    private var socket: Socket? = null
    private var outStream: OutputStream? = null
    private var streamJob: Job? = null
    private var senderJob: Job? = null
    private var frameChannel = kotlinx.coroutines.channels.Channel<ByteArray>(kotlinx.coroutines.channels.Channel.CONFLATED)
    private val scope = CoroutineScope(Dispatchers.IO)

    private var frameCount = 0
    private var bytesThisSec = 0L
    private var lastStatTime = System.currentTimeMillis()
    private val baos = ByteArrayOutputStream(64 * 1024)

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            setupCamera()
        } else {
            Toast.makeText(this, "Camera permission is required for ZeroCam", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private lateinit var connMgr: EcosystemConnectionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroCamBinding.inflate(layoutInflater)
        setContentView(binding.root)

        connMgr = EcosystemConnectionManager.getInstance(this)
        cameraExecutor = Executors.newSingleThreadExecutor()

        observeConnectionState()

        binding.btnCamBack.setOnClickListener {
            finish()
        }

        binding.btnCamSwitch.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            useFrontCamera = !useFrontCamera
            bindCameraUseCases()
        }

        binding.btnToggleControls.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val isVis = binding.cardBottomControls.visibility == android.view.View.VISIBLE
            binding.cardBottomControls.visibility = if (isVis) android.view.View.GONE else android.view.View.VISIBLE
        }

        // Resolution Chips
        binding.btnRes4K.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            switchResolution(3840, 2160)
        }
        binding.btnRes1080p.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            switchResolution(1920, 1080)
        }
        binding.btnRes720p.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            switchResolution(1280, 720)
        }
        updateResolutionUI(targetWidth, targetHeight)

        binding.btnCodecToggle.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            useH264Hardware = !useH264Hardware
            updateCodecUI()
            if (!useH264Hardware) {
                h264Encoder?.stop()
                h264Encoder = null
                Toast.makeText(this, "📸 Switched to Turbo JPEG Safe Mode", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "⚡ Switched to Hardware H.264 Mode", Toast.LENGTH_SHORT).show()
                if (isStreaming) {
                    initH264Encoder(targetWidth, targetHeight)
                }
            }
        }
        updateCodecUI()

        binding.btnCamTorch.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            toggleTorch()
        }

        binding.btnCamStreamToggle.setOnClickListener {
            if (isStreaming) {
                stopStream()
            } else {
                val ip = connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
                startStream(ip, DEFAULT_PORT)
            }
        }

        binding.btnCamOledStandby.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = android.content.Intent(this, OledStandbyActivity::class.java).apply {
                putExtra("EXTRA_REASON", "ZeroCam Webcam Active")
            }
            startActivity(intent)
        }

        // Tap-to-focus on camera viewfinder
        binding.cameraPreviewView.setOnTouchListener { _, event ->
            if (event.action == android.view.MotionEvent.ACTION_UP) {
                val factory = binding.cameraPreviewView.meteringPointFactory
                val point = factory.createPoint(event.x, event.y)
                val action = FocusMeteringAction.Builder(point, FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE)
                    .setAutoCancelDuration(3, java.util.concurrent.TimeUnit.SECONDS)
                    .build()
                camera?.cameraControl?.startFocusAndMetering(action)
            }
            true
        }

        checkPermissionAndStart()
    }

    private fun observeConnectionState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    connMgr.connectionState.collectLatest { state ->
                        updateConnectionUI(state, connMgr.activeMode.value, connMgr.targetHost.value)
                    }
                }
                launch {
                    connMgr.activeMode.collectLatest { mode ->
                        updateConnectionUI(connMgr.connectionState.value, mode, connMgr.targetHost.value)
                    }
                }
            }
        }
    }

    private fun updateConnectionUI(state: ConnectionState, mode: String, host: String) {
        val (icon, modeStr) = when (mode) {
            ZeroLinkConfig.MODE_USB -> Pair("⌁", "USB ADB Cable")
            ZeroLinkConfig.MODE_TETHER -> Pair("⚡", "USB Tethering")
            else -> Pair("📡", "Wi-Fi LAN")
        }

        binding.tvCamLinkIcon.text = icon
        when (state) {
            ConnectionState.CONNECTED -> {
                binding.tvCamLinkInfo.text = "Linked: $modeStr ($host:8889)"
                binding.tvCamLinkBadge.text = "● LINKED"
                binding.tvCamLinkBadge.setTextColor(android.graphics.Color.parseColor("#10B981"))
            }
            ConnectionState.CONNECTING, ConnectionState.RECONNECTING -> {
                binding.tvCamLinkInfo.text = "Connecting to $host:8889..."
                binding.tvCamLinkBadge.text = "○ CONNECTING"
                binding.tvCamLinkBadge.setTextColor(android.graphics.Color.parseColor("#F59E0B"))
            }
            ConnectionState.DISCONNECTED -> {
                binding.tvCamLinkInfo.text = "Offline • Tap Home to connect"
                binding.tvCamLinkBadge.text = "○ OFFLINE"
                binding.tvCamLinkBadge.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
            }
        }
    }

    private fun updateResolutionUI(w: Int, h: Int) {
        val activeBg = ContextCompat.getColorStateList(this, R.color.text_primary)
        val inactiveBg = ContextCompat.getColorStateList(this, R.color.surface)
        val textWhite = android.graphics.Color.WHITE
        val textSecondary = ContextCompat.getColor(this, R.color.text_secondary)
        val strokeColor = ContextCompat.getColorStateList(this, R.color.surface_stroke)

        // 4K UHD
        if (w >= 3840) {
            binding.btnRes4K.backgroundTintList = activeBg
            binding.btnRes4K.setTextColor(textWhite)
            binding.btnRes4K.strokeWidth = 0
        } else {
            binding.btnRes4K.backgroundTintList = inactiveBg
            binding.btnRes4K.setTextColor(textSecondary)
            binding.btnRes4K.strokeColor = strokeColor
            binding.btnRes4K.strokeWidth = 1
        }

        // 1080p
        if (w == 1920) {
            binding.btnRes1080p.backgroundTintList = activeBg
            binding.btnRes1080p.setTextColor(textWhite)
            binding.btnRes1080p.strokeWidth = 0
        } else {
            binding.btnRes1080p.backgroundTintList = inactiveBg
            binding.btnRes1080p.setTextColor(textSecondary)
            binding.btnRes1080p.strokeColor = strokeColor
            binding.btnRes1080p.strokeWidth = 1
        }

        // 720p
        if (w == 1280) {
            binding.btnRes720p.backgroundTintList = activeBg
            binding.btnRes720p.setTextColor(textWhite)
            binding.btnRes720p.strokeWidth = 0
        } else {
            binding.btnRes720p.backgroundTintList = inactiveBg
            binding.btnRes720p.setTextColor(textSecondary)
            binding.btnRes720p.strokeColor = strokeColor
            binding.btnRes720p.strokeWidth = 1
        }
    }

    private fun updateCodecUI() {
        if (useH264Hardware) {
            binding.btnCodecToggle.text = "⚡ H.264 HW"
            binding.btnCodecToggle.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#10B981"))
            binding.btnCodecToggle.setTextColor(Color.WHITE)
        } else {
            binding.btnCodecToggle.text = "📸 JPEG Safe"
            binding.btnCodecToggle.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#111827"))
            binding.btnCodecToggle.setTextColor(Color.WHITE)
        }
    }

    private fun initH264Encoder(w: Int, h: Int) {
        h264Encoder?.stop()
        val (fps, bitrate) = when {
            w >= 3840 -> Pair(30, 24000)
            w >= 1920 -> Pair(60, 12000)
            else -> Pair(60, 6000)
        }
        val enc = CameraH264Encoder(w, h, targetFps = fps, bitrateKbps = bitrate) { nalBytes, isKeyframe, rotDeg ->
            val payloadLen = nalBytes.size
            val nowMs = System.currentTimeMillis()
            val flags: Short = if (isKeyframe) 0x03 else 0x01

            val packet = ByteArray(20 + payloadLen)
            val buf = ByteBuffer.wrap(packet)
            buf.put("ZCAM".toByteArray(Charsets.US_ASCII))
            buf.putInt(payloadLen)
            buf.putLong(nowMs)
            buf.putShort(rotDeg.toShort())
            buf.putShort(flags)
            System.arraycopy(nalBytes, 0, packet, 20, payloadLen)

            frameChannel.trySend(packet)

            frameCount++
            bytesThisSec += packet.size
        }
        val ok = enc.start()
        if (ok) {
            h264Encoder = enc
            Log.i(TAG, "Hardware H.264 Encoder successfully started ($w x $h @ ${fps}fps)")
        } else {
            Log.w(TAG, "Hardware H.264 Encoder start failed; fallback to Turbo JPEG")
            h264Encoder = null
        }
    }

    private fun switchResolution(w: Int, h: Int) {
        if (targetWidth == w && targetHeight == h) return
        targetWidth = w
        targetHeight = h
        updateResolutionUI(w, h)
        bindCameraUseCases()
        if (isStreaming) {
            val ip = connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
            if (ip.isNotEmpty()) {
                startStream(ip, DEFAULT_PORT)
            }
        }
        val label = if (w >= 3840) "4K Ultra HD (3840x2160)" else if (w >= 1920) "Full HD 1080p" else "HD 720p"
        Toast.makeText(this, "💎 Resolution: $label", Toast.LENGTH_SHORT).show()
    }

    private fun checkPermissionAndStart() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            setupCamera()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun setupCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            try {
                cameraProvider = future.get()
                bindCameraUseCases()
            } catch (e: Exception) {
                Log.e(TAG, "Camera provider failed: ${e.message}")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @androidx.annotation.OptIn(androidx.camera.camera2.interop.ExperimentalCamera2Interop::class)
    private fun bindCameraUseCases() {
        val provider = cameraProvider ?: return
        val cameraSelector = if (useFrontCamera) {
            CameraSelector.DEFAULT_FRONT_CAMERA
        } else {
            CameraSelector.DEFAULT_BACK_CAMERA
        }

        val targetSize = android.util.Size(targetWidth, targetHeight)

        @Suppress("DEPRECATION")
        val previewBuilder = Preview.Builder()
            .setTargetResolution(targetSize)

        // Adaptive FPS range: 30 FPS for 4K UHD, 60 FPS for 1080p & 720p
        val fpsRange = if (targetWidth >= 3840) android.util.Range(30, 30) else android.util.Range(60, 60)
        val previewExt = androidx.camera.camera2.interop.Camera2Interop.Extender(previewBuilder)
        previewExt.setCaptureRequestOption(
            android.hardware.camera2.CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,
            fpsRange
        )
        previewExt.setCaptureRequestOption(
            android.hardware.camera2.CaptureRequest.CONTROL_AF_MODE,
            android.hardware.camera2.CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE
        )

        val preview = previewBuilder.build().also {
            it.setSurfaceProvider(binding.cameraPreviewView.surfaceProvider)
        }

        @Suppress("DEPRECATION")
        val imageAnalysisBuilder = ImageAnalysis.Builder()
            .setTargetResolution(targetSize)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)

        val analysisExt = androidx.camera.camera2.interop.Camera2Interop.Extender(imageAnalysisBuilder)
        analysisExt.setCaptureRequestOption(
            android.hardware.camera2.CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,
            fpsRange
        )

        val imageAnalysis = imageAnalysisBuilder.build()

        imageAnalysis.setAnalyzer(cameraExecutor!!) { imageProxy ->
            processFrameForStream(imageProxy)
        }

        try {
            provider.unbindAll()
            camera = provider.bindToLifecycle(this, cameraSelector, preview, imageAnalysis)
            isTorchOn = false
        } catch (e: Exception) {
            Log.e(TAG, "Binding use cases failed: ${e.message}")
        }
    }

    private fun toggleTorch() {
        camera?.let { cam ->
            if (cam.cameraInfo.hasFlashUnit()) {
                isTorchOn = !isTorchOn
                cam.cameraControl.enableTorch(isTorchOn)
            }
        }
    }

    private fun startStream(hostIp: String, port: Int) {
        stopStream()

        binding.btnCamStreamToggle.text = "Connecting..."
        binding.tvCamStatus.text = "● Connecting..."

        streamJob = scope.launch {
            try {
                // Remotely wake up ZeroCam module on PC if not active
                NetworkDiscovery.wakeModule(hostIp, "zerocam")
                delay(200)

                var s: Socket? = null
                var lastErr: Exception? = null
                for (attempt in 1..3) {
                    try {
                        val sock = Socket()
                        sock.tcpNoDelay = true
                        sock.connect(InetSocketAddress(hostIp, port), 2500)
                        s = sock
                        break
                    } catch (e: Exception) {
                        lastErr = e
                        if (attempt < 3) {
                            NetworkDiscovery.wakeModule(hostIp, "zerocam")
                            delay(350)
                        }
                    }
                }
                if (s == null) {
                    throw lastErr ?: Exception("Unable to connect to PC ZeroCam server")
                }

                socket = s
                outStream = s.getOutputStream()

                // Send initial handshake
                val hs = JSONObject().apply {
                    put("action", "CONNECT")
                    put("model", Build.MODEL)
                    put("device_model", Build.MODEL)
                    put("width", targetWidth)
                    put("height", targetHeight)
                }
                outStream?.write((hs.toString() + "\n").toByteArray(Charsets.UTF_8))
                outStream?.flush()

                isStreaming = true
                val isWired = hostIp == "127.0.0.1" || hostIp == "localhost"
                val resTag = if (targetWidth >= 3840) "4K" else if (targetWidth >= 1920) "1080p" else "720p"
                withContext(Dispatchers.Main) {
                    binding.btnCamStreamToggle.text = "Stop Webcam Stream"
                    binding.tvCamStatus.text = if (isWired) "● LIVE $resTag (⚡ Wired USB)" else "● LIVE $resTag (📡 Wi-Fi)"
                }

                // Initialize Hardware H.264 Encoder if enabled
                if (useH264Hardware) {
                    initH264Encoder(targetWidth, targetHeight)
                }

                // Launch dedicated non-blocking network frame sender
                senderJob = scope.launch {
                    for (packet in frameChannel) {
                        val out = outStream ?: break
                        try {
                            out.write(packet)
                            out.flush()
                        } catch (e: Exception) {
                            break
                        }
                    }
                }

                // Listen for control commands from PC
                val inStream = s.getInputStream()
                val reader = inStream.bufferedReader()
                while (isActive && !s.isClosed) {
                    val line = reader.readLine() ?: break
                    handlePcCommand(line)
                }

            } catch (e: Exception) {
                Log.e(TAG, "Stream error: ${e.message}")
            } finally {
                withContext(NonCancellable) {
                    withContext(Dispatchers.Main) {
                        stopStream()
                    }
                }
            }
        }
    }

    private fun handlePcCommand(cmdText: String) {
        try {
            val json = JSONObject(cmdText)
            val action = json.optString("action")
            when (action) {
                "SWITCH_CAMERA" -> {
                    runOnUiThread {
                        useFrontCamera = !useFrontCamera
                        bindCameraUseCases()
                    }
                }
                "TOGGLE_TORCH" -> {
                    runOnUiThread {
                        toggleTorch()
                    }
                }
                "SET_RESOLUTION" -> {
                    val w = json.optInt("width", 1920)
                    val h = json.optInt("height", 1080)
                    runOnUiThread {
                        switchResolution(w, h)
                    }
                }
                "SET_QUALITY" -> {
                    val q = json.optInt("quality", 90)
                    jpegQuality = q
                }
                "SET_ZOOM" -> {
                    val zoom = json.optDouble("zoom", 0.0).toFloat()
                    camera?.cameraControl?.setLinearZoom(zoom.coerceIn(0f, 1f))
                }
                "SET_EXPOSURE" -> {
                    val exp = json.optInt("exposure", 0)
                    camera?.cameraControl?.setExposureCompensationIndex(exp)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Command parsing error: ${e.message}")
        }
    }

    private fun processFrameForStream(imageProxy: ImageProxy) {
        if (!isStreaming) {
            imageProxy.close()
            return
        }

        // Hardware H.264 Path: GPU encoding directly from camera YUV buffer (< 1ms CPU)
        if (useH264Hardware) {
            val w = imageProxy.width
            val h = imageProxy.height
            if (h264Encoder == null || h264Encoder?.width != w || h264Encoder?.height != h) {
                initH264Encoder(w, h)
            }
            val enc = h264Encoder
            if (enc?.isAvailable() == true) {
                try {
                    enc.encodeFrame(imageProxy)
                    val now = System.currentTimeMillis()
                    if (now - lastStatTime >= 1000) {
                        val dt = (now - lastStatTime) / 1000f
                        val fps = frameCount / dt
                        val avgKb = if (frameCount > 0) (bytesThisSec / frameCount / 1024) else 0
                        val mbps = (bytesThisSec * 8f) / (dt * 1_000_000f)
                        frameCount = 0
                        bytesThisSec = 0
                        lastStatTime = now
                        runOnUiThread {
                            binding.tvCamFps.text = "⚡ H.264 ${fps.toInt()} FPS • ${avgKb}KB/f • ${String.format("%.1f", mbps)}M"
                        }
                    }
                    imageProxy.close()
                    return
                } catch (e: Exception) {
                    Log.e(TAG, "Hardware H.264 encode error, fallback to JPEG: ${e.message}")
                }
            }
        }

        // Turbo JPEG Safe Path: 100% Reliable, Zero Green Screen, Fast Compression
        try {
            val bitmap = imageProxy.toBitmap()
            baos.reset()
            bitmap.compress(Bitmap.CompressFormat.JPEG, 75, baos)
            val jpegBytes = baos.toByteArray()
            bitmap.recycle()

            // Construct [ZCAM][Length (4B)][Timestamp (8B)][Rotation (2B)][Flags (2B)][Bytes]
            val payloadLen = jpegBytes.size
            val nowMs = System.currentTimeMillis()
            val rotationDeg = imageProxy.imageInfo.rotationDegrees

            val packet = ByteArray(20 + payloadLen)
            val buf = ByteBuffer.wrap(packet)
            buf.put("ZCAM".toByteArray(Charsets.US_ASCII))
            buf.putInt(payloadLen)
            buf.putLong(nowMs)
            buf.putShort(rotationDeg.toShort())
            buf.putShort(0.toShort())
            System.arraycopy(jpegBytes, 0, packet, 20, payloadLen)

            frameChannel.trySend(packet)

            frameCount++
            bytesThisSec += packet.size
            val now = System.currentTimeMillis()
            if (now - lastStatTime >= 1000) {
                val dt = (now - lastStatTime) / 1000f
                val fps = frameCount / dt
                val avgKb = if (frameCount > 0) (bytesThisSec / frameCount / 1024) else 0
                val mbps = (bytesThisSec * 8f) / (dt * 1_000_000f)
                frameCount = 0
                bytesThisSec = 0
                lastStatTime = now
                runOnUiThread {
                    binding.tvCamFps.text = "📸 JPEG ${fps.toInt()} FPS • ${avgKb}KB/f • ${String.format("%.1f", mbps)}M"
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "Frame stream error: ${e.message}")
        } finally {
            imageProxy.close()
        }
    }

    private fun stopStream() {
        isStreaming = false
        h264Encoder?.stop()
        h264Encoder = null
        senderJob?.cancel()
        senderJob = null
        streamJob?.cancel()
        streamJob = null
        try {
            socket?.close()
        } catch (e: Exception) {}
        socket = null
        outStream = null

        runOnUiThread {
            binding.btnCamStreamToggle.text = "Start Webcam Stream"
            binding.tvCamStatus.text = "○ Camera Ready"
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopStream()
        cameraExecutor?.shutdown()
    }
}
