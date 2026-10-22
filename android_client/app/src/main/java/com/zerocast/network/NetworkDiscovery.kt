package com.zerocast.network

import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.atomic.AtomicBoolean

class NetworkDiscovery(
    private val onServerFound: (ip: String, port: Int) -> Unit
) {
    companion object {
        private const val TAG = "ZeroCast-Discovery"
        private const val DISCOVERY_PORT = 8889
    }

    private val isScanning = AtomicBoolean(false)
    private var scope: CoroutineScope? = null
    private var socket: DatagramSocket? = null

    fun startDiscovery() {
        if (isScanning.getAndSet(true)) return

        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        scope?.launch {
            try {
                socket = DatagramSocket(DISCOVERY_PORT).apply {
                    broadcast = true
                    soTimeout = 3000
                }

                // Send discovery ping
                sendDiscoveryBroadcast()

                val buffer = ByteArray(2048)
                while (isScanning.get()) {
                    try {
                        val packet = DatagramPacket(buffer, buffer.size)
                        socket?.receive(packet)

                        val text = String(packet.data, 0, packet.length).trim()
                        if (text.contains("ZEROCAST_BEACON")) {
                            val json = JSONObject(text)
                            val ip = json.optString("ip", packet.address.hostAddress ?: "")
                            val port = json.optInt("port", 8888)

                            withContext(Dispatchers.Main) {
                                onServerFound(ip, port)
                            }
                            break
                        }
                    } catch (_: Exception) {
                        // Timeout: re-broadcast
                        if (isScanning.get()) {
                            sendDiscoveryBroadcast()
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Discovery socket error: ${e.message}")
            } finally {
                stopDiscovery()
            }
        }
    }

    private fun sendDiscoveryBroadcast() {
        try {
            val msg = "ZEROCAST_DISCOVERY_REQ".toByteArray()
            val broadcastAddr = InetAddress.getByName("255.255.255.255")
            val pingPacket = DatagramPacket(msg, msg.size, broadcastAddr, DISCOVERY_PORT)
            socket?.send(pingPacket)
        } catch (_: Exception) {}
    }

    fun stopDiscovery() {
        isScanning.set(false)
        try {
            socket?.close()
        } catch (_: Exception) {}
        socket = null
        scope?.cancel()
        scope = null
    }
}
