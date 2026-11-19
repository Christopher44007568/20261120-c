#!/usr/bin/env python3
# Minimal dependency-free PPM(P3) -> PNG converter for snapshot inspection.
import struct, sys, zlib

def read_ppm(path):
    with open(path) as f:
        tok = f.read().split()
    assert tok[0] == 'P3'
    w, h, maxv = int(tok[1]), int(tok[2]), int(tok[3])
    vals = [int(x) for x in tok[4:]]
    return w, h, vals

def write_png(path, w, h, rgb):
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        row = rgb[y * w * 3:(y + 1) * w * 3]
        raw.extend(bytes(max(0, min(255, v)) for v in row))
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)

if __name__ == '__main__':
    for src in sys.argv[1:]:
        w, h, vals = read_ppm(src)
        write_png(src.replace('.ppm', '.png'), w, h, vals)
        print('wrote', src.replace('.ppm', '.png'))
