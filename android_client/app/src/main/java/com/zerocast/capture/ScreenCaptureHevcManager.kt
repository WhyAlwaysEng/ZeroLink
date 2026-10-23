package com.zerocast.capture

import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.projection.MediaProjection
import android.os.Bundle
import android.util.Log
import android.view.Surface
import com.zerocast.network.StreamSender
import com.zerocast.protocol.PacketHeader
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

class ScreenCaptureHevcManager(
    private val mediaProjection: MediaProjection,
    private val width: Int,
    private val height: Int,
    private val dpi: Int,
    private val targetFps: Int = 60,
    private val bitrateKbps: Int = 8000,
    private val streamSender: StreamSender,
    private val useCbrCap: Boolean = true
) {
    companion object {
        private const val TAG = "ScreenCaptureHEVC"
        private const val MIME_TYPE = MediaFormat.MIMETYPE_VIDEO_HEVC
    }

    private var mediaCodec: MediaCodec? = null
    private var inputSurface: Surface? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var drainThread: Thread? = null
    private val isRunning = AtomicBoolean(false)
    private var vpsSpsPpsBuffer: ByteArray? = null

    fun start() {
        if (isRunning.getAndSet(true)) return

        try {
            // Ensure width and height are multiples of 2
            val alignedWidth = (width + 1) and 1.inv()
            val alignedHeight = (height + 1) and 1.inv()

            // Probe if hardware encoder supports CBR (Constant Bitrate)
            val isCbrSupported = try {
                val probeCodec = MediaCodec.createEncoderByType(MIME_TYPE)
                val supported = probeCodec.codecInfo.getCapabilitiesForType(MIME_TYPE)
                    .encoderCapabilities.isBitrateModeSupported(MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)
                probeCodec.release()
                supported
            } catch (_: Exception) {
                false
            }

            val bitrateMode = if (useCbrCap && isCbrSupported) {
                Log.d(TAG, "HEVC Bitrate Mode: BITRATE_MODE_CBR (Strict Bandwidth Cap)")
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR
            } else {
                Log.d(TAG, "HEVC Bitrate Mode: BITRATE_MODE_VBR (Adaptive Dynamic)")
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR
            }

            val format = MediaFormat.createVideoFormat(MIME_TYPE, alignedWidth, alignedHeight).apply {
                setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
                setInteger(MediaFormat.KEY_BIT_RATE, bitrateKbps * 1000)
                setInteger(MediaFormat.KEY_FRAME_RATE, targetFps)
                setInteger(MediaFormat.KEY_CAPTURE_RATE, targetFps)
                setInteger(MediaFormat.KEY_OPERATING_RATE, targetFps)

                // Hardware-level framerate constraints
                setFloat(MediaFormat.KEY_MAX_FPS_TO_ENCODER, targetFps.toFloat())
                setInteger("max-fps-to-encoder", targetFps)
                setFloat("max-fps-to-encoder", targetFps.toFloat())
                setInteger("max-fps", targetFps)
                setInteger("frame-rate", targetFps)

                // Ultra Low-Latency Tuning: Strictly disable B-Frames (0 lookahead delay)
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                    try {
                        setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0)
                    } catch (_: Exception) {}
                }
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                    try {
                        setInteger(MediaFormat.KEY_LATENCY, 0) // 0 = lowest possible encoder latency
                    } catch (_: Exception) {}
                }
                try {
                    setInteger(MediaFormat.KEY_PRIORITY, 0) // 0 = Realtime Priority
                } catch (_: Exception) {}

                // Motion Estimation & Speed optimization (CRITICAL FOR HIGH MOTION)
                // Complexity 0 instructs hardware encoder to use fastest motion estimation
                try {
                    setInteger(MediaFormat.KEY_COMPLEXITY, 0)
                } catch (_: Exception) {}

                // Bitrate ceiling to prevent 4x-5x burst explosion during rapid motion
                try {
                    val maxBitrate = (bitrateKbps * 1.25).toInt() * 1000
                    setInteger("max-bitrate", maxBitrate)
                } catch (_: Exception) {}

                // Vendor-specific extensions to suppress heavy filters and lookahead queues
                try {
                    setInteger("vendor.qcom-ext-enc-b-frame.enable", 0)
                    setInteger("vendor.rtc-ext-enc-low-latency.enable", 1)
                    setInteger("vendor.mediatek.ext-enc-low-latency", 1)
                    // Disable heavy SAO (Sample Adaptive Offset) filter which chokes mobile GPU on fast scenes
                    setInteger("vendor.qcom-ext-enc-caps.sao.enable", 0)
                    setInteger("vendor.qcom-ext-enc-sao.enable", 0)
                    setInteger("vendor.qcom-ext-enc-caps.preprocess.enable", 0)
                    // MediaTek speed preset: 1 = speed priority over compression
                    setInteger("vendor.mediatek.ext-enc-speed-preset", 1)
                } catch (_: Exception) {}

                setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1) // Keyframe every 1s for fast recovery and smooth motion
                try {
                    setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.HEVCProfileMain)
                } catch (_: Exception) {}
                setInteger(MediaFormat.KEY_BITRATE_MODE, bitrateMode)
                setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 10_000_000L)
            }

            mediaCodec = MediaCodec.createEncoderByType(MIME_TYPE)
            mediaCodec?.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            inputSurface = mediaCodec?.createInputSurface()
            mediaCodec?.start()

            try {
                val fpsBundle = Bundle().apply {
                    putFloat("max-fps-to-encoder", targetFps.toFloat())
                    putInt("max-fps-to-encoder", targetFps)
                    putInt("max-fps", targetFps)
                    putInt("frame-rate", targetFps)
                }
                mediaCodec?.setParameters(fpsBundle)
            } catch (_: Exception) {}

            requestKeyFrame()

            virtualDisplay = mediaProjection.createVirtualDisplay(
                "ZeroCast-HEVCDisplay",
                alignedWidth,
                alignedHeight,
                dpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                inputSurface,
                null,
                null
            )

            drainThread = Thread({
                drainEncoder()
            }, "ZeroCast-HEVCDrain")
            drainThread?.start()

            Log.d(TAG, "Hardware H.265 / HEVC encoder started: ${alignedWidth}x${alignedHeight} @ ${targetFps} FPS (${bitrateKbps} Kbps)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start HEVC hardware capture: ${e.message}", e)
            stop()
            throw e // Let caller fallback to H.264
        }
    }

    fun requestKeyFrame() {
        try {
            val params = Bundle().apply {
                putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0)
            }
            mediaCodec?.setParameters(params)
        } catch (_: Exception) {}
    }

    fun updateBitrate(newBitrateKbps: Int) {
        try {
            val params = Bundle().apply {
                putInt(MediaCodec.PARAMETER_KEY_VIDEO_BITRATE, newBitrateKbps * 1000)
            }
            mediaCodec?.setParameters(params)
            Log.d(TAG, "Dynamic Adaptive Bitrate adjusted to ${newBitrateKbps} Kbps (HEVC)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to dynamically adjust HEVC bitrate: ${e.message}")
        }
    }

    private fun drainEncoder() {
        val codec = mediaCodec ?: return
        val bufferInfo = MediaCodec.BufferInfo()

        while (isRunning.get()) {
            try {
                val outputIndex = codec.dequeueOutputBuffer(bufferInfo, 10_000)
                if (outputIndex >= 0) {
                    val outputBuffer: ByteBuffer? = codec.getOutputBuffer(outputIndex)
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
                            // Store VPS / SPS / PPS
                            vpsSpsPpsBuffer = nalu
                        }

                        val alreadyHasVps = if (nalu.size >= 5) {
                            val off = if (nalu[2] == 1.toByte()) 3 else 4
                            val nType = (nalu[off].toInt() and 0x7E) shr 1
                            nType == 32
                        } else false

                        val payload = if (isKeyframe && vpsSpsPpsBuffer != null && !isConfig && !alreadyHasVps) {
                            vpsSpsPpsBuffer!! + nalu
                        } else {
                            nalu
                        }

                        var flags: Byte = 0
                        if (isKeyframe) {
                            flags = (flags.toInt() or PacketHeader.FLAG_KEYFRAME.toInt()).toByte()
                        }
                        if (isConfig) {
                            flags = (flags.toInt() or PacketHeader.FLAG_CODEC_CONFIG.toInt()).toByte()
                        }
                        if (width > height) {
                            flags = (flags.toInt() or PacketHeader.FLAG_ORIENTATION_LANDSCAPE.toInt()).toByte()
                        }

                        streamSender.enqueueFrame(PacketHeader.TYPE_VIDEO_HEVC, flags, payload)
                    }
                    codec.releaseOutputBuffer(outputIndex, false)
                }
            } catch (e: Exception) {
                if (isRunning.get()) {
                    Log.e(TAG, "HEVC Drain error: ${e.message}")
                }
                break
            }
        }
    }

    fun stop() {
        if (!isRunning.getAndSet(false)) return
        try {
            drainThread?.interrupt()
            drainThread = null
            virtualDisplay?.release()
            virtualDisplay = null
            mediaCodec?.stop()
            mediaCodec?.release()
            mediaCodec = null
            inputSurface?.release()
            inputSurface = null
            vpsSpsPpsBuffer = null
            Log.d(TAG, "HEVC capture stopped.")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping HEVC: ${e.message}")
        }
    }
}
