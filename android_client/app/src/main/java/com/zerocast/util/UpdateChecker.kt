package com.zerocast.util

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.widget.Toast
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

    private const val GITHUB_REPO = "WhyAlwaysEng/ZeroLink"
    private const val RELEASES_API = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
    private const val FALLBACK_VERSION = "1.0.0"

    fun getAppVersion(activity: Activity): String {
        return try {
            val pInfo = activity.packageManager.getPackageInfo(activity.packageName, 0)
            pInfo.versionName ?: FALLBACK_VERSION
        } catch (e: Exception) {
            FALLBACK_VERSION
        }
    }

    fun checkForUpdates(activity: Activity, isManualCheck: Boolean = false) {
        val currentVersion = getAppVersion(activity)
        if (isManualCheck) {
            Toast.makeText(activity, "Checking for ZeroLink updates...", Toast.LENGTH_SHORT).show()
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val url = URL(RELEASES_API)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.setRequestProperty("User-Agent", "ZeroLink-Android/$currentVersion")
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

                    // Find direct APK download asset if present
                    val assets = json.optJSONArray("assets")
                    var directApkUrl: String? = null
                    if (assets != null) {
                        for (i in 0 until assets.length()) {
                            val item = assets.getJSONObject(i)
                            val name = item.optString("name", "")
                            if (name.endsWith(".apk", ignoreCase = true)) {
                                directApkUrl = item.optString("browser_download_url", "")
                                break
                            }
                        }
                    }
                    val targetUrl = directApkUrl ?: htmlUrl

                    withContext(Dispatchers.Main) {
                        if (!activity.isFinishing && !activity.isDestroyed) {
                            if (isNewerVersion(tagName, currentVersion)) {
                                showUpdateDialog(activity, tagName, targetUrl, releaseNotes, currentVersion)
                            } else if (isManualCheck) {
                                MaterialAlertDialogBuilder(activity)
                                    .setTitle("You're Up to Date! 🎉")
                                    .setMessage("ZeroLink v$currentVersion is currently the latest version.")
                                    .setPositiveButton("OK", null)
                                    .show()
                            }
                        }
                    }
                } else if (isManualCheck) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(activity, "No new updates found on GitHub.", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                if (isManualCheck) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(activity, "Could not check for updates: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
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
        val snippet = if (notes.length > 250) notes.take(250) + "..." else notes
        val message = StringBuilder()
            .append("A new release of ZeroLink is ready on GitHub.\n\n")
            .append("• Installed: v$currentVersion\n")
            .append("• Available: $tag\n")
        if (snippet.isNotBlank()) {
            message.append("\nWhat's New:\n$snippet")
        }

        MaterialAlertDialogBuilder(activity)
            .setTitle("🚀 Update Available: $tag")
            .setMessage(message.toString())
            .setPositiveButton("Download APK") { _, _ ->
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(downloadUrl))
                activity.startActivity(intent)
            }
            .setNegativeButton("Later", null)
            .show()
    }
}
