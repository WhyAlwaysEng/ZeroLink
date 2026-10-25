package com.zerocast.service

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.zerocast.util.ZeroLinkConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

class ZeroNotificationListenerService : NotificationListenerService() {

    companion object {
        private const val TAG = "ZeroNotify"
        private const val NOTIFY_PORT = 8887
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        if (sbn == null) return

        // Check if user enabled notification mirroring
        if (!ZeroLinkConfig.getNotifyMirror(this)) return

        // Skip our own notifications to prevent feedback loops
        if (sbn.packageName == packageName) return

        // Privacy filter for banking & financial applications
        if (ZeroLinkConfig.getPrivacyFilterBanking(this)) {
            val pkg = sbn.packageName.lowercase()
            val isBankingApp = pkg.contains("bank") || pkg.contains("kplus") || pkg.contains("scb") ||
                    pkg.contains("ktb") || pkg.contains("krungsri") || pkg.contains("ttbbank") ||
                    pkg.contains("gsb") || pkg.contains("cimb") || pkg.contains("uob") ||
                    pkg.contains("truemoney") || pkg.contains("wallet")
            if (isBankingApp) {
                Log.d(TAG, "Suppressed sensitive banking notification: $pkg")
                return
            }
        }

        // Skip ongoing persistent notifications (media players, foreground services, downloads)
        if (sbn.isOngoing) return

        val notification = sbn.notification ?: return
        val extras = notification.extras ?: return

        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim() ?: ""
        val text = (extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()
            ?: extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString())?.trim() ?: ""

        // Skip completely empty notifications
        if (title.isEmpty() && text.isEmpty()) return

        val pm = applicationContext.packageManager
        val appName = try {
            val appInfo = pm.getApplicationInfo(sbn.packageName, 0)
            pm.getApplicationLabel(appInfo).toString()
        } catch (_: Exception) {
            sbn.packageName
        }

        val serverIp = ZeroLinkConfig.getServerIp(this)
        if (serverIp.isEmpty()) return

        // Send notification asynchronously to PC (Supports both TCP Master Gateway & UDP)
        CoroutineScope(Dispatchers.IO).launch {
            val jsonPayload = JSONObject().apply {
                put("type", "ZEROLINK_NOTIFY")
                put("app", appName)
                put("title", title)
                put("text", text)
                put("package", sbn.packageName)
                put("time", System.currentTimeMillis())
            }

            var sentViaTcp = false
            // 1. Try TCP Master Gateway (works over both USB 127.0.0.1 and Wi-Fi)
            try {
                val sock = java.net.Socket()
                sock.soTimeout = 1500
                sock.connect(java.net.InetSocketAddress(serverIp, 8886), 1200)
                val writer = java.io.OutputStreamWriter(sock.getOutputStream(), Charsets.UTF_8)
                writer.write(jsonPayload.toString() + "\n")
                writer.flush()
                sock.close()
                sentViaTcp = true
            } catch (_: Exception) {}

            // 2. Fallback to UDP if not sent via TCP and not loopback
            if (!sentViaTcp && serverIp != "127.0.0.1") {
                try {
                    val payload = jsonPayload.toString().toByteArray(Charsets.UTF_8)
                    DatagramSocket().use { socket ->
                        val address = InetAddress.getByName(serverIp)
                        val packet = DatagramPacket(payload, payload.size, address, NOTIFY_PORT)
                        socket.send(packet)
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to send notification via UDP: ${e.message}")
                }
            }
        }
    }
}
