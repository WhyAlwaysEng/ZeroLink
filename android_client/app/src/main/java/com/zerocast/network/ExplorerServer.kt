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
    val action: String,      // DOWNLOAD, UPLOAD, MOVE, DELETE
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
            socket.tcpNoDelay = true
            socket.sendBufferSize = 2 * 1024 * 1024
            socket.receiveBufferSize = 512 * 1024
            socket.soTimeout = 20000
            val input = socket.getInputStream()
            val reader = BufferedReader(InputStreamReader(input, Charsets.UTF_8))
            val output = socket.getOutputStream()

            while (isRunning && !socket.isClosed) {
                val requestLine = reader.readLine() ?: break
                if (requestLine.isEmpty()) continue
                val parts = requestLine.split(" ")
                if (parts.size < 2) break

                val method = parts[0].uppercase()
                val rawPath = parts[1]
                val uri = Uri.parse(rawPath)
                val path = uri.path ?: "/"

                val headers = HashMap<String, String>()
                while (true) {
                    val line = reader.readLine() ?: break
                    if (line.isEmpty()) break
                    val idx = line.indexOf(":")
                    if (idx > 0) {
                        val key = line.substring(0, idx).trim().lowercase()
                        val value = line.substring(idx + 1).trim()
                        headers[key] = value
                    }
                }

                val rangeHeader = headers["range"]
                val connHeader = headers["connection"]?.lowercase()

                when {
                    path == "/api/storage" -> {
                        handleStorage(output)
                    }
                    path == "/api/gallery/photos" || path == "/api/gallery/media" -> {
                        val album = uri.getQueryParameter("album")
                        val type = uri.getQueryParameter("type") ?: "all" // all, photos, videos
                        val offset = uri.getQueryParameter("offset")?.toIntOrNull() ?: 0
                        val limit = uri.getQueryParameter("limit")?.toIntOrNull() ?: 100
                        handleGalleryMedia(output, type, album, offset, limit)
                    }
                    path == "/api/media/thumb" -> {
                        val idStr = uri.getQueryParameter("id") ?: "0"
                        val id = idStr.toLongOrNull() ?: 0L
                        val isVideo = uri.getQueryParameter("type") == "video"
                        handleThumbnail(output, id, isVideo)
                    }
                    path == "/api/media/raw" -> {
                        val idStr = uri.getQueryParameter("id") ?: "0"
                        val id = idStr.toLongOrNull() ?: 0L
                        val isVideo = uri.getQueryParameter("type") == "video"
                        val isDownload = uri.getQueryParameter("download") == "true"
                        val bytesSent = handleRawMedia(output, id, isVideo, rangeHeader)
                        if (isDownload && bytesSent > 0 && rangeHeader == null) {
                            onLogEntry?.invoke(AuditLogEntry("DOWNLOAD", if (isVideo) "Video #$id" else "Photo #$id", bytesSent, clientIp))
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
                        val isDownload = uri.getQueryParameter("download") != "false"
                        val bytesSent = handleFileDownload(output, decodedPath, rangeHeader)
                        if (isDownload && bytesSent > 0 && rangeHeader == null) {
                            onLogEntry?.invoke(AuditLogEntry("DOWNLOAD", decodedPath, bytesSent, clientIp))
                        }
                    }
                    else -> {
                        sendJsonResponse(output, 404, JSONObject().put("error", "Not found").toString())
                    }
                }
                output.flush()

                if (connHeader == "close") {
                    break
                }
            }
        } catch (e: Exception) {
            // Socket closed or EOF
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

    private fun handleGalleryMedia(out: OutputStream, typeFilter: String, albumFilter: String?, offset: Int = 0, limit: Int = 80) {
        val list = ArrayList<JSONObject>()

        // 1. Photos
        if (typeFilter == "all" || typeFilter == "photos") {
            val projection = arrayOf(
                MediaStore.Images.Media._ID,
                MediaStore.Images.Media.DISPLAY_NAME,
                MediaStore.Images.Media.DATE_MODIFIED,
                MediaStore.Images.Media.SIZE,
                MediaStore.Images.Media.BUCKET_DISPLAY_NAME
            )
            var selection: String? = null
            var selectionArgs: Array<String>? = null
            if (!albumFilter.isNullOrEmpty() && albumFilter != "all") {
                selection = "${MediaStore.Images.Media.BUCKET_DISPLAY_NAME} = ?"
                selectionArgs = arrayOf(albumFilter)
            }
            try {
                val cursor = context.contentResolver.query(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    projection, selection, selectionArgs,
                    "${MediaStore.Images.Media.DATE_MODIFIED} DESC"
                )
                cursor?.use { c ->
                    val idCol = c.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
                    val nameCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
                    val dateCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_MODIFIED)
                    val sizeCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.SIZE)
                    val bucketCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.BUCKET_DISPLAY_NAME)

                    var count = 0
                    while (c.moveToNext() && count < 8000) {
                        val id = c.getLong(idCol)
                        val name = c.getString(nameCol) ?: "Photo"
                        val date = c.getLong(dateCol) * 1000L
                        val size = c.getLong(sizeCol)
                        val album = c.getString(bucketCol) ?: "Other"

                        list.add(JSONObject().apply {
                            put("id", id)
                            put("name", name)
                            put("date", date)
                            put("size", size)
                            put("album", album)
                            put("type", "image")
                            put("duration", 0L)
                        })
                        count++
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Image query error: ${e.message}")
            }
        }

        // 2. Videos
        if (typeFilter == "all" || typeFilter == "videos") {
            val projection = arrayOf(
                MediaStore.Video.Media._ID,
                MediaStore.Video.Media.DISPLAY_NAME,
                MediaStore.Video.Media.DATE_MODIFIED,
                MediaStore.Video.Media.SIZE,
                MediaStore.Video.Media.DURATION,
                MediaStore.Video.Media.BUCKET_DISPLAY_NAME
            )
            var selection: String? = null
            var selectionArgs: Array<String>? = null
            if (!albumFilter.isNullOrEmpty() && albumFilter != "all") {
                selection = "${MediaStore.Video.Media.BUCKET_DISPLAY_NAME} = ?"
                selectionArgs = arrayOf(albumFilter)
            }
            try {
                val cursor = context.contentResolver.query(
                    MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                    projection, selection, selectionArgs,
                    "${MediaStore.Video.Media.DATE_MODIFIED} DESC"
                )
                cursor?.use { c ->
                    val idCol = c.getColumnIndexOrThrow(MediaStore.Video.Media._ID)
                    val nameCol = c.getColumnIndexOrThrow(MediaStore.Video.Media.DISPLAY_NAME)
                    val dateCol = c.getColumnIndexOrThrow(MediaStore.Video.Media.DATE_MODIFIED)
                    val sizeCol = c.getColumnIndexOrThrow(MediaStore.Video.Media.SIZE)
                    val durationCol = c.getColumnIndexOrThrow(MediaStore.Video.Media.DURATION)
                    val bucketCol = c.getColumnIndexOrThrow(MediaStore.Video.Media.BUCKET_DISPLAY_NAME)

                    var count = 0
                    while (c.moveToNext() && count < 5000) {
                        val id = c.getLong(idCol)
                        val name = c.getString(nameCol) ?: "Video"
                        val date = c.getLong(dateCol) * 1000L
                        val size = c.getLong(sizeCol)
                        val duration = c.getLong(durationCol)
                        val album = c.getString(bucketCol) ?: "Videos"

                        list.add(JSONObject().apply {
                            put("id", id)
                            put("name", name)
                            put("date", date)
                            put("size", size)
                            put("album", album)
                            put("type", "video")
                            put("duration", duration)
                        })
                        count++
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Video query error: ${e.message}")
            }
        }

        // Sort descending by date
        list.sortByDescending { it.optLong("date") }

        val totalCount = list.size
        val safeOffset = offset.coerceAtLeast(0)
        val safeLimit = if (limit <= 0) 100 else limit
        val pagedList = if (safeOffset < totalCount) {
            list.subList(safeOffset, minOf(safeOffset + safeLimit, totalCount))
        } else {
            emptyList<JSONObject>()
        }

        val array = JSONArray()
        for (item in pagedList) {
            array.put(item)
        }

        val responseJson = JSONObject().apply {
            put("total", totalCount)
            put("offset", safeOffset)
            put("limit", safeLimit)
            put("hasMore", (safeOffset + safeLimit) < totalCount)
            put("items", array)
        }

        sendJsonResponse(out, 200, responseJson.toString())
    }

    private fun handleThumbnail(out: OutputStream, id: Long, isVideo: Boolean) {
        val uri = if (isVideo) {
            ContentUris.withAppendedId(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, id)
        } else {
            ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
        }

        try {
            val bmp: Bitmap? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                context.contentResolver.loadThumbnail(uri, Size(256, 256), null)
            } else {
                if (isVideo) {
                    MediaStore.Video.Thumbnails.getThumbnail(context.contentResolver, id, MediaStore.Video.Thumbnails.MINI_KIND, null)
                } else {
                    val input = context.contentResolver.openInputStream(uri)
                    val options = BitmapFactory.Options().apply { inSampleSize = 4 }
                    BitmapFactory.decodeStream(input, null, options)
                }
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

    private fun handleRawMedia(out: OutputStream, id: Long, isVideo: Boolean, rangeHeader: String?): Long {
        val uri = if (isVideo) {
            ContentUris.withAppendedId(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, id)
        } else {
            ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
        }

        var totalSent = 0L
        try {
            val afd = context.contentResolver.openAssetFileDescriptor(uri, "r") ?: return 0L
            val stat = afd.parcelFileDescriptor?.statSize ?: 0L
            val totalLength = if (afd.length > 0) afd.length else (if (stat > 0) stat else 0L)
            val mime = context.contentResolver.getType(uri) ?: (if (isVideo) "video/mp4" else "image/jpeg")

            if (rangeHeader != null && rangeHeader.startsWith("bytes=") && totalLength > 0) {
                val rangeVal = rangeHeader.removePrefix("bytes=").trim()
                val parts = rangeVal.split("-")
                val start = parts[0].toLongOrNull() ?: 0L
                val end = if (parts.size > 1 && parts[1].isNotEmpty()) parts[1].toLongOrNull() ?: (totalLength - 1) else (totalLength - 1)
                val contentLength = end - start + 1

                val header = "HTTP/1.1 206 Partial Content\r\n" +
                        "Content-Type: $mime\r\n" +
                        "Accept-Ranges: bytes\r\n" +
                        "Content-Range: bytes $start-$end/$totalLength\r\n" +
                        "Content-Length: $contentLength\r\n" +
                        "Connection: keep-alive\r\n\r\n"
                out.write(header.toByteArray(Charsets.UTF_8))

                val fis = afd.createInputStream()
                try {
                    fis.channel.position(start)
                } catch (e: Exception) {
                    var skipped = 0L
                    while (skipped < start) {
                        val s = fis.skip(start - skipped)
                        if (s <= 0) {
                            if (fis.read() == -1) break
                            skipped += 1
                        } else {
                            skipped += s
                        }
                    }
                }

                val buf = ByteArray(128 * 1024)
                var remaining = contentLength
                fis.use { inp ->
                    while (remaining > 0) {
                        val toRead = if (remaining < buf.size) remaining.toInt() else buf.size
                        val read = inp.read(buf, 0, toRead)
                        if (read <= 0) break
                        out.write(buf, 0, read)
                        totalSent += read
                        remaining -= read
                    }
                }
            } else {
                val header = "HTTP/1.1 200 OK\r\n" +
                        "Content-Type: $mime\r\n" +
                        "Accept-Ranges: bytes\r\n" +
                        (if (totalLength > 0) "Content-Length: $totalLength\r\n" else "") +
                        "Connection: keep-alive\r\n\r\n"
                out.write(header.toByteArray(Charsets.UTF_8))

                val fis = afd.createInputStream()
                val buf = ByteArray(128 * 1024)
                fis.use { inp ->
                    while (true) {
                        val read = inp.read(buf)
                        if (read <= 0) break
                        out.write(buf, 0, read)
                        totalSent += read
                    }
                }
            }
            out.flush()
            afd.close()
        } catch (e: Exception) {
            Log.e(TAG, "Raw media streaming error: ${e.message}")
        }
        return totalSent
    }

    private fun handleFileList(out: OutputStream, path: String) {
        val dir = File(path)
        val array = JSONArray()

        if (dir.exists() && dir.isDirectory) {
            val rawFiles = dir.listFiles()
            if (rawFiles != null) {
                val list = ArrayList<JSONObject>(rawFiles.size)
                for (f in rawFiles) {
                    val isDir = f.isDirectory
                    val name = f.name
                    val ext = if (isDir) "" else f.extension.lowercase()
                    val category = when {
                        isDir -> "folder"
                        ext in listOf("jpg", "jpeg", "png", "webp", "gif") -> "image"
                        ext in listOf("mp4", "mkv", "mov", "avi", "webm") -> "video"
                        ext in listOf("pdf", "doc", "docx", "txt", "xlsx") -> "document"
                        ext in listOf("zip", "rar", "7z", "tar", "gz") -> "archive"
                        ext == "apk" -> "apk"
                        else -> "file"
                    }
                    list.add(JSONObject().apply {
                        put("name", name)
                        put("path", f.absolutePath)
                        put("isDir", isDir)
                        put("size", if (isDir) 0L else f.length())
                        put("date", f.lastModified())
                        put("category", category)
                    })
                }

                // In-memory sort with zero repeated disk stat calls
                list.sortWith(compareBy({ !it.optBoolean("isDir") }, { it.optString("name").lowercase() }))

                for (item in list) {
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

    private fun handleFileDownload(out: OutputStream, path: String, rangeHeader: String?): Long {
        val file = File(path)
        if (!file.exists() || file.isDirectory) {
            sendJsonResponse(out, 404, JSONObject().put("error", "File not found").toString())
            return 0L
        }

        var totalSent = 0L
        val totalLength = file.length()
        val ext = file.extension.lowercase()
        val mime = when (ext) {
            "mp4" -> "video/mp4"
            "mkv" -> "video/x-matroska"
            "webm" -> "video/webm"
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "pdf" -> "application/pdf"
            else -> "application/octet-stream"
        }

        try {
            if (rangeHeader != null && rangeHeader.startsWith("bytes=") && totalLength > 0) {
                val rangeVal = rangeHeader.removePrefix("bytes=").trim()
                val parts = rangeVal.split("-")
                val start = parts[0].toLongOrNull() ?: 0L
                val end = if (parts.size > 1 && parts[1].isNotEmpty()) parts[1].toLongOrNull() ?: (totalLength - 1) else (totalLength - 1)
                val contentLength = end - start + 1

                val header = "HTTP/1.1 206 Partial Content\r\n" +
                        "Content-Type: $mime\r\n" +
                        "Accept-Ranges: bytes\r\n" +
                        "Content-Range: bytes $start-$end/$totalLength\r\n" +
                        "Content-Length: $contentLength\r\n" +
                        "Connection: keep-alive\r\n\r\n"
                out.write(header.toByteArray(Charsets.UTF_8))

                val fis = FileInputStream(file)
                try {
                    fis.channel.position(start)
                } catch (e: Exception) {
                    var skipped = 0L
                    while (skipped < start) {
                        val s = fis.skip(start - skipped)
                        if (s <= 0) {
                            if (fis.read() == -1) break
                            skipped += 1
                        } else {
                            skipped += s
                        }
                    }
                }

                val buf = ByteArray(128 * 1024)
                var remaining = contentLength
                fis.use { inp ->
                    while (remaining > 0) {
                        val toRead = if (remaining < buf.size) remaining.toInt() else buf.size
                        val read = inp.read(buf, 0, toRead)
                        if (read <= 0) break
                        out.write(buf, 0, read)
                        totalSent += read
                        remaining -= read
                    }
                }
            } else {
                val header = "HTTP/1.1 200 OK\r\n" +
                        "Content-Type: $mime\r\n" +
                        "Accept-Ranges: bytes\r\n" +
                        "Content-Disposition: attachment; filename=\"${file.name}\"\r\n" +
                        "Content-Length: $totalLength\r\n" +
                        "Connection: keep-alive\r\n\r\n"
                out.write(header.toByteArray(Charsets.UTF_8))

                val fis = FileInputStream(file)
                val buf = ByteArray(128 * 1024)
                fis.use { inp ->
                    while (true) {
                        val read = inp.read(buf)
                        if (read <= 0) break
                        out.write(buf, 0, read)
                        totalSent += read
                    }
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
