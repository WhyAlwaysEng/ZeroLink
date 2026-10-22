package com.zerocast.capture

import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import com.zerocast.network.StreamSender
import com.zerocast.protocol.PacketHeader
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

class ScreenCaptureManager(
    private val mediaProjection: MediaProjection,
    private val width: Int,
    private val height: Int,
    private val dpi: Int,
    private val targetFps: Int = 30,
    private val jpegQuality: Int = 75,
    private val streamSender: StreamSender
) {
    companion object {
        private const val TAG = "ScreenCapture"
    }

    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var backgroundThread: HandlerThread? = null
    private var backgroundHandler: Handler? = null
    private val isRunning = AtomicBoolean(false)

    private val minFrameIntervalNs = (1_000_000_000L / targetFps.coerceAtLeast(1))
    private var lastFrameTimeNs = 0L

    private var reusableBitmap: Bitmap? = null
    private val baos = ByteArrayOutputStream(64 * 1024)

    fun start() {
        if (isRunning.getAndSet(true)) return

        backgroundThread = HandlerThread("ZeroCast-ScreenCapture").apply { start() }
        backgroundHandler = Handler(backgroundThread!!.looper)

        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2).apply {
            setOnImageAvailableListener({ reader ->
                onImageAvailable(reader)
            }, backgroundHandler)
        }

        virtualDisplay = mediaProjection.createVirtualDisplay(
            "ZeroCast-VirtualDisplay",
            width,
            height,
            dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface,
            null,
            backgroundHandler
        )

        Log.d(TAG, "Screen capture started: ${width}x${height} @ ${targetFps} FPS (Quality: $jpegQuality%)")
    }

    private fun onImageAvailable(reader: ImageReader) {
        var image: Image? = null
        try {
            image = reader.acquireLatestImage() ?: return

            val nowNs = System.nanoTime()
            if (nowNs - lastFrameTimeNs < minFrameIntervalNs) {
                return // Throttle to target FPS
            }
            lastFrameTimeNs = nowNs

            val planes = image.planes
            val buffer = planes[0].buffer
            val pixelStride = planes[0].pixelStride
            val rowStride = planes[0].rowStride
            val rowPadding = rowStride - pixelStride * width

            // Create or reuse bitmap
            val fullBitmapWidth = width + rowPadding / pixelStride
            if (reusableBitmap == null || reusableBitmap!!.width != fullBitmapWidth || reusableBitmap!!.height != height) {
                reusableBitmap?.recycle()
                reusableBitmap = Bitmap.createBitmap(fullBitmapWidth, height, Bitmap.Config.ARGB_8888)
            }

            val bmp = reusableBitmap ?: return
            bmp.copyPixelsFromBuffer(buffer)

            // Crop rowStride padding if present
            val finalBitmap = if (rowPadding == 0) {
                bmp
            } else {
                Bitmap.createBitmap(bmp, 0, 0, width, height)
            }

            baos.reset()
            finalBitmap.compress(Bitmap.CompressFormat.JPEG, jpegQuality, baos)
            val jpegBytes = baos.toByteArray()

            if (finalBitmap != bmp) {
                finalBitmap.recycle()
            }

            val flags: Byte = if (width > height) PacketHeader.FLAG_ORIENTATION_LANDSCAPE else 0
            streamSender.enqueueFrame(PacketHeader.TYPE_VIDEO_MJPEG, flags, jpegBytes)

        } catch (e: Exception) {
            Log.e(TAG, "Error capturing screen frame: ${e.message}")
        } finally {
            image?.close()
        }
    }

    fun stop() {
        if (!isRunning.getAndSet(false)) return
        try {
            virtualDisplay?.release()
            virtualDisplay = null
            imageReader?.close()
            imageReader = null
            reusableBitmap?.recycle()
            reusableBitmap = null
            backgroundThread?.quitSafely()
            backgroundThread = null
            backgroundHandler = null
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping screen capture: ${e.message}")
        }
    }
}
