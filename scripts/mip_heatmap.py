"""High-frequency checker oblique-view mip heatmap and clamp verification."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proctree.imaging import heat_color, write_png
from proctree.texture import (
    build_checker,
    build_mip_chain,
    oblique_render,
    verify_clamp_no_sparkle,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")


def gray_png(values: list[list[float]]) -> list[list[tuple[int, int, int]]]:
    return [
        [tuple(int(round(v * 255)) for _ in range(3)) for v in row]
        for row in values
    ]


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    base = build_checker(size=512, tiles=64)
    chain = build_mip_chain(base)
    render = oblique_render(chain, out_size=256, slope=0.9)
    size = render["size"]

    write_png(os.path.join(OUT_DIR, "oblique_color.png"), gray_png(render["color"]))

    max_lod = max(value for row in render["lod"] for value in row)
    heat = [
        [heat_color(render["lod"][y][x], 0.0, max_lod) for x in range(size)]
        for y in range(size)
    ]
    write_png(os.path.join(OUT_DIR, "mip_lod_heatmap.png"), heat)

    mask = [
        [(220, 60, 60) if render["clamped"][y][x] else (40, 40, 40) for x in range(size)]
        for y in range(size)
    ]
    write_png(os.path.join(OUT_DIR, "clamp_mask.png"), mask)

    report = verify_clamp_no_sparkle(render)
    report.update(
        {
            "texture_size": 512,
            "checker_tiles": 64,
            "mip_levels": len(chain),
            "render_size": size,
            "oblique_slope": 0.9,
            "lod_min": round(min(v for row in render["lod"] for v in row), 4),
            "lod_max": round(max_lod, 4),
        }
    )
    with open(os.path.join(OUT_DIR, "mip_report.json"), "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
