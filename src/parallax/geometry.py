"""Small 3D ray/geometry helpers built on numpy."""

from __future__ import annotations

import numpy as np

EPS = 1.0e-9


def normalize(v: np.ndarray, axis: int = -1) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    n = np.where(n < EPS, 1.0, n)
    return v / n


def ray_box(p: np.ndarray, r: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    """Slab-method ray/AABB intersection.

    Returns ``(t_near, t_far)`` or ``None``. For an origin inside the box
    ``t_near < 0 < t_far`` and the first forward hit distance is ``t_far``.
    """
    p = np.asarray(p, dtype=float)
    r = np.asarray(r, dtype=float)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    t_near = -np.inf
    t_far = np.inf
    for i in range(3):
        if abs(r[i]) < EPS:
            if p[i] < lo[i] - EPS or p[i] > hi[i] + EPS:
                return None
            continue
        t1 = (lo[i] - p[i]) / r[i]
        t2 = (hi[i] - p[i]) / r[i]
        if t1 > t2:
            t1, t2 = t2, t1
        t_near = max(t_near, t1)
        t_far = min(t_far, t2)
        if t_near > t_far + EPS:
            return None
    return t_near, t_far


def box_exit(p: np.ndarray, r: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Distance to the first box face hit by a forward ray from inside."""
    hit = ray_box(p, r, lo, hi)
    if hit is None:
        raise ValueError("ray does not intersect the probe box")
    _, t_far = hit
    if t_far < -EPS:
        raise ValueError("ray points away from the box")
    return max(t_far, 0.0)


def ray_plane(p: np.ndarray, r: np.ndarray, normal: np.ndarray, d: float):
    """Intersect ray with plane ``normal . x = d``. Returns t or None."""
    denom = float(np.dot(normal, r))
    if abs(denom) < EPS:
        return None
    t = (d - float(np.dot(normal, p))) / denom
    return t if t >= -EPS else None


def angle_between(a: np.ndarray, b: np.ndarray) -> float:
    """Angle in radians between two vectors."""
    a = normalize(np.asarray(a, dtype=float))
    b = normalize(np.asarray(b, dtype=float))
    cos_t = float(np.clip(np.dot(a, b), -1.0, 1.0))
    return float(np.arccos(cos_t))


def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((np.asarray(x, dtype=float) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
