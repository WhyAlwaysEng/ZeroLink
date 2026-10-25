package com.zerocast.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.provider.Settings
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroExplorerBinding
import com.zerocast.network.AuditLogEntry
import com.zerocast.network.ExplorerServer
import com.zerocast.network.NetworkDiscovery
import com.zerocast.util.ZeroLinkConfig
import java.io.File
import java.text.DecimalFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ZeroExplorerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroExplorerBinding
    private var explorerServer: ExplorerServer? = null
    private val logList = ArrayList<AuditLogEntry>()
    private lateinit var logAdapter: AuditLogAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroExplorerBinding.inflate(layoutInflater)
        setContentView(binding.root)

        logAdapter = AuditLogAdapter(logList)
        binding.rvExplorerLogs.layoutManager = LinearLayoutManager(this)
        binding.rvExplorerLogs.adapter = logAdapter

        binding.btnExplorerBack.setOnClickListener {
            finish()
        }

        binding.switchExplorerService.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                startServer()
                binding.tvExplorerStatus.text = "● RUNNING (Port 8896)"
                binding.tvExplorerStatus.setTextColor(android.graphics.Color.parseColor("#111827"))
            } else {
                stopServer()
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
            logList.clear()
            logAdapter.notifyDataSetChanged()
            binding.tvLogEmpty.visibility = View.VISIBLE
            binding.rvExplorerLogs.visibility = View.GONE
            Toast.makeText(this, "Session Log Cleared", Toast.LENGTH_SHORT).show()
        }

        binding.btnWebDirect.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val ip = getDeviceIp()
            val webUrl = "http://$ip:8896/"

            com.google.android.material.dialog.MaterialAlertDialogBuilder(this)
                .setTitle("🌐 ZeroLink Web Direct")
                .setMessage("Open this address in any browser (Chrome, Edge, Safari) on your PC, Mac, or tablet:\n\n👉 $webUrl\n\nYou can view photos and download files directly without installing any program on your PC!")
                .setPositiveButton("Open Browser") { _, _ ->
                    try {
                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(webUrl))
                        startActivity(intent)
                    } catch (_: Exception) {}
                }
                .setNeutralButton("Copy Link") { _, _ ->
                    val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                    val clip = android.content.ClipData.newPlainText("ZeroLink Web", webUrl)
                    clipboard.setPrimaryClip(clip)
                    Toast.makeText(this, "Copied: $webUrl", Toast.LENGTH_SHORT).show()
                }
                .setNegativeButton("Close", null)
                .show()
        }

        startServer()
        updateStorageSummary()
        updatePermissionStatus()
    }

    private fun getDeviceIp(): String {
        try {
            val interfaces = java.net.NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val iface = interfaces.nextElement()
                if (iface.isLoopback || !iface.isUp) continue
                val addrs = iface.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (!addr.isLoopbackAddress && addr is java.net.Inet4Address) {
                        val host = addr.hostAddress
                        if (host != null && (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172."))) {
                            return host
                        }
                    }
                }
            }
        } catch (_: Exception) {}
        return "127.0.0.1"
    }

    private fun startServer() {
        if (explorerServer == null) {
            explorerServer = ExplorerServer(this, 8896) { entry ->
                runOnUiThread {
                    if (!isFinishing && !isDestroyed) {
                        logList.add(0, entry)
                        if (logList.size > 200) logList.removeAt(logList.lastIndex)
                        logAdapter.notifyItemInserted(0)
                        binding.rvExplorerLogs.scrollToPosition(0)
                        binding.tvLogEmpty.visibility = View.GONE
                        binding.rvExplorerLogs.visibility = View.VISIBLE
                    }
                }
            }
            explorerServer?.start()
        }
    }

    private fun stopServer() {
        explorerServer?.stop()
        explorerServer = null
    }

    override fun onResume() {
        super.onResume()
        updatePermissionStatus()
        updateStorageSummary()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopServer()
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
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val root = Environment.getExternalStorageDirectory()
                val stat = StatFs(root.path)
                val blockSize = stat.blockSizeLong
                val totalBlocks = stat.blockCountLong
                val availableBlocks = stat.availableBlocksLong

                val totalBytes = totalBlocks * blockSize
                val freeBytes = availableBlocks * blockSize
                val usedBytes = totalBytes - freeBytes

                val totalGB = totalBytes.toDouble() / (1024 * 1024 * 1024)
                val usedGB = usedBytes.toDouble() / (1024 * 1024 * 1024)
                val freePercent = if (totalBytes > 0) ((freeBytes.toDouble() / totalBytes) * 100).toInt() else 0
                val usedPercent = 100 - freePercent

                val df = DecimalFormat("#.#")
                withContext(Dispatchers.Main) {
                    binding.tvStorageSummary.text = "${df.format(usedGB)} GB / ${df.format(totalGB)} GB used (${freePercent}% free)"
                    binding.progressBarStorage.progress = usedPercent
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    binding.tvStorageSummary.text = "Storage: Ready"
                }
            }
        }
    }

    inner class AuditLogAdapter(private val items: List<AuditLogEntry>) :
        RecyclerView.Adapter<AuditLogAdapter.LogViewHolder>() {

        private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

        inner class LogViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val tvAction: TextView = view.findViewById(R.id.tvLogAction)
            val tvPath: TextView = view.findViewById(R.id.tvLogPath)
            val tvMeta: TextView = view.findViewById(R.id.tvLogMeta)
            val tvSize: TextView = view.findViewById(R.id.tvLogSize)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): LogViewHolder {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_audit_log, parent, false)
            return LogViewHolder(v)
        }

        override fun onBindViewHolder(holder: LogViewHolder, position: Int) {
            val item = items[position]
            holder.tvAction.text = item.action
            holder.tvPath.text = item.path
            holder.tvMeta.text = "IP: ${item.clientIp} • ${timeFmt.format(Date(item.timestamp))}"

            if (item.sizeBytes > 0) {
                val mb = item.sizeBytes.toDouble() / (1024 * 1024)
                holder.tvSize.visibility = View.VISIBLE
                holder.tvSize.text = String.format(Locale.US, "%.1f MB", mb)
            } else {
                holder.tvSize.visibility = View.GONE
            }
        }

        override fun getItemCount(): Int = items.size
    }
}
