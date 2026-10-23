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
            Toast.makeText(this, "⌁ USB Mode Selected (127.0.0.1)", Toast.LENGTH_SHORT).show()
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

        // Section 3: Precision Trackpad Setup
        setupTouchpad()
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
                    binding.tvPadStatus.text = if (isWired) "● Connected (⌁ USB)" else "● Connected (◫ Wi-Fi)"
                    binding.tvPadStatus.setTextColor(android.graphics.Color.parseColor("#111827"))
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
            binding.tvPadStatus.setTextColor(android.graphics.Color.parseColor("#4B5563"))
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

    private var lastTouchX = 0f
    private var lastTouchY = 0f
    private var startTouchX = 0f
    private var startTouchY = 0f
    private var touchDownTime = 0L
    private var isTapCandidate = false
    private val moveSensitivity = 1.6f
    private val scrollSensitivity = 1.2f

    @android.annotation.SuppressLint("ClickableViewAccessibility")
    private fun setupTouchpad() {
        binding.touchpadSurface.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    view.parent.requestDisallowInterceptTouchEvent(true)
                    startTouchX = event.x
                    startTouchY = event.y
                    lastTouchX = event.x
                    lastTouchY = event.y
                    touchDownTime = System.currentTimeMillis()
                    isTapCandidate = true
                    true
                }
                android.view.MotionEvent.ACTION_POINTER_DOWN -> {
                    isTapCandidate = false
                    lastTouchX = event.x
                    lastTouchY = event.y
                    true
                }
                android.view.MotionEvent.ACTION_MOVE -> {
                    if (event.pointerCount == 1) {
                        val dx = (event.x - lastTouchX) * moveSensitivity
                        val dy = (event.y - lastTouchY) * moveSensitivity
                        if (Math.abs(event.x - startTouchX) > 12f || Math.abs(event.y - startTouchY) > 12f) {
                            isTapCandidate = false
                        }
                        if (dx.toInt() != 0 || dy.toInt() != 0) {
                            sendMouseMove(dx.toInt(), dy.toInt())
                        }
                        lastTouchX = event.x
                        lastTouchY = event.y
                    } else if (event.pointerCount >= 2) {
                        isTapCandidate = false
                        val dy = (event.y - lastTouchY) * scrollSensitivity
                        if (dy.toInt() != 0) {
                            sendMouseScroll((dy * 15).toInt())
                        }
                        lastTouchY = event.y
                    }
                    true
                }
                android.view.MotionEvent.ACTION_UP -> {
                    view.parent.requestDisallowInterceptTouchEvent(false)
                    val elapsed = System.currentTimeMillis() - touchDownTime
                    if (isTapCandidate && elapsed < 220) {
                        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        sendMouseClick("left")
                    }
                    true
                }
                android.view.MotionEvent.ACTION_CANCEL -> {
                    view.parent.requestDisallowInterceptTouchEvent(false)
                    true
                }
                else -> false
            }
        }

        binding.btnMouseLeft.setOnTouchListener { v, event ->
            when (event.action) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    sendMouseDown("left")
                    true
                }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                    sendMouseUp("left")
                    true
                }
                else -> false
            }
        }

        binding.btnMouseRight.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            sendMouseClick("right")
        }
    }

    private fun sendMouseMove(dx: Int, dy: Int) {
        val json = JSONObject().apply {
            put("action", "MOUSE_MOVE")
            put("dx", dx)
            put("dy", dy)
        }
        sendJson(json)
    }

    private fun sendMouseClick(button: String) {
        val json = JSONObject().apply {
            put("action", "MOUSE_CLICK")
            put("button", button)
        }
        sendJson(json)
    }

    private fun sendMouseDown(button: String) {
        val json = JSONObject().apply {
            put("action", "MOUSE_DOWN")
            put("button", button)
        }
        sendJson(json)
    }

    private fun sendMouseUp(button: String) {
        val json = JSONObject().apply {
            put("action", "MOUSE_UP")
            put("button", button)
        }
        sendJson(json)
    }

    private fun sendMouseScroll(dy: Int) {
        val json = JSONObject().apply {
            put("action", "MOUSE_SCROLL")
            put("dy", dy)
        }
        sendJson(json)
    }

    override fun onDestroy() {
        super.onDestroy()
        disconnect()
        discovery?.stopDiscovery()
    }
}
