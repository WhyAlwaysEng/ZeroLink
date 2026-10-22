package com.zerocast.capture

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.util.Log
import android.util.Size
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.zerocast.network.StreamSender
import com.zerocast.protocol.PacketHeader
import java.io.ByteArrayOutputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class CameraCaptureManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val useFrontCamera: Boolean = false,
    private val targetWidth: Int = 1280,
    private val targetHeight: Int = 720,
    private val jpegQuality: Int = 75,
    private val streamSender: StreamSender
) {
    companion object {
        private const val TAG = "CameraCapture"
    }

    private var cameraExecutor: ExecutorService? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private val isRunning = AtomicBoolean(false)
    private val baos = ByteArrayOutputStream(64 * 1024)

    fun start() {
        if (isRunning.getAndSet(true)) return

        cameraExecutor = Executors.newSingleThreadExecutor()
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)

        cameraProviderFuture.addListener({
            try {
                cameraProvider = cameraProviderFuture.get()
                bindCameraUseCases()
            } catch (e: Exception) {
                Log.e(TAG, "Camera provider binding failed: ${e.message}", e)
            }
        }, ContextCompat.getMainExecutor(context))
    }

    private fun bindCameraUseCases() {
        val provider = cameraProvider ?: return
        val cameraSelector = if (useFrontCamera) {
            CameraSelector.DEFAULT_FRONT_CAMERA
        } else {
            CameraSelector.DEFAULT_BACK_CAMERA
        }

        val imageAnalysis = ImageAnalysis.Builder()
            .setTargetResolution(Size(targetWidth, targetHeight))
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
            .build()

        imageAnalysis.setAnalyzer(cameraExecutor!!) { imageProxy ->
            processCameraFrame(imageProxy)
        }

        try {
            provider.unbindAll()
            provider.bindToLifecycle(lifecycleOwner, cameraSelector, imageAnalysis)
            Log.d(TAG, "Camera streaming bound successfully.")
        } catch (e: Exception) {
            Log.e(TAG, "Use case binding failed: ${e.message}", e)
        }
    }

    private fun processCameraFrame(imageProxy: ImageProxy) {
        try {
            val bitmap = imageProxy.toBitmap()
            val rotation = imageProxy.imageInfo.rotationDegrees

            val finalBitmap = if (rotation != 0) {
                val matrix = Matrix().apply { postRotate(rotation.toFloat()) }
                Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
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

            val flags: Byte = if (imageProxy.width > imageProxy.height) PacketHeader.FLAG_ORIENTATION_LANDSCAPE else 0
            streamSender.enqueueFrame(PacketHeader.TYPE_VIDEO_MJPEG, flags, jpegBytes)

        } catch (e: Exception) {
            Log.e(TAG, "Camera frame process error: ${e.message}")
        } finally {
            imageProxy.close()
        }
    }

    fun stop() {
        if (!isRunning.getAndSet(false)) return
        try {
            cameraProvider?.unbindAll()
            cameraExecutor?.shutdown()
            cameraExecutor = null
            cameraProvider = null
            Log.d(TAG, "Camera capture stopped.")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping camera: ${e.message}")
        }
    }
}
