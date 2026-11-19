"""Normal estimation, artificial inconsistency and consistent orientation.

Pipeline:
1. ``estimate_normals`` fits local tangent planes with PCA (Open3D). The
   resulting orientations have arbitrary/random signs.
2. ``make_normals_inconsistent`` flips a controlled fraction of normals so the
   orientation field contains explicit contradictions.
3. ``orient_normals_consistent`` propagates a coherent orientation over the
   nearest-neighbour graph (minimum spanning tree on tangent-plane
   compatibility), removing the contradictions.
"""

from __future__ import annotations

import numpy as np
import open3d as o3d


def to_point_cloud(
    points: np.ndarray, normals: np.ndarray | None = None
) -> o3d.geometry.PointCloud:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
    if normals is not None:
        pcd.normals = o3d.utility.Vector3dVector(
            np.asarray(normals, dtype=np.float64)
        )
    return pcd


def estimate_normals(
    points: np.ndarray, knn: int = 30
) -> tuple[o3d.geometry.PointCloud, np.ndarray]:
    """PCA tangent-plane normals; signs are intentionally unordered."""
    pcd = to_point_cloud(points)
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamKNN(knn=knn)
    )
    normals = np.asarray(pcd.normals, dtype=np.float64)
    return pcd, normals


def make_normals_inconsistent(
    normals: np.ndarray,
    flip_fraction: float = 0.35,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Randomly flip ``flip_fraction`` of the normals.

    Returns the corrupted normals and the boolean mask of flipped indices.
    """
    rng = np.random.default_rng() if rng is None else rng
    normals = np.array(normals, dtype=np.float64)
    n = normals.shape[0]
    flip_count = int(round(flip_fraction * n))
    flip_idx = rng.choice(n, size=flip_count, replace=False)
    corrupted = normals.copy()
    corrupted[flip_idx] *= -1.0
    flip_mask = np.zeros(n, dtype=bool)
    flip_mask[flip_idx] = True
    return corrupted, flip_mask


def orient_normals_consistent(
    points: np.ndarray,
    normals: np.ndarray,
    knn: int = 16,
    reference_point: np.ndarray | None = None,
) -> np.ndarray:
    """Propagate one coherent orientation across the tangent-plane graph.

    Open3D builds an MST on the KNN graph and aligns neighbouring normals so
    their dot products stay positive. A global sign is then fixed against
    ``reference_point`` (default: far below the object), which makes enclosed
    surfaces point outward.
    """
    pcd = to_point_cloud(points, normals)
    pcd.orient_normals_consistent_tangent_plane(k=knn)
    oriented = np.asarray(pcd.normals, dtype=np.float64)
    if reference_point is None:
        reference_point = np.array([0.0, 0.0, -100.0])
    centroid = np.asarray(points, dtype=np.float64).mean(axis=0)
    outward_hint = centroid - np.asarray(reference_point, dtype=np.float64)
    if np.dot(oriented.mean(axis=0), outward_hint) < 0.0:
        oriented = -oriented
    return oriented


def normal_consistency_rate(
    normals: np.ndarray, ground_truth: np.ndarray
) -> float:
    """Fraction of normals aligned with ground truth.

    Normals are unoriented tangent-plane lines, so a global sign ambiguity is
    removed by taking ``max(p, 1 - p)``.
    """
    normals = np.asarray(normals, dtype=np.float64)
    ground_truth = np.asarray(ground_truth, dtype=np.float64)
    dots = np.einsum("ij,ij->i", normals, ground_truth)
    aligned = float(np.mean(dots > 0.0))
    return max(aligned, 1.0 - aligned)
