package com.zerocast.protocol

import java.io.DataOutputStream
import java.nio.ByteBuffer

object PacketHeader {
    const val MAGIC_BYTE: Byte = 0xAA.toByte()
    const val HEADER_SIZE = 16

    const val TYPE_VIDEO_MJPEG: Byte = 0x01
    const val TYPE_VIDEO_H264: Byte = 0x02
    const val TYPE_AUDIO: Byte = 0x03
    const val TYPE_CONFIG_JSON: Byte = 0x04
    const val TYPE_INPUT_CONTROL: Byte = 0x05
    const val TYPE_VIDEO_HEVC: Byte = 0x06
    const val TYPE_VIDEO_AV1: Byte = 0x07

    const val FLAG_KEYFRAME: Byte = 0x01
    const val FLAG_CODEC_CONFIG: Byte = 0x02
    const val FLAG_ORIENTATION_LANDSCAPE: Byte = 0x04

    fun writeTo(
        outputStream: DataOutputStream,
        type: Byte,
        flags: Byte,
        payloadSize: Int,
        timestampUs: Long
    ) {
        outputStream.writeByte(MAGIC_BYTE.toInt())
        outputStream.writeByte(type.toInt())
        outputStream.writeByte(flags.toInt())
        outputStream.writeByte(0x00) // Reserved
        outputStream.writeInt(payloadSize) // 4 Bytes Big-Endian
        outputStream.writeLong(timestampUs) // 8 Bytes Big-Endian
    }
}

data class FramePacket(
    val type: Byte,
    val flags: Byte,
    val timestampUs: Long,
    val payload: ByteArray
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as FramePacket
        return type == other.type &&
                flags == other.flags &&
                timestampUs == other.timestampUs &&
                payload.contentEquals(other.payload)
    }

    override fun hashCode(): Int {
        var result = type.toInt()
        result = 31 * result + flags.toInt()
        result = 31 * result + timestampUs.hashCode()
        result = 31 * result + payload.contentHashCode()
        return result
    }
}
