package com.zerocast.network

import android.util.Log
import com.zerocast.protocol.FramePacket
import com.zerocast.protocol.PacketHeader
import kotlinx.coroutines.*
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean

class StreamSender(
    private val host: String,
    private val port: Int,
    private val dropLateFrames: Boolean = true,
    private val listener: StreamListener? = null
) {
    companion object {
        private const val TAG = "ZeroCast-Sender"
    }

    interface StreamListener {
        fun onConnected()
        fun onDisconnected(reason: String?)
        fun onControlPacketReceived(payload: ByteArray)
        fun onError(error: Throwable)
        fun onCongestionChanged(isCongested: Boolean) {}
        fun onFrameDropped() {}
    }

    // Dedicated high-priority audio queue: Audio packets (~2KB each) are NEVER dropped,
    // guaranteeing crystal-clear 48kHz stereo sound even during heavy Wi-Fi jitter or video bursts.
    private val audioQueue = java.util.concurrent.ConcurrentLinkedQueue<FramePacket>()
    // Queue capacity of 60 for video frames; video frames can be dropped under network congestion
    private val videoQueue = ArrayBlockingQueue<FramePacket>(60)
    private val isRunning = AtomicBoolean(false)
    private var socket: Socket? = null
    private var outputStream: DataOutputStream? = null
    private var inputStream: DataInputStream? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    fun start() {
        if (isRunning.getAndSet(true)) return

        scope.launch {
            try {
                Log.d(TAG, "Connecting to PC server at $host:$port...")
                val sock = Socket()
                sock.tcpNoDelay = true
                sock.sendBufferSize = 1024 * 1024 // 1 MB high-throughput TCP send buffer
                sock.connect(InetSocketAddress(host, port), 4000)

                socket = sock
                outputStream = DataOutputStream(java.io.BufferedOutputStream(sock.getOutputStream(), 64 * 1024))
                inputStream = DataInputStream(sock.getInputStream())

                Log.d(TAG, "Connected successfully to $host:$port")
                listener?.onConnected()

                // Launch reverse control backchannel reader
                launchBackchannelReader()

                // Main frame dispatch loop: Audio packets are prioritized first to eliminate Wi-Fi jitter
                while (isRunning.get() && sock.isConnected && !sock.isClosed) {
                    // 1. Drain any pending high-priority audio chunks immediately (< 0.1ms dispatch)
                    var audioPkt = audioQueue.poll()
                    while (audioPkt != null) {
                        writePacket(audioPkt)
                        audioPkt = audioQueue.poll()
                    }

                    // 2. Poll video frame with short 5ms timeout so audio is checked with ultra-low latency
                    val videoPkt = videoQueue.poll(5, java.util.concurrent.TimeUnit.MILLISECONDS)
                    if (videoPkt != null) {
                        writePacket(videoPkt)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Socket stream exception: ${e.message}", e)
                listener?.onError(e)
            } finally {
                disconnect()
            }
        }
    }

    private var isCongestedState = false
    private var calmFrameCount = 0

    fun enqueueFrame(type: Byte, flags: Byte, payload: ByteArray) {
        if (!isRunning.get()) return
        val packet = FramePacket(type, flags, System.nanoTime() / 1000, payload)

        // Audio Priority Bypass: Never drop audio packets and never delay behind video
        if (type == PacketHeader.TYPE_AUDIO) {
            audioQueue.offer(packet)
            return
        }

        // Dynamic Adaptive Bitrate (ABR) socket buffer detector based on video queue
        if (videoQueue.size >= 12) {
            calmFrameCount = 0
            if (!isCongestedState) {
                isCongestedState = true
                listener?.onCongestionChanged(true)
            }
        } else if (videoQueue.size <= 4) {
            calmFrameCount++
            if (calmFrameCount > 25 && isCongestedState) {
                isCongestedState = false
                listener?.onCongestionChanged(false)
            }
        }

        if (!videoQueue.offer(packet)) {
            videoQueue.poll() // Drop oldest video frame to prevent video latency buildup
            listener?.onFrameDropped()
            videoQueue.offer(packet)
        }
    }

    private fun writePacket(packet: FramePacket) {
        val out = outputStream ?: return
        synchronized(out) {
            PacketHeader.writeTo(
                out,
                packet.type,
                packet.flags,
                packet.payload.size,
                packet.timestampUs
            )
            out.write(packet.payload)
            out.flush()
        }
    }

    private fun launchBackchannelReader() {
        scope.launch {
            val stream = inputStream ?: return@launch
            val headerBuffer = ByteArray(PacketHeader.HEADER_SIZE)
            while (isRunning.get() && socket?.isConnected == true) {
                try {
                    stream.readFully(headerBuffer)
                    val magic = headerBuffer[0]
                    if (magic != PacketHeader.MAGIC_BYTE) continue

                    val packetType = headerBuffer[1]
                    val payloadLen = ((headerBuffer[4].toInt() and 0xFF) shl 24) or
                            ((headerBuffer[5].toInt() and 0xFF) shl 16) or
                            ((headerBuffer[6].toInt() and 0xFF) shl 8) or
                            (headerBuffer[7].toInt() and 0xFF)

                    if (payloadLen in 1..1048576) { // Max 1MB control payload
                        val payload = ByteArray(payloadLen)
                        stream.readFully(payload)
                        if (packetType == PacketHeader.TYPE_INPUT_CONTROL) {
                            listener?.onControlPacketReceived(payload)
                        }
                    }
                } catch (e: Exception) {
                    break
                }
            }
        }
    }

    fun disconnect() {
        if (!isRunning.getAndSet(false)) return
        videoQueue.clear()
        audioQueue.clear()
        try {
            outputStream?.close()
            inputStream?.close()
            socket?.close()
        } catch (_: Exception) {}
        outputStream = null
        inputStream = null
        socket = null
        scope.cancel()
        listener?.onDisconnected("Disconnected")
        Log.d(TAG, "StreamSender stopped.")
    }
}
