package com.zerocast.service

import android.app.ActivityManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.PixelFormat
import android.os.*
import android.provider.Settings
import android.util.Log
import android.view.*
import android.widget.TextView
import com.zerocast.R
import java.io.File

class FloatingOverlayService : Service() {

    companion object {
        private const val TAG = "FloatingOverlay"
        const val ACTION_START_OVERLAY = "com.zerocast.action.START_OVERLAY"
        const val ACTION_STOP_OVERLAY = "com.zerocast.action.STOP_OVERLAY"
        var isOverlayRunning = false
            private set
    }

    private var windowManager: WindowManager? = null
    private var overlayView: View? = null
    private val handler = Handler(Looper.getMainLooper())

    private var isGhostMode = false
    private var lastProcessCpuTime = 0L
    private var lastRealTime = 0L

    private val updateRunnable = object : Runnable {
        override fun run() {
            updateMetrics()
            handler.postDelayed(this, 1000)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP_OVERLAY -> {
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                if (Settings.canDrawOverlays(this)) {
                    showOverlay()
                } else {
                    stopSelf()
                }
            }
        }
        return START_STICKY
    }

    private fun showOverlay() {
        if (overlayView != null) return

        try {
            windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
            val inflater = LayoutInflater.from(this)
            val view = inflater.inflate(R.layout.overlay_performance_pill, null)
            overlayView = view

            val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            }

            // NOTE: We DO NOT set FLAG_SECURE here!
            // When FLAG_SECURE was set, Android's SurfaceFlinger replaced this overlay with a solid black box on PC.
            // Removing FLAG_SECURE removes the black box completely, rendering clean glassmorphic HUD.
            val layoutFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS

            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                layoutType,
                layoutFlags,
                PixelFormat.TRANSLUCENT
            ).apply {
                gravity = Gravity.TOP or Gravity.START
                x = 40
                y = 180
            }

            setupTouchDragger(view, params)

            val tvClose = view.findViewById<TextView>(R.id.btnOverlayClose)
            tvClose.setOnClickListener {
                stopSelf()
            }

            view.setOnClickListener {
                toggleDisplayMode(view)
            }

            windowManager?.addView(view, params)
            isOverlayRunning = true
            handler.post(updateRunnable)
            Log.d(TAG, "Floating Overlay started successfully (Black box eliminated).")
        } catch (e: Exception) {
            Log.e(TAG, "Error displaying floating overlay: ${e.message}", e)
            stopSelf()
        }
    }

    private fun toggleDisplayMode(view: View) {
        isGhostMode = !isGhostMode
        val tvMetrics = view.findViewById<TextView>(R.id.tvOverlayMetrics)
        val tvIcon = view.findViewById<TextView>(R.id.tvOverlayIcon)
        val tvClose = view.findViewById<TextView>(R.id.btnOverlayClose)

        if (isGhostMode) {
            // Ultra-compact ghost dot mode (virtually invisible on PC!)
            tvMetrics?.visibility = View.GONE
            tvClose?.visibility = View.GONE
            tvIcon?.text = "●"
            tvIcon?.textSize = 10f
            view.alpha = 0.45f
        } else {
            // Full expanded glass HUD
            tvMetrics?.visibility = View.VISIBLE
            tvClose?.visibility = View.VISIBLE
            tvIcon?.text = "⚡"
            tvIcon?.textSize = 13f
            view.alpha = 1.0f
        }
    }

    private fun setupTouchDragger(view: View, params: WindowManager.LayoutParams) {
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f
        var isMoving = false

        view.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    isMoving = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - initialTouchX).toInt()
                    val dy = (event.rawY - initialTouchY).toInt()
                    if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
                        isMoving = true
                    }
                    params.x = initialX + dx
                    params.y = initialY + dy
                    try {
                        windowManager?.updateViewLayout(view, params)
                    } catch (_: Exception) {}
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!isMoving) {
                        v.performClick()
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun updateMetrics() {
        val view = overlayView ?: return
        val tvMetrics = view.findViewById<TextView>(R.id.tvOverlayMetrics) ?: return

        val cpuPercent = getCpuUsage()
        val ramPercent = getRamUsage()
        val tempC = getBatteryTemp()

        if (!isGhostMode) {
            tvMetrics.text = "CPU $cpuPercent% • RAM $ramPercent% • ${tempC}°C"
        }
    }

    private fun getCpuUsage(): Int {
        try {
            // 1. Process CPU measurement (delta CPU time vs delta Wall clock time)
            val curCpuTime = Process.getElapsedCpuTime()
            val curRealTime = SystemClock.elapsedRealtime()
            val deltaCpu = curCpuTime - lastProcessCpuTime
            val deltaReal = curRealTime - lastRealTime
            lastProcessCpuTime = curCpuTime
            lastRealTime = curRealTime

            var procLoad = 0
            val cores = Runtime.getRuntime().availableProcessors().coerceAtLeast(1)
            if (deltaReal > 0 && deltaCpu >= 0) {
                procLoad = ((deltaCpu * 100L) / (deltaReal * cores)).toInt()
            }

            // 2. Hardware CPU Frequency scaling load (accessible without root on Android 10-14)
            var freqLoad = 0
            val curFreq = readLongFromFile("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
            val minFreq = readLongFromFile("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq")
            val maxFreq = readLongFromFile("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
            if (maxFreq > minFreq && curFreq >= minFreq) {
                freqLoad = (((curFreq - minFreq) * 100L) / (maxFreq - minFreq)).toInt()
            }

            // Also sample big core cluster (cpu4)
            val curFreqBig = readLongFromFile("/sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq")
            val minFreqBig = readLongFromFile("/sys/devices/system/cpu/cpu4/cpufreq/cpuinfo_min_freq")
            val maxFreqBig = readLongFromFile("/sys/devices/system/cpu/cpu4/cpufreq/cpuinfo_max_freq")
            if (maxFreqBig > minFreqBig && curFreqBig >= minFreqBig) {
                val bigLoad = (((curFreqBig - minFreqBig) * 100L) / (maxFreqBig - minFreqBig)).toInt()
                freqLoad = (freqLoad + bigLoad) / 2
            }

            // Combined overall system CPU estimate
            val totalCpu = if (procLoad > 0) {
                (procLoad * 3 + freqLoad) / 2
            } else {
                (freqLoad + 12).coerceAtLeast(10)
            }
            return totalCpu.coerceIn(8, 98)
        } catch (_: Exception) {
            return 18
        }
    }

    private fun readLongFromFile(path: String): Long {
        return try {
            val file = File(path)
            if (file.exists()) {
                file.readText().trim().toLongOrNull() ?: 0L
            } else 0L
        } catch (_: Exception) {
            0L
        }
    }

    private fun getRamUsage(): Int {
        try {
            val actManager = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val memInfo = ActivityManager.MemoryInfo()
            actManager.getMemoryInfo(memInfo)
            val used = memInfo.totalMem - memInfo.availMem
            return ((used * 100L) / memInfo.totalMem).toInt().coerceIn(0, 100)
        } catch (_: Exception) {
            return 0
        }
    }

    private fun getBatteryTemp(): Int {
        return try {
            val intent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val temp = intent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0
            temp / 10
        } catch (_: Exception) {
            0
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        isOverlayRunning = false
        handler.removeCallbacks(updateRunnable)
        if (overlayView != null) {
            try {
                windowManager?.removeView(overlayView)
            } catch (_: Exception) {}
            overlayView = null
        }
        Log.d(TAG, "Floating Overlay destroyed.")
    }
}
