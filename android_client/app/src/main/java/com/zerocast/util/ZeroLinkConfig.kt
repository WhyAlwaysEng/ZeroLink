package com.zerocast.util

import android.content.Context

object ZeroLinkConfig {
    const val DEFAULT_CAST_PORT = 8888
    const val DEFAULT_CLIP_PORT = 8889
    const val DEFAULT_DROP_PORT = 8890

    private const val PREF_NAME = "zerolink_prefs"
    private const val KEY_SERVER_IP = "server_ip"

    fun getServerIp(context: Context): String {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        return sp.getString(KEY_SERVER_IP, "127.0.0.1") ?: "127.0.0.1"
    }

    fun setServerIp(context: Context, ip: String) {
        val sp = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        sp.edit().putString(KEY_SERVER_IP, ip).apply()
    }
}
