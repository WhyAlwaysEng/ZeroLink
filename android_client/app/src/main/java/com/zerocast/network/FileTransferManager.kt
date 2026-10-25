package com.zerocast.network

import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.OpenableColumns
import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.*
import java.net.InetSocketAddress
import java.net.Socket

class FileTransferManager(private val context: Context) {
    private val TAG = "ZeroDrop"

    private var receiverSocket: Socket? = null
    private var receiverJob: Job? = null
    var isReceiverRunning = false
        private set
    var isReceiverConnected = false
        private set

    /**
     * Sends a file from Android to PC over a dedicated upload connection.
     */
    fun sendFileToPc(
        host: String,
        port: Int = com.zerocast.util.ZeroLinkConfig.DEFAULT_DROP_PORT,
        uri: Uri,
        onProgress: (String, Int, Float) -> Unit,
        onSuccess: (String) -> Unit,
        onError: (String, String) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            val (filename, filesize) = getFileInfo(uri)
            var socket: Socket? = null

            try {
                withContext(Dispatchers.Main) { onProgress(filename, 0, 0f) }

                val s = Socket()
                s.tcpNoDelay = true
                s.sendBufferSize = 1024 * 1024
                s.receiveBufferSize = 1024 * 1024
                s.connect(InetSocketAddress(host, port), 4000)
                socket = s

                val out = java.io.BufferedOutputStream(s.getOutputStream(), 262144)
                val header = JSONObject().apply {
                    put("action", "SEND_FILE")
                    put("filename", filename)
                    put("filesize", filesize)
                }.toString() + "\n"

                out.write(header.toByteArray(Charsets.UTF_8))
                out.flush()

                val rawInputStream = context.contentResolver.openInputStream(uri)
                    ?: throw Exception("Could not open input stream for $filename")
                val inputStream = java.io.BufferedInputStream(rawInputStream, 262144)

                val buffer = ByteArray(262144)
                var sent: Long = 0
                val startTime = System.currentTimeMillis()
                var lastUpdate = startTime

                inputStream.use { stream ->
                    var bytesRead: Int
                    while (stream.read(buffer).also { bytesRead = it } != -1) {
                        out.write(buffer, 0, bytesRead)
                        sent += bytesRead

                        val now = System.currentTimeMillis()
                        if (now - lastUpdate >= 150) {
                            val elapsedSec = (now - startTime) / 1000f
                            val speedMb = if (elapsedSec > 0) (sent / 1048576f) / elapsedSec else 0f
                            val pct = if (filesize > 0) ((sent.toFloat() / filesize) * 100).toInt() else 0
                            withContext(Dispatchers.Main) {
                                onProgress(filename, pct, speedMb)
                            }
                            lastUpdate = now
                        }
                    }
                }
                out.flush()

                withContext(Dispatchers.Main) {
                    onProgress(filename, 100, 0f)
                    onSuccess(filename)
                }
            } catch (e: Exception) {
                Log.e(TAG, "File transfer failed: ${e.message}")
                withContext(Dispatchers.Main) {
                    onError(filename, e.message ?: "Transfer error")
                }
            } finally {
                try { socket?.close() } catch (e: Exception) {}
            }
        }
    }

    /**
     * Starts a persistent receiver worker that connects to PC on port 8890
     * and listens for incoming files pushed by the PC.
     */
    fun startReceiveWorker(
        host: String,
        port: Int = com.zerocast.util.ZeroLinkConfig.DEFAULT_DROP_PORT,
        onProgress: (String, Int, Float) -> Unit,
        onFileReceived: (File) -> Unit,
        onError: (String, String) -> Unit,
        onStatusChanged: (Boolean, String) -> Unit
    ) {
        stopReceiveWorker()
        isReceiverRunning = true

        receiverJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive && isReceiverRunning) {
                try {
                    withContext(Dispatchers.Main) {
                        onStatusChanged(false, "Connecting...")
                    }

                    val s = Socket()
                    s.tcpNoDelay = true
                    s.receiveBufferSize = 1024 * 1024
                    s.sendBufferSize = 1024 * 1024
                    s.connect(InetSocketAddress(host, port), 4000)
                    receiverSocket = s

                    val out = java.io.BufferedOutputStream(s.getOutputStream(), 262144)
                    val inStream = java.io.BufferedInputStream(s.getInputStream(), 262144)

                    // Register as receiver
                    val regHeader = JSONObject().apply {
                        put("action", "REGISTER_RECEIVER")
                        put("device", Build.MODEL)
                        put("device_model", Build.MODEL)
                        put("model", Build.MODEL)
                    }.toString() + "\n"
                    out.write(regHeader.toByteArray(Charsets.UTF_8))
                    out.flush()

                    // Read registration response
                    val regLine = readLineFromStream(inStream)
                    if (regLine == null || !regLine.contains("REGISTERED")) {
                        s.close()
                        throw Exception("Registration rejected")
                    }

                    isReceiverConnected = true
                    withContext(Dispatchers.Main) {
                        onStatusChanged(true, "● CONNECTED TO PC")
                    }

                    // Main receiver loop
                    while (isActive && isReceiverRunning) {
                        val headerLine = readLineFromStream(inStream) ?: break
                        if (headerLine.isBlank()) continue

                        val meta = JSONObject(headerLine)
                        val action = meta.optString("action")

                        if (action == "PUSH_TO_PHONE") {
                            val rawName = meta.optString("filename", "received_file")
                            val filesize = meta.optLong("filesize", 0L)

                            val targetDir = getZeroDropDir()
                            var targetFile = File(targetDir, rawName)

                            // Deduplicate filename
                            val dotIdx = rawName.lastIndexOf('.')
                            val base = if (dotIdx != -1) rawName.substring(0, dotIdx) else rawName
                            val ext = if (dotIdx != -1) rawName.substring(dotIdx) else ""
                            var counter = 1
                            while (targetFile.exists()) {
                                targetFile = File(targetDir, "${base}_$counter$ext")
                                counter++
                            }

                            withContext(Dispatchers.Main) {
                                onProgress(targetFile.name, 0, 0f)
                            }

                            val fos = java.io.BufferedOutputStream(FileOutputStream(targetFile), 262144)
                            val buf = ByteArray(262144)
                            var received: Long = 0
                            val startTime = System.currentTimeMillis()
                            var lastUpdate = startTime

                            fos.use { output ->
                                while (received < filesize && isActive && isReceiverRunning) {
                                    val needed = Math.min(buf.size.toLong(), filesize - received).toInt()
                                    val count = inStream.read(buf, 0, needed)
                                    if (count == -1) break
                                    output.write(buf, 0, count)
                                    received += count

                                    val now = System.currentTimeMillis()
                                    if (now - lastUpdate >= 150) {
                                        val elapsedSec = (now - startTime) / 1000f
                                        val speedMb = if (elapsedSec > 0) (received / 1048576f) / elapsedSec else 0f
                                        val pct = if (filesize > 0) ((received.toFloat() / filesize) * 100).toInt() else 0
                                        withContext(Dispatchers.Main) {
                                            onProgress(targetFile.name, pct, speedMb)
                                        }
                                        lastUpdate = now
                                    }
                                }
                                output.flush()
                            }

                            if (received >= filesize) {
                                // Scan file into MediaStore so Gallery/Files can see it
                                MediaScannerConnection.scanFile(
                                    context,
                                    arrayOf(targetFile.absolutePath),
                                    null,
                                    null
                                )

                                // Send ACK back to PC
                                val ack = JSONObject().apply {
                                    put("status", "OK")
                                    put("filename", targetFile.name)
                                }.toString() + "\n"
                                out.write(ack.toByteArray(Charsets.UTF_8))
                                out.flush()

                                withContext(Dispatchers.Main) {
                                    onProgress(targetFile.name, 100, 0f)
                                    onFileReceived(targetFile)
                                }
                            } else {
                                targetFile.delete()
                                throw IOException("Transfer interrupted")
                            }
                        }
                    }
                } catch (e: Exception) {
                    isReceiverConnected = false
                    Log.d(TAG, "ZeroDrop receiver connection: ${e.message}")
                    withContext(Dispatchers.Main) {
                        val errMsg = when (e) {
                            is java.net.ConnectException -> "Connection refused: Ensure ZeroDrop is ENABLED on PC"
                            is java.net.SocketTimeoutException -> "Connection timed out"
                            else -> e.localizedMessage ?: "Connection failed"
                        }
                        onStatusChanged(false, "○ DISCONNECTED ($errMsg)")
                    }
                } finally {
                    isReceiverConnected = false
                    try { receiverSocket?.close() } catch (e: Exception) {}
                    receiverSocket = null
                }

                // Wait before reconnecting if still enabled
                if (isReceiverRunning) {
                    delay(3000)
                }
            }
        }
    }

    private fun readLineFromStream(inStream: InputStream): String? {
        val baos = ByteArrayOutputStream()
        var b: Int
        while (inStream.read().also { b = it } != -1) {
            if (b == '\n'.code) break
            baos.write(b)
        }
        if (b == -1 && baos.size() == 0) return null
        return baos.toString("UTF-8")
    }

    fun stopReceiveWorker() {
        isReceiverRunning = false
        isReceiverConnected = false
        receiverJob?.cancel()
        receiverJob = null
        try {
            receiverSocket?.close()
        } catch (e: Exception) {}
        receiverSocket = null
    }

    private fun getFileInfo(uri: Uri): Pair<String, Long> {
        var name = "file_${System.currentTimeMillis()}"
        var size: Long = 0

        val cursor = context.contentResolver.query(uri, null, null, null, null)
        cursor?.use {
            if (it.moveToFirst()) {
                val nameIdx = it.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val sizeIdx = it.getColumnIndex(OpenableColumns.SIZE)
                if (nameIdx != -1) name = it.getString(nameIdx)
                if (sizeIdx != -1) size = it.getLong(sizeIdx)
            }
        }
        return Pair(name, size)
    }

    companion object {
        fun getZeroDropDir(): File {
            val downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            val dir = File(downloads, "ZeroDrop")
            if (!dir.exists()) dir.mkdirs()
            return dir
        }
    }
}
