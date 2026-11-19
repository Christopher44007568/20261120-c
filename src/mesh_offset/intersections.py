"""Triangle/triangle self-intersection counting for indexed meshes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


@dataclass(frozen=True)
class IntersectionReport:
    count: int
    candidate_pairs: int
    triangle_pairs: tuple[tuple[int, int], ...]


def _coplanar_overlap(a: np.ndarray, b: np.ndarray, eps: float) -> bool:
    normal = np.cross(a[1] - a[0], a[2] - a[0])
    length = np.linalg.norm(normal)
    if length <= eps:
        return False
    normal /= length
    drop = int(np.argmax(np.abs(normal)))
    keep = [axis for axis in range(3) if axis != drop]
    pa, pb = a[:, keep], b[:, keep]
    for polygon in (pa, pb):
        for index in range(3):
            edge = polygon[(index + 1) % 3] - polygon[index]
            axis = np.array([-edge[1], edge[0]])
            proj_a, proj_b = pa @ axis, pb @ axis
            clearance = 1e-7 * max(1.0, np.linalg.norm(axis))
            if (
                proj_a.max() <= proj_b.min() + clearance
                or proj_b.max() <= proj_a.min() + clearance
            ):
                return False
    return True


def _plane_interval(triangle: np.ndarray, distances: np.ndarray, axis: np.ndarray, eps: float):
    if (distances > eps).all() or (distances < -eps).all():
        return None
    points: list[np.ndarray] = []
    for index in range(3):
        if abs(distances[index]) <= eps:
            points.append(triangle[index])
    for index in range(3):
        nxt = (index + 1) % 3
        di, dj = distances[index], distances[nxt]
        if (di < -eps and dj > eps) or (di > eps and dj < -eps):
            fraction = di / (di - dj)
            points.append(triangle[index] + fraction * (triangle[nxt] - triangle[index]))
    if len(points) < 2:
        return None
    values = [float(point @ axis) for point in points]
    return min(values), max(values)


def triangles_intersect_proper(
    a: np.ndarray,
    b: np.ndarray,
    *,
    eps: float = 1e-9,
    overlap_tolerance: float = 1e-7,
) -> bool:
    """Return True only for a non-degenerate intersection.

    Vertex/edge contacts are ignored.  This keeps a valid conforming mesh
    from being reported as self-intersecting merely because nearby triangles
    meet at a shared geometric location.
    """

    normal_a = np.cross(a[1] - a[0], a[2] - a[0])
    normal_b = np.cross(b[1] - b[0], b[2] - b[0])
    length_a = np.linalg.norm(normal_a)
    length_b = np.linalg.norm(normal_b)
    if length_a <= eps or length_b <= eps:
        return False
    normal_a /= length_a
    normal_b /= length_b

    offset_b = -normal_a @ a[0]
    distances_b = b @ normal_a + offset_b
    if (distances_b > eps).all() or (distances_b < -eps).all():
        return False

    offset_a = -normal_b @ b[0]
    distances_a = a @ normal_b + offset_a
    if (distances_a > eps).all() or (distances_a < -eps).all():
        return False

    cross = np.cross(normal_a, normal_b)
    if np.linalg.norm(cross) <= 1e-7:
        if abs(normal_a @ b[0] + offset_b) > 1e-7:
            return False
        return _coplanar_overlap(a, b, eps)

    cross /= np.linalg.norm(cross)
    interval_a = _plane_interval(a, distances_a, cross, eps)
    interval_b = _plane_interval(b, distances_b, cross, eps)
    if interval_a is None or interval_b is None:
        return False
    overlap = min(interval_a[1], interval_b[1]) - max(interval_a[0], interval_b[0])
    return overlap > overlap_tolerance


def _candidate_pairs(
    triangles: np.ndarray, faces: np.ndarray, tolerance: float
) -> list[tuple[int, int]]:
    lower = triangles.min(axis=1)
    upper = triangles.max(axis=1)
    bounds = np.hstack((lower, upper))
    tree = trimesh.util.bounds_tree(bounds)
    pairs: set[tuple[int, int]] = set()
    for index, box in enumerate(bounds):
        for other in tree.intersection(tuple(box)):
            other = int(other)
            if other <= index:
                continue
            if np.any(lower[index] > upper[other] + tolerance):
                continue
            if np.any(lower[other] > upper[index] + tolerance):
                continue
            if set(faces[index]).intersection(faces[other]):
                continue
            pairs.add((index, other))
    return sorted(pairs)


def count_self_intersections(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    tolerance: float = 1e-9,
) -> IntersectionReport:
    """Count properly intersecting non-adjacent triangle pairs."""

    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    triangles = vertices[faces]
    pairs = _candidate_pairs(triangles, faces, tolerance)
    hits: list[tuple[int, int]] = []
    for left, right in pairs:
        if triangles_intersect_proper(
            triangles[left], triangles[right], eps=tolerance
        ):
            hits.append((left, right))
    return IntersectionReport(len(hits), len(pairs), tuple(hits))
