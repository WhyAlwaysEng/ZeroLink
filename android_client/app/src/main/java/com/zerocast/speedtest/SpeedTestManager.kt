package com.zerocast.speedtest

import android.os.Handler
import android.os.Looper
import android.util.Log
import org.json.JSONObject
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.concurrent.thread

class SpeedTestManager(
    private val host: String = "127.0.0.1",
    private val port: Int = com.zerocast.util.ZeroLinkConfig.DEFAULT_SPEEDTEST_PORT,
    private val listener: SpeedTestListener
) {
    interface SpeedTestListener {
        fun onPingCompleted(avgPingMs: Float, jitterMs: Float)
        fun onProgress(progress: Float, currentMbps: Float)
        fun onCompleted(result: SpeedTestResult)
        fun onError(message: String)
    }

    data class SpeedTestResult(
        val mbps: Float,
        val avgPingMs: Float,
        val jitterMs: Float,
        val isUsb: Boolean,
        val host: String,
        val recommendation: String,
        val recommendedBitrateIndex: Int
    )

    private val mainHandler = Handler(Looper.getMainLooper())
    @Volatile
    private var isCancelled = false
    private var socket: Socket? = null

    companion object {
        private const val TAG = "SpeedTestManager"
        private const val CHUNK_SIZE = 64 * 1024
    }

    fun startTest() {
        isCancelled = false
        thread(name = "ZeroLink-SpeedTest") {
            try {
                val isUsb = host == "127.0.0.1" || host == "localhost"
                val sock = Socket()
                socket = sock
                sock.tcpNoDelay = true
                sock.soTimeout = 5000
                sock.connect(InetSocketAddress(host, port), 4000)

                val inputStream = sock.getInputStream()
                val outputStream = sock.getOutputStream()

                // Phase 1: Ping & Jitter Probes
                val pings = mutableListOf<Float>()
                for (i in 0 until 8) {
                    if (isCancelled) break
                    val t0 = System.nanoTime()
                    val pingJson = JSONObject().apply {
                        put("cmd", "PING")
                        put("ts", System.currentTimeMillis())
                    }.toString().toByteArray(Charsets.UTF_8)

                    writeFrame(outputStream, pingJson)

                    val resp = readFrame(inputStream) ?: break
                    val t1 = System.nanoTime()
                    val rttMs = (t1 - t0) / 1_000_000f
                    pings.add(rttMs)
                    Thread.sleep(30)
                }

                val avgPing = if (pings.isNotEmpty()) pings.average().toFloat() else 0f
                val jitter = if (pings.size > 1) (pings.maxOrNull()!! - pings.minOrNull()!!) else 0f

                mainHandler.post {
                    listener.onPingCompleted(avgPing, jitter)
                }

                // Phase 2: Bandwidth Test (PC sending stream -> Phone receiving)
                val bwReq = JSONObject().apply {
                    put("cmd", "START_BANDWIDTH_TEST")
                    put("duration", 3.0)
                }.toString().toByteArray(Charsets.UTF_8)
                writeFrame(outputStream, bwReq)

                // Read confirmation header
                readFrame(inputStream)

                val startTime = System.currentTimeMillis()
                val testDurationMs = 3000L
                var totalBytes = 0L
                val buffer = ByteArray(CHUNK_SIZE)

                sock.soTimeout = 1500
                var lastProgressReport = startTime

                while (System.currentTimeMillis() - startTime < testDurationMs && !isCancelled) {
                    val n = inputStream.read(buffer)
                    if (n <= 0) break
                    totalBytes += n

                    val now = System.currentTimeMillis()
                    if (now - lastProgressReport >= 120) {
                        val elapsedSec = (now - startTime) / 1000f
                        val currentMbps = if (elapsedSec > 0) (totalBytes * 8f) / (elapsedSec * 1_000_000f) else 0f
                        val progress = minOf(1.0f, elapsedSec / 3.0f)
                        mainHandler.post {
                            listener.onProgress(progress, currentMbps)
                        }
                        lastProgressReport = now
                    }
                }

                val totalElapsedSec = maxOf(0.001f, (System.currentTimeMillis() - startTime) / 1000f)
                val finalMbps = (totalBytes * 8f) / (totalElapsedSec * 1_000_000f)

                sock.close()

                // Generate smart recommendations
                val (recText, recIdx) = evaluateConnection(finalMbps, avgPing, isUsb)
                val result = SpeedTestResult(
                    mbps = String.format("%.1f", finalMbps).toFloat(),
                    avgPingMs = String.format("%.1f", avgPing).toFloat(),
                    jitterMs = String.format("%.1f", jitter).toFloat(),
                    isUsb = isUsb,
                    host = host,
                    recommendation = recText,
                    recommendedBitrateIndex = recIdx
                )

                mainHandler.post {
                    listener.onProgress(1.0f, finalMbps)
                    listener.onCompleted(result)
                }

            } catch (e: Exception) {
                Log.e(TAG, "Speed test failed: ${e.message}", e)
                mainHandler.post {
                    listener.onError(e.message ?: "Failed to connect to SpeedTest server on PC")
                }
            } finally {
                try {
                    socket?.close()
                } catch (_: Exception) {}
            }
        }
    }

    fun cancel() {
        isCancelled = true
        try {
            socket?.close()
        } catch (_: Exception) {}
    }

    private fun evaluateConnection(mbps: Float, ping: Float, isUsb: Boolean): Pair<String, Int> {
        return when {
            isUsb || mbps >= 60f -> Pair(
                "⚡ Exceptional Connection ($mbps Mbps • ${ping}ms latency)\nOptimal for 50 - 80 Mbps Extreme Quality (60 FPS Lossless).",
                1 // 50 Mbps
            )
            mbps >= 30f -> Pair(
                "🚀 High Performance Link ($mbps Mbps • ${ping}ms latency)\nOptimal for 25 - 35 Mbps High Quality (60 FPS).",
                3 // 25 Mbps
            )
            mbps >= 15f -> Pair(
                "✨ Balanced Connection ($mbps Mbps • ${ping}ms latency)\nOptimal for 14 - 18 Mbps Balanced Mode.",
                4 // 18 Mbps
            )
            mbps >= 8f -> Pair(
                "📶 Standard Connection ($mbps Mbps • ${ping}ms latency)\nRecommended for 10 Mbps Standard Mode.",
                6 // 10 Mbps
            )
            else -> Pair(
                "⚠️ Limited Bandwidth ($mbps Mbps • ${ping}ms latency)\nRecommended for 3 - 6 Mbps. Consider connecting via USB Cable for maximum stability.",
                7 // 6 Mbps
            )
        }
    }

    private fun writeFrame(outputStream: OutputStream, data: ByteArray) {
        val lenBuf = ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN).putInt(data.size).array()
        outputStream.write(lenBuf)
        outputStream.write(data)
        outputStream.flush()
    }

    private fun readFrame(inputStream: InputStream): ByteArray? {
        val lenBytes = ByteArray(4)
        var read = 0
        while (read < 4) {
            val n = inputStream.read(lenBytes, read, 4 - read)
            if (n <= 0) return null
            read += n
        }
        val size = ByteBuffer.wrap(lenBytes).order(ByteOrder.BIG_ENDIAN).int
        if (size <= 0 || size > 2_000_000) return null

        val data = ByteArray(size)
        var totalRead = 0
        while (totalRead < size) {
            val n = inputStream.read(data, totalRead, size - totalRead)
            if (n <= 0) return null
            totalRead += n
        }
        return data
    }
}
