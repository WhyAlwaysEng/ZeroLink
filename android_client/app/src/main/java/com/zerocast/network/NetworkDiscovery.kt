package com.zerocast.network

import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.*
import java.util.concurrent.atomic.AtomicBoolean

class NetworkDiscovery(
    private val onServerFound: (ip: String, port: Int, name: String) -> Unit
) {
    constructor(legacyCallback: (ip: String, port: Int) -> Unit) : this({ ip, port, _ ->
        legacyCallback(ip, port)
    })

    companion object {
        private const val TAG = "ZeroLink-Discovery"
        const val DISCOVERY_PORT = 8887 // UDP beacon & notifications
        const val GATEWAY_PORT = 8886   // TCP Master Gateway & ZeroWake

        /**
         * Sends a remote wake-up request to the PC Master Gateway to activate a specific module on-demand.
         */
        fun wakeModule(host: String, moduleId: String, callback: ((Boolean) -> Unit)? = null) {
            CoroutineScope(Dispatchers.IO).launch {
                var success = false
                try {
                    val socket = Socket()
                    socket.soTimeout = 2500
                    socket.connect(InetSocketAddress(host, GATEWAY_PORT), 2000)

                    val writer = OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8)
                    val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))

                    val req = JSONObject().apply {
                        put("action", "WAKE")
                        put("module", moduleId)
                    }.toString() + "\n"

                    writer.write(req)
                    writer.flush()

                    val resp = reader.readLine()
                    if (resp != null && resp.contains("READY")) {
                        success = true
                    }
                    socket.close()
                } catch (e: Exception) {
                    Log.d(TAG, "Wake module '$moduleId' attempt: ${e.message}")
                }
                withContext(Dispatchers.Main) {
                    callback?.invoke(success)
                }
            }
        }

        /**
         * Sends a remote sleep request to the PC Master Gateway to stop a specific module when user leaves.
         */
        fun sleepModule(host: String, moduleId: String, callback: ((Boolean) -> Unit)? = null) {
            CoroutineScope(Dispatchers.IO).launch {
                var success = false
                try {
                    val socket = Socket()
                    socket.soTimeout = 2000
                    socket.connect(InetSocketAddress(host, GATEWAY_PORT), 1500)

                    val writer = OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8)
                    val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))

                    val req = JSONObject().apply {
                        put("action", "SLEEP")
                        put("module", moduleId)
                    }.toString() + "\n"

                    writer.write(req)
                    writer.flush()

                    val resp = reader.readLine()
                    if (resp != null && resp.contains("STOPPED")) {
                        success = true
                    }
                    socket.close()
                } catch (e: Exception) {
                    Log.d(TAG, "Sleep module '$moduleId' attempt: ${e.message}")
                }
                withContext(Dispatchers.Main) {
                    callback?.invoke(success)
                }
            }
        }
    }

    private val isScanning = AtomicBoolean(false)
    private var scope: CoroutineScope? = null
    private var socket: DatagramSocket? = null

    fun startDiscovery() {
        if (isScanning.getAndSet(true)) return

        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        val currentScope = scope ?: return

        // 1. UDP Broadcast Listener & Ping
        currentScope.launch {
            runUdpDiscovery()
        }

        // 2. USB / ADB Loopback Gateway Probe (127.0.0.1:8886)
        currentScope.launch {
            delay(100)
            if (isScanning.get()) {
                probeTcpGateway("127.0.0.1")
            }
        }

        // 3. Direct Hotspot Link Priority Probes (< 100ms discovery, zero router needed)
        currentScope.launch {
            if (isScanning.get()) {
                // Windows Mobile Hotspot default PC gateway
                probeTcpGateway("192.168.137.1")
                // Android Mobile Hotspot connected clients from ARP table
                getHotspotArpClients().forEach { clientIp ->
                    if (isScanning.get()) {
                        probeTcpGateway(clientIp)
                    }
                }
            }
        }

        // 4. Fast Parallel Subnet TCP Scanner (bypasses Wi-Fi router AP Isolation / UDP blocks)
        currentScope.launch {
            delay(300)
            if (isScanning.get()) {
                scanLocalSubnet()
            }
        }
    }

    private suspend fun runUdpDiscovery() {
        try {
            socket = DatagramSocket(null).apply {
                reuseAddress = true
                broadcast = true
                bind(InetSocketAddress(DISCOVERY_PORT))
                soTimeout = 2500
            }

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
                    if (isScanning.get()) {
                        sendDiscoveryBroadcast()
                    }
                }
            }
        } catch (e: Exception) {
            Log.d(TAG, "UDP Discovery stopped: ${e.message}")
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

    private suspend fun probeTcpGateway(ip: String): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val sock = Socket()
                sock.soTimeout = 400
                sock.connect(InetSocketAddress(ip, GATEWAY_PORT), 350)

                val writer = OutputStreamWriter(sock.getOutputStream(), Charsets.UTF_8)
                val reader = BufferedReader(InputStreamReader(sock.getInputStream(), Charsets.UTF_8))

                writer.write("{\"action\":\"PING\"}\n")
                writer.flush()

                val line = reader.readLine()
                sock.close()

                if (line != null && line.contains("PONG")) {
                    val json = JSONObject(line)
                    val resolvedIp = if (ip == "127.0.0.1") "127.0.0.1" else json.optString("ip", ip)
                    val port = json.optInt("port", 8888)
                    val name = json.optString("name", "ZeroLink PC")

                    withContext(Dispatchers.Main) {
                        onServerFound(resolvedIp, port, name)
                    }
                    return@withContext true
                }
            } catch (_: Exception) {}
            false
        }
    }

    private suspend fun scanLocalSubnet() {
        val localIps = getLocalIpAddresses()
        for (localIp in localIps) {
            val parts = localIp.split(".")
            if (parts.size != 4) continue
            val subnetPrefix = "${parts[0]}.${parts[1]}.${parts[2]}."

            // Scan in batches of 32 parallel probes
            val hostBatch = (1..254).toList()
            hostBatch.chunked(32).forEach { batch ->
                if (!isScanning.get()) return
                coroutineScope {
                    batch.map { hostNum ->
                        async(Dispatchers.IO) {
                            val targetIp = "$subnetPrefix$hostNum"
                            if (targetIp != localIp && isScanning.get()) {
                                probeTcpGateway(targetIp)
                            }
                        }
                    }.awaitAll()
                }
            }
        }
    }

    private fun getHotspotArpClients(): List<String> {
        val clients = mutableListOf<String>()
        try {
            val file = java.io.File("/proc/net/arp")
            if (file.exists() && file.canRead()) {
                file.forEachLine { line ->
                    val tokens = line.split("\\s+".toRegex())
                    if (tokens.size >= 4 && tokens[0] != "IP") {
                        val ip = tokens[0]
                        val flags = tokens[2]
                        if (flags != "0x0" && ip.isNotEmpty() && !ip.startsWith("0.")) {
                            clients.add(ip)
                        }
                    }
                }
            }
        } catch (_: Exception) {}
        return clients
    }

    private fun getLocalIpAddresses(): List<String> {
        val result = mutableListOf<String>()
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val addrs = iface.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val host = addr.hostAddress
                        if (host != null && (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172."))) {
                            result.add(host)
                        }
                    }
                }
            }
        } catch (_: Exception) {}
        return result
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
