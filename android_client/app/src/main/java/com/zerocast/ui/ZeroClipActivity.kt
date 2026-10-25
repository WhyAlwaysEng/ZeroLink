package com.zerocast.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroClipBinding
import com.zerocast.databinding.ItemClipHistoryBinding
import com.zerocast.network.ClipboardSyncManager
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.lifecycleScope
import com.zerocast.network.ConnectionState
import com.zerocast.network.EcosystemConnectionManager
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import com.zerocast.util.ZeroLinkConfig
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ZeroClipActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroClipBinding
    private var clipManager: ClipboardSyncManager? = null

    private lateinit var connMgr: EcosystemConnectionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroClipBinding.inflate(layoutInflater)
        setContentView(binding.root)

        connMgr = EcosystemConnectionManager.getInstance(this)

        setupListeners()
        observeConnectionState()
        updateCurrentClipboardDisplay()

        clipManager = ClipboardSyncManager(
            context = this,
            onStatusChanged = { isConnected, msg ->
                binding.tvClipStatus.text = msg
                if (isConnected) {
                    binding.tvClipStatus.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
                } else {
                    binding.tvClipStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
                }
            },
            onClipSynced = { text, source, ts ->
                updateCurrentClipboardDisplay()
                addHistoryItem(text, source, ts)
            }
        )

        val host = connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
        startSync(host)
    }

    private fun observeConnectionState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    connMgr.connectionState.collectLatest { state ->
                        updateConnectionUI(state, connMgr.activeMode.value, connMgr.targetHost.value)
                    }
                }
                launch {
                    connMgr.activeMode.collectLatest { mode ->
                        updateConnectionUI(connMgr.connectionState.value, mode, connMgr.targetHost.value)
                    }
                }
            }
        }
    }

    private fun updateConnectionUI(state: ConnectionState, mode: String, host: String) {
        val (icon, modeStr) = when (mode) {
            ZeroLinkConfig.MODE_USB -> Pair("⌁", "USB ADB Cable")
            ZeroLinkConfig.MODE_TETHER -> Pair("⚡", "USB Tethering")
            else -> Pair("📡", "Wi-Fi LAN")
        }

        binding.tvClipLinkIcon.text = icon
        when (state) {
            ConnectionState.CONNECTED -> {
                binding.tvClipLinkTitle.text = "Master Link: $modeStr"
                binding.tvClipLinkSubtitle.text = "Endpoint: $host:8893"
                binding.tvClipLinkBadge.text = "● READY"
                binding.tvClipLinkBadge.setTextColor(Color.parseColor("#10B981"))
            }
            ConnectionState.CONNECTING, ConnectionState.RECONNECTING -> {
                binding.tvClipLinkTitle.text = "Connecting to Master Link..."
                binding.tvClipLinkSubtitle.text = "Connecting to $host:8893..."
                binding.tvClipLinkBadge.text = "○ CONNECTING"
                binding.tvClipLinkBadge.setTextColor(Color.parseColor("#F59E0B"))
            }
            ConnectionState.DISCONNECTED -> {
                binding.tvClipLinkTitle.text = "Master Link: Offline"
                binding.tvClipLinkSubtitle.text = "Disconnected • Tap Home to connect"
                binding.tvClipLinkBadge.text = "○ OFFLINE"
                binding.tvClipLinkBadge.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
            }
        }
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            finish()
        }

        binding.cardConnectionStatus.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val host = connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
            startSync(host)
        }

        binding.btnSendClipToPc.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip
            if (clip != null && clip.itemCount > 0) {
                val txt = clip.getItemAt(0).text?.toString() ?: ""
                if (txt.isNotEmpty()) {
                    clipManager?.sendClipboardText(txt)
                    addHistoryItem(txt, "PHONE", System.currentTimeMillis())
                    Toast.makeText(this, "Pushed to PC clipboard!", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "Clipboard is empty", Toast.LENGTH_SHORT).show()
                }
            }
        }

        binding.btnClearHistory.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.llClipHistory.removeAllViews()
            binding.tvEmptyHistory.visibility = View.VISIBLE
        }
    }

    private fun startSync(targetHost: String? = null) {
        val ip = targetHost ?: connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
        clipManager?.start(ip, ZeroLinkConfig.DEFAULT_CLIP_PORT)
    }

    private fun updateCurrentClipboardDisplay() {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = cm.primaryClip
        if (clip != null && clip.itemCount > 0) {
            val text = clip.getItemAt(0).text?.toString()
            binding.tvCurrentClip.text = text ?: "Clipboard is empty"
        } else {
            binding.tvCurrentClip.text = "Clipboard is empty"
        }
    }

    private fun addHistoryItem(text: String, source: String, ts: Long) {
        binding.tvEmptyHistory.visibility = View.GONE
        val itemBinding = ItemClipHistoryBinding.inflate(layoutInflater, binding.llClipHistory, false)

        itemBinding.tvClipSource.text = if (source == "PC") "💻 From PC" else "📱 From Phone"
        val timeStr = SimpleDateFormat("hh:mm:ss a", Locale.getDefault()).format(Date(ts))
        itemBinding.tvClipTime.text = timeStr
        itemBinding.tvClipText.text = text

        itemBinding.btnCopyClip.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("ZeroClip", text))
            Toast.makeText(this, "Copied to clipboard", Toast.LENGTH_SHORT).show()
            updateCurrentClipboardDisplay()
        }

        binding.llClipHistory.addView(itemBinding.root, 0)
    }

    override fun onResume() {
        super.onResume()
        updateCurrentClipboardDisplay()
    }

    override fun onDestroy() {
        super.onDestroy()
        clipManager?.stop()
    }
}
