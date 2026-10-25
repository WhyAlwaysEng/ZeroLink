package com.zerocast.network

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.util.Log
import com.zerocast.util.ZeroLinkConfig
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.UUID

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    RECONNECTING
}

/**
 * EcosystemConnectionManager: Singleton Master Link for the entire ZeroLink Ecosystem.
 * Manages active connection lifecycle, atomic mode transitions (Wi-Fi <-> USB),
 * 2-second heartbeat health checks, auto-reconnect, and session tokens.
 */
class EcosystemConnectionManager private constructor(private val appContext: Context) {

    companion object {
        private const val TAG = "EcosystemConnMgr"
        const val GATEWAY_PORT = 8886

        @Volatile
        private var instance: EcosystemConnectionManager? = null

        fun getInstance(context: Context): EcosystemConnectionManager {
            return instance ?: synchronized(this) {
                instance ?: EcosystemConnectionManager(context.applicationContext).also { instance = it }
            }
        }
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val mutex = Mutex()

    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    private val _activeMode = MutableStateFlow(ZeroLinkConfig.getConnectionMode(appContext))
    val activeMode: StateFlow<String> = _activeMode.asStateFlow()

    private val _targetHost = MutableStateFlow(ZeroLinkConfig.getServerIp(appContext).ifEmpty { "127.0.0.1" })
    val targetHost: StateFlow<String> = _targetHost.asStateFlow()

    private val _latencyMs = MutableStateFlow(0)
    val latencyMs: StateFlow<Int> = _latencyMs.asStateFlow()

    private val _deviceName = MutableStateFlow("ZeroLink PC")
    val deviceName: StateFlow<String> = _deviceName.asStateFlow()

    private var currentSessionId = UUID.randomUUID().toString()
    private var gatewaySocket: Socket? = null
    private var socketWriter: BufferedWriter? = null
    private var socketReader: BufferedReader? = null
    private var connectionJob: Job? = null
    private var isExplicitDisconnect = false

    init {
        registerUsbReceiver()
    }

    fun getSessionId(): String = currentSessionId

    fun isLinked(): Boolean = _connectionState.value == ConnectionState.CONNECTED

    /**
     * Connect to PC Gateway using the specified or active mode.
     */
    fun connect(mode: String? = null, manualIp: String? = null) {
        scope.launch {
            mutex.withLock {
                isExplicitDisconnect = false
                val targetMode = mode ?: _activeMode.value
                _activeMode.value = targetMode
                ZeroLinkConfig.setConnectionMode(appContext, targetMode)

                // Resolve host IP for selected mode
                val resolvedHost = when (targetMode) {
                    ZeroLinkConfig.MODE_USB -> "127.0.0.1"
                    ZeroLinkConfig.MODE_TETHER -> manualIp ?: NetworkDiscovery.getTetheringHostCandidate() ?: "10.242.214.162"
                    ZeroLinkConfig.MODE_WIFI -> manualIp ?: ZeroLinkConfig.getServerIp(appContext).ifEmpty { "192.168.101.107" }
                    else -> manualIp ?: ZeroLinkConfig.getServerIp(appContext).ifEmpty { "127.0.0.1" }
                }

                _targetHost.value = resolvedHost
                ZeroLinkConfig.setServerIp(appContext, resolvedHost)
                currentSessionId = UUID.randomUUID().toString()

                startGatewayLoop(resolvedHost)
            }
        }
    }

    /**
     * Atomically switch connection mode (e.g. Wi-Fi -> USB Tethering).
     * If already connected, gracefully tears down old sockets and immediately connects with the new interface.
     * If disconnected, updates mode configuration without forcing auto-connect.
     */
    fun switchMode(newMode: String, manualIp: String? = null) {
        scope.launch {
            mutex.withLock {
                val wasConnected = (_connectionState.value == ConnectionState.CONNECTED)
                Log.i(TAG, "Mode switch: ${_activeMode.value} -> $newMode (wasConnected=$wasConnected)")
                teardownCurrentSocket()
                _activeMode.value = newMode
                ZeroLinkConfig.setConnectionMode(appContext, newMode)

                val resolvedHost = when (newMode) {
                    ZeroLinkConfig.MODE_USB -> "127.0.0.1"
                    ZeroLinkConfig.MODE_TETHER -> manualIp ?: NetworkDiscovery.getTetheringHostCandidate() ?: "10.242.214.162"
                    ZeroLinkConfig.MODE_WIFI -> manualIp ?: ZeroLinkConfig.getServerIp(appContext).ifEmpty { "192.168.101.107" }
                    else -> manualIp ?: "127.0.0.1"
                }

                _targetHost.value = resolvedHost
                ZeroLinkConfig.setServerIp(appContext, resolvedHost)
                currentSessionId = UUID.randomUUID().toString()

                if (wasConnected) {
                    isExplicitDisconnect = false
                    startGatewayLoop(resolvedHost)
                } else {
                    isExplicitDisconnect = true
                    _connectionState.value = ConnectionState.DISCONNECTED
                    _latencyMs.value = 0
                }
            }
        }
    }

    /**
     * Explicit disconnect requested by user.
     */
    fun disconnect() {
        scope.launch {
            mutex.withLock {
                isExplicitDisconnect = true
                _connectionState.value = ConnectionState.DISCONNECTED
                _latencyMs.value = 0
                teardownCurrentSocket()
            }
        }
    }

    /**
     * Reconnect to the last active configuration.
     */
    fun reconnect() {
        connect(_activeMode.value, _targetHost.value)
    }

    private fun teardownCurrentSocket() {
        connectionJob?.cancel()
        connectionJob = null
        try {
            socketWriter?.write("{\"action\": \"DISCONNECT\"}\n")
            socketWriter?.flush()
        } catch (_: Exception) {}
        try {
            gatewaySocket?.close()
        } catch (_: Exception) {}
        gatewaySocket = null
        socketWriter = null
        socketReader = null
    }

    private fun startGatewayLoop(host: String) {
        connectionJob?.cancel()
        connectionJob = scope.launch {
            while (isActive && !isExplicitDisconnect) {
                _connectionState.value = if (gatewaySocket == null) ConnectionState.CONNECTING else ConnectionState.RECONNECTING
                Log.d(TAG, "Connecting to Master Gateway at $host:$GATEWAY_PORT...")

                try {
                    val sock = Socket().apply {
                        tcpNoDelay = true
                        soTimeout = 4000
                    }
                    sock.connect(InetSocketAddress(host, GATEWAY_PORT), 3000)
                    gatewaySocket = sock

                    val writer = BufferedWriter(OutputStreamWriter(sock.getOutputStream(), Charsets.UTF_8))
                    val reader = BufferedReader(InputStreamReader(sock.getInputStream(), Charsets.UTF_8))
                    socketWriter = writer
                    socketReader = reader

                    // Initial Connect Handshake
                    val handshake = JSONObject().apply {
                        put("action", "CONNECT")
                        put("model", Build.MODEL)
                        put("device_model", Build.MODEL)
                        put("session_id", currentSessionId)
                        put("timestamp", System.currentTimeMillis())
                    }
                    writer.write(handshake.toString() + "\n")
                    writer.flush()

                    val responseLine = reader.readLine()
                    if (responseLine != null) {
                        try {
                            val res = JSONObject(responseLine)
                            _deviceName.value = res.optString("name", "ZeroLink PC")
                        } catch (_: Exception) {}
                    }

                    _connectionState.value = ConnectionState.CONNECTED
                    Log.i(TAG, "● Linked to ZeroLink PC Master Gateway at $host")

                    // 2-Second Heartbeat Ping-Pong Loop
                    while (isActive && !isExplicitDisconnect && !sock.isClosed) {
                        delay(2000)
                        val t0 = System.currentTimeMillis()
                        val ping = JSONObject().apply {
                            put("action", "PING")
                            put("session_id", currentSessionId)
                            put("timestamp", t0)
                        }
                        writer.write(ping.toString() + "\n")
                        writer.flush()

                        val pongLine = reader.readLine() ?: break
                        val t1 = System.currentTimeMillis()
                        val rtt = (t1 - t0).toInt().coerceAtLeast(1)
                        _latencyMs.value = rtt
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Gateway socket error: ${e.message}")
                } finally {
                    try {
                        gatewaySocket?.close()
                    } catch (_: Exception) {}
                    gatewaySocket = null
                }

                if (!isExplicitDisconnect && isActive) {
                    _connectionState.value = ConnectionState.RECONNECTING
                    _latencyMs.value = 0
                    delay(2000)
                }
            }

            if (isExplicitDisconnect) {
                _connectionState.value = ConnectionState.DISCONNECTED
                _latencyMs.value = 0
            }
        }
    }

    private fun registerUsbReceiver() {
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_POWER_CONNECTED)
            addAction(Intent.ACTION_POWER_DISCONNECTED)
            addAction("android.hardware.usb.action.USB_STATE")
        }
        try {
            appContext.registerReceiver(object : BroadcastReceiver() {
                override fun onReceive(context: Context?, intent: Intent?) {
                    when (intent?.action) {
                        Intent.ACTION_POWER_CONNECTED -> {
                            Log.i(TAG, "USB Cable plugged in. Checking tethering IP...")
                            if (_activeMode.value == ZeroLinkConfig.MODE_WIFI && _connectionState.value != ConnectionState.CONNECTED) {
                                val candidate = NetworkDiscovery.getTetheringHostCandidate()
                                if (candidate != null) {
                                    switchMode(ZeroLinkConfig.MODE_TETHER, candidate)
                                }
                            }
                        }
                        Intent.ACTION_POWER_DISCONNECTED -> {
                            Log.i(TAG, "USB Cable disconnected.")
                            if (_activeMode.value != ZeroLinkConfig.MODE_WIFI) {
                                switchMode(ZeroLinkConfig.MODE_WIFI)
                            }
                        }
                    }
                }
            }, filter)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to register USB broadcast receiver: ${e.message}")
        }
    }
}
