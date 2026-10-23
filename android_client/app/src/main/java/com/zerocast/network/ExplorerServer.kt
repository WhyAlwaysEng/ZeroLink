package com.zerocast.network

import android.content.ContentUris
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.provider.MediaStore
import android.util.Log
import android.util.Size
import org.json.JSONArray
import org.json.JSONObject
import java.io.*
import java.net.ServerSocket
import java.net.Socket
import java.net.URLDecoder
import java.util.concurrent.Executors

data class AuditLogEntry(
    val action: String,      // VIEW, DOWNLOAD, BROWSE, STORAGE
    val path: String,
    val sizeBytes: Long,
    val clientIp: String,
    val timestamp: Long = System.currentTimeMillis()
)

class ExplorerServer(
    private val context: Context,
    private val port: Int = 8896,
    private val onLogEntry: ((AuditLogEntry) -> Unit)? = null
) {
    companion object {
        private const val TAG = "ZeroExplorerServer"
    }

    private var serverSocket: ServerSocket? = null
    private var isRunning = false
    private val executor = Executors.newCachedThreadPool()

    fun start() {
        if (isRunning) return
        isRunning = true
        executor.execute {
            try {
                serverSocket = ServerSocket(port)
                Log.i(TAG, "ZeroExplorer HTTP Server listening on port $port")
                while (isRunning && serverSocket != null && !serverSocket!!.isClosed) {
                    val client = serverSocket!!.accept()
                    executor.execute { handleClient(client) }
                }
            } catch (e: Exception) {
                if (isRunning) Log.e(TAG, "Server socket error: ${e.message}")
            }
        }
    }

    fun stop() {
        isRunning = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {}
        serverSocket = null
    }

    private fun handleClient(socket: Socket) {
        val clientIp = socket.inetAddress?.hostAddress ?: "Unknown"
        try {
            socket.soTimeout = 10000
            val input = socket.getInputStream()
            val reader = BufferedReader(InputStreamReader(input, Charsets.UTF_8))
            val output = socket.getOutputStream()

            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return

            val method = parts[0].uppercase()
            val rawPath = parts[1]
            val uri = Uri.parse(rawPath)
            val path = uri.path ?: "/"

            // Consume remaining headers
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) break
            }

            when {
                path == "/api/storage" -> {
                    handleStorage(output)
                }
                path == "/api/gallery/photos" -> {
                    val album = uri.getQueryParameter("album")
                    handleGalleryPhotos(output, album)
                }
                path == "/api/media/thumb" -> {
                    val idStr = uri.getQueryParameter("id") ?: "0"
                    val id = idStr.toLongOrNull() ?: 0L
                    handleThumbnail(output, id)
                }
                path == "/api/media/raw" -> {
                    val idStr = uri.getQueryParameter("id") ?: "0"
                    val id = idStr.toLongOrNull() ?: 0L
                    val bytesSent = handleRawMedia(output, id)
                    if (bytesSent > 0) {
                        onLogEntry?.invoke(AuditLogEntry("DOWNLOAD", "Photo #$id", bytesSent, clientIp))
                    }
                }
                path == "/api/files/list" -> {
                    val folderParam = uri.getQueryParameter("path")
                    val decodedPath = if (!folderParam.isNullOrEmpty()) URLDecoder.decode(folderParam, "UTF-8") else Environment.getExternalStorageDirectory().path
                    handleFileList(output, decodedPath)
                }
                path == "/api/files/download" -> {
                    val fileParam = uri.getQueryParameter("path")
                    val decodedPath = if (!fileParam.isNullOrEmpty()) URLDecoder.decode(fileParam, "UTF-8") else ""
                    val bytesSent = handleFileDownload(output, decodedPath)
                    if (bytesSent > 0) {
                        onLogEntry?.invoke(AuditLogEntry("DOWNLOAD", decodedPath, bytesSent, clientIp))
                    }
                }
                else -> {
                    sendJsonResponse(output, 404, JSONObject().put("error", "Not found").toString())
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Request handling error: ${e.message}")
        } finally {
            try { socket.close() } catch (e: Exception) {}
        }
    }

    private fun handleStorage(out: OutputStream) {
        val root = Environment.getExternalStorageDirectory()
        val stat = StatFs(root.path)
        val blockSize = stat.blockSizeLong
        val totalBlocks = stat.blockCountLong
        val availableBlocks = stat.availableBlocksLong

        val totalBytes = totalBlocks * blockSize
        val freeBytes = availableBlocks * blockSize
        val usedBytes = totalBytes - freeBytes

        val freePercent = if (totalBytes > 0) ((freeBytes.toDouble() / totalBytes) * 100).toInt() else 0
        val usedPercent = 100 - freePercent

        val json = JSONObject().apply {
            put("path", root.path)
            put("totalBytes", totalBytes)
            put("usedBytes", usedBytes)
            put("freeBytes", freeBytes)
            put("freePercent", freePercent)
            put("usedPercent", usedPercent)
        }
        sendJsonResponse(out, 200, json.toString())
    }

    private fun handleGalleryPhotos(out: OutputStream, albumFilter: String?) {
        val array = JSONArray()
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.DATE_MODIFIED,
            MediaStore.Images.Media.SIZE,
            MediaStore.Images.Media.BUCKET_DISPLAY_NAME
        )
        val sortOrder = "${MediaStore.Images.Media.DATE_MODIFIED} DESC"

        var selection: String? = null
        var selectionArgs: Array<String>? = null
        if (!albumFilter.isNullOrEmpty() && albumFilter != "all") {
            selection = "${MediaStore.Images.Media.BUCKET_DISPLAY_NAME} = ?"
            selectionArgs = arrayOf(albumFilter)
        }

        try {
            val cursor = context.contentResolver.query(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                projection,
                selection,
                selectionArgs,
                sortOrder
            )
            cursor?.use { c ->
                val idCol = c.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
                val nameCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
                val dateCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_MODIFIED)
                val sizeCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.SIZE)
                val bucketCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.BUCKET_DISPLAY_NAME)

                var count = 0
                while (c.moveToNext() && count < 300) {
                    val id = c.getLong(idCol)
                    val name = c.getString(nameCol) ?: "Unknown"
                    val date = c.getLong(dateCol) * 1000L
                    val size = c.getLong(sizeCol)
                    val album = c.getString(bucketCol) ?: "Other"

                    val item = JSONObject().apply {
                        put("id", id)
                        put("name", name)
                        put("date", date)
                        put("size", size)
                        put("album", album)
                    }
                    array.put(item)
                    count++
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Gallery query error: ${e.message}")
        }

        sendJsonResponse(out, 200, array.toString())
    }

    private fun handleThumbnail(out: OutputStream, id: Long) {
        val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
        try {
            val bmp: Bitmap? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                context.contentResolver.loadThumbnail(uri, Size(256, 256), null)
            } else {
                val input = context.contentResolver.openInputStream(uri)
                val options = BitmapFactory.Options().apply { inSampleSize = 4 }
                BitmapFactory.decodeStream(input, null, options)
            }

            if (bmp != null) {
                val byteOut = ByteArrayOutputStream()
                bmp.compress(Bitmap.CompressFormat.JPEG, 75, byteOut)
                val bytes = byteOut.toByteArray()
                bmp.recycle()

                val header = "HTTP/1.1 200 OK\r\n" +
                        "Content-Type: image/jpeg\r\n" +
                        "Content-Length: ${bytes.size}\r\n" +
                        "Connection: close\r\n\r\n"
                out.write(header.toByteArray(Charsets.UTF_8))
                out.write(bytes)
                out.flush()
                return
            }
        } catch (e: Exception) {
            Log.e(TAG, "Thumbnail error: ${e.message}")
        }
        sendJsonResponse(out, 404, JSONObject().put("error", "Thumbnail not found").toString())
    }

    private fun handleRawMedia(out: OutputStream, id: Long): Long {
        val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
        var totalSent = 0L
        try {
            val input = context.contentResolver.openInputStream(uri) ?: return 0L
            val pfd = context.contentResolver.openFileDescriptor(uri, "r")
            val length = pfd?.statSize ?: -1L
            pfd?.close()

            val header = "HTTP/1.1 200 OK\r\n" +
                    "Content-Type: application/octet-stream\r\n" +
                    (if (length > 0) "Content-Length: $length\r\n" else "") +
                    "Connection: close\r\n\r\n"
            out.write(header.toByteArray(Charsets.UTF_8))

            val buf = ByteArray(65536)
            input.use { inp ->
                while (true) {
                    val read = inp.read(buf)
                    if (read <= 0) break
                    out.write(buf, 0, read)
                    totalSent += read
                }
            }
            out.flush()
        } catch (e: Exception) {
            Log.e(TAG, "Raw media error: ${e.message}")
        }
        return totalSent
    }

    private fun handleFileList(out: OutputStream, path: String) {
        val dir = File(path)
        val array = JSONArray()

        if (dir.exists() && dir.isDirectory) {
            val files = dir.listFiles()
            if (files != null) {
                val sorted = files.sortedWith(compareBy({ !it.isDirectory }, { it.name.lowercase() }))
                for (f in sorted) {
                    val item = JSONObject().apply {
                        put("name", f.name)
                        put("path", f.absolutePath)
                        put("isDir", f.isDirectory)
                        put("size", if (f.isDirectory) 0L else f.length())
                        put("date", f.lastModified())
                    }
                    array.put(item)
                }
            }
        }

        val json = JSONObject().apply {
            put("currentPath", dir.absolutePath)
            put("parentPath", dir.parent ?: "")
            put("files", array)
        }
        sendJsonResponse(out, 200, json.toString())
    }

    private fun handleFileDownload(out: OutputStream, path: String): Long {
        val file = File(path)
        if (!file.exists() || file.isDirectory) {
            sendJsonResponse(out, 404, JSONObject().put("error", "File not found").toString())
            return 0L
        }

        var totalSent = 0L
        try {
            val length = file.length()
            val header = "HTTP/1.1 200 OK\r\n" +
                    "Content-Type: application/octet-stream\r\n" +
                    "Content-Disposition: attachment; filename=\"${file.name}\"\r\n" +
                    "Content-Length: $length\r\n" +
                    "Connection: close\r\n\r\n"
            out.write(header.toByteArray(Charsets.UTF_8))

            val fis = FileInputStream(file)
            val buf = ByteArray(65536)
            fis.use { inp ->
                while (true) {
                    val read = inp.read(buf)
                    if (read <= 0) break
                    out.write(buf, 0, read)
                    totalSent += read
                }
            }
            out.flush()
        } catch (e: Exception) {
            Log.e(TAG, "File download error: ${e.message}")
        }
        return totalSent
    }

    private fun sendJsonResponse(out: OutputStream, code: Int, json: String) {
        val bytes = json.toByteArray(Charsets.UTF_8)
        val statusText = if (code == 200) "OK" else if (code == 404) "Not Found" else "Error"
        val header = "HTTP/1.1 $code $statusText\r\n" +
                "Content-Type: application/json; charset=utf-8\r\n" +
                "Content-Length: ${bytes.size}\r\n" +
                "Access-Control-Allow-Origin: *\r\n" +
                "Connection: close\r\n\r\n"
        out.write(header.toByteArray(Charsets.UTF_8))
        out.write(bytes)
        out.flush()
    }
}
