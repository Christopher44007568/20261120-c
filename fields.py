"""Scalar fields with sharp features (edges/corners) and analytic helpers."""
import numpy as np


def box_sdf(p, half=0.7):
    """Exact SDF of an axis-aligned box centred at origin."""
    p = np.asarray(p, dtype=float)
    q = np.abs(p) - half
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    inside = np.minimum(np.max(q, axis=-1), 0.0)
    return outside + inside


def sphere_sdf(p, radius=1.0):
    p = np.asarray(p, dtype=float)
    return np.linalg.norm(p, axis=-1) - radius


def make_field(name):
    """Return f(p) for batched points p of shape (..., 3)."""
    if name == "box":
        return lambda p: box_sdf(p, 0.7)
    if name == "box_sphere_isect":
        # Intersection of a sphere and a box: sharp edges where they meet.
        return lambda p: np.maximum(sphere_sdf(p, 1.0), box_sdf(p, 0.72))
    if name == "box_minus_cyl":
        # Box with a cylindrical hole along z: sharp concave edges.
        def f(p):
            p = np.asarray(p, dtype=float)
            cyl = np.linalg.norm(p[..., :2], axis=-1) - 0.35
            return np.maximum(box_sdf(p, 0.7), -cyl)
        return f
    raise ValueError(name)


def gradient(f, p, eps=1e-5):
    """Central-difference gradient of f at points p (..., 3)."""
    p = np.asarray(p, dtype=float)
    g = np.zeros_like(p)
    for axis in range(3):
        d = np.zeros(3)
        d[axis] = eps
        g[..., axis] = (f(p + d) - f(p - d)) / (2.0 * eps)
    return g


def box_edge_samples(half=0.7, n_per_edge=200):
    """Points lying exactly on the 12 sharp edges of a box."""
    pts = []
    t = np.linspace(-half, half, n_per_edge)
    for fixed_axis in range(3):
        free = [a for a in range(3) if a != fixed_axis]
        for s0 in (-half, half):
            for s1 in (-half, half):
                p = np.zeros((n_per_edge, 3))
                p[:, fixed_axis] = t
                p[:, free[0]] = s0
                p[:, free[1]] = s1
                pts.append(p)
    return np.concatenate(pts, axis=0)


def _circle_samples(axis, sign, offset, radius, n=600):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    p = np.zeros((n, 3))
    free = [a for a in range(3) if a != axis]
    p[:, axis] = sign * offset
    p[:, free[0]] = radius * np.cos(t)
    p[:, free[1]] = radius * np.sin(t)
    return p


def edge_samples(name, n=200):
    """Exact samples on the sharp edges of each test field."""
    if name == "box":
        return box_edge_samples(0.7, n)
    if name == "box_sphere_isect":
        half = 0.72
        radius = np.sqrt(1.0 - half ** 2)
        return np.concatenate(
            [_circle_samples(a, s, half, radius) for a in range(3) for s in (-1, 1)]
        )
    if name == "box_minus_cyl":
        return np.concatenate([_circle_samples(2, s, 0.7, 0.35) for s in (-1, 1)])
    raise ValueError(name)
