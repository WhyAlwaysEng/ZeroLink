package com.zerocast.network

import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.atomic.AtomicBoolean

class NetworkDiscovery(
    private val onServerFound: (ip: String, port: Int, name: String) -> Unit
) {
    constructor(legacyCallback: (ip: String, port: Int) -> Unit) : this({ ip, port, _ ->
        legacyCallback(ip, port)
    })

    companion object {
        private const val TAG = "ZeroLink-Discovery"
        const val DISCOVERY_PORT = 8887
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
                    soTimeout = 2500
                }

                // Send discovery ping immediately
                sendDiscoveryBroadcast()

                val buffer = ByteArray(2048)
                while (isScanning.get()) {
                    try {
                        val packet = DatagramPacket(buffer, buffer.size)
                        socket?.receive(packet)

                        val text = String(packet.data, 0, packet.length).trim()
                        if (text.contains("ZEROLINK_BEACON") || text.contains("ZEROCAST_BEACON")) {
                            val json = JSONObject(text)
                            val ip = json.optString("ip", packet.address?.hostAddress ?: "")
                            val port = json.optInt("port", 8888)
                            val name = json.optString("name", "ZeroLink PC")

                            if (ip.isNotEmpty() && ip != "127.0.0.1") {
                                withContext(Dispatchers.Main) {
                                    onServerFound(ip, port, name)
                                }
                            }
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
            val msg = "ZEROLINK_DISCOVER".toByteArray()
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

    fun startListening() = startDiscovery()
    fun stopListening() = stopDiscovery()
}
