package com.zerocast.ui

import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroClipBinding
import com.zerocast.network.ClipboardSyncManager
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.ZeroLinkConfig

class ZeroClipActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroClipBinding
    private var clipManager: ClipboardSyncManager? = null
    private var discovery: NetworkDiscovery? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroClipBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val savedIp = ZeroLinkConfig.getServerIp(this)
        binding.etServerIp.setText(savedIp)

        setupListeners()
        updateCurrentClipboardDisplay()

        clipManager = ClipboardSyncManager(this) { isConnected, msg ->
            binding.tvClipStatus.text = msg
            if (isConnected) {
                binding.tvClipStatus.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
                binding.btnConnect.text = "Disconnect"
            } else {
                binding.tvClipStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
                binding.btnConnect.text = "Sync"
            }
        }

        // Auto-connect on open
        startSync()
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            finish()
        }

        binding.btnConnect.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            if (binding.btnConnect.text == "Disconnect") {
                clipManager?.stop()
            } else {
                startSync()
            }
        }

        binding.btnModeUsb.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etServerIp.setText("127.0.0.1")
            startSync()
        }

        binding.btnAutoDiscover.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.tvClipStatus.text = "Searching..."
            discovery = NetworkDiscovery { ip, _ ->
                binding.etServerIp.setText(ip)
                ZeroLinkConfig.setServerIp(this, ip)
                startSync()
            }
            discovery?.startDiscovery()
        }

        binding.btnSendClipToPc.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip
            if (clip != null && clip.itemCount > 0) {
                val txt = clip.getItemAt(0).text?.toString() ?: ""
                if (txt.isNotEmpty()) {
                    clipManager?.sendClipboardText(txt)
                    Toast.makeText(this, "Pushed to PC clipboard!", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "Clipboard is empty", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun startSync() {
        val ip = binding.etServerIp.text.toString().trim()
        if (ip.isNotEmpty()) {
            ZeroLinkConfig.setServerIp(this, ip)
            clipManager?.start(ip, ZeroLinkConfig.DEFAULT_CLIP_PORT)
        }
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

    override fun onResume() {
        super.onResume()
        updateCurrentClipboardDisplay()
    }

    override fun onDestroy() {
        super.onDestroy()
        clipManager?.stop()
    }
}
