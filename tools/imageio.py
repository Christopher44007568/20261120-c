"""Small dependency-free image helpers used by the report generator."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def read_ppm(path: str | Path) -> tuple[int, int, bytearray]:
    data = Path(path).read_bytes()
    if not data.startswith(b"P6"):
        raise ValueError(f"not a binary PPM: {path}")
    fields: list[bytes] = []
    pos = 2
    while len(fields) < 3:
        while pos < len(data) and data[pos] in b" \t\r\n":
            pos += 1
        if data[pos : pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        start = pos
        while pos < len(data) and data[pos] not in b" \t\r\n":
            pos += 1
        fields.append(data[start:pos])
    width, height, maxval = (int(v) for v in fields)
    if maxval != 255:
        raise ValueError("only 8-bit PPM is supported")
    while pos < len(data) and data[pos] in b" \t\r\n":
        pos += 1
    pixels = bytearray(data[pos:])
    if len(pixels) != width * height * 3:
        raise ValueError(f"bad PPM payload size: {len(pixels)}")
    return width, height, pixels


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: str | Path, width: int, height: int, rgb: bytes | bytearray) -> None:
    if len(rgb) != width * height * 3:
        raise ValueError("RGB buffer size does not match image dimensions")
    stride = width * 3
    raw = bytearray((stride + 1) * height)
    for y in range(height):
        src = y * stride
        dst = y * (stride + 1)
        raw[dst + 1 : dst + stride + 1] = rgb[src : src + stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )
    Path(path).write_bytes(payload)


def ppm_to_png(src: str | Path, dst: str | Path) -> None:
    width, height, pixels = read_ppm(src)
    write_png(dst, width, height, pixels)

