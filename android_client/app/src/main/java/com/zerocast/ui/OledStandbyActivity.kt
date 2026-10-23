package com.zerocast.ui

import android.os.Bundle
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.zerocast.databinding.ActivityOledStandbyBinding

/**
 * Ultra-power-saver OLED black standby screen (#000000 pure black).
 * Keeps screen on and foreground network/camera/audio streaming alive
 * while turning off OLED pixels and dropping hardware brightness to 1%.
 * Double-tap anywhere to wake.
 */
class OledStandbyActivity : AppCompatActivity() {

    private lateinit var binding: ActivityOledStandbyBinding
    private lateinit var gestureDetector: GestureDetector

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Keep screen on so phone doesn't sleep / suspend Wi-Fi / kill stream
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Minimize hardware brightness to 0.01f (1%)
        val lp = window.attributes
        lp.screenBrightness = 0.01f
        window.attributes = lp

        // Fullscreen immersive (hide system status and nav bars)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE

        binding = ActivityOledStandbyBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val reason = intent.getStringExtra("EXTRA_REASON")
        if (!reason.isNullOrEmpty()) {
            binding.tvStandbySub.text = "$reason • 0% Screen Power"
        }

        gestureDetector = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDoubleTap(e: MotionEvent): Boolean {
                finish()
                return true
            }

            override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                binding.tvStandbyHint.alpha = 1.0f
                binding.tvStandbyHint.animate().alpha(0.45f).setDuration(1200).start()
                return true
            }
        })

        binding.root.setOnTouchListener { _, event ->
            gestureDetector.onTouchEvent(event)
            true
        }
    }
}
