package com.zerocast.ui

import android.content.Intent
import android.os.Bundle
import android.view.HapticFeedbackConstants
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.zerocast.databinding.ActivityMainBinding
import com.zerocast.util.UpdateChecker

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupModuleCards()

        // Asynchronously check for GitHub updates
        UpdateChecker.checkForUpdates(this)
    }

    private fun setupModuleCards() {
        // Module 1: ZeroCast (Core Mirroring)
        binding.cardModuleZeroCast.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroCastActivity::class.java)
            startActivity(intent)
        }

        // Module 2: ZeroDrop (File Transfer)
        binding.cardModuleZeroDrop.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroDropActivity::class.java)
            startActivity(intent)
        }

        // Module 3: ZeroClip (Universal Clipboard)
        binding.cardModuleZeroClip.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroClipActivity::class.java)
            startActivity(intent)
        }

        // Module 4: ZeroPad (Virtual Controller)
        binding.cardModuleZeroPad.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            MaterialAlertDialogBuilder(this)
                .setTitle("🎮 ZeroPad")
                .setMessage("Transform your Android phone into a low-latency virtual gamepad, streamer macro deck, or wireless PC touchpad.\n\nComing soon in ZeroLink v1.2!")
                .setPositiveButton("Got it", null)
                .show()
        }
    }
}
