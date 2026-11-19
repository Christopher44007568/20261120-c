"""Seamless spherical noise: 3D gradient noise sampled on the unit sphere.

The noise field is a pure function f(p) of the 3D position p on the sphere
surface, so it is seamless by construction: the longitude wrap (lon 0 / 360)
and both poles map to identical 3D points and therefore identical values.
No blending, mirroring or tiling is ever needed.
"""
import numpy as np

_GRADIENTS = np.array([
    [1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
    [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
    [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
    [1, 1, 0], [0, -1, 1], [-1, 1, 0], [0, -1, -1],
], dtype=np.float64) / np.sqrt(2.0)


def _hash_u32(values, seed):
    """Vectorized 32-bit integer hash (lowbias32)."""
    x = (values.astype(np.uint32) ^ np.uint32(seed & 0xFFFFFFFF)).copy()
    x ^= x >> np.uint32(16)
    x *= np.uint32(0x7FEB352D)
    x ^= x >> np.uint32(15)
    x *= np.uint32(0x846CA68B)
    x ^= x >> np.uint32(16)
    return x


def _corner_hash(ix, iy, iz, seed):
    h = _hash_u32(ix, seed ^ 0x8DA6B343)
    h = _hash_u32(h ^ iy.astype(np.uint32), seed ^ 0xD8163841)
    h = _hash_u32(h ^ iz.astype(np.uint32), seed ^ 0xCB1AB31F)
    return h


def gradient_noise_3d(points, seed=0):
    """Perlin-style gradient noise. points: (..., 3) -> (...) in ~[-1, 1]."""
    points = np.asarray(points, dtype=np.float64)
    base = np.floor(points)
    i0 = base.astype(np.int64)
    frac = points - base
    u = frac * frac * frac * (frac * (frac * 6.0 - 15.0) + 10.0)

    acc = np.zeros(points.shape[:-1], dtype=np.float64)
    for corner in range(8):
        cx, cy, cz = (corner >> 2) & 1, (corner >> 1) & 1, corner & 1
        h = _corner_hash(i0[..., 0] + cx, i0[..., 1] + cy, i0[..., 2] + cz, seed)
        grad = _GRADIENTS[(h & np.uint32(15)).astype(np.intp)]
        d = frac - np.array([cx, cy, cz], dtype=np.float64)
        dot = (d * grad).sum(axis=-1)
        wx = u[..., 0] if cx else 1.0 - u[..., 0]
        wy = u[..., 1] if cy else 1.0 - u[..., 1]
        wz = u[..., 2] if cz else 1.0 - u[..., 2]
        acc += dot * wx * wy * wz
    return acc * 2.0


def fbm_3d(points, octaves=6, lacunarity=2.0, gain=0.5, seed=0):
    """Fractal Brownian motion over 3D gradient noise."""
    total = np.zeros(points.shape[:-1], dtype=np.float64)
    amplitude, amplitude_sum = 1.0, 0.0
    p = points
    for octave in range(octaves):
        total += amplitude * gradient_noise_3d(p, seed + octave * 101)
        amplitude_sum += amplitude
        amplitude *= gain
        p = p * lacunarity
    return total / amplitude_sum


def ridged_fbm_3d(points, octaves=5, lacunarity=2.0, gain=0.5, seed=0):
    """Ridged multifractal: sharp mountain crests. Output in [0, 1]."""
    total = np.zeros(points.shape[:-1], dtype=np.float64)
    amplitude, amplitude_sum = 1.0, 0.0
    p = points
    for octave in range(octaves):
        n = gradient_noise_3d(p, seed + 7000 + octave * 131)
        ridge = (1.0 - np.abs(n)) ** 2
        total += amplitude * ridge
        amplitude_sum += amplitude
        amplitude *= gain
        p = p * lacunarity
    return total / amplitude_sum


def sphere_directions(lon_deg, lat_deg):
    """(lon, lat) degrees -> unit vectors (..., 3). Seamless by construction."""
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    cos_lat = np.cos(lat)
    return np.stack([cos_lat * np.cos(lon),
                     np.sin(lat),
                     cos_lat * np.sin(lon)], axis=-1)
