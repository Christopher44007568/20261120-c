"""Screened Poisson surface reconstruction (Kazhdan & Hoppe, 2013).

Poisson reconstruction estimates the indicator function of the solid region
from the oriented point set. The oriented normals define a sampled vector
field ``V``; the indicator gradient should equal that field, so the indicator
``chi`` minimises the variational problem

    min_chi  || grad chi - V ||^2  +  lambda * || chi - chi_p ||^2

which, after applying divergence and the Laplacian, reduces to the screened
Poisson equation

    ( Delta - lambda ) chi = div V .

Open3D solves this on an adaptive octree with multigrid; an isosurface of the
resulting scalar field (default iso-value 0) is extracted as a triangle mesh.
"""

from __future__ import annotations

import time

import numpy as np
import open3d as o3d

from .normals import to_point_cloud


def poisson_reconstruct(
    points: np.ndarray,
    normals: np.ndarray,
    depth: int = 8,
    width: float = 0.0,
    scale: float = 1.1,
    linear_fit: bool = False,
    density_quantile: float | None = 0.05,
) -> tuple[o3d.geometry.TriangleMesh, dict]:
    """Run screened Poisson reconstruction and time it.

    Parameters mirror Open3D's ``create_from_point_cloud_poisson``.
    ``density_quantile`` removes the low-confidence fringe triangles that
    Poisson meshes tend to produce where samples are sparse.
    """
    pcd = to_point_cloud(points, normals)
    start = time.perf_counter()
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd,
        depth=depth,
        width=width,
        scale=scale,
        linear_fit=linear_fit,
    )
    elapsed = time.perf_counter() - start

    densities = np.asarray(densities, dtype=np.float64)
    n_vertices_before = len(mesh.vertices)
    n_triangles_before = len(mesh.triangles)

    cropped = False
    if density_quantile is not None and density_quantile > 0.0:
        threshold = np.quantile(densities, density_quantile)
        keep = densities >= threshold
        mesh.remove_vertices_by_mask(~keep)
        cropped = True

    mesh.compute_vertex_normals()
    info = {
        "elapsed_sec": elapsed,
        "n_vertices": len(mesh.vertices),
        "n_triangles": len(mesh.triangles),
        "n_vertices_raw": n_vertices_before,
        "n_triangles_raw": n_triangles_before,
        "density_quantile": density_quantile,
        "cropped": cropped,
        "depth": depth,
    }
    return mesh, info
