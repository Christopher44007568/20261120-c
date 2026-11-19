"""Perspective-correct depth interpolation: fixed-point vs floating-point."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FRAC_BITS = 16
SCALE = 1 << FRAC_BITS


@dataclass
class Vertex:
    x: float   # screen x
    y: float   # screen y
    z: float   # view-space depth
    w: float   # clip-space w


def _edge(a: Vertex, b: Vertex, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    return (px - a.x) * (b.y - a.y) - (py - a.y) * (b.x - a.x)


def rasterize_quad(verts: list[Vertex], width: int, height: int) -> dict:
    """Rasterize quad (two triangles) with perspective-correct depth."""
    z_float = np.full((height, width), np.nan)
    z_fixed = np.full((height, width), np.nan)
    covered = np.zeros((height, width), dtype=bool)
    tris = [(verts[0], verts[1], verts[2]), (verts[0], verts[2], verts[3])]
    for tri in tris:
        _raster_tri(tri, width, height, z_float, z_fixed, covered)
    return {"float": z_float, "fixed": z_fixed, "covered": covered}


def _raster_tri(tri, width, height, z_float, z_fixed, covered):
    xs = [v.x for v in tri]
    ys = [v.y for v in tri]
    x0 = max(0, int(np.floor(min(xs))))
    x1 = min(width - 1, int(np.ceil(max(xs))))
    y0 = max(0, int(np.floor(min(ys))))
    y1 = min(height - 1, int(np.ceil(max(ys))))
    if x1 < x0 or y1 < y0:
        return
    px, py = np.meshgrid(np.arange(x0, x1 + 1) + 0.5,
                         np.arange(y0, y1 + 1) + 0.5)
    a, b, c = tri
    area = _edge(a, b, c.x, c.y)
    if area == 0:
        return
    w0 = _edge(b, c, px, py) / area
    w1 = _edge(c, a, px, py) / area
    w2 = _edge(a, b, px, py) / area
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if not inside.any():
        return

    # Float64 perspective-correct interpolation.
    inv_w = np.array([1.0 / v.w for v in tri])
    z_over_w = np.array([v.z / v.w for v in tri])
    denom = w0 * inv_w[0] + w1 * inv_w[1] + w2 * inv_w[2]
    numer = w0 * z_over_w[0] + w1 * z_over_w[1] + w2 * z_over_w[2]
    zf = numer / denom

    # Fixed-point Q16.16 interpolation of the same quantities.
    iw_q = np.round(inv_w * SCALE).astype(np.int64)
    zw_q = np.round(z_over_w * SCALE).astype(np.int64)
    w0q = np.round(w0 * SCALE).astype(np.int64)
    w1q = np.round(w1 * SCALE).astype(np.int64)
    w2q = np.round(w2 * SCALE).astype(np.int64)
    denom_q = (w0q * iw_q[0] + w1q * iw_q[1] + w2q * iw_q[2]) >> FRAC_BITS
    numer_q = (w0q * zw_q[0] + w1q * zw_q[1] + w2q * zw_q[2]) >> FRAC_BITS
    with np.errstate(divide="ignore", invalid="ignore"):
        zq = np.where(denom_q != 0,
                      numer_q.astype(np.float64) / denom_q.astype(np.float64),
                      np.nan)

    region = (slice(y0, y1 + 1), slice(x0, x1 + 1))
    write = inside & ~covered[region]
    zf_full = z_float[region]
    zq_full = z_fixed[region]
    zf_full[write] = zf[write]
    zq_full[write] = zq[write]
    covered[region] |= inside
