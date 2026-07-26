import json
import struct
from typing import Dict, Tuple


PROTOCOL_VERSION = 1
MAX_HEADER_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024


def encode_frame(header: Dict, png_bytes: bytes) -> bytes:
    """Encode one overlay snapshot for the Game Bar mailbox client."""
    frame_header = dict(header)
    frame_header["version"] = PROTOCOL_VERSION
    header_bytes = json.dumps(
        frame_header,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    if len(header_bytes) > MAX_HEADER_BYTES:
        raise ValueError("overlay frame header is too large")
    if len(png_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("overlay frame image is too large")

    return (
        struct.pack("<I", len(header_bytes))
        + header_bytes
        + struct.pack("<I", len(png_bytes))
        + png_bytes
    )


def decode_frame(payload: bytes) -> Tuple[Dict, bytes]:
    """Decode a complete frame. Used by tests and diagnostic clients."""
    if len(payload) < 8:
        raise ValueError("overlay frame is truncated")

    header_size = struct.unpack_from("<I", payload, 0)[0]
    if header_size > MAX_HEADER_BYTES:
        raise ValueError("overlay frame header is too large")

    image_size_offset = 4 + header_size
    if len(payload) < image_size_offset + 4:
        raise ValueError("overlay frame is truncated")

    image_size = struct.unpack_from("<I", payload, image_size_offset)[0]
    if image_size > MAX_IMAGE_BYTES:
        raise ValueError("overlay frame image is too large")

    expected_size = image_size_offset + 4 + image_size
    if len(payload) != expected_size:
        raise ValueError("overlay frame length does not match its header")

    header = json.loads(payload[4:image_size_offset].decode("utf-8"))
    image = payload[image_size_offset + 4:expected_size]
    return header, image
