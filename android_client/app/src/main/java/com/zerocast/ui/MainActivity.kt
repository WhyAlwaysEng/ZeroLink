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

        // Module 4: ZeroMix (Virtual Audio Mixer & Sound Deck)
        binding.cardModuleZeroMix.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroMixActivity::class.java)
            startActivity(intent)
        }

        // Module 5: ZeroDisplay (Extended 2nd Monitor)
        binding.cardModuleZeroDisplay.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroDisplayActivity::class.java)
            startActivity(intent)
        }

        // Module 6: ZeroCam (Wireless 4K Webcam)
        binding.cardModuleZeroCam.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroCamActivity::class.java)
            startActivity(intent)
        }

        // Module 7: ZeroPad (Stream Deck & PC Media Remote)
        binding.cardModuleZeroPad.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroPadActivity::class.java)
            startActivity(intent)
        }

        // Module 8: ZeroExplorer (Phone Gallery & Storage Explorer)
        binding.cardModuleZeroExplorer.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroExplorerActivity::class.java)
            startActivity(intent)
        }
    }
}
