package com.zerocast.network

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.io.PrintWriter
import java.net.InetSocketAddress
import java.net.Socket

data class SoundboardItem(
    val id: String,
    val name: String
)

data class ZeroMixState(
    val micVol: Int = 100,
    val musicVol: Int = 80,
    val soundVol: Int = 90,
    val micMuted: Boolean = false,
    val musicMuted: Boolean = false,
    val soundMuted: Boolean = false,
    val duckingEnabled: Boolean = true,
    val duckingLevel: Int = 20,
    val sounds: List<SoundboardItem> = emptyList()
)

class ZeroMixManager(
    private val context: Context,
    private val onStatusChanged: (Boolean, String) -> Unit = { _, _ -> },
    private val onStateUpdated: (ZeroMixState) -> Unit = {},
    private val onSoundsUpdated: (List<SoundboardItem>) -> Unit = {}
) {
    private val TAG = "ZeroMix"
    private val mainHandler = Handler(Looper.getMainLooper())

    private var socket: Socket? = null
    private var writer: PrintWriter? = null
    private var connectionJob: Job? = null
    var isConnected = false
        private set

    fun start(host: String, port: Int = 8891) {
        stop()

        connectionJob = CoroutineScope(Dispatchers.IO).launch {
            try {
                withContext(Dispatchers.Main) { onStatusChanged(false, "Connecting...") }

                val s = Socket()
                s.connect(InetSocketAddress(host, port), 4000)
                socket = s
                writer = PrintWriter(OutputStreamWriter(s.getOutputStream(), "UTF-8"), true)
                isConnected = true

                withContext(Dispatchers.Main) {
                    onStatusChanged(true, "● CONNECTED TO PC")
                }

                // Register client with device model and request initial state
                sendCommand(JSONObject().apply {
                    put("action", "CONNECT")
                    put("device_model", android.os.Build.MODEL)
                    put("model", android.os.Build.MODEL)
                })

                val reader = BufferedReader(InputStreamReader(s.getInputStream(), "UTF-8"))
                while (isActive && isConnected) {
                    val line = reader.readLine() ?: break
                    if (line.isBlank()) continue

                    try {
                        val json = JSONObject(line)
                        val action = json.optString("action")

                        if (action == "STATE_UPDATE") {
                            val state = parseState(json)
                            withContext(Dispatchers.Main) {
                                onStateUpdated(state)
                                onSoundsUpdated(state.sounds)
                            }
                        } else if (action == "SOUND_LIST") {
                            val list = parseSounds(json.optJSONArray("sounds"))
                            withContext(Dispatchers.Main) {
                                onSoundsUpdated(list)
                            }
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Parse error: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                Log.d(TAG, "Connection failed: ${e.message}")
            } finally {
                withContext(Dispatchers.Main) {
                    onStatusChanged(false, "○ DISCONNECTED")
                }
                stop()
            }
        }
    }

    private fun parseState(json: JSONObject): ZeroMixState {
        val sounds = parseSounds(json.optJSONArray("sounds"))
        return ZeroMixState(
            micVol = json.optInt("mic_vol", 100),
            musicVol = json.optInt("music_vol", 80),
            soundVol = json.optInt("sound_vol", 90),
            micMuted = json.optBoolean("mic_muted", false),
            musicMuted = json.optBoolean("music_muted", false),
            soundMuted = json.optBoolean("sound_muted", false),
            duckingEnabled = json.optBoolean("ducking_enabled", true),
            duckingLevel = json.optInt("ducking_level", 20),
            sounds = sounds
        )
    }

    private fun parseSounds(arr: JSONArray?): List<SoundboardItem> {
        val list = mutableListOf<SoundboardItem>()
        if (arr != null) {
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i)
                if (obj != null) {
                    list.add(SoundboardItem(
                        id = obj.optString("id"),
                        name = obj.optString("name")
                    ))
                }
            }
        }
        return list
    }

    fun requestRefreshSounds() {
        sendCommand(JSONObject().apply { put("action", "REFRESH_SOUNDS") })
    }

    fun playSound(id: String) {
        sendCommand(JSONObject().apply {
            put("action", "PLAY_SOUND")
            put("id", id)
        })
    }

    fun stopSound() {
        sendCommand(JSONObject().apply { put("action", "STOP_SOUND") })
    }

    fun setVolume(channel: String, volume: Int) {
        sendCommand(JSONObject().apply {
            put("action", "SET_VOLUME")
            put("channel", channel)
            put("volume", volume)
        })
    }

    fun setMute(channel: String, muted: Boolean) {
        sendCommand(JSONObject().apply {
            put("action", "SET_MUTE")
            put("channel", channel)
            put("muted", muted)
        })
    }

    fun setDucking(enabled: Boolean, level: Int) {
        sendCommand(JSONObject().apply {
            put("action", "SET_DUCKING")
            put("enabled", enabled)
            put("level", level)
        })
    }

    private fun sendCommand(json: JSONObject) {
        if (!isConnected || writer == null) return
        CoroutineScope(Dispatchers.IO).launch {
            try {
                writer?.println(json.toString())
            } catch (e: Exception) {
                Log.e(TAG, "Send error: ${e.message}")
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
        connectionJob?.cancel()
        connectionJob = null
    }
}
