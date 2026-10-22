package com.zerocast.ui

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import com.zerocast.databinding.ActivityZeroDropBinding
import com.zerocast.network.FileTransferManager
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.ZeroLinkConfig
import java.io.File

class ZeroDropActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroDropBinding
    private lateinit var transferManager: FileTransferManager
    private var discovery: NetworkDiscovery? = null

    private val filePickerLauncher = registerForActivityResult(
        ActivityResultContracts.GetMultipleContents()
    ) { uris: List<Uri> ->
        if (uris.isNotEmpty()) {
            sendSelectedFiles(uris)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroDropBinding.inflate(layoutInflater)
        setContentView(binding.root)

        transferManager = FileTransferManager(this)

        val savedIp = ZeroLinkConfig.getServerIp(this)
        binding.etServerIp.setText(savedIp)

        setupListeners()
    }

    private fun setupListeners() {
        binding.btnBack.setOnClickListener {
            finish()
        }

        binding.btnModeUsb.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.etServerIp.setText("127.0.0.1")
            ZeroLinkConfig.setServerIp(this, "127.0.0.1")
        }

        binding.btnAutoDiscover.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            binding.tvDropStatus.text = "Searching..."
            discovery = NetworkDiscovery { ip, _ ->
                binding.etServerIp.setText(ip)
                binding.tvDropStatus.text = "● PC FOUND"
                ZeroLinkConfig.setServerIp(this, ip)
            }
            discovery?.startDiscovery()
        }

        binding.btnSelectFiles.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            filePickerLauncher.launch("*/*")
        }

        binding.cardSendFiles.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            filePickerLauncher.launch("*/*")
        }

        binding.btnOpenDownloads.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val dropDir = FileTransferManager.getZeroDropDir()
            Toast.makeText(this, "Files saved in: Download/ZeroDrop", Toast.LENGTH_LONG).show()
        }
    }

    private fun sendSelectedFiles(uris: List<Uri>) {
        val host = binding.etServerIp.text.toString().trim()
        if (host.isEmpty()) {
            Toast.makeText(this, "Please enter target PC IP or use Auto Scan / USB", Toast.LENGTH_SHORT).show()
            return
        }

        ZeroLinkConfig.setServerIp(this, host)
        binding.cardProgress.visibility = View.VISIBLE

        for (uri in uris) {
            transferManager.sendFileToPc(
                host = host,
                port = ZeroLinkConfig.DEFAULT_DROP_PORT,
                uri = uri,
                onProgress = { filename, percent, speedMb ->
                    binding.tvTransferFilename.text = "$filename ($percent%)"
                    binding.tvTransferSpeed.text = "${String.format("%.1f", speedMb)} MB/s"
                    binding.progressBarTransfer.progress = percent
                },
                onSuccess = { filename ->
                    binding.cardProgress.visibility = View.GONE
                    Toast.makeText(this, "Sent: $filename", Toast.LENGTH_SHORT).show()
                },
                onError = { filename, error ->
                    binding.cardProgress.visibility = View.GONE
                    Toast.makeText(this, "Failed to send $filename: $error", Toast.LENGTH_LONG).show()
                }
            )
        }
    }
}
