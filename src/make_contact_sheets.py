"""Compose contact-sheet images for frequency sweep, views and tree sets."""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "artifacts")


def sheet(paths: list[str], labels: list[str], target: str,
          cell: int = 420, cols: int = 2) -> None:
    rows = (len(paths) + cols - 1) // cols
    pad, header = 14, 34
    canvas = Image.new("RGB",
                       (cols * cell + (cols + 1) * pad,
                        rows * (cell + header) + (rows + 1) * pad),
                       (12, 12, 18))
    draw = ImageDraw.Draw(canvas)
    for i, (path, label) in enumerate(zip(paths, labels)):
        img = Image.open(os.path.join(OUT, path)).resize((cell, cell))
        col, row = i % cols, i // cols
        x = pad + col * (cell + pad)
        y = pad + row * (cell + header + pad)
        draw.text((x + 4, y), label, fill=(230, 230, 240))
        canvas.paste(img, (x, y + header))
    canvas.save(os.path.join(OUT, target))
    print("wrote", target)


def main() -> None:
    freq_paths = [f"renders/galaxy_freq{f:.1f}.png" for f in (0.5, 1.0, 2.0, 4.0)]
    sheet(freq_paths, [f"noise frequency = {f}" for f in (0.5, 1.0, 2.0, 4.0)],
          "contact_frequency.png")

    view_paths = [f"renders/galaxy_view_{n}.png"
                  for n in ("top", "oblique", "edge", "side")]
    sheet(view_paths, ["top 88°", "oblique 32°", "edge 4°", "side 55°"],
          "contact_views.png")

    tree_paths = [f"renders/trees/tree_depth{d}.png" for d in range(1, 5)]
    sheet(tree_paths, [f"L-system depth {d}" for d in range(1, 5)],
          "contact_tree_depth.png", cell=380)

    rule_paths = [f"renders/trees/tree_rule_{n}.png"
                  for n in ("dense_bushy", "balanced", "tall_sparse")]
    sheet(rule_paths, ["dense bushy (28°, 4 branches)",
                       "balanced (22.5°, split rule)",
                       "tall sparse (16°, narrow rule)"],
          "contact_tree_rules.png", cell=380)


if __name__ == "__main__":
    main()
