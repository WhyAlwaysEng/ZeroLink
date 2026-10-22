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
    private var jpegQuality = 90

    private var socket: Socket? = null
    private var outStream: OutputStream? = null
    private var streamJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO)

    private var discovery: NetworkDiscovery? = null

    private var frameCount = 0
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

    private fun bindCameraUseCases() {
        val provider = cameraProvider ?: return
        val cameraSelector = if (useFrontCamera) {
            CameraSelector.DEFAULT_FRONT_CAMERA
        } else {
            CameraSelector.DEFAULT_BACK_CAMERA
        }

        val targetSize = android.util.Size(targetWidth, targetHeight)

        @Suppress("DEPRECATION")
        val preview = Preview.Builder()
            .setTargetResolution(targetSize)
            .build()
            .also {
                it.setSurfaceProvider(binding.cameraPreviewView.surfaceProvider)
            }

        @Suppress("DEPRECATION")
        val imageAnalysis = ImageAnalysis.Builder()
            .setTargetResolution(targetSize)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
            .build()

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
                withContext(Dispatchers.Main) {
                    binding.btnCamStreamToggle.text = "Stop Webcam Stream"
                    binding.tvCamStatus.text = "● LIVE (Broadcasting to PC)"
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
        if (!isStreaming || outStream == null) {
            imageProxy.close()
            return
        }

        try {
            val planes = imageProxy.planes
            val buffer: ByteBuffer = planes[0].buffer
            val pixelStride = planes[0].pixelStride
            val rowStride = planes[0].rowStride
            val rowPadding = rowStride - pixelStride * imageProxy.width

            val bitmap = Bitmap.createBitmap(
                imageProxy.width + rowPadding / pixelStride,
                imageProxy.height,
                Bitmap.Config.ARGB_8888
            )
            bitmap.copyPixelsFromBuffer(buffer)

            val rotationDegrees = imageProxy.imageInfo.rotationDegrees
            val matrix = Matrix()
            if (rotationDegrees != 0) {
                matrix.postRotate(rotationDegrees.toFloat())
            }

            val finalBitmap = if (rotationDegrees != 0 || rowPadding > 0) {
                Bitmap.createBitmap(bitmap, 0, 0, imageProxy.width, imageProxy.height, matrix, false)
            } else {
                bitmap
            }

            baos.reset()
            finalBitmap.compress(Bitmap.CompressFormat.JPEG, jpegQuality, baos)
            val jpegBytes = baos.toByteArray()

            if (finalBitmap != bitmap) {
                finalBitmap.recycle()
            }
            bitmap.recycle()

            // Construct [ZCAM][Length (4B)][Timestamp (8B)][Bytes]
            val payloadLen = jpegBytes.size
            val nowMs = System.currentTimeMillis()

            val header = ByteBuffer.allocate(16)
            header.put("ZCAM".toByteArray(Charsets.US_ASCII))
            header.putInt(payloadLen)
            header.putLong(nowMs)

            val out = outStream
            if (out != null) {
                synchronized(out) {
                    out.write(header.array())
                    out.write(jpegBytes)
                    out.flush()
                }
            }

            frameCount++
            val now = System.currentTimeMillis()
            if (now - lastStatTime >= 1000) {
                val fps = frameCount * 1000f / (now - lastStatTime)
                frameCount = 0
                lastStatTime = now
                runOnUiThread {
                    binding.tvCamFps.text = "${fps.toInt()} FPS"
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
