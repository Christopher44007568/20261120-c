"""Minimal PNG writer (stdlib only)."""
import struct
import zlib


def write_png(path, width, height, pixels):
    """pixels: list of rows, each row a list of (r, g, b) tuples 0-255."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b in row:
            raw += bytes((r, g, b))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(chunk(b"IEND", b""))


def tonemap(v, exposure=1.0):
    """Simple Reinhard tonemap + gamma, v in [0, inf)."""
    x = 1.0 - pow(2.718281828459045, -exposure * max(v, 0.0))
    return int(round(255.0 * (x ** (1.0 / 2.2))))
