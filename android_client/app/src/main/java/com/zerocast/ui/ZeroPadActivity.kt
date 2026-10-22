package com.zerocast.ui

import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.HapticFeedbackConstants
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.zerocast.databinding.ActivityZeroPadBinding
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.ZeroLinkConfig
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket

class ZeroPadActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ZeroPad"
        private const val DEFAULT_PORT = 8894
    }

    private lateinit var binding: ActivityZeroPadBinding

    private var socket: Socket? = null
    private var outStream: OutputStream? = null
    private var isConnected = false
    private var connectionJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO)
    private var discovery: NetworkDiscovery? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroPadBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Pre-fill IP
        val lastIp = ZeroLinkConfig.getServerIp(this)
        if (lastIp.isNotEmpty() && lastIp != "127.0.0.1") {
            binding.etPadHostIp.setText(lastIp)
        }

        discovery = NetworkDiscovery { discoveredIp, _ ->
            runOnUiThread {
                if (binding.etPadHostIp.text.isNullOrEmpty()) {
                    binding.etPadHostIp.setText(discoveredIp)
                }
            }
        }
        discovery?.startDiscovery()

        binding.btnPadBack.setOnClickListener {
            finish()
        }

        binding.btnPadUsbMode.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etPadHostIp.setText("127.0.0.1")
            Toast.makeText(this, "⚡ USB Mode Selected (127.0.0.1)", Toast.LENGTH_SHORT).show()
        }

        binding.btnPadConnect.setOnClickListener {
            if (isConnected) {
                disconnect()
            } else {
                val ip = binding.etPadHostIp.text.toString().trim()
                if (ip.isEmpty()) {
                    Toast.makeText(this, "Please enter PC Host IP", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                ZeroLinkConfig.setServerIp(this, ip)
                connect(ip, DEFAULT_PORT)
            }
        }

        // Section 1: Media buttons
        binding.btnMediaPlayPause.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendMediaKey("PLAY_PAUSE")
        }
        binding.btnMediaNext.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendMediaKey("NEXT")
        }
        binding.btnMediaPrev.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendMediaKey("PREV")
        }
        binding.btnMediaVolUp.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendMediaKey("VOL_UP")
        }
        binding.btnMediaVolDown.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendMediaKey("VOL_DOWN")
        }
        binding.btnMediaMute.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendMediaKey("MUTE")
        }

        // Section 2: Macros
        binding.btnMacroDiscordMute.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            sendMacro("DISCORD_MUTE")
        }
        binding.btnMacroDiscordDeafen.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            sendMacro("DISCORD_DEAFEN")
        }
        binding.btnMacroScreenshot.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            sendMacro("SCREENSHOT")
        }
        binding.btnMacroDesktop.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            sendMacro("SHOW_DESKTOP")
        }
        binding.btnMacroTaskMgr.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            sendMacro("TASK_MANAGER")
        }
        binding.btnMacroLock.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.REJECT)
            sendMacro("LOCK_PC")
        }

        // Section 3: App Launchers
        binding.btnLaunchChrome.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendLaunch("chrome")
        }
        binding.btnLaunchDiscord.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendLaunch("discord")
        }
        binding.btnLaunchExplorer.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendLaunch("explorer")
        }
        binding.btnLaunchCalc.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendLaunch("calc")
        }
    }

    private fun connect(host: String, port: Int) {
        disconnect()
        binding.btnPadConnect.text = "Connecting..."
        binding.tvPadStatus.text = "● Connecting..."

        connectionJob = scope.launch {
            try {
                val s = Socket()
                s.tcpNoDelay = true
                s.connect(InetSocketAddress(host, port), 4000)
                socket = s
                outStream = s.getOutputStream()

                // Send Handshake
                val hs = JSONObject().apply {
                    put("action", "CONNECT")
                    put("model", Build.MODEL)
                    put("device_model", Build.MODEL)
                }
                outStream?.write((hs.toString() + "\n").toByteArray(Charsets.UTF_8))
                outStream?.flush()

                isConnected = true
                val isWired = host == "127.0.0.1" || host == "localhost"
                withContext(Dispatchers.Main) {
                    binding.btnPadConnect.text = "Disconnect"
                    binding.tvPadStatus.text = if (isWired) "● Connected (⚡ USB)" else "● Connected (📡 Wi-Fi)"
                    binding.tvPadStatus.setTextColor(android.graphics.Color.parseColor("#10B981"))
                }

                // Keep socket open
                val inStream = s.getInputStream()
                val reader = inStream.bufferedReader()
                while (isActive && !s.isClosed) {
                    reader.readLine() ?: break
                }
            } catch (e: Exception) {
                Log.e(TAG, "Connection failed: ${e.message}")
            } finally {
                withContext(Dispatchers.Main) {
                    disconnect()
                }
            }
        }
    }

    private fun disconnect() {
        isConnected = false
        connectionJob?.cancel()
        connectionJob = null
        try {
            socket?.close()
        } catch (e: Exception) {}
        socket = null
        outStream = null

        runOnUiThread {
            binding.btnPadConnect.text = "Connect"
            binding.tvPadStatus.text = "○ Disconnected"
            binding.tvPadStatus.setTextColor(android.graphics.Color.parseColor("#94A3B8"))
        }
    }

    private fun sendJson(json: JSONObject) {
        if (!isConnected || outStream == null) {
            Toast.makeText(this, "Not connected to PC Hub", Toast.LENGTH_SHORT).show()
            return
        }
        scope.launch {
            try {
                val payload = (json.toString() + "\n").toByteArray(Charsets.UTF_8)
                val out = outStream
                if (out != null) {
                    synchronized(out) {
                        out.write(payload)
                        out.flush()
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Send error: ${e.message}")
            }
        }
    }

    private fun sendMediaKey(key: String) {
        val json = JSONObject().apply {
            put("action", "MEDIA_KEY")
            put("key", key)
        }
        sendJson(json)
    }

    private fun sendMacro(name: String) {
        val json = JSONObject().apply {
            put("action", "MACRO")
            put("name", name)
        }
        sendJson(json)
    }

    private fun sendLaunch(target: String) {
        val json = JSONObject().apply {
            put("action", "LAUNCH")
            put("target", target)
        }
        sendJson(json)
    }

    override fun onDestroy() {
        super.onDestroy()
        disconnect()
        discovery?.stopDiscovery()
    }
}
