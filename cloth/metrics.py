"""Evaluation metrics: surface error, normal continuity, cracks, creases."""
from __future__ import annotations

import numpy as np


def nearest_distances(points: np.ndarray, reference: np.ndarray,
                      chunk: int = 2048) -> np.ndarray:
    """Distance from each point to the nearest reference point."""
    out = np.empty(len(points))
    for s in range(0, len(points), chunk):
        p = points[s:s + chunk]
        d2 = np.sum((p[:, None, :] - reference[None, :, :]) ** 2, axis=-1)
        out[s:s + chunk] = np.sqrt(d2.min(axis=1))
    return out


def surface_error(points, reference):
    """Symmetric RMSE / max / mean error between two point sets."""
    d_a = nearest_distances(points, reference)
    d_b = nearest_distances(reference, points)
    both = np.concatenate([d_a, d_b])
    return {
        "rmse": float(np.sqrt(np.mean(both ** 2))),
        "max": float(both.max()),
        "mean": float(both.mean()),
    }


def interior_edges(triangles: np.ndarray):
    """Map undirected edge -> list of adjacent face indices."""
    edge_map: dict[tuple, list[int]] = {}
    for fi, t in enumerate(triangles):
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            edge_map.setdefault((min(a, b), max(a, b)), []).append(fi)
    return edge_map


def face_normals(positions, triangles):
    p0 = positions[triangles[:, 0]]
    p1 = positions[triangles[:, 1]]
    p2 = positions[triangles[:, 2]]
    fn = np.cross(p1 - p0, p2 - p0)
    ln = np.linalg.norm(fn, axis=1, keepdims=True)
    ln[ln < 1e-30] = 1.0
    return fn / ln


def normal_continuity(positions, triangles):
    """Dihedral angle (deg) between adjacent face normals across edges."""
    fn = face_normals(positions, triangles)
    angles = []
    for fl in interior_edges(triangles).values():
        if len(fl) == 2:
            c = np.clip(np.dot(fn[fl[0]], fn[fl[1]]), -1.0, 1.0)
            angles.append(np.degrees(np.arccos(c)))
    angles = np.array(angles)
    return {"mean_deg": float(angles.mean()), "max_deg": float(angles.max()),
            "p95_deg": float(np.percentile(angles, 95))}


def normal_field_deviation(geom_positions, triangles, analytic_normals):
    """Angle (deg) between an analytic normal field and geometric normals."""
    from .mesh import vertex_normals
    vn = vertex_normals(geom_positions, triangles)
    c = np.clip(np.sum(vn * analytic_normals, axis=1), -1.0, 1.0)
    ang = np.degrees(np.arccos(c))
    return {"mean_deg": float(ang.mean()), "max_deg": float(ang.max())}


def crack_gap(samples_a: np.ndarray, samples_b: np.ndarray) -> float:
    """Max distance between two sample sequences of the same edge curve."""
    return float(np.linalg.norm(samples_a - samples_b, axis=1).max())


def dihedral_along_edges(positions, triangles, edge_set):
    """Dihedral angles (deg) across the given mesh edges."""
    fn = face_normals(positions, triangles)
    emap = interior_edges(triangles)
    out = []
    for e in edge_set:
        key = (min(e), max(e))
        fl = emap.get(key, [])
        if len(fl) == 2:
            c = np.clip(np.dot(fn[fl[0]], fn[fl[1]]), -1.0, 1.0)
            out.append(np.degrees(np.arccos(c)))
    return np.array(out)
