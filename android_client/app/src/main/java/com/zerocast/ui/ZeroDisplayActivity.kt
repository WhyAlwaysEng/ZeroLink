package com.zerocast.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.SurfaceHolder
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.zerocast.databinding.ActivityZeroDisplayBinding
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.ZeroLinkConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.DataInputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket

class ZeroDisplayActivity : AppCompatActivity(), SurfaceHolder.Callback {

    companion object {
        private const val TAG = "ZeroDisplay"
        private const val DEFAULT_PORT = 8892
    }

    private lateinit var binding: ActivityZeroDisplayBinding
    private var surfaceHolder: SurfaceHolder? = null
    private var isSurfaceReady = false

    private var socket: Socket? = null
    private var outStream: OutputStream? = null
    private var inStream: DataInputStream? = null
    private var clientJob: Job? = null

    private var discovery: NetworkDiscovery? = null
    private val scope = CoroutineScope(Dispatchers.IO)

    // Touch gesture tracking
    private var prevY = 0f
    private var isTwoFingerScroll = false

    // Frame stats & rendering options
    private var frameCount = 0
    private var lastStatTime = System.currentTimeMillis()
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
    private val dstRect = Rect()
    private val bmpOptions = BitmapFactory.Options().apply {
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroDisplayBinding.inflate(layoutInflater)
        setContentView(binding.root)

        hideSystemUI()

        binding.surfaceDisplay.holder.addCallback(this)

        // Pre-fill IP from config or discovery
        val lastIp = ZeroLinkConfig.getServerIp(this)
        if (lastIp.isNotEmpty() && lastIp != "127.0.0.1") {
            binding.etDisplayHostIp.setText(lastIp)
        }

        discovery = NetworkDiscovery { discoveredIp, _ ->
            runOnUiThread {
                if (binding.etDisplayHostIp.text.isNullOrEmpty()) {
                    binding.etDisplayHostIp.setText(discoveredIp)
                }
            }
        }
        discovery?.startDiscovery()

        binding.btnConnectDisplay.setOnClickListener {
            val ip = binding.etDisplayHostIp.text.toString().trim()
            if (ip.isEmpty()) {
                Toast.makeText(this, "Please enter PC Host IP", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            ZeroLinkConfig.setServerIp(this, ip)
            startDisplayStream(ip, DEFAULT_PORT)
        }

        binding.btnDisplayBack.setOnClickListener {
            finish()
        }

        binding.btnHudBack.setOnClickListener {
            finish()
        }

        binding.btnHudDisconnect.setOnClickListener {
            disconnectStream()
        }

        setupTouchListener()
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        surfaceHolder = holder
        isSurfaceReady = true
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        dstRect.set(0, 0, width, height)
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        isSurfaceReady = false
        surfaceHolder = null
    }

    private fun startDisplayStream(hostIp: String, port: Int) {
        disconnectStream()

        binding.layoutSetup.visibility = View.GONE
        binding.layoutHud.visibility = View.VISIBLE
        binding.tvHudStatus.text = "● Connecting..."

        clientJob = scope.launch {
            try {
                val s = Socket()
                s.tcpNoDelay = true
                s.connect(InetSocketAddress(hostIp, port), 4000)
                socket = s
                outStream = s.getOutputStream()
                inStream = DataInputStream(s.getInputStream())

                // Send handshake with device model
                val handshake = JSONObject().apply {
                    put("action", "CONNECT")
                    put("model", Build.MODEL)
                    put("device_model", Build.MODEL)
                }
                sendJson(handshake)

                withContext(Dispatchers.Main) {
                    binding.tvHudStatus.text = "● Connected (60 FPS)"
                }

                // Stream decoding loop
                val magicBuf = ByteArray(4)
                while (isActive && !s.isClosed) {
                    inStream?.readFully(magicBuf)
                    val magic = String(magicBuf, Charsets.US_ASCII)
                    if (magic != "ZDIS") {
                        // Resync if misaligned
                        continue
                    }

                    val payloadLen = inStream!!.readInt()
                    val timestamp = inStream!!.readLong()

                    if (payloadLen <= 0 || payloadLen > 10 * 1024 * 1024) {
                        continue
                    }

                    val jpegData = ByteArray(payloadLen)
                    inStream!!.readFully(jpegData)

                    val bmp = BitmapFactory.decodeByteArray(jpegData, 0, payloadLen, bmpOptions)
                    if (bmp != null && isSurfaceReady && surfaceHolder != null) {
                        val canvas = surfaceHolder?.lockCanvas()
                        if (canvas != null) {
                            try {
                                canvas.drawColor(Color.BLACK)
                                canvas.drawBitmap(bmp, null, dstRect, paint)
                            } finally {
                                surfaceHolder?.unlockCanvasAndPost(canvas)
                            }
                        }
                        bmp.recycle()

                        frameCount++
                        val now = System.currentTimeMillis()
                        if (now - lastStatTime >= 1000) {
                            val fps = frameCount * 1000f / (now - lastStatTime)
                            frameCount = 0
                            lastStatTime = now
                            withContext(Dispatchers.Main) {
                                binding.tvHudStatus.text = "● ${fps.toInt()} FPS"
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Stream error: ${e.message}")
            } finally {
                withContext(NonCancellable) {
                    withContext(Dispatchers.Main) {
                        disconnectStream()
                    }
                }
            }
        }
    }

    private fun sendJson(json: JSONObject) {
        scope.launch {
            try {
                val bytes = (json.toString() + "\n").toByteArray(Charsets.UTF_8)
                outStream?.write(bytes)
                outStream?.flush()
            } catch (e: Exception) {
                Log.e(TAG, "sendJson error: ${e.message}")
            }
        }
    }

    private fun setupTouchListener() {
        binding.surfaceDisplay.setOnTouchListener { v, event ->
            if (outStream == null) return@setOnTouchListener false

            val width = v.width.toFloat()
            val height = v.height.toFloat()
            if (width <= 0 || height <= 0) return@setOnTouchListener false

            val normX = (event.x / width).coerceIn(0f, 1f)
            val normY = (event.y / height).coerceIn(0f, 1f)

            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    isTwoFingerScroll = false
                    prevY = event.y
                    val msg = JSONObject().apply {
                        put("action", "TOUCH_DOWN")
                        put("norm_x", normX)
                        put("norm_y", normY)
                        put("button", "left")
                    }
                    sendJson(msg)
                    true
                }
                MotionEvent.ACTION_POINTER_DOWN -> {
                    // Two fingers touched: toggle into scroll mode
                    if (event.pointerCount >= 2) {
                        isTwoFingerScroll = true
                        prevY = (event.getY(0) + event.getY(1)) / 2f
                    }
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (isTwoFingerScroll && event.pointerCount >= 2) {
                        val currentY = (event.getY(0) + event.getY(1)) / 2f
                        val dy = (currentY - prevY) / height * 8f
                        prevY = currentY
                        val msg = JSONObject().apply {
                            put("action", "SCROLL")
                            put("dy", dy)
                        }
                        sendJson(msg)
                    } else {
                        val msg = JSONObject().apply {
                            put("action", "TOUCH_MOVE")
                            put("norm_x", normX)
                            put("norm_y", normY)
                        }
                        sendJson(msg)
                    }
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    val msg = JSONObject().apply {
                        put("action", "TOUCH_UP")
                        put("norm_x", normX)
                        put("norm_y", normY)
                        put("button", "left")
                    }
                    sendJson(msg)
                    isTwoFingerScroll = false
                    true
                }
                else -> false
            }
        }
    }

    private fun disconnectStream() {
        clientJob?.cancel()
        clientJob = null
        try {
            socket?.close()
        } catch (e: Exception) {}
        socket = null
        outStream = null
        inStream = null

        binding.layoutSetup.visibility = View.VISIBLE
        binding.layoutHud.visibility = View.GONE
    }

    private fun hideSystemUI() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let { controller ->
                controller.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                controller.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            )
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        disconnectStream()
        discovery?.stopDiscovery()
    }
}
