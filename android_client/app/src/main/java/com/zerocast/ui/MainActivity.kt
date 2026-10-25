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
import com.zerocast.BuildConfig
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

        // Dynamic Version & GitHub Update Trigger
        val currentVer = BuildConfig.VERSION_NAME
        binding.tvHeaderSubtitle.text = "Ecosystem Hub v$currentVer • Windows & Android"
        binding.tvHeaderSubtitle.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            UpdateChecker.checkForUpdates(this, isManualCheck = true)
        }

        binding.btnSettings.setOnClickListener {
            if (ZeroLinkConfig.getHapticFeedback(this)) {
                it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            }
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        setupDiscoveryCard()
        setupNotificationMirrorCard()
        setupModuleCards()

        // Asynchronously check for GitHub updates in background
        UpdateChecker.checkForUpdates(this, isManualCheck = false)
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

    private fun updateDiscoveryCardUI(mode: String, ip: String, name: String = "ZeroLink PC") {
        binding.tvDiscoveryTitle.text = name
        when (mode) {
            ZeroLinkConfig.MODE_USB -> {
                binding.tvDiscoverySubtitle.text = "Linked (USB ADB): 127.0.0.1"
                binding.tvDiscoveryBadge.text = "● USB"
                binding.tvHubStatus.text = "● LINKED"
            }
            ZeroLinkConfig.MODE_TETHER -> {
                val isTether = NetworkDiscovery.isTetheringIp(ip)
                val displayIp = if (isTether) ip else "Searching USB..."
                binding.tvDiscoverySubtitle.text = "Linked (USB Tether): $displayIp"
                binding.tvDiscoveryBadge.text = "● TETHER"
                binding.tvHubStatus.text = if (isTether) "● LINKED" else "○ SEARCHING"
            }
            ZeroLinkConfig.MODE_WIFI -> {
                val isWifi = NetworkDiscovery.isWifiIp(ip)
                binding.tvDiscoverySubtitle.text = if (isWifi) "Linked (Wi-Fi LAN): $ip" else "Scanning Wi-Fi LAN..."
                binding.tvDiscoveryBadge.text = if (isWifi) "● CONNECTED" else "● SCANNING"
                binding.tvHubStatus.text = if (isWifi) "● LINKED" else "○ STANDBY"
            }
            ZeroLinkConfig.MODE_MANUAL -> {
                binding.tvDiscoverySubtitle.text = "Target IP: $ip"
                binding.tvDiscoveryBadge.text = "● MANUAL"
                binding.tvHubStatus.text = if (ip.isNotEmpty()) "● LINKED" else "○ STANDBY"
            }
            else -> {
                when {
                    ip == "127.0.0.1" -> {
                        binding.tvDiscoverySubtitle.text = "Linked (USB ADB): 127.0.0.1"
                        binding.tvDiscoveryBadge.text = "● USB"
                        binding.tvHubStatus.text = "● LINKED"
                    }
                    NetworkDiscovery.isTetheringIp(ip) -> {
                        binding.tvDiscoverySubtitle.text = "Linked (USB Tether): $ip"
                        binding.tvDiscoveryBadge.text = "● TETHER"
                        binding.tvHubStatus.text = "● LINKED"
                    }
                    else -> {
                        val isWifi = NetworkDiscovery.isWifiIp(ip)
                        binding.tvDiscoverySubtitle.text = if (isWifi) "Linked (Wi-Fi LAN): $ip" else "Scanning Wi-Fi LAN..."
                        binding.tvDiscoveryBadge.text = if (isWifi) "● CONNECTED" else "● SCANNING"
                        binding.tvHubStatus.text = if (isWifi) "● LINKED" else "○ STANDBY"
                    }
                }
            }
        }
    }

    private fun startDiscovery() {
        val currentIp = ZeroLinkConfig.getServerIp(this)
        val mode = ZeroLinkConfig.getConnectionMode(this)

        updateDiscoveryCardUI(mode, currentIp)

        // 1. If user locked to USB ADB mode:
        if (mode == ZeroLinkConfig.MODE_USB) {
            networkDiscovery?.stopListening()
            networkDiscovery = NetworkDiscovery { ip, _, name ->
                if (ip == "127.0.0.1") {
                    updateDiscoveryCardUI(ZeroLinkConfig.MODE_USB, "127.0.0.1", name)
                }
            }
            networkDiscovery?.startListening(ZeroLinkConfig.MODE_USB)
            return
        }

        // 2. If user locked to USB Tethering mode:
        if (mode == ZeroLinkConfig.MODE_TETHER) {
            networkDiscovery?.stopListening()
            networkDiscovery = NetworkDiscovery { ip, _, name ->
                if (NetworkDiscovery.isTetheringIp(ip)) {
                    ZeroLinkConfig.setServerIp(this, ip)
                    updateDiscoveryCardUI(ZeroLinkConfig.MODE_TETHER, ip, name)
                }
            }
            networkDiscovery?.startListening(ZeroLinkConfig.MODE_TETHER)
            return
        }

        // 3. If user locked to Wi-Fi mode:
        if (mode == ZeroLinkConfig.MODE_WIFI) {
            networkDiscovery?.stopListening()
            networkDiscovery = NetworkDiscovery { ip, _, name ->
                if (NetworkDiscovery.isWifiIp(ip)) {
                    ZeroLinkConfig.setServerIp(this, ip)
                    updateDiscoveryCardUI(ZeroLinkConfig.MODE_WIFI, ip, name)
                }
            }
            networkDiscovery?.startListening(ZeroLinkConfig.MODE_WIFI)
            return
        }

        // 4. If user entered Manual IP:
        if (mode == ZeroLinkConfig.MODE_MANUAL) {
            networkDiscovery?.stopListening()
            return
        }

        // 5. AUTO mode:
        networkDiscovery?.stopListening()
        networkDiscovery = NetworkDiscovery { ip, _, name ->
            val linkType = when {
                ip == "127.0.0.1" -> "USB ADB"
                ip.startsWith("10.") || ip.startsWith("192.168.42.") || ip.startsWith("192.168.43.") -> "USB Tether"
                else -> "Wi-Fi LAN"
            }

            // Priority Check: Wi-Fi UDP beacon MUST NOT overwrite an active USB ADB link
            val activeIp = ZeroLinkConfig.getServerIp(this)
            val currentIsUsb = activeIp == "127.0.0.1"
            if (currentIsUsb && ip != "127.0.0.1") {
                return@NetworkDiscovery
            }

            ZeroLinkConfig.setServerIp(this, ip)
            binding.tvDiscoveryTitle.text = name
            binding.tvDiscoverySubtitle.text = "Linked ($linkType): $ip"
            binding.tvDiscoveryBadge.text = "● CONNECTED"
            binding.tvHubStatus.text = "● LINKED"
        }
        networkDiscovery?.startListening(ZeroLinkConfig.MODE_AUTO)
    }

    private fun setupDiscoveryCard() {
        binding.cardDiscovery.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            showManualIpDialog()
        }
    }

    private fun showManualIpDialog() {
        val items = arrayOf(
            "⌁ USB ADB (127.0.0.1) • Ultra Latency <1ms",
            "⚡ USB Tethering (Virtual LAN)",
            "📡 Wi-Fi LAN (Auto-Discover PC)",
            "✍️ Enter Custom IP Address..."
        )

        MaterialAlertDialogBuilder(this)
            .setTitle("Select Connection Mode")
            .setItems(items) { _, which ->
                when (which) {
                    0 -> {
                        // USB ADB
                        ZeroLinkConfig.setConnectionMode(this, ZeroLinkConfig.MODE_USB)
                        ZeroLinkConfig.setServerIp(this, "127.0.0.1")
                        startDiscovery()
                        Toast.makeText(this, "⚡ Switched to USB ADB mode (127.0.0.1)", Toast.LENGTH_SHORT).show()
                    }
                    1 -> {
                        // USB Tethering
                        ZeroLinkConfig.setConnectionMode(this, ZeroLinkConfig.MODE_TETHER)
                        val tetherCandidate = NetworkDiscovery.getTetheringHostCandidate()
                        if (tetherCandidate != null) {
                            ZeroLinkConfig.setServerIp(this, tetherCandidate)
                        } else {
                            val lastIp = ZeroLinkConfig.getServerIp(this)
                            if (!NetworkDiscovery.isTetheringIp(lastIp)) {
                                ZeroLinkConfig.setServerIp(this, "")
                            }
                        }
                        startDiscovery()
                        val msg = if (tetherCandidate != null) "⚡ USB Tethering mode: $tetherCandidate" else "⚡ Switched to USB Tethering mode"
                        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                    }
                    2 -> {
                        // Wi-Fi LAN
                        ZeroLinkConfig.setConnectionMode(this, ZeroLinkConfig.MODE_WIFI)
                        val lastIp = ZeroLinkConfig.getServerIp(this)
                        if (lastIp == "127.0.0.1" || NetworkDiscovery.isTetheringIp(lastIp)) {
                            ZeroLinkConfig.setServerIp(this, "")
                        }
                        startDiscovery()
                        Toast.makeText(this, "📡 Switched to Wi-Fi LAN mode", Toast.LENGTH_SHORT).show()
                    }
                    3 -> {
                        // Custom IP
                        ZeroLinkConfig.setConnectionMode(this, ZeroLinkConfig.MODE_MANUAL)
                        showCustomIpInputDialog()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showCustomIpInputDialog() {
        val currentIp = ZeroLinkConfig.getServerIp(this)
        val input = EditText(this).apply {
            hint = "e.g. 192.168.1.100 or 10.242.214.162"
            setText(if (currentIp != "127.0.0.1") currentIp else "")
            setSingleLine()
            setPadding(50, 40, 50, 40)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle("Manual PC IP Address")
            .setMessage("Enter your PC's IP address directly:")
            .setView(input)
            .setPositiveButton("Save & Connect") { _, _ ->
                val ip = input.text.toString().trim()
                if (ip.isNotEmpty()) {
                    ZeroLinkConfig.setServerIp(this, ip)
                    binding.tvDiscoverySubtitle.text = "Target: $ip"
                    binding.tvDiscoveryBadge.text = "● SET"
                }
                startDiscovery()
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

    private fun openModuleWithWake(moduleId: String, activityClass: Class<*>) {
        val serverIp = ZeroLinkConfig.getServerIp(this)
        if (serverIp.isNotEmpty()) {
            NetworkDiscovery.wakeModule(serverIp, moduleId)
            if (moduleId == "zeromix") {
                NetworkDiscovery.wakeModule(serverIp, "zerocast")
            }
        }
        val intent = Intent(this, activityClass)
        startActivity(intent)
    }

    private fun setupModuleCards() {
        // Module 1: ZeroCast (Core Mirroring)
        binding.cardModuleZeroCast.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zerocast", ZeroCastActivity::class.java)
        }

        // Module 2: ZeroDrop (File Transfer)
        binding.cardModuleZeroDrop.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zerodrop", ZeroDropActivity::class.java)
        }

        // Module 3: ZeroClip (Universal Clipboard)
        binding.cardModuleZeroClip.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zeroclip", ZeroClipActivity::class.java)
        }

        // Module 4: ZeroMix (Virtual Audio Mixer & Sound Deck)
        binding.cardModuleZeroMix.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zeromix", ZeroMixActivity::class.java)
        }

        // Module 5: ZeroDisplay (Extended 2nd Monitor)
        binding.cardModuleZeroDisplay.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zerodisplay", ZeroDisplayActivity::class.java)
        }

        // Module 6: ZeroCam (Wireless 4K Webcam)
        binding.cardModuleZeroCam.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zerocam", ZeroCamActivity::class.java)
        }

        // Module 7: ZeroPad (Stream Deck & PC Media Remote)
        binding.cardModuleZeroPad.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zeropad", ZeroPadActivity::class.java)
        }

        // Module 8: ZeroExplorer (Phone Gallery & Storage Explorer)
        binding.cardModuleZeroExplorer.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zeroexplorer", ZeroExplorerActivity::class.java)
        }

        // Module 9: ZeroDev (Module Workshop & Latency Probe)
        binding.cardModuleZeroDev.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModuleWithWake("zerodev", ZeroDevActivity::class.java)
        }
    }
}
