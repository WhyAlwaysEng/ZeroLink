package com.zerocast.network

import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Environment
import android.provider.OpenableColumns
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.net.InetSocketAddress
import java.net.Socket

class FileTransferManager(private val context: Context) {
    private val TAG = "ZeroDrop"

    fun sendFileToPc(
        host: String,
        port: Int = 8890,
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

                socket = Socket()
                socket.connect(InetSocketAddress(host, port), 4000)

                val out = socket.getOutputStream()
                val header = JSONObject().apply {
                    put("action", "SEND_FILE")
                    put("filename", filename)
                    put("filesize", filesize)
                }.toString() + "\n"

                out.write(header.toByteArray(Charsets.UTF_8))
                out.flush()

                val inputStream = context.contentResolver.openInputStream(uri)
                    ?: throw Exception("Could not open input stream for $filename")

                val buffer = ByteArray(65536)
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
