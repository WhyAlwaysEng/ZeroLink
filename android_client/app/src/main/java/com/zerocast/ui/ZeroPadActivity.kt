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
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            if (isConnected || binding.btnPadConnect.text == "Disconnect" || binding.btnPadConnect.text == "Connecting...") {
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

        // Section 3b: Gyro Air Mouse Setup
        setupGyroAirMouse()

        // Section 4: Remote Keyboard & Text Injection
        setupRemoteKeyboard()
    }

    private fun connect(host: String, port: Int) {
        disconnect()
        NetworkDiscovery.wakeModule(host, "zeropad")
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
                withContext(NonCancellable) {
                    withContext(Dispatchers.Main) {
                        disconnect()
                    }
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
    private var isDragging = false
    private var twoFingerDownTime = 0L
    private var isTwoFingerTapCandidate = false
    private val dragHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private var dragRunnable: Runnable? = null
    private val moveSensitivity = 1.6f
    private val scrollSensitivity = 1.2f

    // Gyro Air Mouse Sensor & State
    private var sensorManager: android.hardware.SensorManager? = null
    private var gyroSensor: android.hardware.Sensor? = null
    private var isGyroEnabled = false
    private var isAimHolding = false
    private var isGyroRegistered = false
    private var gyroSensitivity = 1.8f

    private val gyroListener = object : android.hardware.SensorEventListener {
        override fun onSensorChanged(event: android.hardware.SensorEvent) {
            if (event.sensor.type == android.hardware.Sensor.TYPE_GYROSCOPE) {
                if (isGyroEnabled || isAimHolding) {
                    val pitchVel = event.values[0] // Rotation around X (Up/Down)
                    val yawVel = event.values[2]   // Rotation around Z (Left/Right)

                    val deadzone = 0.035f
                    val rawDx = -yawVel
                    val rawDy = -pitchVel

                    val dx = if (Math.abs(rawDx) > deadzone) rawDx * gyroSensitivity * 16f else 0f
                    val dy = if (Math.abs(rawDy) > deadzone) rawDy * gyroSensitivity * 16f else 0f

                    if (dx.toInt() != 0 || dy.toInt() != 0) {
                        sendMouseMove(dx.toInt(), dy.toInt())
                    }
                }
            }
        }

        override fun onAccuracyChanged(sensor: android.hardware.Sensor?, accuracy: Int) {}
    }

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
                    isDragging = false

                    // Schedule Hold-to-Drag gesture (press and hold still for 260ms)
                    dragRunnable?.let { dragHandler.removeCallbacks(it) }
                    dragRunnable = Runnable {
                        if (isTapCandidate && !isDragging) {
                            isDragging = true
                            isTapCandidate = false
                            view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                            sendMouseDown("left")
                            binding.tvTrackpadHint.text = "● DRAGGING / SELECTING (Lift finger to drop)"
                            binding.tvTrackpadHint.setTextColor(android.graphics.Color.parseColor("#111827"))
                        }
                    }
                    dragHandler.postDelayed(dragRunnable!!, 260)
                    true
                }
                android.view.MotionEvent.ACTION_POINTER_DOWN -> {
                    isTapCandidate = false
                    twoFingerDownTime = System.currentTimeMillis()
                    isTwoFingerTapCandidate = true
                    dragRunnable?.let { dragHandler.removeCallbacks(it) }
                    if (isDragging) {
                        sendMouseUp("left")
                        isDragging = false
                        binding.tvTrackpadHint.text = "Slide to move • Hold still to drag"
                        binding.tvTrackpadHint.setTextColor(android.graphics.Color.parseColor("#4B5563"))
                    }
                    lastTouchX = event.x
                    lastTouchY = event.y
                    true
                }
                android.view.MotionEvent.ACTION_POINTER_UP -> {
                    val twoElapsed = System.currentTimeMillis() - twoFingerDownTime
                    if (isTwoFingerTapCandidate && twoElapsed < 280) {
                        isTwoFingerTapCandidate = false
                        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        sendMouseClick("right")
                    }
                    true
                }
                android.view.MotionEvent.ACTION_MOVE -> {
                    if (event.pointerCount == 1) {
                        val dist = Math.hypot((event.x - startTouchX).toDouble(), (event.y - startTouchY).toDouble())
                        if (!isDragging && dist > 14.0) {
                            isTapCandidate = false
                            dragRunnable?.let { dragHandler.removeCallbacks(it) }
                        }
                        val dx = (event.x - lastTouchX) * moveSensitivity
                        val dy = (event.y - lastTouchY) * moveSensitivity
                        if (dx.toInt() != 0 || dy.toInt() != 0) {
                            sendMouseMove(dx.toInt(), dy.toInt())
                        }
                        lastTouchX = event.x
                        lastTouchY = event.y
                    } else if (event.pointerCount >= 2) {
                        val scrollDist = Math.abs(event.y - lastTouchY)
                        if (scrollDist > 8.0) {
                            isTwoFingerTapCandidate = false
                        }
                        isTapCandidate = false
                        dragRunnable?.let { dragHandler.removeCallbacks(it) }
                        if (isDragging) {
                            sendMouseUp("left")
                            isDragging = false
                            binding.tvTrackpadHint.text = "Slide to move • Hold still to drag"
                            binding.tvTrackpadHint.setTextColor(android.graphics.Color.parseColor("#4B5563"))
                        }
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
                    dragRunnable?.let { dragHandler.removeCallbacks(it) }
                    val elapsed = System.currentTimeMillis() - touchDownTime
                    if (isDragging) {
                        view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                        sendMouseUp("left")
                        isDragging = false
                        binding.tvTrackpadHint.text = "Slide to move • Hold still to drag"
                        binding.tvTrackpadHint.setTextColor(android.graphics.Color.parseColor("#4B5563"))
                    } else if (isTapCandidate && elapsed < 220) {
                        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        sendMouseClick("left")
                    }
                    true
                }
                android.view.MotionEvent.ACTION_CANCEL -> {
                    view.parent.requestDisallowInterceptTouchEvent(false)
                    dragRunnable?.let { dragHandler.removeCallbacks(it) }
                    if (isDragging) {
                        sendMouseUp("left")
                        isDragging = false
                        binding.tvTrackpadHint.text = "Slide to move • Hold still to drag"
                        binding.tvTrackpadHint.setTextColor(android.graphics.Color.parseColor("#4B5563"))
                    }
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

    private fun setupGyroAirMouse() {
        sensorManager = getSystemService(android.content.Context.SENSOR_SERVICE) as? android.hardware.SensorManager
        gyroSensor = sensorManager?.getDefaultSensor(android.hardware.Sensor.TYPE_GYROSCOPE)

        if (gyroSensor == null) {
            binding.tvGyroStatus.text = "Gyroscope sensor not available on this device"
            binding.switchGyroAirMouse.isEnabled = false
            binding.btnGyroHoldAim.isEnabled = false
            return
        }

        binding.switchGyroAirMouse.setOnCheckedChangeListener { _, isChecked ->
            isGyroEnabled = isChecked
            if (isChecked) {
                binding.tvGyroStatus.text = "● Active: Waving phone in air moves PC cursor"
                binding.tvGyroStatus.setTextColor(android.graphics.Color.parseColor("#111827"))
                registerGyro()
            } else {
                binding.tvGyroStatus.text = "Air Mouse sensor idle • Slide or Hold to aim"
                binding.tvGyroStatus.setTextColor(android.graphics.Color.parseColor("#4B5563"))
                if (!isAimHolding) unregisterGyro()
            }
        }

        binding.btnGyroHoldAim.setOnTouchListener { v, event ->
            when (event.action) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    isAimHolding = true
                    binding.tvGyroStatus.text = "● AIMING: Air pointer active"
                    binding.tvGyroStatus.setTextColor(android.graphics.Color.parseColor("#111827"))
                    registerGyro()
                    true
                }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                    isAimHolding = false
                    if (!isGyroEnabled) {
                        binding.tvGyroStatus.text = "Air Mouse sensor idle"
                        binding.tvGyroStatus.setTextColor(android.graphics.Color.parseColor("#4B5563"))
                        unregisterGyro()
                    }
                    true
                }
                else -> false
            }
        }

        binding.sbGyroSensitivity.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: android.widget.SeekBar?, progress: Int, fromUser: Boolean) {
                val sens = (progress.coerceAtLeast(5)) / 10.0f
                gyroSensitivity = sens
                binding.tvGyroSensVal.text = String.format(java.util.Locale.US, "%.1fx", sens)
            }
            override fun onStartTrackingTouch(seekBar: android.widget.SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: android.widget.SeekBar?) {}
        })
    }

    private fun registerGyro() {
        if (!isGyroRegistered && gyroSensor != null) {
            sensorManager?.registerListener(gyroListener, gyroSensor, android.hardware.SensorManager.SENSOR_DELAY_GAME)
            isGyroRegistered = true
        }
    }

    private fun unregisterGyro() {
        if (isGyroRegistered) {
            sensorManager?.unregisterListener(gyroListener)
            isGyroRegistered = false
        }
    }

    override fun onPause() {
        super.onPause()
        dragRunnable?.let { dragHandler.removeCallbacks(it) }
        if (isDragging) {
            isDragging = false
            sendMouseUp("left")
        }
        if (isGyroEnabled) {
            binding.switchGyroAirMouse.isChecked = false
        }
        unregisterGyro()
    }

    private fun setupRemoteKeyboard() {
        binding.btnPadSendText.setOnClickListener {
            val text = binding.etPadInputText.text?.toString() ?: ""
            if (text.isNotEmpty()) {
                it.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                sendTypeText(text)
                binding.etPadInputText.setText("")
            }
        }

        binding.etPadInputText.setOnEditorActionListener { _, actionId, event ->
            if (actionId == android.view.inputmethod.EditorInfo.IME_ACTION_SEND ||
                (event != null && event.keyCode == android.view.KeyEvent.KEYCODE_ENTER && !event.isShiftPressed)) {
                val text = binding.etPadInputText.text?.toString() ?: ""
                if (text.isNotEmpty()) {
                    sendTypeText(text)
                    binding.etPadInputText.setText("")
                }
                true
            } else {
                false
            }
        }

        binding.btnKeyBackspace.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendSpecialKey("BACKSPACE")
        }
        binding.btnKeySpace.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendSpecialKey("SPACE")
        }
        binding.btnKeyEnter.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendSpecialKey("ENTER")
        }
        binding.btnKeyTab.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            sendSpecialKey("TAB")
        }
    }

    private fun sendTypeText(text: String) {
        val json = JSONObject().apply {
            put("action", "TYPE_TEXT")
            put("text", text)
        }
        sendJson(json)
    }

    private fun sendSpecialKey(key: String) {
        val json = JSONObject().apply {
            put("action", "SPECIAL_KEY")
            put("key", key)
        }
        sendJson(json)
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
        dragRunnable?.let { dragHandler.removeCallbacks(it) }
        if (isDragging) {
            isDragging = false
            sendMouseUp("left")
        }
        unregisterGyro()
        disconnect()
        discovery?.stopDiscovery()
    }
}
