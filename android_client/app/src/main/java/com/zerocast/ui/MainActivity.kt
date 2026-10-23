package com.zerocast.ui

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.HapticFeedbackConstants
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.zerocast.R
import com.zerocast.databinding.ActivityMainBinding
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.UpdateChecker
import com.zerocast.util.ZeroLinkConfig

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var networkDiscovery: NetworkDiscovery? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupDiscoveryCard()
        setupNotificationMirrorCard()
        setupModuleCards()

        // Asynchronously check for GitHub updates
        UpdateChecker.checkForUpdates(this)
    }

    override fun onResume() {
        super.onResume()
        updateNotificationUiState()
        startDiscovery()
    }

    override fun onPause() {
        super.onPause()
        networkDiscovery?.stopListening()
    }

    private fun startDiscovery() {
        val currentIp = ZeroLinkConfig.getServerIp(this)
        if (currentIp.isNotEmpty() && currentIp != "127.0.0.1") {
            binding.tvDiscoveryTitle.text = "Linked PC"
            binding.tvDiscoverySubtitle.text = "IP: $currentIp • Ready"
            binding.tvDiscoveryBadge.text = "● LINKED"
        }

        networkDiscovery?.stopListening()
        networkDiscovery = NetworkDiscovery { ip, _, name ->
            ZeroLinkConfig.setServerIp(this, ip)
            binding.tvDiscoveryTitle.text = name
            binding.tvDiscoverySubtitle.text = "Linked: $ip • Auto-Connected"
            binding.tvDiscoveryBadge.text = "● CONNECTED"
            binding.tvHubStatus.text = "● LINKED"
        }
        networkDiscovery?.startListening()
    }

    private fun setupDiscoveryCard() {
        binding.cardDiscovery.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            showManualIpDialog()
        }
    }

    private fun showManualIpDialog() {
        val currentIp = ZeroLinkConfig.getServerIp(this)
        val input = EditText(this).apply {
            hint = "e.g. 192.168.1.100"
            setText(if (currentIp != "127.0.0.1") currentIp else "")
            setSingleLine()
            setPadding(50, 40, 50, 40)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle("PC Link & Auto-Discovery")
            .setMessage("ZeroLink automatically detects your PC over Wi-Fi. You can also specify the IP address manually:")
            .setView(input)
            .setPositiveButton("Save & Rescan") { _, _ ->
                val ip = input.text.toString().trim()
                if (ip.isNotEmpty()) {
                    ZeroLinkConfig.setServerIp(this, ip)
                    binding.tvDiscoverySubtitle.text = "Manual Target: $ip"
                    binding.tvDiscoveryBadge.text = "● SET"
                }
                startDiscovery()
            }
            .setNeutralButton("Rescan LAN") { _, _ ->
                startDiscovery()
                Toast.makeText(this, "Scanning for ZeroLink PC on Wi-Fi...", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun isNotificationAccessGranted(): Boolean {
        val pkgName = packageName
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        return flat != null && flat.contains(pkgName)
    }

    private fun updateNotificationUiState() {
        val isGranted = isNotificationAccessGranted()
        val isPrefEnabled = ZeroLinkConfig.getNotifyMirror(this)

        binding.switchZeroNotify.setOnCheckedChangeListener(null)
        binding.switchZeroNotify.isChecked = isGranted && isPrefEnabled

        if (!isGranted && isPrefEnabled) {
            binding.tvNotifySubtitle.text = "Permission needed: Tap to grant notification access"
        } else if (isGranted && isPrefEnabled) {
            binding.tvNotifySubtitle.text = "Active: Mirroring LINE, calls & alerts to PC"
        } else {
            binding.tvNotifySubtitle.text = "Mirror calls, LINE & alerts to PC tray"
        }

        binding.switchZeroNotify.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                if (!isNotificationAccessGranted()) {
                    binding.switchZeroNotify.isChecked = false
                    Toast.makeText(this, "Please grant Notification Access for ZeroLink", Toast.LENGTH_LONG).show()
                    try {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    } catch (_: Exception) {
                        startActivity(Intent(Settings.ACTION_SETTINGS))
                    }
                } else {
                    ZeroLinkConfig.setNotifyMirror(this, true)
                    binding.tvNotifySubtitle.text = "Active: Mirroring LINE, calls & alerts to PC"
                    Toast.makeText(this, "ZeroNotify active: Notifications will mirror to PC", Toast.LENGTH_SHORT).show()
                }
            } else {
                ZeroLinkConfig.setNotifyMirror(this, false)
                binding.tvNotifySubtitle.text = "Mirror calls, LINE & alerts to PC tray"
            }
        }
    }

    private fun setupNotificationMirrorCard() {
        binding.cardZeroNotify.setOnClickListener {
            binding.switchZeroNotify.performClick()
        }
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

        // Module 9: ZeroDev (Module Workshop & Latency Probe)
        binding.cardModuleZeroDev.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val intent = Intent(this, ZeroDevActivity::class.java)
            startActivity(intent)
        }
    }
}
