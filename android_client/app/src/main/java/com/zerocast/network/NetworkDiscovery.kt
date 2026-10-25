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
         * Detects active USB Tethering virtual network interface and returns default PC host candidate.
         * First inspects the kernel ARP table for instant 0ms resolution of the active PC client.
         */
        fun getTetheringHostCandidate(): String? {
            // 1. Instant check from kernel ARP table (0ms, 100% accurate for active tethering clients)
            try {
                val file = java.io.File("/proc/net/arp")
                if (file.exists()) {
                    for (line in file.readLines()) {
                        val tokens = line.trim().split("\\s+".toRegex())
                        if (tokens.size >= 6) {
                            val ip = tokens[0]
                            val flags = tokens[2]
                            val dev = tokens[5].lowercase()
                            if (flags == "0x2" && (dev.contains("rndis") || dev.contains("usb") || dev.contains("ncm") || dev.contains("eth"))) {
                                if (ip != "127.0.0.1" && !ip.startsWith("0.")) {
                                    return ip
                                }
                            }
                        }
                    }
                }
            } catch (_: Exception) {}
            return null
        }

        fun getTetheringSubnets(): List<String> {
            val subnets = mutableListOf<String>()
            try {
                val interfaces = NetworkInterface.getNetworkInterfaces()
                while (interfaces.hasMoreElements()) {
                    val iface = interfaces.nextElement()
                    if (iface.isLoopback || !iface.isUp) continue
                    val name = iface.name.lowercase()
                    if (name.contains("rndis") || name.contains("usb") || name.contains("ncm") || name.contains("eth")) {
                        for (ifAddr in iface.interfaceAddresses) {
                            val addr = ifAddr.address
                            if (addr is Inet4Address && !addr.isLoopbackAddress) {
                                val host = addr.hostAddress ?: continue
                                val parts = host.split(".")
                                if (parts.size == 4) {
                                    subnets.add("${parts[0]}.${parts[1]}.${parts[2]}.")
                                }
                            }
                        }
                    }
                }
            } catch (_: Exception) {}
            return subnets
        }

        fun isTetheringIp(ip: String): Boolean {
            if (ip == "127.0.0.1" || ip.isEmpty()) return false
            for (subnet in getTetheringSubnets()) {
                if (ip.startsWith(subnet)) return true
            }
            return ip.startsWith("192.168.42.") || ip.startsWith("192.168.43.")
        }

        fun getWifiSubnets(): List<String> {
            val subnets = mutableListOf<String>()
            try {
                val interfaces = NetworkInterface.getNetworkInterfaces()
                while (interfaces.hasMoreElements()) {
                    val iface = interfaces.nextElement()
                    if (iface.isLoopback || !iface.isUp) continue
                    val name = iface.name.lowercase()
                    if (name.contains("wlan") || name.contains("wifi") || name.contains("swlan") || name.contains("p2p")) {
                        for (ifAddr in iface.interfaceAddresses) {
                            val addr = ifAddr.address
                            if (addr is Inet4Address && !addr.isLoopbackAddress) {
                                val host = addr.hostAddress ?: continue
                                val parts = host.split(".")
                                if (parts.size == 4) {
                                    subnets.add("${parts[0]}.${parts[1]}.${parts[2]}.")
                                }
                            }
                        }
                    }
                }
            } catch (_: Exception) {}
            return subnets
        }

        fun isWifiIp(ip: String): Boolean {
            if (ip == "127.0.0.1" || ip.isEmpty() || isTetheringIp(ip)) return false
            val subnets = getWifiSubnets()
            if (subnets.isEmpty()) return true
            for (subnet in subnets) {
                if (ip.startsWith(subnet)) return true
            }
            return false
        }

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
    private var currentDiscoveryMode: String = "AUTO"

    fun startDiscovery(mode: String = "AUTO") {
        if (isScanning.getAndSet(true)) return
        currentDiscoveryMode = mode

        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        val currentScope = scope ?: return

        when (mode) {
            "USB" -> {
                // USB ADB Only: Probe 127.0.0.1 loopback
                currentScope.launch {
                    delay(50)
                    if (isScanning.get()) {
                        probeTcpGateway("127.0.0.1")
                    }
                }
            }
            "TETHER" -> {
                // USB Tethering Only: Probe tethering interface
                currentScope.launch {
                    if (isScanning.get()) {
                        scanTetheringInterfaces()
                    }
                }
            }
            "WIFI" -> {
                // Wi-Fi LAN Only: Listen to UDP beacons & probe Wi-Fi subnet only (exclude tethering/USB)
                currentScope.launch {
                    runUdpDiscovery()
                }
                currentScope.launch {
                    probeTcpGateway("192.168.137.1")
                    getHotspotArpClients().forEach { clientIp ->
                        if (isScanning.get()) {
                            probeTcpGateway(clientIp)
                        }
                    }
                }
                currentScope.launch {
                    delay(300)
                    if (isScanning.get()) {
                        scanLocalSubnet(filterTethering = true)
                    }
                }
            }
            else -> {
                // AUTO: Probe all available transport links
                currentScope.launch {
                    runUdpDiscovery()
                }
                currentScope.launch {
                    delay(100)
                    if (isScanning.get()) {
                        probeTcpGateway("127.0.0.1")
                    }
                }
                currentScope.launch {
                    if (isScanning.get()) {
                        scanTetheringInterfaces()
                    }
                }
                currentScope.launch {
                    if (isScanning.get()) {
                        probeTcpGateway("192.168.137.1")
                        getHotspotArpClients().forEach { clientIp ->
                            if (isScanning.get()) {
                                probeTcpGateway(clientIp)
                            }
                        }
                    }
                }
                currentScope.launch {
                    delay(300)
                    if (isScanning.get()) {
                        scanLocalSubnet(filterTethering = false)
                    }
                }
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
                            // If in Wi-Fi mode, strictly reject tethering IP beacons
                            if (currentDiscoveryMode == "WIFI" && isTetheringIp(ip)) {
                                continue
                            }
                            if (currentDiscoveryMode == "TETHER" && !isTetheringIp(ip)) {
                                continue
                            }
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
            // 1. Generic broadcast
            try {
                val broadcastAddr = InetAddress.getByName("255.255.255.255")
                val pingPacket = DatagramPacket(msg, msg.size, broadcastAddr, DISCOVERY_PORT)
                socket?.send(pingPacket)
            } catch (_: Exception) {}

            // 2. Specific broadcast on all active network interfaces (including USB Tethering rndis0, usb0, etc.)
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                for (ifAddr in iface.interfaceAddresses) {
                    val bcast = ifAddr.broadcast
                    if (bcast != null) {
                        try {
                            val packet = DatagramPacket(msg, msg.size, bcast, DISCOVERY_PORT)
                            socket?.send(packet)
                        } catch (_: Exception) {}
                    }
                }
            }
        } catch (_: Exception) {}
    }

    private suspend fun scanTetheringInterfaces() {
        try {
            // First check ARP table for instantaneous resolution (< 1ms)
            getTetheringHostCandidate()?.let { candidate ->
                if (isScanning.get() && probeTcpGateway(candidate)) return
            }

            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val name = iface.name.lowercase()
                // USB Tethering interfaces typically contain "rndis", "usb", "ncm", or "eth"
                if (name.contains("rndis") || name.contains("usb") || name.contains("ncm") || name.contains("eth")) {
                    for (ifAddr in iface.interfaceAddresses) {
                        val addr = ifAddr.address
                        if (addr is Inet4Address && !addr.isLoopbackAddress) {
                            val hostAddress = addr.hostAddress ?: continue
                            val parts = hostAddress.split(".")
                            if (parts.size == 4) {
                                val prefix = "${parts[0]}.${parts[1]}.${parts[2]}."
                                coroutineScope {
                                    // 1. Ultra-fast probe of common USB Tethering PC IP assignments (< 100ms discovery)
                                    val priorityHosts = listOf(162, 1, 2, 3, 4, 10, 50, 100, 101, 254)
                                    for (h in priorityHosts) {
                                        val target = "$prefix$h"
                                        if (target != hostAddress && isScanning.get()) {
                                            if (probeTcpGateway(target)) return@coroutineScope
                                        }
                                    }

                                    // 2. Full subnet sweep in chunks if not found in priority set
                                    val fastScan = (1..254).filterNot { priorityHosts.contains(it) }
                                    fastScan.chunked(32).forEach { chunk ->
                                        if (!isScanning.get()) return@coroutineScope
                                        chunk.map { h ->
                                            async(Dispatchers.IO) {
                                                val target = "$prefix$h"
                                                if (target != hostAddress && isScanning.get()) {
                                                    probeTcpGateway(target)
                                                }
                                            }
                                        }.awaitAll()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        } catch (_: Exception) {}
    }

    private suspend fun probeTcpGateway(ip: String): Boolean {
        return withContext(Dispatchers.IO) {
            // Respect explicit mode locks
            if (currentDiscoveryMode == "WIFI" && (ip == "127.0.0.1" || isTetheringIp(ip))) {
                return@withContext false
            }
            if (currentDiscoveryMode == "USB" && ip != "127.0.0.1") {
                return@withContext false
            }
            if (currentDiscoveryMode == "TETHER" && (ip == "127.0.0.1" || !isTetheringIp(ip))) {
                return@withContext false
            }

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
                    val returnedIp = json.optString("ip", "")
                    // Crucial: The exact IP probed and connected via TCP is the guaranteed working route.
                    // Do not override with returnedIp (which may be the PC's Wi-Fi IP while on USB tethering).
                    val resolvedIp = if (ip == "127.0.0.1") "127.0.0.1"
                                     else if (ip.isNotEmpty()) ip
                                     else if (returnedIp.isNotEmpty() && returnedIp != "127.0.0.1") returnedIp
                                     else ip
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

    private suspend fun scanLocalSubnet(filterTethering: Boolean = false) {
        val localIps = getLocalIpAddresses(filterTethering)
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

    private fun getLocalIpAddresses(filterTethering: Boolean = false): List<String> {
        val result = mutableListOf<String>()
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val name = iface.name.lowercase()
                if (filterTethering && (name.contains("rndis") || name.contains("usb") || name.contains("ncm"))) {
                    continue
                }
                val addrs = iface.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val host = addr.hostAddress
                        if (host != null && (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172."))) {
                            if (filterTethering && isTetheringIp(host)) {
                                continue
                            }
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

    fun startListening(mode: String = "AUTO") = startDiscovery(mode)
    fun stopListening() = stopDiscovery()
}
