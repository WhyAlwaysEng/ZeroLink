package com.zerocast.ui

import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.os.Bundle
import android.provider.Settings
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.zerocast.BuildConfig
import com.zerocast.R
import com.zerocast.databinding.ActivityMainBinding
import com.zerocast.network.ConnectionState
import com.zerocast.network.EcosystemConnectionManager
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.UpdateChecker
import com.zerocast.util.ZeroLinkConfig
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var connMgr: EcosystemConnectionManager
    private var networkDiscovery: NetworkDiscovery? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        connMgr = EcosystemConnectionManager.getInstance(this)

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

        setupMasterGatewayPanel()
        setupNotificationMirrorCard()
        setupModuleCards()
        observeConnectionManager()

        // Asynchronously check for GitHub updates in background
        UpdateChecker.checkForUpdates(this, isManualCheck = false)
    }

    override fun onResume() {
        super.onResume()
        updateNotificationUiState()
        // No auto-connect on resume: User retains full manual control via Discovery or Connect button
    }

    override fun onDestroy() {
        super.onDestroy()
        networkDiscovery?.stopListening()
    }

    private fun setupMasterGatewayPanel() {
        // Mode Tabs
        binding.btnModeUsb.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            connMgr.switchMode(ZeroLinkConfig.MODE_USB, "127.0.0.1")
            Toast.makeText(this, "⚡ Switched to USB ADB (127.0.0.1)", Toast.LENGTH_SHORT).show()
        }

        binding.btnModeTether.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val candidate = NetworkDiscovery.getTetheringHostCandidate()
            connMgr.switchMode(ZeroLinkConfig.MODE_TETHER, candidate)
            val msg = if (candidate != null) "⚡ USB Tethering found: $candidate" else "⚡ Switched to USB Tethering mode"
            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
        }

        binding.btnModeWifi.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val lastWifi = ZeroLinkConfig.getServerIp(this).takeIf { ip -> NetworkDiscovery.isWifiIp(ip) }
            connMgr.switchMode(ZeroLinkConfig.MODE_WIFI, lastWifi)
            Toast.makeText(this, "📡 Switched to Wi-Fi LAN mode", Toast.LENGTH_SHORT).show()
        }

        // Master Connect / Disconnect Action Button
        binding.btnMasterConnect.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            when (connMgr.connectionState.value) {
                ConnectionState.CONNECTED, ConnectionState.CONNECTING, ConnectionState.RECONNECTING -> {
                    connMgr.disconnect()
                    Toast.makeText(this, "Disconnected from PC Gateway", Toast.LENGTH_SHORT).show()
                }
                ConnectionState.DISCONNECTED -> {
                    val inputIp = binding.etGatewayIp.text.toString().trim()
                    connMgr.connect(manualIp = inputIp.ifEmpty { null })
                }
            }
        }

        // Auto Discover Button - Pure Discovery without forcing auto-connect
        binding.btnAutoDiscoverGateway.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.tvGatewayHint.text = "🔍 Scanning network for ZeroLink PC..."
            networkDiscovery?.stopListening()
            networkDiscovery = NetworkDiscovery { ip, _, name ->
                runOnUiThread {
                    binding.etGatewayIp.setText(ip)
                    binding.tvDiscoveryTitle.text = name
                    binding.tvGatewayHint.text = "✅ Found: $name ($ip) • Tap CONNECT to link"
                    ZeroLinkConfig.setServerIp(this@MainActivity, ip)
                }
            }
            val currentMode = connMgr.activeMode.value
            networkDiscovery?.startListening(currentMode)
        }
    }

    private fun observeConnectionManager() {
        lifecycleScope.launch {
            connMgr.activeMode.collectLatest { mode ->
                updateModeTabsUI(mode)
            }
        }

        lifecycleScope.launch {
            connMgr.targetHost.collectLatest { host ->
                if (!binding.etGatewayIp.hasFocus()) {
                    binding.etGatewayIp.setText(host)
                }
            }
        }

        lifecycleScope.launch {
            connMgr.deviceName.collectLatest { name ->
                binding.tvDiscoveryTitle.text = name
            }
        }

        lifecycleScope.launch {
            connMgr.latencyMs.collectLatest { latency ->
                if (latency > 0) {
                    binding.tvPingLatency.text = "${latency}ms ping"
                    binding.tvPingLatency.setTextColor(Color.parseColor("#10B981"))
                } else {
                    binding.tvPingLatency.text = "-- ms"
                    binding.tvPingLatency.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_tertiary))
                }
            }
        }

        lifecycleScope.launch {
            connMgr.connectionState.collectLatest { state ->
                when (state) {
                    ConnectionState.CONNECTED -> {
                        binding.tvDiscoveryBadge.text = "● LINKED"
                        binding.tvDiscoveryBadge.setTextColor(Color.parseColor("#10B981"))
                        binding.tvDiscoveryBadge.setBackgroundResource(R.drawable.bg_badge_pill)
                        binding.tvHubStatus.text = "● LINKED"

                        binding.btnMasterConnect.text = "✕ DISCONNECT"
                        binding.btnMasterConnect.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#DC2626"))

                        val modeName = when (connMgr.activeMode.value) {
                            ZeroLinkConfig.MODE_USB -> "USB Cable ADB"
                            ZeroLinkConfig.MODE_TETHER -> "USB Tethering"
                            else -> "Wi-Fi LAN"
                        }
                        binding.tvDiscoverySubtitle.text = "Active single-pipe link via $modeName"
                    }
                    ConnectionState.CONNECTING -> {
                        binding.tvDiscoveryBadge.text = "○ CONNECTING"
                        binding.tvDiscoveryBadge.setTextColor(Color.parseColor("#F59E0B"))
                        binding.tvHubStatus.text = "○ CONNECTING"

                        binding.btnMasterConnect.text = "✕ CANCEL CONNECTING"
                        binding.btnMasterConnect.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#DC2626"))
                        binding.tvDiscoverySubtitle.text = "Connecting to Master Gateway on Port 8886..."
                    }
                    ConnectionState.RECONNECTING -> {
                        binding.tvDiscoveryBadge.text = "○ RECONNECTING"
                        binding.tvDiscoveryBadge.setTextColor(Color.parseColor("#F59E0B"))
                        binding.tvHubStatus.text = "○ RECONNECTING"

                        binding.btnMasterConnect.text = "✕ CANCEL RECONNECT"
                        binding.btnMasterConnect.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#DC2626"))
                        binding.tvDiscoverySubtitle.text = "Gateway heartbeat lost. Auto-reconnecting..."
                    }
                    ConnectionState.DISCONNECTED -> {
                        binding.tvDiscoveryBadge.text = "DISCONNECTED"
                        binding.tvDiscoveryBadge.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_secondary))
                        binding.tvHubStatus.text = "○ STANDBY"

                        binding.btnMasterConnect.text = "⚡ CONNECT TO PC"
                        binding.btnMasterConnect.backgroundTintList = ColorStateList.valueOf(Color.parseColor("#111827"))
                        binding.tvDiscoverySubtitle.text = "Single pipe for ZeroCast, ZeroCam, ZeroDisplay & all tools"
                    }
                }
            }
        }
    }

    private fun updateModeTabsUI(activeMode: String) {
        val primaryColor = ContextCompat.getColor(this, R.color.text_primary)
        val secondaryColor = ContextCompat.getColor(this, R.color.text_secondary)
        val activeBg = ColorStateList.valueOf(primaryColor)
        val inactiveBg = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.surface_variant))

        when (activeMode) {
            ZeroLinkConfig.MODE_USB -> {
                binding.btnModeUsb.backgroundTintList = activeBg
                binding.btnModeUsb.setTextColor(Color.WHITE)
                binding.btnModeTether.backgroundTintList = inactiveBg
                binding.btnModeTether.setTextColor(secondaryColor)
                binding.btnModeWifi.backgroundTintList = inactiveBg
                binding.btnModeWifi.setTextColor(secondaryColor)

                binding.btnAutoDiscoverGateway.visibility = View.GONE
                binding.tvGatewayHint.text = "USB ADB Cable Mode • Port 8886 Master Link (<1ms latency)"
            }
            ZeroLinkConfig.MODE_TETHER -> {
                binding.btnModeUsb.backgroundTintList = inactiveBg
                binding.btnModeUsb.setTextColor(secondaryColor)
                binding.btnModeTether.backgroundTintList = activeBg
                binding.btnModeTether.setTextColor(Color.WHITE)
                binding.btnModeWifi.backgroundTintList = inactiveBg
                binding.btnModeWifi.setTextColor(secondaryColor)

                binding.btnAutoDiscoverGateway.visibility = View.VISIBLE
                binding.tvGatewayHint.text = "USB Tethering Virtual LAN • Subnet 192.168.42.x / 10.x (<2ms latency)"
            }
            else -> { // MODE_WIFI
                binding.btnModeUsb.backgroundTintList = inactiveBg
                binding.btnModeUsb.setTextColor(secondaryColor)
                binding.btnModeTether.backgroundTintList = inactiveBg
                binding.btnModeTether.setTextColor(secondaryColor)
                binding.btnModeWifi.backgroundTintList = activeBg
                binding.btnModeWifi.setTextColor(Color.WHITE)

                binding.btnAutoDiscoverGateway.visibility = View.VISIBLE
                binding.tvGatewayHint.text = "Wi-Fi LAN Gateway • Fast 5GHz Recommended"
            }
        }
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

    private fun openModule(activityClass: Class<*>) {
        val intent = Intent(this, activityClass)
        startActivity(intent)
    }

    private fun setupModuleCards() {
        // Module 1: ZeroCast (Core Mirroring)
        binding.cardModuleZeroCast.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroCastActivity::class.java)
        }

        // Module 2: ZeroDrop (File Transfer)
        binding.cardModuleZeroDrop.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroDropActivity::class.java)
        }

        // Module 3: ZeroClip (Universal Clipboard)
        binding.cardModuleZeroClip.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroClipActivity::class.java)
        }

        // Module 4: ZeroMix (Virtual Audio Mixer & Sound Deck)
        binding.cardModuleZeroMix.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroMixActivity::class.java)
        }

        // Module 5: ZeroDisplay (Extended 2nd Monitor)
        binding.cardModuleZeroDisplay.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroDisplayActivity::class.java)
        }

        // Module 6: ZeroCam (Wireless 4K Webcam)
        binding.cardModuleZeroCam.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroCamActivity::class.java)
        }

        // Module 7: ZeroPad (Stream Deck & PC Media Remote)
        binding.cardModuleZeroPad.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroPadActivity::class.java)
        }

        // Module 8: ZeroExplorer (Phone Gallery & Storage Explorer)
        binding.cardModuleZeroExplorer.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openModule(ZeroExplorerActivity::class.java)
        }
    }
}
