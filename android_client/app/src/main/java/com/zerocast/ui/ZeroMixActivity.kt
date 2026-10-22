package com.zerocast.ui

import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroMixBinding
import com.zerocast.databinding.ItemSoundboardBtnBinding
import com.zerocast.network.NetworkDiscovery
import com.zerocast.network.SoundboardItem
import com.zerocast.network.ZeroMixManager
import com.zerocast.network.ZeroMixState
import com.zerocast.util.ZeroLinkConfig

class ZeroMixActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroMixBinding
    private var mixManager: ZeroMixManager? = null
    private var discovery: NetworkDiscovery? = null

    private var isUserDragging = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroMixBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val savedIp = ZeroLinkConfig.getServerIp(this)
        binding.etServerIp.setText(savedIp)

        setupListeners()

        mixManager = ZeroMixManager(
            context = this,
            onStatusChanged = { isConnected, msg ->
                binding.tvMixStatus.text = msg
                if (isConnected) {
                    binding.tvMixStatus.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
                    binding.btnConnect.text = "Connected"
                } else {
                    binding.tvMixStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
                    binding.btnConnect.text = "Connect"
                }
            },
            onStateUpdated = { state ->
                applyMixerState(state)
            },
            onSoundsUpdated = { sounds ->
                renderSoundboard(sounds)
            }
        )

        // Auto-connect
        startConnect()
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            finish()
        }

        binding.btnConnect.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            startConnect()
        }

        binding.btnModeUsb.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etServerIp.setText("127.0.0.1")
            ZeroLinkConfig.setServerIp(this, "127.0.0.1")
            startConnect()
        }

        binding.btnAutoDiscover.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.tvMixStatus.text = "Searching..."
            discovery = NetworkDiscovery { ip, _ ->
                binding.etServerIp.setText(ip)
                ZeroLinkConfig.setServerIp(this, ip)
                startConnect()
            }
            discovery?.startDiscovery()
        }

        // Faders
        binding.sbMicVol.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                binding.tvMicVol.text = "$progress%"
                if (fromUser) {
                    mixManager?.setVolume("mic", progress)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) { isUserDragging = true }
            override fun onStopTrackingTouch(seekBar: SeekBar?) { isUserDragging = false }
        })

        binding.sbMusicVol.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                binding.tvMusicVol.text = "$progress%"
                if (fromUser) {
                    mixManager?.setVolume("music", progress)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) { isUserDragging = true }
            override fun onStopTrackingTouch(seekBar: SeekBar?) { isUserDragging = false }
        })

        binding.sbSoundVol.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                binding.tvSoundVol.text = "$progress%"
                if (fromUser) {
                    mixManager?.setVolume("soundboard", progress)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) { isUserDragging = true }
            override fun onStopTrackingTouch(seekBar: SeekBar?) { isUserDragging = false }
        })

        // Mute buttons
        binding.btnMuteMic.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val isMuted = binding.btnMuteMic.text == "MUTED"
            val newMute = !isMuted
            mixManager?.setMute("mic", newMute)
            updateMuteBtnStyle(binding.btnMuteMic, newMute)
        }

        binding.btnMuteMusic.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val isMuted = binding.btnMuteMusic.text == "MUTED"
            val newMute = !isMuted
            mixManager?.setMute("music", newMute)
            updateMuteBtnStyle(binding.btnMuteMusic, newMute)
        }

        // Ducking
        binding.switchDucking.setOnCheckedChangeListener { _, isChecked ->
            mixManager?.setDucking(isChecked, binding.sbDuckLevel.progress)
        }

        binding.sbDuckLevel.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                binding.tvDuckLevel.text = "$progress%"
                if (fromUser) {
                    mixManager?.setDucking(binding.switchDucking.isChecked, progress)
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        // Soundboard Controls
        binding.btnRefreshSounds.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            mixManager?.requestRefreshSounds()
            Toast.makeText(this, "🔄 Refreshing soundboard from PC...", Toast.LENGTH_SHORT).show()
        }

        binding.btnStopSound.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            mixManager?.stopSound()
        }
    }

    private fun startConnect() {
        val host = binding.etServerIp.text.toString().trim()
        if (host.isNotEmpty()) {
            ZeroLinkConfig.setServerIp(this, host)
            mixManager?.start(host, ZeroLinkConfig.DEFAULT_MIX_PORT)
        }
    }

    private fun applyMixerState(state: ZeroMixState) {
        if (!isUserDragging) {
            binding.sbMicVol.progress = state.micVol
            binding.tvMicVol.text = "${state.micVol}%"

            binding.sbMusicVol.progress = state.musicVol
            binding.tvMusicVol.text = "${state.musicVol}%"

            binding.sbSoundVol.progress = state.soundVol
            binding.tvSoundVol.text = "${state.soundVol}%"
        }

        updateMuteBtnStyle(binding.btnMuteMic, state.micMuted)
        updateMuteBtnStyle(binding.btnMuteMusic, state.musicMuted)

        binding.switchDucking.isChecked = state.duckingEnabled
        binding.sbDuckLevel.progress = state.duckingLevel
        binding.tvDuckLevel.text = "${state.duckingLevel}%"
    }

    private fun updateMuteBtnStyle(btn: android.widget.Button, isMuted: Boolean) {
        if (isMuted) {
            btn.text = "MUTED"
            btn.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_dark))
        } else {
            btn.text = "MUTE"
            btn.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
        }
    }

    private fun renderSoundboard(sounds: List<SoundboardItem>) {
        binding.llSoundboardPads.removeAllViews()

        if (sounds.isEmpty()) {
            binding.tvEmptySounds.visibility = View.VISIBLE
            return
        }

        binding.tvEmptySounds.visibility = View.GONE

        // Build 2-column rows
        var currentRow: LinearLayout? = null
        for (i in sounds.indices) {
            if (i % 2 == 0) {
                currentRow = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    )
                }
                binding.llSoundboardPads.addView(currentRow)
            }

            val item = sounds[i]
            val padBinding = ItemSoundboardBtnBinding.inflate(layoutInflater, currentRow, false)
            padBinding.tvSoundName.text = item.name

            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            padBinding.root.layoutParams = lp

            padBinding.root.setOnClickListener {
                it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                mixManager?.playSound(item.id)
                Toast.makeText(this, "▶ Playing: ${item.name}", Toast.LENGTH_SHORT).show()
            }

            currentRow?.addView(padBinding.root)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        mixManager?.stop()
    }
}
