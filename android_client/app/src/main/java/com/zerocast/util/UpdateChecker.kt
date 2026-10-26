package com.zerocast.util

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.FileProvider
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.FileOutputStream
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

object UpdateChecker {

    private const val GITHUB_REPO = "WhyAlwaysEng/ZeroLink"
    private const val RELEASES_API = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
    private const val FALLBACK_VERSION = "1.0.0"

    private var downloadJob: Job? = null

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
                conn.connectTimeout = 5000
                conn.readTimeout = 5000

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
                    var apkSize: Long = 0L

                    if (assets != null) {
                        for (i in 0 until assets.length()) {
                            val item = assets.getJSONObject(i)
                            val name = item.optString("name", "")
                            if (name.endsWith(".apk", ignoreCase = true)) {
                                directApkUrl = item.optString("browser_download_url", "")
                                apkSize = item.optLong("size", 0L)
                                break
                            }
                        }
                    }

                    withContext(Dispatchers.Main) {
                        if (!activity.isFinishing && !activity.isDestroyed) {
                            if (isNewerVersion(tagName, currentVersion)) {
                                showUpdatePrompt(
                                    activity = activity,
                                    tagName = tagName,
                                    apkUrl = directApkUrl,
                                    htmlUrl = htmlUrl,
                                    notes = releaseNotes,
                                    currentVersion = currentVersion,
                                    apkSize = apkSize
                                )
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

    private fun showUpdatePrompt(
        activity: Activity,
        tagName: String,
        apkUrl: String?,
        htmlUrl: String,
        notes: String,
        currentVersion: String,
        apkSize: Long
    ) {
        val snippet = if (notes.length > 300) notes.take(300) + "..." else notes
        val sizeMb = if (apkSize > 0) String.format(" (%.1f MB)", apkSize / (1024f * 1024f)) else ""

        val message = StringBuilder()
            .append("A new release of ZeroLink is available.\n\n")
            .append("• Installed: v$currentVersion\n")
            .append("• Available: $tagName$sizeMb\n")
        if (snippet.isNotBlank()) {
            message.append("\nWhat's New:\n$snippet")
        }

        MaterialAlertDialogBuilder(activity)
            .setTitle("🚀 Update Available: $tagName")
            .setMessage(message.toString())
            .setPositiveButton(if (apkUrl != null) "Update Now" else "Open GitHub") { _, _ ->
                if (apkUrl != null) {
                    checkPermissionAndStartDownload(activity, apkUrl, apkSize)
                } else {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(htmlUrl))
                    activity.startActivity(intent)
                }
            }
            .setNeutralButton("Open in Browser") { _, _ ->
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(htmlUrl))
                activity.startActivity(intent)
            }
            .setNegativeButton("Later", null)
            .show()
    }

    private fun checkPermissionAndStartDownload(activity: Activity, apkUrl: String, apkSize: Long) {
        // On Android 8.0+ (Oreo), verify that app can install unknown packages
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!activity.packageManager.canRequestPackageInstalls()) {
                MaterialAlertDialogBuilder(activity)
                    .setTitle("Install Permission Required")
                    .setMessage("To install updates directly inside ZeroLink, please grant 'Install unknown apps' permission in Android Settings.")
                    .setPositiveButton("Open Settings") { _, _ ->
                        try {
                            val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                                data = Uri.parse("package:${activity.packageName}")
                            }
                            activity.startActivity(intent)
                        } catch (e: Exception) {
                            Toast.makeText(activity, "Please allow install permission in Settings", Toast.LENGTH_SHORT).show()
                        }
                    }
                    .setNegativeButton("Cancel", null)
                    .show()
                return
            }
        }

        startInAppDownload(activity, apkUrl, apkSize)
    }

    private fun startInAppDownload(activity: Activity, apkUrl: String, apkSize: Long) {
        // Create modern download progress layout programmatically
        val dp = activity.resources.displayMetrics.density
        val padHorizontal = (24 * dp).toInt()
        val padVertical = (16 * dp).toInt()

        val layout = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padHorizontal, padVertical, padHorizontal, padVertical)
        }

        val statusText = TextView(activity).apply {
            text = "Connecting to download server..."
            textSize = 13f
            setTextColor(Color.LTGRAY)
            setPadding(0, 0, 0, (12 * dp).toInt())
        }

        val progressBar = ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = false
            max = 100
            progress = 0
        }

        layout.addView(statusText)
        layout.addView(progressBar)

        var dialog: AlertDialog? = null
        dialog = MaterialAlertDialogBuilder(activity)
            .setTitle("Downloading ZeroLink Update...")
            .setView(layout)
            .setCancelable(false)
            .setNegativeButton("Cancel") { _, _ ->
                downloadJob?.cancel()
                Toast.makeText(activity, "Update download cancelled", Toast.LENGTH_SHORT).show()
            }
            .create()

        dialog.show()

        downloadJob = CoroutineScope(Dispatchers.IO).launch {
            val downloadDir = activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: activity.cacheDir
            val destinationFile = File(downloadDir, "ZeroLink_update.apk")
            try {
                if (destinationFile.exists()) {
                    destinationFile.delete()
                }

                val conn = URL(apkUrl).openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.setRequestProperty("User-Agent", "ZeroLink-InAppUpdater")
                conn.connectTimeout = 10000
                conn.readTimeout = 15000
                conn.connect()

                val totalBytes = if (conn.contentLengthLong > 0) conn.contentLengthLong else apkSize
                val inputStream = conn.inputStream
                val outputStream = FileOutputStream(destinationFile)

                val buffer = ByteArray(128 * 1024)
                var bytesRead: Int
                var downloadedBytes = 0L

                while (inputStream.read(buffer).also { bytesRead = it } != -1) {
                    outputStream.write(buffer, 0, bytesRead)
                    downloadedBytes += bytesRead

                    val percent = if (totalBytes > 0) ((downloadedBytes * 100) / totalBytes).toInt() else 0
                    val dlMb = downloadedBytes / (1024f * 1024f)
                    val totMb = totalBytes / (1024f * 1024f)

                    withContext(Dispatchers.Main) {
                        progressBar.progress = percent
                        if (totalBytes > 0) {
                            statusText.text = String.format("Downloading: %.1f MB / %.1f MB (%d%%)", dlMb, totMb, percent)
                        } else {
                            statusText.text = String.format("Downloading: %.1f MB...", dlMb)
                        }
                    }
                }

                outputStream.flush()
                outputStream.close()
                inputStream.close()

                withContext(Dispatchers.Main) {
                    dialog.dismiss()
                    installDownloadedApk(activity, destinationFile)
                }
            } catch (ce: CancellationException) {
                if (destinationFile.exists()) destinationFile.delete()
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    dialog.dismiss()
                    Toast.makeText(activity, "Download failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun installDownloadedApk(activity: Activity, apkFile: File) {
        if (!apkFile.exists() || apkFile.length() == 0L) {
            Toast.makeText(activity, "Downloaded update file is invalid.", Toast.LENGTH_SHORT).show()
            return
        }

        try {
            val apkUri: Uri = FileProvider.getUriForFile(
                activity,
                "${activity.packageName}.fileprovider",
                apkFile
            )

            val installIntent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(apkUri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }

            activity.startActivity(installIntent)
        } catch (e: Exception) {
            Toast.makeText(activity, "Failed to launch package installer: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
}
