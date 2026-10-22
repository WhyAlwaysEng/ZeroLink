"""ZeroCast Protocol Specification
Defines binary framing header constants, packing, and parsing.
"""

import struct
from dataclasses import dataclass
from typing import Optional, Tuple

MAGIC_BYTE = 0xAA
HEADER_SIZE = 16

# Packet Types
TYPE_VIDEO_MJPEG = 0x01
TYPE_VIDEO_H264 = 0x02
TYPE_AUDIO = 0x03
TYPE_CONFIG_JSON = 0x04
TYPE_INPUT_CONTROL = 0x05

# Flags
FLAG_KEYFRAME = 0x01
FLAG_CODEC_CONFIG = 0x02
FLAG_ORIENTATION_LANDSCAPE = 0x04

# Binary header format:
# > = Big-Endian
# B = Magic Byte (1B)
# B = Packet Type (1B)
# B = Flags (1B)
# B = Reserved (1B)
# I = Payload Length (4B, uint32)
# Q = Timestamp in Microseconds (8B, uint64)
HEADER_STRUCT = struct.Struct(">BBBB I Q")


@dataclass
class Packet:
    packet_type: int
    flags: int
    payload_length: int
    timestamp_us: int
    payload: bytes


def pack_header(packet_type: int, flags: int, payload_length: int, timestamp_us: int) -> bytes:
    """Pack the 16-byte protocol header."""
    return HEADER_STRUCT.pack(
        MAGIC_BYTE,
        packet_type,
        flags,
        0,  # Reserved
        payload_length,
        timestamp_us
    )


def unpack_header(data: bytes) -> Optional[Tuple[int, int, int, int]]:
    """Unpack a 16-byte header.
    Returns (packet_type, flags, payload_length, timestamp_us) or None if invalid magic.
    """
    if len(data) < HEADER_SIZE:
        return None
    magic, p_type, flags, _, length, ts_us = HEADER_STRUCT.unpack(data[:HEADER_SIZE])
    if magic != MAGIC_BYTE:
        return None
    return p_type, flags, length, ts_us
