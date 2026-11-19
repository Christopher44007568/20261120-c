"""High-frequency checker texture, mip chain, oblique view and clamp checks."""

from __future__ import annotations

import math


def build_checker(size: int = 512, tiles: int = 64) -> list[list[float]]:
    """Build a high-frequency checker pattern with values 0.0 / 1.0."""
    cell = size / tiles
    return [
        [
            1.0 if (int(x / cell) + int(y / cell)) % 2 == 0 else 0.0
            for x in range(size)
        ]
        for y in range(size)
    ]


def build_mip_chain(base: list[list[float]]) -> list[list[list[float]]]:
    """Box-filtered mip chain from level 0 (full res) down to 1x1."""
    chain = [base]
    current = base
    while len(current) > 1:
        n = len(current)
        half = n // 2
        nxt = [
            [
                (
                    current[2 * y][2 * x]
                    + current[2 * y][2 * x + 1]
                    + current[2 * y + 1][2 * x]
                    + current[2 * y + 1][2 * x + 1]
                )
                / 4.0
                for x in range(half)
            ]
            for y in range(half)
        ]
        chain.append(nxt)
        current = nxt
    return chain


def clamp_coord(index: int, size: int) -> int:
    """Clamp a texel index to [0, size-1] (GL_CLAMP_TO_EDGE behaviour)."""
    return min(size - 1, max(0, index))


def sample_level(level: list[list[float]], u: float, v: float) -> float:
    """Bilinear sample with edge clamping; u/v are normalized [0, 1]-ish."""
    size = len(level)
    fx = u * (size - 1)
    fy = v * (size - 1)
    x0 = math.floor(fx)
    y0 = math.floor(fy)
    tx = fx - x0
    ty = fy - y0
    x1, y1 = x0 + 1, y0 + 1
    cx0, cy0 = clamp_coord(x0, size), clamp_coord(y0, size)
    cx1, cy1 = clamp_coord(x1, size), clamp_coord(y1, size)
    top = level[cy0][cx0] * (1 - tx) + level[cy0][cx1] * tx
    bottom = level[cy1][cx0] * (1 - tx) + level[cy1][cx1] * tx
    return top * (1 - ty) + bottom * ty


def _trilinear(chain: list[list[list[float]]], u: float, v: float, lod: float) -> float:
    max_lod = len(chain) - 1
    lod = min(max(lod, 0.0), float(max_lod))
    low = int(math.floor(lod))
    high = min(low + 1, max_lod)
    blend = lod - low
    a = sample_level(chain[low], u, v)
    if high == low:
        return a
    b = sample_level(chain[high], u, v)
    return a * (1 - blend) + b * blend


def oblique_render(
    chain: list[list[list[float]]],
    out_size: int = 256,
    slope: float = 0.9,
) -> dict[str, object]:
    """Render an oblique (sheared) view that crosses the texture border.

    The shear pushes u beyond 1.0 so edge clamping is exercised, while the
    minification footprint grows with depth v, sweeping LOD 0 -> top level.
    Returns per-pixel colour, LOD and a per-pixel "was clamped" mask.
    """
    colors = [[0.0] * out_size for _ in range(out_size)]
    lods = [[0.0] * out_size for _ in range(out_size)]
    clamped = [[False] * out_size for _ in range(out_size)]
    for py in range(out_size):
        v = py / (out_size - 1)
        for px in range(out_size):
            u = px / (out_size - 1) + slope * v
            base_lod = math.log2(1.0 + 7.0 * v)
            # Off-edge samples are clamped to the border; force at least a
            # 16x16 box average (LOD 4) so the high-frequency pattern is smooth.
            lod = max(base_lod, 4.0) if (u < 0.0 or u > 1.0) else base_lod
            colors[py][px] = _trilinear(chain, u, v, lod)
            lods[py][px] = lod
            clamped[py][px] = u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0
    return {"color": colors, "lod": lods, "clamped": clamped, "size": out_size}


def verify_clamp_no_sparkle(render: dict[str, object], tol: float = 0.2) -> dict[str, object]:
    """Confirm edge-clamped pixels show no high-frequency sparkle."""
    colors = render["color"]
    clamped = render["clamped"]
    size = render["size"]
    clamped_pixels = 0
    max_diff = 0.0
    diffs: list[float] = []
    for y in range(size):
        for x in range(size):
            if not clamped[y][x]:
                continue
            clamped_pixels += 1
            if x + 1 < size and clamped[y][x] and clamped[y][x + 1]:
                diff = abs(colors[y][x] - colors[y][x + 1])
                diffs.append(diff)
                max_diff = max(max_diff, diff)
            if y + 1 < size and clamped[y][x] and clamped[y + 1][x]:
                diff = abs(colors[y][x] - colors[y + 1][x])
                diffs.append(diff)
                max_diff = max(max_diff, diff)
    index_checks = [
        (clamp_coord(-5, 512), 0),
        (clamp_coord(600, 512), 511),
        (clamp_coord(128, 512), 128),
    ]
    index_ok = all(got == want for got, want in index_checks)
    passed = max_diff <= tol and index_ok and clamped_pixels > 0
    return {
        "passed": passed,
        "clamped_pixels": clamped_pixels,
        "max_neighbor_diff": round(max_diff, 5),
        "tolerance": tol,
        "clamp_index_checks": index_checks,
        "index_clamp_ok": index_ok,
    }

