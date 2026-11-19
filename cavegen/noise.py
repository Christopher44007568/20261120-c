"""3D value noise with fBm, used as the cave density field."""
from __future__ import annotations

import numpy as np


def _trilinear_resample(coarse: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """Resample a coarse grid to `shape` with trilinear interpolation."""
    nx, ny, nz = shape
    cx, cy, cz = coarse.shape
    gx = np.linspace(0.0, cx - 1.0, nx)
    gy = np.linspace(0.0, cy - 1.0, ny)
    gz = np.linspace(0.0, cz - 1.0, nz)

    x0 = np.clip(np.floor(gx).astype(int), 0, cx - 2)
    y0 = np.clip(np.floor(gy).astype(int), 0, cy - 2)
    z0 = np.clip(np.floor(gz).astype(int), 0, cz - 2)
    tx = (gx - x0)[:, None, None]
    ty = (gy - y0)[None, :, None]
    tz = (gz - z0)[None, None, :]

    c = coarse
    c000 = c[np.ix_(x0, y0, z0)]
    c100 = c[np.ix_(x0 + 1, y0, z0)]
    c010 = c[np.ix_(x0, y0 + 1, z0)]
    c110 = c[np.ix_(x0 + 1, y0 + 1, z0)]
    c001 = c[np.ix_(x0, y0, z0 + 1)]
    c101 = c[np.ix_(x0 + 1, y0, z0 + 1)]
    c011 = c[np.ix_(x0, y0 + 1, z0 + 1)]
    c111 = c[np.ix_(x0 + 1, y0 + 1, z0 + 1)]

    c00 = c000 * (1 - tx) + c100 * tx
    c10 = c010 * (1 - tx) + c110 * tx
    c01 = c001 * (1 - tx) + c101 * tx
    c11 = c011 * (1 - tx) + c111 * tx
    c0 = c00 * (1 - ty) + c10 * ty
    c1 = c01 * (1 - ty) + c11 * ty
    return c0 * (1 - tz) + c1 * tz


def fbm_noise_3d(
    shape: tuple[int, int, int],
    frequency: float,
    seed: int = 0,
    octaves: int = 3,
    persistence: float = 0.5,
) -> np.ndarray:
    """Fractal value noise in [0, 1].

    `frequency` is the number of noise cells spanning the grid at octave 0.
    """
    rng = np.random.default_rng(seed)
    field = np.zeros(shape, dtype=np.float64)
    amplitude = 1.0
    total = 0.0
    freq = max(2, int(round(frequency)) + 1)
    for _ in range(octaves):
        coarse = rng.random((freq + 1, freq + 1, freq + 1))
        field += amplitude * _trilinear_resample(coarse, shape)
        total += amplitude
        amplitude *= persistence
        freq *= 2
    field /= total
    return field
