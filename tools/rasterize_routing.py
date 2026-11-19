"""Stdlib PNG rasterizer for the demo board (visual verification helper)."""

import struct
import zlib

from layout.router import Router
from layout.scenario import build_demo_board

COLORS = {
    "bg": (255, 255, 255), "panel0": (238, 244, 251),
    "panel1": (251, 243, 238), "obs": (68, 68, 68),
    "grid": (214, 214, 214), "via": (17, 17, 17),
    "net": [(31, 119, 180), (214, 39, 40), (44, 160, 44),
            (148, 103, 189), (255, 127, 14)],
}


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(COLORS["bg"]) * (w * h)

    def put(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = 3 * (y * self.w + x)
            self.px[i:i + 3] = bytes(color)

    def rect(self, x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(self.h, y1)):
            for x in range(max(0, x0), min(self.w, x1)):
                self.put(x, y, color)

    def line(self, x0, y0, x1, y1, color, thick=2):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for ox in range(-thick, thick + 1):
                for oy in range(-thick, thick + 1):
                    self.put(x0 + ox, y0 + oy, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disk(self, cx, cy, r, color):
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.put(x, y, color)

    def save(self, path):
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 3:
                                        (y + 1) * self.w * 3])
                       for y in range(self.h))
        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data)))
        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
               + chunk(b"IDAT", zlib.compress(raw, 9))
               + chunk(b"IEND", b""))
        with open(path, "wb") as fh:
            fh.write(png)


def main():
    board, pins = build_demo_board()
    result = Router(board, pins, rip_up_passes=3).route()
    cell, gap = 26, 30
    panel_w, panel_h = board.width * cell, board.height * cell
    width = board.layers * panel_w + (board.layers + 1) * gap
    height = panel_h + 2 * gap
    canvas = Canvas(width, height)
    net_color = {net: COLORS["net"][i % len(COLORS["net"])]
                 for i, net in enumerate(sorted(result.nets))}
    for layer in range(board.layers):
        ox = gap + layer * (panel_w + gap)
        canvas.rect(ox, gap, ox + panel_w, gap + panel_h,
                    COLORS[f"panel{layer}"])
        for gx in range(board.width + 1):
            canvas.line(ox + gx * cell, gap, ox + gx * cell,
                        gap + panel_h, COLORS["grid"], 1)
        for gy in range(board.height + 1):
            canvas.line(ox, gap + gy * cell, ox + panel_w,
                        gap + gy * cell, COLORS["grid"], 1)
        for obs in board.obstacles:
            if obs.layer == layer:
                canvas.rect(ox + obs.x0 * cell, gap + obs.y0 * cell,
                            ox + obs.x1 * cell, gap + obs.y1 * cell,
                            COLORS["obs"])
        for net, path in result.nets.items():
            pts = [(ox + (x + 0.5) * cell, gap + (y + 0.5) * cell)
                   for ly, (x, y) in path if ly == layer]
            for (a, b), (c, d) in zip(pts, pts[1:]):
                canvas.line(int(a), int(b), int(c), int(d),
                            net_color[net], 2)
        for _, via_cell, lo, hi in result.vias:
            if lo <= layer <= hi:
                cx = ox + (via_cell[0] + 0.5) * cell
                cy = gap + (via_cell[1] + 0.5) * cell
                canvas.disk(int(cx), int(cy), 7, (255, 255, 255))
                canvas.disk(int(cx), int(cy), 3, COLORS["via"])
        for pin in pins:
            if pin.layer == layer:
                cx = int(ox + (pin.x + 0.5) * cell)
                cy = int(gap + (pin.y + 0.5) * cell)
                canvas.disk(cx, cy, 5, net_color[pin.net])
    canvas.save("artifacts/routing_preview.png")
    print("wrote artifacts/routing_preview.png",
          f"crossings={result.crossings} vias={result.via_count}")


if __name__ == "__main__":
    main()
