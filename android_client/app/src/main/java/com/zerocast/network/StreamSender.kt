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
    }

    // Queue capacity of 36 allows smooth interleaved video & audio packets without blocking AudioRecord
    private val frameQueue = ArrayBlockingQueue<FramePacket>(36)
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
                sock.sendBufferSize = 128 * 1024
                sock.connect(InetSocketAddress(host, port), 4000)

                socket = sock
                outputStream = DataOutputStream(sock.getOutputStream())
                inputStream = DataInputStream(sock.getInputStream())

                Log.d(TAG, "Connected successfully to $host:$port")
                listener?.onConnected()

                // Launch reverse control backchannel reader
                launchBackchannelReader()

                // Main frame dispatch loop
                while (isRunning.get() && sock.isConnected && !sock.isClosed) {
                    val packet = frameQueue.take()
                    writePacket(packet)
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

        // Dynamic Adaptive Bitrate (ABR) socket buffer detector
        if (frameQueue.remainingCapacity() <= 6) {
            calmFrameCount = 0
            if (!isCongestedState) {
                isCongestedState = true
                listener?.onCongestionChanged(true)
            }
        } else if (frameQueue.size <= 4) {
            calmFrameCount++
            if (calmFrameCount > 35 && isCongestedState) {
                isCongestedState = false
                listener?.onCongestionChanged(false)
            }
        }

        if (!frameQueue.offer(packet)) {
            frameQueue.poll() // Drop oldest packet to prevent backpressure blocking
            frameQueue.offer(packet)
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
        frameQueue.clear()
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
