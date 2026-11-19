"""Synthetic point clouds with ground-truth normals and Gaussian noise.

Every generator returns ``(points, normals)`` as ``numpy.ndarray``:
    points  : (N, 3) float64 samples on the underlying surface
    normals : (N, 3) float64 unit analytic normals at the *clean* samples

Noise is added along an isotropic 3D Gaussian, which simulates scanner
measurement error. The returned normals stay attached to the clean surface
positions so they can serve as ground truth later.
"""

from __future__ import annotations

import numpy as np


def _as_array(points: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    return points, normals


def sample_sphere(
    n_points: int = 6000,
    radius: float = 1.0,
    noise_sigma: float = 0.0,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a sphere using the uniform (area-preserving) direction method."""
    rng = np.random.default_rng() if rng is None else rng
    z = rng.uniform(-1.0, 1.0, n_points)
    theta = rng.uniform(0.0, 2.0 * np.pi, n_points)
    radial = np.sqrt(1.0 - z**2)
    unit = np.column_stack(
        (radial * np.cos(theta), radial * np.sin(theta), z)
    )
    points = radius * unit
    normals = unit.copy()
    if noise_sigma > 0.0:
        points = points + rng.normal(0.0, noise_sigma, size=points.shape)
    return _as_array(points, normals)


def sample_torus(
    n_points: int = 8000,
    major_radius: float = 1.0,
    minor_radius: float = 0.35,
    noise_sigma: float = 0.0,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a torus of revolution around the z axis."""
    rng = np.random.default_rng() if rng is None else rng
    u = rng.uniform(0.0, 2.0 * np.pi, n_points)
    v = rng.uniform(0.0, 2.0 * np.pi, n_points)
    cos_v, sin_v = np.cos(v), np.sin(v)
    ring = major_radius + minor_radius * cos_v
    points = np.column_stack(
        (ring * np.cos(u), ring * np.sin(u), minor_radius * sin_v)
    )
    # Outward normal of a torus points away from the tube centerline.
    normals = np.column_stack(
        (cos_v * np.cos(u), cos_v * np.sin(u), sin_v)
    )
    if noise_sigma > 0.0:
        points = points + rng.normal(0.0, noise_sigma, size=points.shape)
    return _as_array(points, normals)


def ground_truth_sphere_sdf(
    points: np.ndarray, radius: float = 1.0
) -> np.ndarray:
    """Signed distance to a centered sphere (positive outside)."""
    points = np.asarray(points, dtype=np.float64)
    return np.linalg.norm(points, axis=1) - radius
