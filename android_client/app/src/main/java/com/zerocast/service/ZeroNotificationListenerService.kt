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
        if (serverIp.isEmpty() || serverIp == "127.0.0.1") return

        // Send UDP packet asynchronously to PC
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val payload = JSONObject().apply {
                    put("type", "ZEROLINK_NOTIFY")
                    put("app", appName)
                    put("title", title)
                    put("text", text)
                    put("package", sbn.packageName)
                    put("time", System.currentTimeMillis())
                }.toString().toByteArray(Charsets.UTF_8)

                DatagramSocket().use { socket ->
                    val address = InetAddress.getByName(serverIp)
                    val packet = DatagramPacket(payload, payload.size, address, NOTIFY_PORT)
                    socket.send(packet)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Failed to send notification to $serverIp: ${e.message}")
            }
        }
    }
}
