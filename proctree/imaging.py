"""Minimal PNG writer and heatmap color mapping (stdlib only)."""

from __future__ import annotations

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: str, pixels: list[list[tuple[int, int, int]]]) -> None:
    """Write an 8-bit RGB PNG.  ``pixels`` is row-major (rows top to bottom)."""
    height = len(pixels)
    width = len(pixels[0]) if height else 0
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b in row:
            raw.extend((r & 255, g & 255, b & 255))
    encoded = zlib.compress(bytes(raw), 9)
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(_chunk(b"IHDR", ihdr))
        handle.write(_chunk(b"IDAT", encoded))
        handle.write(_chunk(b"IEND", b""))


def heat_color(value: float, lo: float = 0.0, hi: float = 1.0) -> tuple[int, int, int]:
    """Map a scalar to a blue -> cyan -> green -> yellow -> red gradient."""
    if hi <= lo:
        t = 0.0
    else:
        t = min(1.0, max(0.0, (value - lo) / (hi - lo)))
    stops = [
        (0.0, (10, 20, 120)),
        (0.25, (0, 160, 220)),
        (0.5, (30, 180, 60)),
        (0.75, (240, 200, 40)),
        (1.0, (220, 40, 30)),
    ]
    for index in range(1, len(stops)):
        if t <= stops[index][0]:
            t0, c0 = stops[index - 1]
            t1, c1 = stops[index]
            local = (t - t0) / (t1 - t0)
            return tuple(
                round(c0[k] + (c1[k] - c0[k]) * local) for k in range(3)
            )
    return stops[-1][1]
