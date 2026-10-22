package com.zerocast.util

import android.app.Activity
import android.content.Intent
import android.net.Uri
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

object UpdateChecker {

    private const val GITHUB_REPO = "WhyAlwaysEng/ZeroCast"
    private const val RELEASES_API = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
    private const val FALLBACK_VERSION = "1.0.0"

    private fun getAppVersion(activity: Activity): String {
        return try {
            val pInfo = activity.packageManager.getPackageInfo(activity.packageName, 0)
            pInfo.versionName ?: FALLBACK_VERSION
        } catch (e: Exception) {
            FALLBACK_VERSION
        }
    }

    fun checkForUpdates(activity: Activity) {
        val currentVersion = getAppVersion(activity)
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val url = URL(RELEASES_API)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.setRequestProperty("User-Agent", "ZeroCast-Android/$currentVersion")
                conn.setRequestProperty("Accept", "application/vnd.github.v3+json")
                conn.connectTimeout = 4000
                conn.readTimeout = 4000

                if (conn.responseCode == 200) {
                    val reader = BufferedReader(InputStreamReader(conn.inputStream))
                    val response = reader.readText()
                    reader.close()

                    val json = JSONObject(response)
                    val tagName = json.optString("tag_name", "").trim()
                    val htmlUrl = json.optString("html_url", "https://github.com/$GITHUB_REPO/releases")
                    val releaseNotes = json.optString("body", "")

                    if (isNewerVersion(tagName, currentVersion)) {
                        withContext(Dispatchers.Main) {
                            if (!activity.isFinishing && !activity.isDestroyed) {
                                showUpdateDialog(activity, tagName, htmlUrl, releaseNotes, currentVersion)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                // Silently ignore network / rate-limit / 404 errors during startup
            }
        }
    }

    private fun isNewerVersion(remoteTag: String, localVer: String): Boolean {
        val remoteNums = parseVersion(remoteTag)
        val localNums = parseVersion(localVer)
        val maxLen = maxOf(remoteNums.size, localNums.size)

        for (i in 0 until maxLen) {
            val r = remoteNums.getOrElse(i) { 0 }
            val l = localNums.getOrElse(i) { 0 }
            if (r > l) return true
            if (r < l) return false
        }
        return false
    }

    private fun parseVersion(ver: String): List<Int> {
        val clean = ver.replace(Regex("[^0-9.]"), "")
        return clean.split(".").mapNotNull { it.toIntOrNull() }
    }

    private fun showUpdateDialog(
        activity: Activity,
        tag: String,
        downloadUrl: String,
        notes: String,
        currentVersion: String
    ) {
        val snippet = if (notes.length > 200) notes.take(200) + "..." else notes
        val message = StringBuilder()
            .append("A new version of ZeroCast is ready on GitHub.\n\n")
            .append("• Current: v$currentVersion\n")
            .append("• Latest: $tag\n")
        if (snippet.isNotBlank()) {
            message.append("\nNotes:\n$snippet")
        }

        MaterialAlertDialogBuilder(activity)
            .setTitle("🚀 Update Available: $tag")
            .setMessage(message.toString())
            .setPositiveButton("Download / Update") { _, _ ->
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(downloadUrl))
                activity.startActivity(intent)
            }
            .setNegativeButton("Later", null)
            .show()
    }
}
