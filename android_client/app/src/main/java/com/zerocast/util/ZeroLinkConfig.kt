package com.zerocast.util

import android.content.Context

object ZeroLinkConfig {
    const val DEFAULT_CAST_PORT = 8888
    const val DEFAULT_CLIP_PORT = 8889
    const val DEFAULT_DROP_PORT = 8890
    const val DEFAULT_MIX_PORT = 8891

    private const val PREF_NAME = "zerolink_prefs"
    private const val KEY_SERVER_IP = "server_ip"
    private const val KEY_CAST_PORT = "cast_port"
    private const val KEY_CAST_RES = "cast_res"
    private const val KEY_CAST_FPS = "cast_fps"
    private const val KEY_CAST_BITRATE = "cast_bitrate"
    private const val KEY_CAST_AUDIO = "cast_audio"
    private const val KEY_CAST_DIM = "cast_dim"

    fun getServerIp(context: Context): String {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getString(KEY_SERVER_IP, "127.0.0.1") ?: "127.0.0.1"
    }

    fun setServerIp(context: Context, ip: String) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putString(KEY_SERVER_IP, ip).apply()
    }

    fun getCastPort(context: Context): Int {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getInt(KEY_CAST_PORT, DEFAULT_CAST_PORT)
    }

    fun setCastPort(context: Context, port: Int) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putInt(KEY_CAST_PORT, port).apply()
    }

    fun getCastResolution(context: Context): Int {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getInt(KEY_CAST_RES, 0)
    }

    fun setCastResolution(context: Context, index: Int) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putInt(KEY_CAST_RES, index).apply()
    }

    fun getCastFps(context: Context): Int {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getInt(KEY_CAST_FPS, 0) // default 60 FPS
    }

    fun setCastFps(context: Context, index: Int) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putInt(KEY_CAST_FPS, index).apply()
    }

    fun getCastBitrate(context: Context): Int {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getInt(KEY_CAST_BITRATE, 1) // default 14 Mbps
    }

    fun setCastBitrate(context: Context, index: Int) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putInt(KEY_CAST_BITRATE, index).apply()
    }

    fun getCastAudio(context: Context): Boolean {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getBoolean(KEY_CAST_AUDIO, true)
    }

    fun setCastAudio(context: Context, enabled: Boolean) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putBoolean(KEY_CAST_AUDIO, enabled).apply()
    }

    fun getCastDimScreen(context: Context): Boolean {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getBoolean(KEY_CAST_DIM, false)
    }

    fun setCastDimScreen(context: Context, enabled: Boolean) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putBoolean(KEY_CAST_DIM, enabled).apply()
    }
}
