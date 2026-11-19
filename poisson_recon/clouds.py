"""Synthetic shapes, noisy sampling, normals, mesh metrics, and PLY output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class Shape:
    name: str
    radius: float
    radius_fn: Callable[[np.ndarray], np.ndarray]

    def points_from_directions(self, directions: np.ndarray) -> np.ndarray:
        dirs = directions / np.linalg.norm(directions, axis=1, keepdims=True)
        return dirs * self.radius_fn(dirs)[:, None]


def sphere_shape(radius: float = 0.5) -> Shape:
    return Shape("sphere", radius, lambda dirs: np.full(len(dirs), radius))


def bumpy_sphere_shape(radius: float = 0.5, bump: float = 0.06) -> Shape:
    def radius_fn(dirs: np.ndarray) -> np.ndarray:
        theta = np.arccos(np.clip(dirs[:, 2], -1.0, 1.0))
        phi = np.arctan2(dirs[:, 1], dirs[:, 0])
        return radius * (1.0 + bump * np.sin(3.0 * theta) * np.cos(4.0 * phi))

    return Shape("bumpy_sphere", radius, radius_fn)


def fibonacci_directions(count: int) -> np.ndarray:
    index = np.arange(count, dtype=float) + 0.5
    phi = np.arccos(1.0 - 2.0 * index / count)
    theta = np.pi * (1.0 + 5.0**0.5) * index
    return np.column_stack(
        [np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)]
    )


def sample_shape(
    shape: Shape, count: int, rng: np.random.Generator, noise_sigma: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    directions = fibonacci_directions(count)
    clean = shape.points_from_directions(directions)
    points = clean + rng.normal(0.0, noise_sigma, clean.shape)
    return points, clean


def estimate_normals_pca(
    points: np.ndarray,
    neighbors: int = 30,
    center: np.ndarray | None = None,
) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    tree = cKDTree(pts)
    k = min(int(neighbors), len(pts))
    _, indices = tree.query(pts, k=k)
    normals = np.empty_like(pts)
    for index, neighborhood in enumerate(indices):
        local = pts[neighborhood] - pts[neighborhood].mean(axis=0)
        covariance = local.T @ local / max(1, len(neighborhood) - 1)
        _, vectors = np.linalg.eigh(covariance)
        normals[index] = vectors[:, 0]
    reference = pts - (np.mean(pts, axis=0) if center is None else center)
    flip = np.einsum("ij,ij->i", normals, reference) < 0.0
    normals[flip] *= -1.0
    lengths = np.linalg.norm(normals, axis=1)
    return normals / np.maximum(lengths[:, None], 1e-12)


def radial_error_metrics(
    points: np.ndarray, shape: Shape
) -> dict[str, float]:
    pts = np.asarray(points, dtype=float)
    radii = np.linalg.norm(pts, axis=1)
    valid = np.isfinite(radii) & (radii > 0.25 * shape.radius) & (radii < 1.75 * shape.radius)
    if np.count_nonzero(valid) < 10:
        return {
            "count": int(np.count_nonzero(valid)),
            "radial_mean_mm": float("nan"),
            "radial_rmse_mm": float("nan"),
            "radial_p95_mm": float("nan"),
            "radial_max_mm": float("nan"),
        }
    selected = pts[valid]
    selected_radii = radii[valid]
    expected = shape.radius_fn(selected / selected_radii[:, None])
    error = selected_radii - expected
    absolute = np.abs(error)
    return {
        "count": int(np.count_nonzero(valid)),
        "radial_mean_mm": float(absolute.mean() * 1000.0),
        "radial_rmse_mm": float(np.sqrt(np.mean(error**2)) * 1000.0),
        "radial_p95_mm": float(np.percentile(absolute, 95) * 1000.0),
        "radial_max_mm": float(absolute.max() * 1000.0),
    }


def sample_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    count: int,
    rng: np.random.Generator,
) -> np.ndarray:
    verts = np.asarray(vertices, dtype=float)
    tris = np.asarray(faces, dtype=np.int64)
    if len(tris) == 0:
        return verts[:count]
    v0 = verts[tris[:, 0]]
    v1 = verts[tris[:, 1]]
    v2 = verts[tris[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
    probabilities = areas / max(float(areas.sum()), 1e-18)
    chosen = rng.choice(len(tris), size=count, p=probabilities)
    u = rng.random(count)
    v = rng.random(count)
    flip = u + v > 1.0
    u[flip] = 1.0 - u[flip]
    v[flip] = 1.0 - v[flip]
    a = verts[tris[chosen, 0]]
    b = verts[tris[chosen, 1]]
    c = verts[tris[chosen, 2]]
    return a + u[:, None] * (b - a) + v[:, None] * (c - a)


def chamfer_metrics_mm(
    surface_points: np.ndarray, ground_truth: np.ndarray
) -> dict[str, float]:
    surface = np.asarray(surface_points, dtype=float)
    truth = np.asarray(ground_truth, dtype=float)
    truth_tree = cKDTree(truth)
    surface_tree = cKDTree(surface)
    surface_to_truth = float(truth_tree.query(surface)[0].mean())
    truth_to_surface = float(surface_tree.query(truth)[0].mean())
    return {
        "chamfer_mm": 0.5 * (surface_to_truth + truth_to_surface) * 1000.0,
        "surface_to_truth_mm": surface_to_truth * 1000.0,
        "truth_to_surface_mm": truth_to_surface * 1000.0,
    }


def write_ply(
    path: str | Path,
    vertices: np.ndarray,
    faces: np.ndarray | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    verts = np.asarray(vertices, dtype=float)
    tris = None if faces is None else np.asarray(faces, dtype=np.int64)
    with path.open("w", encoding="ascii") as handle:
        handle.write("ply\nformat ascii 1.0\n")
        handle.write(f"element vertex {len(verts)}\n")
        handle.write("property float x\nproperty float y\nproperty float z\n")
        if tris is not None:
            handle.write(f"element face {len(tris)}\n")
            handle.write("property list uchar int vertex_indices\n")
        handle.write("end_header\n")
        for vertex in verts:
            handle.write(f"{vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}\n")
        if tris is not None:
            for tri in tris:
                handle.write(f"3 {tri[0]} {tri[1]} {tri[2]}\n")
