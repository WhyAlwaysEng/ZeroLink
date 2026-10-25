package com.zerocast.ui

import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.text.format.Formatter
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.view.View
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.zerocast.R
import com.zerocast.databinding.ActivityZeroDropBinding
import com.zerocast.databinding.ItemReceivedFileBinding
import com.zerocast.network.FileTransferManager
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.lifecycleScope
import com.zerocast.network.ConnectionState
import com.zerocast.network.EcosystemConnectionManager
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import com.zerocast.util.ZeroLinkConfig
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ZeroDropActivity : AppCompatActivity() {

    private lateinit var binding: ActivityZeroDropBinding
    private lateinit var transferManager: FileTransferManager

    private val filePickerLauncher = registerForActivityResult(
        ActivityResultContracts.GetMultipleContents()
    ) { uris: List<Uri> ->
        if (uris.isNotEmpty()) {
            sendSelectedFiles(uris)
        }
    }

    private lateinit var connMgr: EcosystemConnectionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityZeroDropBinding.inflate(layoutInflater)
        setContentView(binding.root)

        connMgr = EcosystemConnectionManager.getInstance(this)
        transferManager = FileTransferManager(this)

        setupListeners()
        observeConnectionState()
        loadExistingReceivedFiles()

        val host = connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
        startReceiver(host)
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

        binding.tvDropLinkIcon.text = icon
        when (state) {
            ConnectionState.CONNECTED -> {
                binding.tvDropLinkTitle.text = "Master Link: $modeStr"
                binding.tvDropLinkSubtitle.text = "Endpoint: $host:8887"
                binding.tvDropLinkBadge.text = "● READY"
                binding.tvDropLinkBadge.setTextColor(Color.parseColor("#10B981"))
            }
            ConnectionState.CONNECTING, ConnectionState.RECONNECTING -> {
                binding.tvDropLinkTitle.text = "Connecting to Master Link..."
                binding.tvDropLinkSubtitle.text = "Connecting to $host:8887..."
                binding.tvDropLinkBadge.text = "○ CONNECTING"
                binding.tvDropLinkBadge.setTextColor(Color.parseColor("#F59E0B"))
            }
            ConnectionState.DISCONNECTED -> {
                binding.tvDropLinkTitle.text = "Master Link: Offline"
                binding.tvDropLinkSubtitle.text = "Disconnected • Tap Home to connect"
                binding.tvDropLinkBadge.text = "○ OFFLINE"
                binding.tvDropLinkBadge.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
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
            startReceiver(host)
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
            try {
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    val uri = FileProvider.getUriForFile(
                        this@ZeroDropActivity,
                        "${packageName}.fileprovider",
                        dropDir
                    )
                    setDataAndType(uri, "*/*")
                    flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(Intent.createChooser(intent, "Open Folder"))
            } catch (e: Exception) {
                Toast.makeText(this, "Files saved in: Download/ZeroDrop", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun startReceiver(targetHost: String? = null) {
        val host = targetHost ?: connMgr.targetHost.value.ifEmpty { "127.0.0.1" }
        binding.tvDropStatus.text = "Connecting to $host:${ZeroLinkConfig.DEFAULT_DROP_PORT}..."
        binding.tvDropStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))

        transferManager.startReceiveWorker(
            host = host,
            port = ZeroLinkConfig.DEFAULT_DROP_PORT,
            onProgress = { filename, percent, speedMb ->
                binding.cardProgress.visibility = if (percent in 1..99) View.VISIBLE else View.GONE
                binding.tvTransferFilename.text = "📥 Receiving: $filename ($percent%)"
                binding.tvTransferSpeed.text = "${String.format("%.1f", speedMb)} MB/s"
                binding.progressBarTransfer.progress = percent
            },
            onFileReceived = { file ->
                binding.cardProgress.visibility = View.GONE
                Toast.makeText(this, "📥 Received: ${file.name}", Toast.LENGTH_SHORT).show()
                addReceivedFileItem(file, isAtTop = true)
            },
            onError = { filename, error ->
                binding.cardProgress.visibility = View.GONE
                Toast.makeText(this, "Transfer error ($filename): $error", Toast.LENGTH_SHORT).show()
            },
            onStatusChanged = { isConnected, msg ->
                binding.tvDropStatus.text = msg
                if (isConnected) {
                    binding.tvDropStatus.setTextColor(ContextCompat.getColor(this, R.color.text_primary))
                } else {
                    binding.tvDropStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
                }
            }
        )
    }

    private fun sendSelectedFiles(uris: List<Uri>) {
        val host = connMgr.targetHost.value.ifEmpty { "127.0.0.1" }

        ZeroLinkConfig.setServerIp(this, host)
        binding.cardProgress.visibility = View.VISIBLE

        for (uri in uris) {
            transferManager.sendFileToPc(
                host = host,
                port = ZeroLinkConfig.DEFAULT_DROP_PORT,
                uri = uri,
                onProgress = { filename, percent, speedMb ->
                    binding.tvTransferFilename.text = "📤 Sending: $filename ($percent%)"
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

    private fun loadExistingReceivedFiles() {
        val dropDir = FileTransferManager.getZeroDropDir()
        val files = dropDir.listFiles()?.filter { it.isFile }?.sortedByDescending { it.lastModified() }
        if (!files.isNullOrEmpty()) {
            binding.tvEmptyReceived.visibility = View.GONE
            for (f in files.take(15)) {
                addReceivedFileItem(f, isAtTop = false)
            }
        } else {
            binding.tvEmptyReceived.visibility = View.VISIBLE
        }
    }

    private fun addReceivedFileItem(file: File, isAtTop: Boolean) {
        binding.tvEmptyReceived.visibility = View.GONE
        val itemBinding = ItemReceivedFileBinding.inflate(layoutInflater, binding.llReceivedFiles, false)

        itemBinding.tvFileName.text = file.name

        val sizeStr = Formatter.formatFileSize(this, file.length())
        val dateStr = SimpleDateFormat("MMM d, hh:mm a", Locale.getDefault()).format(Date(file.lastModified()))
        itemBinding.tvFileMeta.text = "$sizeStr • $dateStr"

        val ext = file.extension.lowercase()
        itemBinding.tvFileGlyph.text = when (ext) {
            "jpg", "jpeg", "png", "webp", "gif", "bmp" -> "🖼️"
            "mp4", "mkv", "mov", "webm", "avi" -> "🎥"
            "mp3", "m4a", "wav", "flac", "ogg" -> "🎵"
            "pdf", "doc", "docx", "txt", "xlsx" -> "📄"
            "apk" -> "📱"
            "zip", "rar", "7z", "tar", "gz" -> "📦"
            else -> "📁"
        }

        itemBinding.btnOpenFile.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            openFile(file)
        }

        itemBinding.btnShareFile.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            shareFile(file)
        }

        if (isAtTop) {
            binding.llReceivedFiles.addView(itemBinding.root, 0)
        } else {
            binding.llReceivedFiles.addView(itemBinding.root)
        }
    }

    private fun openFile(file: File) {
        try {
            val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", file)
            val mime = getMimeType(file)
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, mime)
                flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "Could not open file: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun shareFile(file: File) {
        try {
            val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", file)
            val mime = getMimeType(file)
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = mime
                putExtra(Intent.EXTRA_STREAM, uri)
                flags = Intent.FLAG_GRANT_READ_URI_PERMISSION
            }
            startActivity(Intent.createChooser(intent, "Share ${file.name}"))
        } catch (e: Exception) {
            Toast.makeText(this, "Could not share file: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun getMimeType(file: File): String {
        val ext = file.extension.lowercase()
        return MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "*/*"
    }

    override fun onResume() {
        super.onResume()
        loadExistingReceivedFiles()
    }

    override fun onDestroy() {
        super.onDestroy()
        transferManager.stopReceiveWorker()
    }
}
