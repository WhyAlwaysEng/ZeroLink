package com.zerocast.capture

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Bundle
import android.util.Log
import androidx.camera.core.ImageProxy
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

class CameraH264Encoder(
    private val width: Int,
    private val height: Int,
    private val targetFps: Int = 30,
    private val bitrateKbps: Int = 4000,
    private val onNalPacket: (packet: ByteArray, isKeyframe: Boolean, rotationDeg: Int) -> Unit
) {
    companion object {
        private const val TAG = "CameraH264"
        private const val MIME_TYPE = MediaFormat.MIMETYPE_VIDEO_AVC
    }

    private var mediaCodec: MediaCodec? = null
    private val isRunning = AtomicBoolean(false)
    private var drainThread: Thread? = null
    private var spsPpsBuffer: ByteArray? = null
    private var currentRotationDeg = 0
    var outputFramesCount = 0L
    var inputFramesCount = 0L

    fun start(): Boolean {
        if (isRunning.getAndSet(true)) return true

        try {
            val alignedWidth = (width + 1) and 1.inv()
            val alignedHeight = (height + 1) and 1.inv()

            val encoder = MediaCodec.createEncoderByType(MIME_TYPE)
            val caps = encoder.codecInfo.getCapabilitiesForType(MIME_TYPE)
            val colorFormat = caps.colorFormats.firstOrNull {
                it == MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420SemiPlanar ||
                it == MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Planar
            } ?: MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420SemiPlanar

            val format = MediaFormat.createVideoFormat(MIME_TYPE, alignedWidth, alignedHeight).apply {
                setInteger(MediaFormat.KEY_COLOR_FORMAT, colorFormat)
                setInteger(MediaFormat.KEY_BIT_RATE, bitrateKbps * 1000)
                setInteger(MediaFormat.KEY_FRAME_RATE, targetFps)
                setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
                setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
                setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR)
            }

            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            encoder.start()
            mediaCodec = encoder

            requestKeyFrame()

            drainThread = Thread({
                drainEncoder()
            }, "ZeroCam-H264Drain")
            drainThread?.start()

            Log.i(TAG, "Hardware H.264 Baseline Camera Encoder started: ${alignedWidth}x${alignedHeight} @ ${targetFps}fps (format=$colorFormat)")
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start H.264 camera encoder: ${e.message}")
            stop()
            return false
        }
    }

    fun isAvailable(): Boolean = isRunning.get() && mediaCodec != null

    fun requestKeyFrame() {
        try {
            val params = Bundle().apply {
                putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0)
            }
            mediaCodec?.setParameters(params)
        } catch (_: Exception) {}
    }

    fun encodeFrame(imageProxy: ImageProxy) {
        val codec = mediaCodec
        if (!isRunning.get() || codec == null) return

        try {
            inputFramesCount++
            currentRotationDeg = imageProxy.imageInfo.rotationDegrees
            val inputIndex = codec.dequeueInputBuffer(5_000)
            if (inputIndex >= 0) {
                val inputBuffer = codec.getInputBuffer(inputIndex)
                if (inputBuffer != null) {
                    inputBuffer.clear()
                    fillYuvBuffer(imageProxy, inputBuffer)
                    val pts = System.nanoTime() / 1000
                    codec.queueInputBuffer(inputIndex, 0, inputBuffer.position(), pts, 0)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Encode frame error: ${e.message}")
        }
    }

    private fun fillYuvBuffer(image: ImageProxy, out: ByteBuffer) {
        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]

        val yBuf = yPlane.buffer
        val uBuf = uPlane.buffer
        val vBuf = vPlane.buffer

        val w = image.width
        val h = image.height

        val yRowStride = yPlane.rowStride
        val yPixelStride = yPlane.pixelStride

        // Fast Y copy
        if (yRowStride == w && yPixelStride == 1) {
            out.put(yBuf)
        } else {
            val rowBytes = ByteArray(w)
            for (r in 0 until h) {
                yBuf.position(r * yRowStride)
                yBuf.get(rowBytes, 0, w)
                out.put(rowBytes, 0, w)
            }
        }

        // UV copy (Semiplanar NV12)
        val uvW = w / 2
        val uvH = h / 2
        val uRowStride = uPlane.rowStride
        val vRowStride = vPlane.rowStride
        val uPixelStride = uPlane.pixelStride
        val vPixelStride = vPlane.pixelStride

        for (r in 0 until uvH) {
            for (c in 0 until uvW) {
                out.put(uBuf.get(r * uRowStride + c * uPixelStride))
                out.put(vBuf.get(r * vRowStride + c * vPixelStride))
            }
        }
    }

    private fun drainEncoder() {
        val codec = mediaCodec ?: return
        val bufferInfo = MediaCodec.BufferInfo()

        while (isRunning.get()) {
            try {
                val outputIndex = codec.dequeueOutputBuffer(bufferInfo, 10_000)
                if (outputIndex >= 0) {
                    val outputBuffer = codec.getOutputBuffer(outputIndex)
                    if (outputBuffer != null && bufferInfo.size > 0) {
                        outputBuffer.position(bufferInfo.offset)
                        outputBuffer.limit(bufferInfo.offset + bufferInfo.size)

                        val chunk = ByteArray(bufferInfo.size)
                        outputBuffer.get(chunk)

                        val isConfig = (bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0
                        val isKeyframe = (bufferInfo.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0

                        val hasStartCode = chunk.size >= 4 && chunk[0] == 0.toByte() && chunk[1] == 0.toByte() &&
                                ((chunk[2] == 1.toByte()) || (chunk[2] == 0.toByte() && chunk[3] == 1.toByte()))
                        val nalu = if (hasStartCode) chunk else byteArrayOf(0, 0, 0, 1) + chunk

                        if (isConfig) {
                            spsPpsBuffer = nalu
                            onNalPacket(nalu, true, currentRotationDeg)
                        } else {
                            val payload = if (isKeyframe && spsPpsBuffer != null) {
                                spsPpsBuffer!! + nalu
                            } else {
                                nalu
                            }
                            outputFramesCount++
                        onNalPacket(payload, isKeyframe, currentRotationDeg)
                        }
                    }
                    codec.releaseOutputBuffer(outputIndex, false)
                }
            } catch (e: Exception) {
                if (isRunning.get()) {
                    Log.e(TAG, "Drain error: ${e.message}")
                }
                break
            }
        }
    }

    fun stop() {
        isRunning.set(false)
        try {
            drainThread?.join(400)
        } catch (_: Exception) {}
        drainThread = null

        try {
            mediaCodec?.stop()
            mediaCodec?.release()
        } catch (_: Exception) {}
        mediaCodec = null
        spsPpsBuffer = null
    }
}
