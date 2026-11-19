"""Stdlib PNG rasterizer for the density sweep summary."""

import json

from tools.rasterize_routing import Canvas


def main():
    summary = json.load(open("artifacts/density_summary.json"))
    width, height = 900, 480
    x0, y0, pw, ph = 80, 60, 760, 320
    canvas = Canvas(width, height)
    max_density = max(g["mean_cell_density"] for g in summary)
    max_cross = max(g["mean_crossings"] for g in summary) or 1
    group_w = pw / len(summary)
    bar_w = group_w * 0.32
    base = y0 + ph
    canvas.line(x0, base, x0 + pw, base, (0, 0, 0), 1)
    canvas.line(x0, y0, x0, base, (0, 0, 0), 1)
    blue, red = (31, 119, 180), (214, 39, 40)
    for i, g in enumerate(summary):
        gx = int(x0 + i * group_w + group_w * 0.18)
        h1 = int(ph * g["mean_cell_density"] / max_density)
        h2 = int(ph * g["mean_crossings"] / max_cross)
        canvas.rect(gx, base - h1, int(gx + bar_w), base, blue)
        canvas.rect(int(gx + bar_w + 4), base - h2,
                    int(gx + 2 * bar_w + 4), base, red)
    canvas.save("artifacts/density_preview.png")
    print("wrote artifacts/density_preview.png")


if __name__ == "__main__":
    main()
