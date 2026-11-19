"""Deterministic 3D value noise with fBm support (seeded, no scipy)."""
from __future__ import annotations

import numpy as np


def _hash3(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, seed: int) -> np.ndarray:
    h = ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263
    h = h + iz.astype(np.int64) * 2147483647 + np.int64(seed) * 1442695040
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFFFF).astype(np.float64) / 4294967295.0


def _smooth(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def value_noise3(x: np.ndarray, y: np.ndarray, z: np.ndarray, seed: int = 0) -> np.ndarray:
    """Trilinearly interpolated value noise, output roughly in [0, 1]."""
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    z0 = np.floor(z).astype(np.int64)
    fx = _smooth(x - x0)
    fy = _smooth(y - y0)
    fz = _smooth(z - z0)

    c000 = _hash3(x0, y0, z0, seed)
    c100 = _hash3(x0 + 1, y0, z0, seed)
    c010 = _hash3(x0, y0 + 1, z0, seed)
    c110 = _hash3(x0 + 1, y0 + 1, z0, seed)
    c001 = _hash3(x0, y0, z0 + 1, seed)
    c101 = _hash3(x0 + 1, y0, z0 + 1, seed)
    c011 = _hash3(x0, y0 + 1, z0 + 1, seed)
    c111 = _hash3(x0 + 1, y0 + 1, z0 + 1, seed)

    x00 = c000 + (c100 - c000) * fx
    x10 = c010 + (c110 - c010) * fx
    x01 = c001 + (c101 - c001) * fx
    x11 = c011 + (c111 - c011) * fx
    y0v = x00 + (x10 - x00) * fy
    y1v = x01 + (x11 - x01) * fy
    return y0v + (y1v - y0v) * fz


def fbm3(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    octaves: int = 4,
    frequency: float = 1.0,
    lacunarity: float = 2.0,
    gain: float = 0.5,
    seed: int = 0,
) -> np.ndarray:
    """Fractal Brownian motion. Result normalised to roughly [0, 1]."""
    total = np.zeros_like(x, dtype=np.float64)
    amp = 1.0
    freq = float(frequency)
    norm = 0.0
    for octave in range(octaves):
        total += amp * value_noise3(x * freq, y * freq, z * freq, seed + octave * 101)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm
