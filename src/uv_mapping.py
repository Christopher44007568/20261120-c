from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import lsqr

from .mesh_ops import TriangleMesh


@dataclass
class UVMap:
    face_uv: np.ndarray
    method: str
    flip_ratio: float


def _triangle_local_coordinates(p: np.ndarray) -> tuple[float, complex]:
    e1 = p[1] - p[0]
    e2 = p[2] - p[0]
    a = float(np.linalg.norm(e1))
    if a < 1e-12:
        return 0.0, 0j
    x = float(np.dot(e2, e1) / a)
    y = float(np.sqrt(max(np.dot(e2, e2) - x * x, 0.0)))
    return a, complex(x, y)


def _lscm_island(mesh: TriangleMesh, faces: np.ndarray) -> np.ndarray | None:
    vertex_ids = np.unique(mesh.faces[faces].ravel())
    if len(vertex_ids) < 3:
        return None
    remap = {int(v): i for i, v in enumerate(vertex_ids)}
    n_vertices = len(vertex_ids)
    areas = mesh.face_areas[faces]
    scale = float(np.sqrt(max(areas.mean(), 1e-12)))

    rows = []
    cols = []
    vals = []
    row_id = 0
    for face, face_area in zip(faces, areas):
        p0, p1, p2 = mesh.vertices[mesh.faces[face]]
        a, z2 = _triangle_local_coordinates(np.asarray((p0, p1, p2)))
        if a < 1e-12 or abs(z2) < 1e-12:
            continue
        coeffs = (a - z2, z2, -a)
        local = [remap[int(v)] for v in mesh.faces[face]]
        weight = float(np.sqrt(max(face_area, 1e-12))) / max(scale, 1e-9)
        real = []
        imag = []
        for coeff, vid in zip(coeffs, local):
            real.extend([(row_id, 2 * vid, weight * coeff.real)])
            real.append((row_id, 2 * vid + 1, -weight * coeff.imag))
            imag.append((row_id + 1, 2 * vid, weight * coeff.imag))
            imag.append((row_id + 1, 2 * vid + 1, weight * coeff.real))
        for r, c, v in real + imag:
            rows.append(r)
            cols.append(c)
            vals.append(v)
        row_id += 2

    points = mesh.vertices[vertex_ids]
    centered = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    projections = centered @ vt[0]
    pin_a = int(np.argmin(projections))
    pin_b = int(np.argmax(projections))
    if pin_a == pin_b:
        pin_a, pin_b = 0, min(1, n_vertices - 1)
    pin_weight = 12.0
    for vid, ux, uy in ((pin_a, 0.0, 0.0), (pin_b, 1.0, 0.0)):
        rows.extend([row_id, row_id + 1])
        cols.extend([2 * vid, 2 * vid + 1])
        vals.extend([pin_weight, pin_weight])
        row_id += 2

    A = coo_matrix(
        (vals, (rows, cols)), shape=(row_id, 2 * n_vertices)
    ).tocsr()
    b = np.zeros(row_id)
    b[-4] = 0.0
    b[-3] = 0.0
    b[-2] = pin_weight
    b[-1] = 0.0
    solution = lsqr(A, b, atol=1e-9, btol=1e-9, iter_lim=5000)[0]
    uv = solution.reshape(n_vertices, 2)
    if not np.all(np.isfinite(uv)):
        return None

    tri_uv = uv[np.searchsorted(vertex_ids, mesh.faces[faces])]
    signed = 0.5 * (
        (tri_uv[:, 1, 0] - tri_uv[:, 0, 0])
        * (tri_uv[:, 2, 1] - tri_uv[:, 0, 1])
        - (tri_uv[:, 1, 1] - tri_uv[:, 0, 1])
        * (tri_uv[:, 2, 0] - tri_uv[:, 0, 0])
    )
    if np.sum(signed) < 0:
        uv[:, 1] *= -1.0
        tri_uv = uv[np.searchsorted(vertex_ids, mesh.faces[faces])]
        signed = -signed
    uv_area = np.sum(np.abs(signed))
    if uv_area < 1e-12:
        return None
    uv *= np.sqrt(float(areas.sum()) / uv_area)

    result = np.empty((len(faces), 3, 2))
    for i, face in enumerate(faces):
        result[i] = uv[[remap[int(v)] for v in mesh.faces[face]]]
    return result


def _project_island(mesh: TriangleMesh, faces: np.ndarray) -> np.ndarray:
    vertex_ids = np.unique(mesh.faces[faces].ravel())
    vertices = mesh.vertices[vertex_ids]
    centered = vertices - vertices.mean(axis=0)
    mean_normal = np.sum(
        mesh.face_normals[faces] * mesh.face_areas[faces, None], axis=0
    )
    mean_normal /= max(np.linalg.norm(mean_normal), 1e-12)
    reference_axis = np.eye(3)[int(np.argmin(np.abs(mean_normal)))]
    tangent_x = np.cross(reference_axis, mean_normal)
    tangent_x /= max(np.linalg.norm(tangent_x), 1e-12)
    tangent_y = np.cross(mean_normal, tangent_x)
    basis = np.stack((tangent_x, tangent_y), axis=1)
    uv = centered @ basis
    uv_area = 0.0
    for face in faces:
        p0, p1, p2 = mesh.vertices[mesh.faces[face]]
        tri = np.asarray([p0, p1, p2]) @ basis
        uv_area += 0.5 * abs(
            (tri[1, 0] - tri[0, 0]) * (tri[2, 1] - tri[0, 1])
            - (tri[1, 1] - tri[0, 1]) * (tri[2, 0] - tri[0, 0])
        )
    target = float(mesh.face_areas[faces].sum())
    if uv_area > 1e-12:
        uv *= np.sqrt(target / uv_area)
    result = np.empty((len(faces), 3, 2))
    for i, face in enumerate(faces):
        result[i] = uv[np.searchsorted(vertex_ids, mesh.faces[face])]
    return result


def build_lscm_uv(mesh: TriangleMesh, labels: np.ndarray) -> UVMap:
    face_uv = np.full((len(mesh.faces), 3, 2), np.nan)
    for label in np.unique(labels):
        faces = np.flatnonzero(labels == label)
        island_uv = _lscm_island(mesh, faces)
        if island_uv is None:
            island_uv = _project_island(mesh, faces)
        face_uv[faces] = island_uv
    _normalize_total_area(face_uv, mesh)
    return UVMap(face_uv, "lscm", _flip_ratio(mesh, face_uv))


def build_planar_projection_uv(mesh: TriangleMesh) -> UVMap:
    faces = np.arange(len(mesh.faces))
    face_uv = _project_island(mesh, faces)
    _normalize_total_area(face_uv, mesh)
    return UVMap(face_uv, "planar-projection", _flip_ratio(mesh, face_uv))


def build_island_projection_uv(mesh: TriangleMesh, labels: np.ndarray) -> UVMap:
    face_uv = np.full((len(mesh.faces), 3, 2), np.nan)
    for label in np.unique(labels):
        faces = np.flatnonzero(labels == label)
        face_uv[faces] = _project_island(mesh, faces)
    _normalize_total_area(face_uv, mesh)
    return UVMap(face_uv, "island-projection", _flip_ratio(mesh, face_uv))


def _normalize_total_area(face_uv: np.ndarray, mesh: TriangleMesh) -> None:
    uv_area = _uv_areas(face_uv).sum()
    target = float(mesh.face_areas.sum())
    if uv_area > 1e-12:
        face_uv *= np.sqrt(target / uv_area)


def _uv_areas(face_uv: np.ndarray) -> np.ndarray:
    return 0.5 * np.abs(
        (face_uv[:, 1, 0] - face_uv[:, 0, 0])
        * (face_uv[:, 2, 1] - face_uv[:, 0, 1])
        - (face_uv[:, 1, 1] - face_uv[:, 0, 1])
        * (face_uv[:, 2, 0] - face_uv[:, 0, 0])
    )


def _flip_ratio(mesh: TriangleMesh, face_uv: np.ndarray) -> float:
    p = mesh.vertices[mesh.faces]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    q = face_uv
    signed = (
        (q[:, 1, 0] - q[:, 0, 0]) * (q[:, 2, 1] - q[:, 0, 1])
        - (q[:, 1, 1] - q[:, 0, 1]) * (q[:, 2, 0] - q[:, 0, 0])
    )
    return float(np.mean(signed < 0))


def texture_stretch(mesh: TriangleMesh, uv: UVMap) -> dict[str, float]:
    stretch = face_stretch_values(mesh, uv)
    weights = mesh.face_areas / mesh.face_areas.sum()
    order = np.argsort(stretch)
    cumulative = np.cumsum(weights[order])
    p95 = float(stretch[order[np.searchsorted(cumulative, 0.95)]])
    return {
        "mean": float(np.sum(weights * stretch)),
        "p95": p95,
        "max": float(stretch.max()),
        "flip_ratio": uv.flip_ratio,
    }


def face_stretch_values(mesh: TriangleMesh, uv: UVMap) -> np.ndarray:
    p = mesh.vertices[mesh.faces]
    e = np.stack((p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    dq = np.stack(
        (uv.face_uv[:, 1] - uv.face_uv[:, 0], uv.face_uv[:, 2] - uv.face_uv[:, 0]),
        axis=1,
    )
    transformation = np.linalg.pinv(e) @ dq
    singular = np.linalg.svd(transformation, compute_uv=False)
    return np.sqrt(0.5 * np.sum(singular**2, axis=1))


def pack_uv_islands(face_uv: np.ndarray, labels: np.ndarray) -> np.ndarray:
    packed = np.full_like(face_uv, np.nan)
    raw_boxes = []
    for label in np.unique(labels):
        faces = np.flatnonzero(labels == label)
        pts = face_uv[faces].reshape(-1, 2)
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        raw_boxes.append((label, faces, lo, hi - lo))
    total_box_area = sum(size[0] * size[1] for _, _, _, size in raw_boxes)
    pre_scale = np.sqrt(0.72 / max(total_box_area, 1e-12))
    boxes = [
        (label, faces, lo * pre_scale, size * pre_scale)
        for label, faces, lo, size in raw_boxes
    ]
    boxes.sort(key=lambda item: item[3][1], reverse=True)

    x = 0.0
    y = 0.0
    shelf_height = 0.0
    gap = 0.025
    for label, faces, lo, size in boxes:
        if x + size[0] > 1.0 and x > 1e-9:
            x = 0.0
            y += shelf_height + gap
            shelf_height = 0.0
        packed[faces] = face_uv[faces] * pre_scale - lo + np.asarray((x, y))
        x += size[0] + gap
        shelf_height = max(shelf_height, size[1])
    all_pts = packed.reshape(-1, 2)
    lo = np.nanmin(all_pts, axis=0)
    span = np.nanmax(all_pts, axis=0) - lo
    post_scale = 0.96 / max(float(span.max()), 1e-9)
    packed = (packed - lo) * post_scale
    return packed

