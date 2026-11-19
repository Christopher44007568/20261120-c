"""Tiny stdlib rasterizer for the line/ellipse/rect SVG emitted by proctree.

Not a general SVG implementation: only the primitives this project emits.
Used solely to produce PNG snapshots for visual inspection.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proctree.imaging import write_png


def _attrs(tag: str) -> dict[str, str]:
    return dict(re.findall(r'([\w:.-]+)="([^"]*)"', tag))


def rasterize(svg_path: str, png_path: str, scale: float = 2.0) -> None:
    text = open(svg_path).read()
    width = int(float(re.search(r'width="([\d.]+)"', text).group(1)) * scale)
    height = int(float(re.search(r'height="([\d.]+)"', text).group(1)) * scale)
    canvas = [[(255, 255, 255) for _ in range(width)] for _ in range(height)]

    def put(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            canvas[y][x] = color

    def fill(cx: float, cy: float, rx: float, ry: float,
             color: tuple[int, int, int]) -> None:
        for y in range(int(cy - ry), int(cy + ry) + 1):
            for x in range(int(cx - rx), int(cx + rx) + 1):
                if rx and ry and ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                    put(x, y, color)

    def line(x0: float, y0: float, x1: float, y1: float,
             thick: float, color: tuple[int, int, int]) -> None:
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        radius = thick / 2.0
        for i in range(steps + 1):
            t = i / max(steps, 1)
            cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            r = int(radius) + 1
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if dx * dx + dy * dy <= radius * radius:
                        put(int(cx) + dx, int(cy) + dy, color)

    def draw_tag(tag: str, offset_x: float) -> None:
        attrs = _attrs(tag)
        if tag.startswith("<rect"):
            for y in range(height):
                for x in range(width):
                    canvas[y][x] = (255, 255, 255)
        elif tag.startswith("<line"):
            if "stroke-width" not in attrs:
                return
            line(
                (float(attrs["x1"]) + offset_x) * scale,
                float(attrs["y1"]) * scale,
                (float(attrs["x2"]) + offset_x) * scale,
                float(attrs["y2"]) * scale,
                float(attrs["stroke-width"]) * scale,
                (107, 74, 43),
            )
        elif tag.startswith("<ellipse"):
            fill(
                (float(attrs["cx"]) + offset_x) * scale,
                float(attrs["cy"]) * scale,
                float(attrs["rx"]) * scale,
                float(attrs["ry"]) * scale,
                (63, 143, 63),
            )

    groups = re.findall(
        r'<g transform="translate\(([\d.]+),0\)">(.*?)</g>', text, flags=re.S
    )
    if groups:
        for offset, body in groups:
            for tag in re.findall(r"<(?:rect|line|ellipse)\b[^>]*/?>", body):
                draw_tag(tag, float(offset))
    else:
        for tag in re.findall(r"<(?:rect|line|ellipse)\b[^>]*/?>", text):
            draw_tag(tag, 0.0)

    write_png(png_path, canvas)


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = [
        ("artifacts/spreading_bush_d5.svg", "artifacts/snapshot_bush_d5.png"),
        ("artifacts/upright_tree_d4.svg", "artifacts/snapshot_tree_d4.png"),
        ("artifacts/spreading_bush_comparison.svg",
         "artifacts/snapshot_bush_comparison.png"),
    ]
    for src, dst in targets:
        rasterize(os.path.join(base, src), os.path.join(base, dst))
        print("wrote", dst)
