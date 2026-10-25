package com.zerocast.network

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.widget.Toast
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.io.PrintWriter
import java.net.InetSocketAddress
import java.net.Socket

class ClipboardSyncManager(
    private val context: Context,
    private val onStatusChanged: (Boolean, String) -> Unit = { _, _ -> },
    private val onClipSynced: (String, String, Long) -> Unit = { _, _, _ -> }
) {
    private val TAG = "ZeroClip"
    private val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val mainHandler = Handler(Looper.getMainLooper())

    private var socket: Socket? = null
    private var writer: PrintWriter? = null
    private var syncJob: Job? = null
    var isConnected = false
        private set

    private var lastSyncedText: String = ""
    private var lastSyncedTimestamp: Long = 0

    private val clipListener = ClipboardManager.OnPrimaryClipChangedListener {
        val clip = clipboard.primaryClip
        if (clip != null && clip.itemCount > 0) {
            val text = clip.getItemAt(0).text?.toString()
            if (!text.isNullOrEmpty() && text != lastSyncedText) {
                lastSyncedText = text
                lastSyncedTimestamp = System.currentTimeMillis()
                sendClipboardText(text)
                onClipSynced(text, "PHONE", lastSyncedTimestamp)
            }
        }
    }

    fun start(host: String, port: Int = 8889) {
        if (isConnected) return

        syncJob = CoroutineScope(Dispatchers.IO).launch {
            try {
                Log.d(TAG, "Connecting to ZeroClip server at $host:$port...")
                withContext(Dispatchers.Main) { onStatusChanged(false, "Connecting...") }

                val s = Socket()
                s.connect(InetSocketAddress(host, port), 4000)
                socket = s
                writer = PrintWriter(OutputStreamWriter(s.getOutputStream(), "UTF-8"), true)
                isConnected = true

                withContext(Dispatchers.Main) {
                    onStatusChanged(true, "● SYNC ACTIVE")
                    clipboard.addPrimaryClipChangedListener(clipListener)
                }

                val reader = BufferedReader(InputStreamReader(s.getInputStream(), "UTF-8"))
                while (isActive && isConnected) {
                    val line = reader.readLine() ?: break
                    if (line.isBlank()) continue

                    try {
                        val json = JSONObject(line)
                        if (json.optString("action") == "SYNC_CLIP") {
                            val text = json.optString("text")
                            val source = json.optString("source", "PC")
                            val ts = json.optLong("timestamp", System.currentTimeMillis())

                            if (text.isNotEmpty() && text != lastSyncedText) {
                                lastSyncedText = text
                                lastSyncedTimestamp = ts

                                withContext(Dispatchers.Main) {
                                    clipboard.removePrimaryClipChangedListener(clipListener)
                                    clipboard.setPrimaryClip(ClipData.newPlainText("ZeroClip", text))
                                    mainHandler.postDelayed({
                                        clipboard.addPrimaryClipChangedListener(clipListener)
                                    }, 200)

                                    val preview = if (text.length > 35) text.substring(0, 32) + "..." else text
                                    Toast.makeText(context, "📋 Synced from $source: $preview", Toast.LENGTH_SHORT).show()
                                    onClipSynced(text, source, ts)
                                }
                            }
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Error parsing clip JSON: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "ZeroClip connection failed: ${e.message}")
            } finally {
                stop()
            }
        }
    }

    fun sendClipboardText(text: String) {
        if (!isConnected || writer == null) return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val json = JSONObject().apply {
                    put("action", "SYNC_CLIP")
                    put("text", text)
                    put("source", "PHONE")
                    put("timestamp", System.currentTimeMillis())
                }
                writer?.println(json.toString())
                Log.d(TAG, "Sent clip to PC: $text")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send clip to PC: ${e.message}")
            }
        }
    }

    fun stop() {
        isConnected = false
        try {
            socket?.close()
        } catch (e: Exception) {}
        socket = null
        writer = null

        mainHandler.post {
            try {
                clipboard.removePrimaryClipChangedListener(clipListener)
            } catch (e: Exception) {}
            onStatusChanged(false, "○ DISCONNECTED")
        }
        syncJob?.cancel()
    }
}
