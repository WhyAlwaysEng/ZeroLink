package com.zerocast.ui

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.zerocast.databinding.ActivityZeroExplorerBinding
import java.io.File
import java.text.DecimalFormat

class ZeroExplorerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroExplorerBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroExplorerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnExplorerBack.setOnClickListener {
            finish()
        }

        binding.switchExplorerService.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                binding.tvExplorerStatus.text = "● RUNNING (Port 8896)"
                binding.tvExplorerStatus.setTextColor(android.graphics.Color.parseColor("#111827"))
            } else {
                binding.tvExplorerStatus.text = "○ PAUSED"
                binding.tvExplorerStatus.setTextColor(android.graphics.Color.parseColor("#6B7280"))
            }
        }

        binding.btnGrantPermission.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            requestStoragePermission()
        }

        binding.btnLogClear.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            binding.tvLogEmpty.visibility = View.VISIBLE
            binding.rvExplorerLogs.visibility = View.GONE
            Toast.makeText(this, "Session Log Cleared", Toast.LENGTH_SHORT).show()
        }

        updateStorageSummary()
        updatePermissionStatus()
    }

    override fun onResume() {
        super.onResume()
        updatePermissionStatus()
        updateStorageSummary()
    }

    private fun updatePermissionStatus() {
        val hasPermission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Environment.isExternalStorageManager()
        } else {
            checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE) == android.content.pm.PackageManager.PERMISSION_GRANTED
        }

        if (hasPermission) {
            binding.tvPermissionStatus.text = "All Files Access: Granted ✓"
            binding.tvPermissionStatus.setTextColor(android.graphics.Color.parseColor("#111827"))
            binding.btnGrantPermission.visibility = View.GONE
        } else {
            binding.tvPermissionStatus.text = "All Files Access: Recommended for full folder browsing"
            binding.tvPermissionStatus.setTextColor(android.graphics.Color.parseColor("#6B7280"))
            binding.btnGrantPermission.visibility = View.VISIBLE
        }
    }

    private fun requestStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                    data = Uri.parse("package:$packageName")
                }
                startActivity(intent)
            } catch (e: Exception) {
                val intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                startActivity(intent)
            }
        } else {
            requestPermissions(arrayOf(android.Manifest.permission.READ_EXTERNAL_STORAGE, android.Manifest.permission.WRITE_EXTERNAL_STORAGE), 101)
        }
    }

    private fun updateStorageSummary() {
        try {
            val stat = StatFs(Environment.getDataDirectory().path)
            val blockSize = stat.blockSizeLong
            val totalBlocks = stat.blockCountLong
            val availableBlocks = stat.availableBlocksLong

            val totalBytes = totalBlocks * blockSize
            val freeBytes = availableBlocks * blockSize
            val usedBytes = totalBytes - freeBytes

            val totalGB = totalBytes.toDouble() / (1024 * 1024 * 1024)
            val usedGB = usedBytes.toDouble() / (1024 * 1024 * 1024)
            val freePercent = ((freeBytes.toDouble() / totalBytes) * 100).toInt()
            val usedPercent = 100 - freePercent

            val df = DecimalFormat("#.#")
            binding.tvStorageSummary.text = "${df.format(usedGB)} GB / ${df.format(totalGB)} GB used (${freePercent}% free)"
            binding.progressBarStorage.progress = usedPercent
        } catch (e: Exception) {
            binding.tvStorageSummary.text = "Storage: Ready"
        }
    }
}
