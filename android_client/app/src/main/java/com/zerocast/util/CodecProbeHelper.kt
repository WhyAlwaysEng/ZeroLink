package com.zerocast.util

import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat
import android.os.Build

object CodecProbeHelper {

    /**
     * Checks if the device has a hardware-accelerated HEVC (H.265) video encoder.
     */
    fun isHardwareHevcSupported(): Boolean {
        return isHardwareEncoderAvailable(MediaFormat.MIMETYPE_VIDEO_HEVC)
    }

    /**
     * Checks if the device has a hardware-accelerated AV1 video encoder.
     */
    fun isHardwareAv1Supported(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            isHardwareEncoderAvailable("video/av01") || isHardwareEncoderAvailable("video/av1")
        } else {
            false
        }
    }

    private fun isHardwareEncoderAvailable(mimeType: String): Boolean {
        return try {
            val list = MediaCodecList(MediaCodecList.REGULAR_CODECS)
            for (info in list.codecInfos) {
                if (!info.isEncoder) continue
                val types = info.supportedTypes
                val matches = types.any { it.equals(mimeType, ignoreCase = true) }
                if (matches) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        if (info.isHardwareAccelerated) {
                            return true
                        }
                    } else {
                        // On older Android, vendor OMX encoders typically start with OMX.qcom, OMX.Exynos, OMX.MTK, etc.
                        val name = info.name.lowercase()
                        if (!name.startsWith("omx.google.") && !name.contains("sw") && !name.contains("google")) {
                            return true
                        }
                    }
                }
            }
            false
        } catch (_: Exception) {
            false
        }
    }
}
