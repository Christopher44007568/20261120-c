"""Procedural density fields: a turbulent smoke plume and a layered cloud/fog bank."""

import numpy as np


def _value_noise(grid, seed):
    """Smooth trilinearly interpolated random values on a (nx,ny,nz) grid."""
    rng = np.random.default_rng(seed)
    coarse_shape = tuple(max(2, s // 8 + 1) for s in grid)
    coarse = rng.random(coarse_shape)
    idx = [np.linspace(0, coarse_shape[k] - 1.001, grid[k]) for k in range(3)]
    x, y, z = np.meshgrid(*idx, indexing="ij")
    x0, y0, z0 = np.floor(x).astype(int), np.floor(y).astype(int), np.floor(z).astype(int)
    fx, fy, fz = x - x0, y - y0, z - z0
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)
    sz = fz * fz * (3 - 2 * fz)

    c000 = coarse[x0, y0, z0]
    c100 = coarse[np.minimum(x0 + 1, coarse_shape[0] - 1), y0, z0]
    c010 = coarse[x0, np.minimum(y0 + 1, coarse_shape[1] - 1), z0]
    c110 = coarse[np.minimum(x0 + 1, coarse_shape[0] - 1),
                  np.minimum(y0 + 1, coarse_shape[1] - 1), z0]
    c001 = coarse[x0, y0, np.minimum(z0 + 1, coarse_shape[2] - 1)]
    c101 = coarse[np.minimum(x0 + 1, coarse_shape[0] - 1), y0,
                  np.minimum(z0 + 1, coarse_shape[2] - 1)]
    c011 = coarse[x0, np.minimum(y0 + 1, coarse_shape[1] - 1),
                  np.minimum(z0 + 1, coarse_shape[2] - 1)]
    c111 = coarse[np.minimum(x0 + 1, coarse_shape[0] - 1),
                  np.minimum(y0 + 1, coarse_shape[1] - 1),
                  np.minimum(z0 + 1, coarse_shape[2] - 1)]
    c00 = c000 * (1 - sx) + c100 * sx
    c10 = c010 * (1 - sx) + c110 * sx
    c01 = c001 * (1 - sx) + c101 * sx
    c11 = c011 * (1 - sx) + c111 * sx
    c0 = c00 * (1 - sy) + c10 * sy
    c1 = c01 * (1 - sy) + c11 * sy
    return c0 * (1 - sz) + c1 * sz


SMOKE_BOUNDS = np.array([[-1.5, -1.0, 0.0], [1.5, 1.0, 3.0]])
CLOUD_BOUNDS = np.array([[-2.0, -1.0, 0.2], [2.0, 1.0, 2.2]])


def _cell_centers(bounds, grid):
    lo, hi = bounds
    axes = [np.linspace(lo[k], hi[k], grid[k]) for k in range(3)]
    return np.meshgrid(*axes, indexing="ij")


def smoke_plume(grid=(48, 48, 96), seed=7):
    """Rising plume: narrow turbulent base that widens and meanders with height.

    The plume rises along the y axis (visible as a vertical column in the
    top-down camera view) with a meandering center line and turbulence.
    """
    x, y, z = _cell_centers(SMOKE_BOUNDS, grid)
    lo, hi = SMOKE_BOUNDS
    h = (y - lo[1]) / (hi[1] - lo[1])
    radius_x = 0.16 + 0.30 * h
    radius_z = 0.16 + 0.22 * h
    meander_x = 0.22 * np.sin(2.2 * np.pi * h)
    meander_z = 0.12 * np.sin(3.1 * np.pi * h + 1.0)
    radial = np.sqrt(((x - meander_x) / radius_x) ** 2 +
                     ((z - meander_z) / radius_z) ** 2)
    envelope = np.exp(-0.5 * radial ** 2) * (0.55 + 0.45 * h)
    turbulence = 0.45 * _value_noise(grid, seed) + \
        0.25 * _value_noise(grid, seed + 100)
    density = envelope * (0.45 + turbulence)
    density *= radial < 2.0
    density = np.maximum(density, 0.0)
    return density / density.max()


def cloud_fog(grid=(72, 48, 48), seed=21):
    """Layered cloud/fog bank: lumpy octave noise masked by a vertical profile."""
    x, y, z = _cell_centers(CLOUD_BOUNDS, grid)
    lo, hi = CLOUD_BOUNDS
    v = (z - lo[2]) / (hi[2] - lo[2])
    vertical = np.sin(np.pi * np.clip(v, 0, 1)) ** 1.5
    n1 = _value_noise(grid, seed)
    n2 = _value_noise(grid, seed + 5)
    n3 = _value_noise(grid, seed + 9)
    noise = 0.55 * n1 + 0.3 * n2 + 0.15 * n3
    lump_centers = [(-1.1, -0.1, 1.1), (0.4, 0.2, 1.35), (1.3, -0.3, 0.9)]
    blobs = np.zeros_like(x)
    for cx, cy, cz in lump_centers:
        blobs += np.exp(-(((x - cx) / 0.85) ** 2 +
                          ((y - cy) / 0.7) ** 2 +
                          ((z - cz) / 0.7) ** 2))
    density = vertical * np.clip(noise - 0.15, 0, None) * (0.6 + 1.4 * blobs)
    density = np.maximum(density, 0.0)
    return density / density.max()
