package com.zerocast.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.net.wifi.WifiManager
import android.os.Bundle
import android.text.format.Formatter
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroDevBinding
import com.zerocast.databinding.ItemPortStatusBinding
import com.zerocast.util.ZeroLinkConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ZeroDevActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroDevBinding

    data class PortDefinition(val port: Int, val name: String, val glyph: String)

    private val ecosystemPorts = listOf(
        PortDefinition(8888, "ZeroCast", "⊡"),
        PortDefinition(8889, "ZeroClip", "⎘"),
        PortDefinition(8890, "ZeroDrop", "⇄"),
        PortDefinition(8891, "ZeroMix", "⧉"),
        PortDefinition(8892, "ZeroDisplay", "▣"),
        PortDefinition(8893, "ZeroCam", "◎"),
        PortDefinition(8894, "ZeroPad", "▦"),
        PortDefinition(8895, "SpeedTest", "⚡"),
        PortDefinition(8896, "ZeroExplorer", "▤"),
        PortDefinition(8897, "ZeroDev", "</>")
    )

    private val portItemBindings = mutableMapOf<Int, ItemPortStatusBinding>()

    // Local Test Server
    private var testServer: ServerSocket? = null
    private var serverJob: Job? = null
    private var isServerRunning = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroDevBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val savedIp = ZeroLinkConfig.getServerIp(this)
        binding.etTargetIp.setText(savedIp)

        setupPortMatrix()
        setupListeners()
        log("ZeroDev Console loaded. Phone local IP: ${getLocalIpAddress()}")
    }

    private fun setupPortMatrix() {
        binding.containerPortMatrix.removeAllViews()
        val inflater = LayoutInflater.from(this)

        for (def in ecosystemPorts) {
            val itemBinding = ItemPortStatusBinding.inflate(inflater, binding.containerPortMatrix, false)
            itemBinding.tvPortGlyph.text = def.glyph
            itemBinding.tvModuleName.text = def.name
            itemBinding.tvPortNumber.text = ":${def.port}"
            itemBinding.tvPortStatus.text = "READY"
            itemBinding.tvPortStatus.setBackgroundResource(R.drawable.bg_badge_pill)
            itemBinding.tvPortStatus.setTextColor(getColor(R.color.text_secondary))

            binding.containerPortMatrix.addView(itemBinding.root)
            portItemBindings[def.port] = itemBinding
        }
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            finish()
        }

        binding.btnProbeSingle.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val ip = binding.etTargetIp.text?.toString()?.trim() ?: ""
            val portStr = binding.etTargetPort.text?.toString()?.trim() ?: "8897"
            val port = portStr.toIntOrNull() ?: 8897
            if (ip.isEmpty()) {
                Toast.makeText(this, "Please enter PC IP", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            ZeroLinkConfig.setServerIp(this, ip)
            probeSinglePort(ip, port)
        }

        binding.btnScanAll.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val ip = binding.etTargetIp.text?.toString()?.trim() ?: ""
            if (ip.isEmpty()) {
                Toast.makeText(this, "Please enter PC IP", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            ZeroLinkConfig.setServerIp(this, ip)
            scanAllPorts(ip)
        }

        binding.btnToggleServer.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            if (isServerRunning) {
                stopTestServer()
            } else {
                val portStr = binding.etLocalServerPort.text?.toString()?.trim() ?: "8897"
                val port = portStr.toIntOrNull() ?: 8897
                startTestServer(port)
            }
        }

        binding.btnClearLog.setOnClickListener {
            binding.tvConsoleLog.text = "[ZeroDev] Log cleared."
        }

        binding.btnCopyLog.setOnClickListener {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("ZeroDev Log", binding.tvConsoleLog.text)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(this, "Log copied to clipboard", Toast.LENGTH_SHORT).show()
        }
    }

    private fun probeSinglePort(ip: String, port: Int) {
        log("Probing PC socket $ip:$port...")
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                probeSocket(ip, port)
            }
            if (result.success) {
                log("✓ $ip:$port connected in ${String.format(Locale.US, "%.1f", result.latencyMs)} ms: ${result.details}")
            } else {
                log("✗ $ip:$port failed (${String.format(Locale.US, "%.1f", result.latencyMs)} ms): ${result.details}")
            }

            // Update item in matrix if present
            portItemBindings[port]?.let { b ->
                if (result.success) {
                    b.tvPortStatus.text = "● OPEN ${String.format(Locale.US, "%.0f", result.latencyMs)}ms"
                    b.tvPortStatus.setTextColor(getColor(R.color.primary))
                } else {
                    b.tvPortStatus.text = "○ CLOSED"
                    b.tvPortStatus.setTextColor(getColor(R.color.text_tertiary))
                }
            }
        }
    }

    private fun scanAllPorts(ip: String) {
        log("--- Scanning all ecosystem ports on $ip ---")
        lifecycleScope.launch {
            ecosystemPorts.forEach { def ->
                portItemBindings[def.port]?.tvPortStatus?.apply {
                    text = "PROBING"
                    setTextColor(getColor(R.color.text_secondary))
                }
            }

            val deferredResults = ecosystemPorts.map { def ->
                async(Dispatchers.IO) {
                    val res = probeSocket(ip, def.port)
                    def to res
                }
            }

            val results = deferredResults.awaitAll()
            var openCount = 0
            results.forEach { (def, res) ->
                val b = portItemBindings[def.port]
                if (res.success) {
                    openCount++
                    b?.tvPortStatus?.text = "● ${String.format(Locale.US, "%.0f", res.latencyMs)}ms"
                    b?.tvPortStatus?.setTextColor(getColor(R.color.primary))
                    log("✓ Port ${def.port} [${def.name}] OPEN (${String.format(Locale.US, "%.1f", res.latencyMs)} ms)")
                } else {
                    b?.tvPortStatus?.text = "○ DOWN"
                    b?.tvPortStatus?.setTextColor(getColor(R.color.text_tertiary))
                }
            }
            log("--- Scan complete: $openCount / ${ecosystemPorts.size} ports active ---")
        }
    }

    data class ProbeResult(val success: Boolean, val latencyMs: Double, val details: String)

    private fun probeSocket(host: String, port: Int, timeoutMs: Int = 1800): ProbeResult {
        val t0 = System.currentTimeMillis()
        val socket = Socket()
        return try {
            socket.connect(InetSocketAddress(host, port), timeoutMs)
            val latency = (System.currentTimeMillis() - t0).toDouble()
            var details = "TCP Handshake OK"
            try {
                socket.soTimeout = 800
                val out = socket.getOutputStream()
                out.write("HEAD / HTTP/1.0\r\n\r\n".toByteArray())
                out.flush()
                val buf = ByteArray(128)
                val len = socket.getInputStream().read(buf)
                if (len > 0) {
                    val resp = String(buf, 0, len)
                    if (resp.startsWith("HTTP/")) {
                        details = resp.substringBefore("\r\n")
                    }
                }
            } catch (_: Exception) {}
            socket.close()
            ProbeResult(true, latency, details)
        } catch (e: Exception) {
            val latency = (System.currentTimeMillis() - t0).toDouble()
            try { socket.close() } catch (_: Exception) {}
            ProbeResult(false, latency, e.message ?: "Connection refused")
        }
    }

    private fun startTestServer(port: Int) {
        try {
            testServer = ServerSocket(port)
            isServerRunning = true
            binding.btnToggleServer.text = "Stop Server"
            binding.tvDevStatus.text = "● LISTENING :$port"
            binding.tvServerInfo.text = "Listening on ${getLocalIpAddress()}:$port (Echo & Diagnostics)"
            log("Test Server started on port $port. Ready for inbound packets.")

            serverJob = lifecycleScope.launch(Dispatchers.IO) {
                while (isActive && isServerRunning) {
                    try {
                        val client = testServer?.accept() ?: break
                        launch(Dispatchers.IO) {
                            handleClient(client)
                        }
                    } catch (e: Exception) {
                        if (isServerRunning) {
                            withContext(Dispatchers.Main) {
                                log("Server accept exception: ${e.message}")
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Toast.makeText(this, "Failed to bind port $port: ${e.message}", Toast.LENGTH_LONG).show()
            log("Failed to start server on port $port: ${e.message}")
        }
    }

    private suspend fun handleClient(socket: Socket) {
        val remoteAddr = socket.remoteSocketAddress.toString()
        withContext(Dispatchers.Main) {
            log("[Server] Connection received from $remoteAddr")
        }
        try {
            socket.soTimeout = 5000
            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
            val writer = PrintWriter(socket.getOutputStream(), true)

            val firstLine = reader.readLine()
            if (firstLine != null) {
                withContext(Dispatchers.Main) {
                    log("[Server] Received: '$firstLine'")
                }
                if (firstLine.startsWith("HEAD") || firstLine.startsWith("GET")) {
                    writer.println("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"status\":\"ok\",\"service\":\"ZeroDev Mobile\",\"device\":\"${android.os.Build.MODEL}\"}")
                } else {
                    writer.println("[ZeroDev Echo] $firstLine")
                }
            }
        } catch (e: Exception) {
            withContext(Dispatchers.Main) {
                log("[Server] Client error ($remoteAddr): ${e.message}")
            }
        } finally {
            try { socket.close() } catch (_: Exception) {}
            withContext(Dispatchers.Main) {
                log("[Server] Connection closed with $remoteAddr")
            }
        }
    }

    private fun stopTestServer() {
        isServerRunning = false
        serverJob?.cancel()
        try {
            testServer?.close()
        } catch (_: Exception) {}
        testServer = null
        binding.btnToggleServer.text = "Start Server"
        binding.tvDevStatus.text = "● READY"
        binding.tvServerInfo.text = "Run a local TCP Echo service to test PC → Phone connectivity."
        log("Test Server stopped.")
    }

    private fun getLocalIpAddress(): String {
        return try {
            val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val ipInt = wifiManager.connectionInfo.ipAddress
            if (ipInt != 0) {
                Formatter.formatIpAddress(ipInt)
            } else {
                "127.0.0.1"
            }
        } catch (_: Exception) {
            "127.0.0.1"
        }
    }

    private fun log(message: String) {
        val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val formatted = "[$time] $message"
        val current = binding.tvConsoleLog.text.toString()
        val updated = "$current\n$formatted"
        binding.tvConsoleLog.text = updated
    }

    override fun onDestroy() {
        super.onDestroy()
        stopTestServer()
    }
}
