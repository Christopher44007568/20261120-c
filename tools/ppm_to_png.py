#!/usr/bin/env python3
"""Convert binary P6 PPM images to PNG using only the Python standard library."""

from __future__ import annotations

import pathlib
import struct
import sys
import zlib


def read_ppm(path: pathlib.Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"P6"):
        raise ValueError(f"{path}: expected a binary P6 PPM")
    tokens: list[bytes] = []
    index = 2
    while len(tokens) < 3:
        while index < len(data) and data[index] in b" \t\r\n":
            index += 1
        if index < len(data) and data[index] == ord("#"):
            index = data.find(b"\n", index) + 1
            continue
        end = index
        while end < len(data) and data[end] not in b" \t\r\n":
            end += 1
        tokens.append(data[index:end])
        index = end
    width, height, maximum = map(int, tokens)
    if maximum != 255:
        raise ValueError(f"{path}: only 8-bit PPM files are supported")
    while index < len(data) and data[index] in b" \t\r\n":
        index += 1
    pixels = data[index:]
    if len(pixels) != width * height * 3:
        raise ValueError(f"{path}: truncated pixel data")
    return width, height, pixels


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: pathlib.Path, width: int, height: int, pixels: bytes) -> None:
    stride = width * 3
    scanlines = b"".join(
        b"\x00" + pixels[y * stride : (y + 1) * stride] for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(scanlines, 9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def main() -> int:
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} INPUT.ppm OUTPUT.png", file=sys.stderr)
        return 2
    source = pathlib.Path(sys.argv[1])
    destination = pathlib.Path(sys.argv[2])
    width, height, pixels = read_ppm(source)
    write_png(destination, width, height, pixels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

