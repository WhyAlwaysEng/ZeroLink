package com.zerocast.capture

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.os.Build
import android.util.Log
import com.zerocast.network.StreamSender
import com.zerocast.protocol.PacketHeader
import java.util.concurrent.atomic.AtomicBoolean

class AudioCaptureManager(
    private val mediaProjection: MediaProjection,
    private val streamSender: StreamSender,
    private val sampleRate: Int = 48000
) {
    companion object {
        private const val TAG = "ZeroCast-Audio"
    }

    private var audioRecord: AudioRecord? = null
    private var recordThread: Thread? = null
    private val isRecording = AtomicBoolean(false)

    @SuppressLint("MissingPermission")
    fun start() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Log.w(TAG, "AudioPlaybackCapture requires Android 10 (API 29) or higher.")
            return
        }

        if (isRecording.getAndSet(true)) return

        try {
            val config = AudioPlaybackCaptureConfiguration.Builder(mediaProjection)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                .addMatchingUsage(AudioAttributes.USAGE_GAME)
                .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                .build()

            val audioFormat = AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setSampleRate(sampleRate)
                .setChannelMask(AudioFormat.CHANNEL_IN_STEREO)
                .build()

            val minBufferSize = AudioRecord.getMinBufferSize(
                sampleRate,
                AudioFormat.CHANNEL_IN_STEREO,
                AudioFormat.ENCODING_PCM_16BIT
            )

            // 16KB buffer matches Android Audio HAL buffer quantum, preventing sample drops
            val bufferSize = if (minBufferSize > 0) {
                maxOf(minBufferSize * 2, 4096 * 4)
            } else {
                16384
            }

            val record = AudioRecord.Builder()
                .setAudioPlaybackCaptureConfig(config)
                .setAudioFormat(audioFormat)
                .setBufferSizeInBytes(bufferSize)
                .build()

            if (record.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord initialization failed! State: ${record.state}")
                record.release()
                stop()
                return
            }

            audioRecord = record
            record.startRecording()

            recordThread = Thread({
                // 4096 bytes matches Android Audio HAL buffer quantum (1024 stereo samples), perfectly aligned to 512/1024 frames
                val buffer = ByteArray(4096)
                while (isRecording.get() && record.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                    val read = record.read(buffer, 0, buffer.size)
                    if (read > 0) {
                        val pcmChunk = if (read == buffer.size) buffer else buffer.copyOf(read)
                        streamSender.enqueueFrame(PacketHeader.TYPE_AUDIO, 0, pcmChunk)
                    } else {
                        try {
                            Thread.sleep(2)
                        } catch (_: InterruptedException) {
                            break
                        }
                    }
                }
            }, "ZeroCast-AudioCapture")
            recordThread?.start()

            Log.d(TAG, "Internal Audio capture started ($sampleRate Hz Stereo).")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start internal audio capture: ${e.message}", e)
            stop()
        }
    }

    fun stop() {
        if (!isRecording.getAndSet(false)) return
        try {
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null
            recordThread?.interrupt()
            recordThread = null
            Log.d(TAG, "Audio capture stopped.")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping audio: ${e.message}")
        }
    }
}
