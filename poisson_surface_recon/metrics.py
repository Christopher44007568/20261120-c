"""Distance errors between the reconstructed mesh and the source point cloud.

Poisson output is a mesh, so distances are evaluated in point-cloud space:
the mesh is densely sampled on its surface and compared with the (noisy)
input samples using nearest-neighbour queries.
"""

from __future__ import annotations

import numpy as np
import open3d as o3d


def nearest_distances(
    source: np.ndarray, target: np.ndarray
) -> np.ndarray:
    """For each source point, distance to its nearest target point."""
    source_pcd = o3d.geometry.PointCloud()
    source_pcd.points = o3d.utility.Vector3dVector(
        np.asarray(source, dtype=np.float64)
    )
    target_pcd = o3d.geometry.PointCloud()
    target_pcd.points = o3d.utility.Vector3dVector(
        np.asarray(target, dtype=np.float64)
    )
    tree = o3d.geometry.KDTreeFlann(target_pcd)
    distances = np.empty(len(source_pcd.points), dtype=np.float64)
    target_pts = np.asarray(target_pcd.points)
    for i, point in enumerate(np.asarray(source_pcd.points)):
        _, idx, _ = tree.search_knn_vector_3d(point, 1)
        nearest = target_pts[idx[0]]
        distances[i] = np.linalg.norm(point - nearest)
    return distances


def chamfer_distance(
    points_a: np.ndarray, points_b: np.ndarray
) -> tuple[float, float, float]:
    """Return (mean one-way A->B, mean B->A, symmetric Chamfer mean)."""
    d_ab = nearest_distances(points_a, points_b)
    d_ba = nearest_distances(points_b, points_a)
    mean_ab = float(d_ab.mean())
    mean_ba = float(d_ba.mean())
    return mean_ab, mean_ba, 0.5 * (mean_ab + mean_ba)


def sample_mesh_surface(
    mesh: o3d.geometry.TriangleMesh, n_samples: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Uniform-area sampling of triangle surfaces (area-weighted)."""
    del rng  # Open3D 0.20's sampler does not accept an RNG seed
    mesh_sampled = mesh.sample_points_uniformly(
        number_of_points=n_samples,
        use_triangle_normal=False,
    )
    return np.asarray(mesh_sampled.points, dtype=np.float64)


def reconstruction_errors(
    mesh: o3d.geometry.TriangleMesh,
    input_points: np.ndarray,
    n_mesh_samples: int = 20000,
    rng: np.random.Generator | None = None,
) -> dict:
    """Point-to-mesh error suite.

    ``accuracy`` is input-point -> mesh distance (how well samples fit);
    ``completeness`` is mesh -> input distance (coverage). Chamfer combines
    both. RMSE and the 95th percentile quantify worst-case behaviour.
    """
    rng = np.random.default_rng() if rng is None else rng
    mesh_points = sample_mesh_surface(mesh, n_mesh_samples, rng)
    d_to_mesh = nearest_distances(input_points, mesh_points)
    d_to_input = nearest_distances(mesh_points, input_points)
    accuracy = float(d_to_mesh.mean())
    completeness = float(d_to_input.mean())
    return {
        "accuracy_mean": accuracy,
        "accuracy_rmse": float(np.sqrt(np.mean(d_to_mesh**2))),
        "accuracy_p95": float(np.quantile(d_to_mesh, 0.95)),
        "completeness_mean": completeness,
        "chamfer": 0.5 * (accuracy + completeness),
        "hausdorff": float(
            max(d_to_mesh.max(), d_to_input.max())
        ),
        "dist_to_mesh": d_to_mesh,
    }


def mesh_smoothness(mesh: o3d.geometry.TriangleMesh, k: int = 8) -> dict:
    """Smoothness proxies based on the reconstructed mesh itself.

    ``normal_variation`` is the mean angle (degrees) between each vertex
    normal and its nearest neighbours' normals; lower means smoother.
    ``edge_cv`` is the coefficient of variation of edge lengths, measuring
    mesh regularity.
    """
    mesh.compute_vertex_normals()
    points = np.asarray(mesh.vertices, dtype=np.float64)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    tree = o3d.geometry.KDTreeFlann(pcd)

    angles = []
    for i in range(len(points)):
        _, idx, _ = tree.search_knn_vector_3d(points[i], k + 1)
        neighbours = [j for j in idx if j != i]
        dots = np.clip(normals[neighbours] @ normals[i], -1.0, 1.0)
        angles.append(np.degrees(np.arccos(np.abs(dots))).mean())
    normal_variation = float(np.mean(angles))

    triangles = np.asarray(mesh.triangles)
    edges = np.vstack(
        [triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]
    )
    edge_lengths = np.linalg.norm(
        points[edges[:, 0]] - points[edges[:, 1]], axis=1
    )
    edge_cv = float(edge_lengths.std() / edge_lengths.mean())
    return {
        "normal_variation_deg": normal_variation,
        "edge_length_cv": edge_cv,
        "mean_edge_length": float(edge_lengths.mean()),
    }


def mesh_quality(mesh: o3d.geometry.TriangleMesh) -> dict:
    """Topological quality: boundary edges, non-manifold edges, watertightness."""
    triangles = np.asarray(mesh.triangles)
    edges = np.vstack(
        [triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]
    )
    ordered = np.sort(edges, axis=1)
    _, counts = np.unique(ordered, axis=0, return_counts=True)
    boundary_edges = int((counts == 1).sum())
    non_manifold_edges = int((counts > 2).sum())
    return {
        "watertight": bool(mesh.is_watertight()),
        "edge_manifold": bool(mesh.is_edge_manifold()),
        "boundary_edges": boundary_edges,
        "non_manifold_edges": non_manifold_edges,
        "boundary_edge_fraction": float(boundary_edges / len(counts)),
    }
