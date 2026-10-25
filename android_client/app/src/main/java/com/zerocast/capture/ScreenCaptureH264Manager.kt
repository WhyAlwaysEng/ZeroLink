package com.zerocast.capture

import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.projection.MediaProjection
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Surface
import com.zerocast.network.StreamSender
import com.zerocast.protocol.PacketHeader
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

class ScreenCaptureH264Manager(
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
        private const val TAG = "ScreenCaptureH264"
        private const val MIME_TYPE = MediaFormat.MIMETYPE_VIDEO_AVC
    }

    private var mediaCodec: MediaCodec? = null
    private var inputSurface: Surface? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var drainThread: Thread? = null
    private val isRunning = AtomicBoolean(false)
    private var spsPpsBuffer: ByteArray? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var lastFrameTimeNs = 0L
    private val minFrameIntervalNs = (1_000_000_000L / targetFps.coerceAtLeast(1))

    fun start() {
        if (isRunning.getAndSet(true)) return

        try {
            // Ensure width and height are multiples of 2
            val alignedWidth = (width + 1) and 1.inv()
            val alignedHeight = (height + 1) and 1.inv()

            // Probe if hardware encoder supports CBR (Constant Bitrate / Hard Ceiling)
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
                Log.d(TAG, "Bitrate Mode: BITRATE_MODE_CBR (Strict Bandwidth Cap / Hard Ceiling)")
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR
            } else {
                Log.d(TAG, "Bitrate Mode: BITRATE_MODE_VBR (Adaptive Dynamic)")
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR
            }

            val format = MediaFormat.createVideoFormat(MIME_TYPE, alignedWidth, alignedHeight).apply {
                setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
                setInteger(MediaFormat.KEY_BIT_RATE, bitrateKbps * 1000)
                setInteger(MediaFormat.KEY_FRAME_RATE, targetFps)
                setInteger(MediaFormat.KEY_CAPTURE_RATE, targetFps)
                setInteger(MediaFormat.KEY_OPERATING_RATE, targetFps)

                // Hardware-level framerate constraints for high-refresh displays (90Hz / 120Hz)
                setFloat(MediaFormat.KEY_MAX_FPS_TO_ENCODER, targetFps.toFloat())
                setInteger("max-fps-to-encoder", targetFps)
                setFloat("max-fps-to-encoder", targetFps.toFloat())
                setInteger("max-fps", targetFps)
                setInteger("frame-rate", targetFps)

                setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1) // Keyframe every 1s
                // Baseline Profile for ZERO decoder buffer latency (no B-frames)
                setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
                setInteger(MediaFormat.KEY_BITRATE_MODE, bitrateMode)

                // Low-Latency Realtime Priority & Speed optimization
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    try {
                        setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0)
                    } catch (_: Exception) {}
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    try {
                        setInteger(MediaFormat.KEY_LATENCY, 0)
                    } catch (_: Exception) {}
                }
                try {
                    setInteger(MediaFormat.KEY_PRIORITY, 0) // Realtime priority
                } catch (_: Exception) {}
                try {
                    setInteger(MediaFormat.KEY_COMPLEXITY, 0) // Fastest motion estimation
                } catch (_: Exception) {}

                // Idle refresh: set to 10 seconds so it doesn't pump redundant ghost frames every 100ms
                setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 10_000_000L)
            }

            mediaCodec = MediaCodec.createEncoderByType(MIME_TYPE)
            mediaCodec?.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            inputSurface = mediaCodec?.createInputSurface()
            mediaCodec?.start()

            // Pass dynamic runtime parameters to enforce max FPS on vendor OMX/C2 drivers
            try {
                val fpsBundle = Bundle().apply {
                    putFloat("max-fps-to-encoder", targetFps.toFloat())
                    putInt("max-fps-to-encoder", targetFps)
                    putInt("max-fps", targetFps)
                    putInt("frame-rate", targetFps)
                }
                mediaCodec?.setParameters(fpsBundle)
            } catch (_: Exception) {}

            // Request initial sync frame
            requestKeyFrame()

            virtualDisplay = mediaProjection.createVirtualDisplay(
                "ZeroCast-H264Display",
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
            }, "ZeroCast-H264Drain")
            drainThread?.start()

            Log.d(TAG, "Hardware H.264 Baseline encoder started: ${alignedWidth}x${alignedHeight} @ ${targetFps} FPS (${bitrateKbps} Kbps)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start H.264 hardware capture: ${e.message}", e)
            stop()
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
            Log.d(TAG, "Dynamic Adaptive Bitrate adjusted to ${newBitrateKbps} Kbps")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to dynamically adjust bitrate: ${e.message}")
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

                        // Note: For H.264 predictive encoding, we MUST NOT drop output P-frames here.
                        // Dropping encoded P-frames breaks the macroblock reference chain and causes severe artifacting.
                        // Framerate throttling is safely handled by KEY_MAX_FPS_TO_ENCODER at the input surface level.

                        // Ensure Annex B start code 0x00000001
                        val hasStartCode = chunk.size >= 4 && chunk[0] == 0.toByte() && chunk[1] == 0.toByte() &&
                                ((chunk[2] == 1.toByte()) || (chunk[2] == 0.toByte() && chunk[3] == 1.toByte()))
                        val nalu = if (hasStartCode) chunk else byteArrayOf(0, 0, 0, 1) + chunk

                        if (isConfig) {
                            // Store SPS / PPS with guaranteed start code
                            spsPpsBuffer = nalu
                        }

                        // When sending a Keyframe, prepend SPS/PPS if available to guarantee instant decoding
                        val payload = if (isKeyframe && spsPpsBuffer != null && !isConfig) {
                            spsPpsBuffer!! + nalu
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

                        streamSender.enqueueFrame(PacketHeader.TYPE_VIDEO_H264, flags, payload)
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
            spsPpsBuffer = null
            Log.d(TAG, "H.264 capture stopped.")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping H.264: ${e.message}")
        }
    }
}
