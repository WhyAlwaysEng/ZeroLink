package com.zerocast.ui

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
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
import com.zerocast.databinding.ActivityZeroCamBinding
import com.zerocast.network.NetworkDiscovery
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

    private var targetWidth = 1280
    private var targetHeight = 720
    private var jpegQuality = 65

    private var h264Encoder: CameraH264Encoder? = null
    private var useH264Hardware = true // GPU Hardware Encoder for 60 FPS Crystal Clarity

    private var socket: Socket? = null
    private var outStream: OutputStream? = null
    private var streamJob: Job? = null
    private var senderJob: Job? = null
    private var frameChannel = kotlinx.coroutines.channels.Channel<ByteArray>(kotlinx.coroutines.channels.Channel.CONFLATED)
    private val scope = CoroutineScope(Dispatchers.IO)

    private var discovery: NetworkDiscovery? = null

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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroCamBinding.inflate(layoutInflater)
        setContentView(binding.root)

        cameraExecutor = Executors.newSingleThreadExecutor()

        // Pre-fill Host IP
        val lastIp = ZeroLinkConfig.getServerIp(this)
        if (lastIp.isNotEmpty() && lastIp != "127.0.0.1") {
            binding.etCamHostIp.setText(lastIp)
        }

        discovery = NetworkDiscovery { discoveredIp, _ ->
            runOnUiThread {
                if (binding.etCamHostIp.text.isNullOrEmpty()) {
                    binding.etCamHostIp.setText(discoveredIp)
                }
            }
        }
        discovery?.startDiscovery()

        binding.btnCamBack.setOnClickListener {
            finish()
        }

        binding.btnCamSwitch.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            useFrontCamera = !useFrontCamera
            bindCameraUseCases()
        }

        binding.btnCamUsbMode.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etCamHostIp.setText("127.0.0.1")
            Toast.makeText(this, "⚡ USB Cable Mode Selected (127.0.0.1)", Toast.LENGTH_SHORT).show()
        }

        binding.btnCamAutoWifi.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            discovery?.startDiscovery()
            Toast.makeText(this, "📡 Searching for PC on Wi-Fi...", Toast.LENGTH_SHORT).show()
        }

        binding.btnCamTorch.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            toggleTorch()
        }

        binding.btnCamStreamToggle.setOnClickListener {
            if (isStreaming) {
                stopStream()
            } else {
                val ip = binding.etCamHostIp.text.toString().trim()
                if (ip.isEmpty()) {
                    Toast.makeText(this, "Please enter PC Host IP", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                ZeroLinkConfig.setServerIp(this, ip)
                startStream(ip, DEFAULT_PORT)
            }
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

        // Lock to 30 FPS Range to avoid HAL throttling down to 5-10 FPS in indoor lighting
        val previewExt = androidx.camera.camera2.interop.Camera2Interop.Extender(previewBuilder)
        previewExt.setCaptureRequestOption(
            android.hardware.camera2.CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,
            android.util.Range(30, 30)
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
            android.util.Range(30, 30)
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
                val s = Socket()
                s.tcpNoDelay = true
                s.connect(InetSocketAddress(hostIp, port), 4000)
                socket = s
                outStream = s.getOutputStream()

                // Send initial handshake
                val hs = JSONObject().apply {
                    put("action", "CONNECT")
                    put("model", Build.MODEL)
                    put("device_model", Build.MODEL)
                }
                outStream?.write((hs.toString() + "\n").toByteArray(Charsets.UTF_8))
                outStream?.flush()

                isStreaming = true
                val isWired = hostIp == "127.0.0.1" || hostIp == "localhost"
                withContext(Dispatchers.Main) {
                    binding.btnCamStreamToggle.text = "Stop Webcam Stream"
                    binding.tvCamStatus.text = if (isWired) "● LIVE (⚡ Wired USB Cable)" else "● LIVE (📡 Wi-Fi: $hostIp)"
                }

                // Initialize Hardware H.264 Encoder if enabled
                if (useH264Hardware) {
                    h264Encoder?.stop()
                    val enc = CameraH264Encoder(targetWidth, targetHeight, targetFps = 30, bitrateKbps = 5000) { nalBytes, isKeyframe, rotDeg ->
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
                        Log.i(TAG, "Hardware H.264 Encoder successfully started")
                    } else {
                        Log.w(TAG, "Hardware H.264 Encoder start failed; using high-speed dynamic JPEG stream")
                        h264Encoder = null
                    }
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
                withContext(Dispatchers.Main) {
                    stopStream()
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
                        targetWidth = w
                        targetHeight = h
                        bindCameraUseCases()
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
        if (useH264Hardware && h264Encoder?.isAvailable() == true) {
            try {
                h264Encoder?.encodeFrame(imageProxy)
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

        val t0 = System.currentTimeMillis()
        try {
            val bitmap = imageProxy.toBitmap()
            val t1 = System.currentTimeMillis()
            val finalBitmap = if (bitmap.width > targetWidth || bitmap.height > targetHeight) {
                val scale = minOf(targetWidth.toFloat() / bitmap.width, targetHeight.toFloat() / bitmap.height)
                val sw = (bitmap.width * scale).toInt()
                val sh = (bitmap.height * scale).toInt()
                Bitmap.createScaledBitmap(bitmap, sw, sh, true).also {
                    if (it != bitmap) bitmap.recycle()
                }
            } else {
                bitmap
            }
            val t2 = System.currentTimeMillis()

            baos.reset()
            finalBitmap.compress(Bitmap.CompressFormat.JPEG, jpegQuality, baos)
            val jpegBytes = baos.toByteArray()
            val t3 = System.currentTimeMillis()
            if (finalBitmap != bitmap) {
                finalBitmap.recycle()
            }
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
            Log.i("ZeroCamPerf", "w=${bitmap.width}x${bitmap.height} -> ${finalBitmap.width}x${finalBitmap.height} | toBmp=${t1-t0}ms scale=${t2-t1}ms comp=${t3-t2}ms | size=${jpegBytes.size/1024}KB")
            if (now - lastStatTime >= 1000) {
                val dt = (now - lastStatTime) / 1000f
                val fps = frameCount / dt
                val avgKb = if (frameCount > 0) (bytesThisSec / frameCount / 1024) else 0
                val mbps = (bytesThisSec * 8f) / (dt * 1_000_000f)
                frameCount = 0
                bytesThisSec = 0
                lastStatTime = now
                runOnUiThread {
                    binding.tvCamFps.text = "${fps.toInt()} FPS • ${avgKb}KB/f • ${String.format("%.1f", mbps)}M"
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

        binding.btnCamStreamToggle.text = "Start Webcam Stream"
        binding.tvCamStatus.text = "○ Camera Ready"
    }

    override fun onDestroy() {
        super.onDestroy()
        stopStream()
        discovery?.stopDiscovery()
        cameraExecutor?.shutdown()
    }
}
