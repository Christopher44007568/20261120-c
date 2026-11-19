from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


@dataclass
class TriangleMesh:
    vertices: np.ndarray
    faces: np.ndarray
    name: str

    @property
    def face_centroids(self) -> np.ndarray:
        return self.vertices[self.faces].mean(axis=1)

    @property
    def face_normals(self) -> np.ndarray:
        p = self.vertices[self.faces]
        normals = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        return normals / np.maximum(lengths[:, None], 1e-12)

    @property
    def face_areas(self) -> np.ndarray:
        p = self.vertices[self.faces]
        return 0.5 * np.linalg.norm(
            np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1
        )


def heightfield_mesh(
    x: np.ndarray,
    y: np.ndarray,
    height: np.ndarray,
    name: str,
) -> TriangleMesh:
    nx, ny = height.shape
    xx, yy = np.meshgrid(x, y, indexing="ij")
    vertices = np.column_stack((xx.ravel(), yy.ravel(), height.ravel()))

    faces = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a = i * ny + j
            b = (i + 1) * ny + j
            c = (i + 1) * ny + j + 1
            d = i * ny + j + 1
            faces.append((a, b, c))
            faces.append((a, c, d))
    return TriangleMesh(vertices, np.asarray(faces, dtype=np.int64), name)


def make_smooth_model(n: int = 48) -> TriangleMesh:
    x = np.linspace(-1.0, 1.0, n)
    y = np.linspace(-1.0, 1.0, n)
    xx, yy = np.meshgrid(x, y, indexing="ij")
    zz = 0.50 * np.sin(1.8 * xx) * np.cos(1.6 * yy)
    zz += 0.25 * (xx**2 - yy**2)
    return heightfield_mesh(x, y, zz, "smooth-saddle")


def make_high_curvature_model(n: int = 64) -> TriangleMesh:
    x = np.linspace(-1.0, 1.0, n)
    y = np.linspace(-1.0, 1.0, n)
    xx, yy = np.meshgrid(x, y, indexing="ij")
    radius = np.hypot(xx, yy)

    def soft_step(value: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(value, -60.0, 60.0)))

    ridge = 0.82 * soft_step(
        (0.27 - np.abs(yy - 0.12 * np.sin(2.6 * xx))) / 0.035
    )
    mesa = 0.56 * soft_step(
        (0.39 - np.hypot(xx + 0.38, yy - 0.18)) / 0.045
    )
    pit = -0.44 * soft_step(
        (0.35 - np.hypot(xx - 0.58, yy + 0.40)) / 0.040
    )
    zz = ridge + mesa + pit + 0.05 * np.cos(4.0 * xx) * np.cos(3.0 * yy)
    return heightfield_mesh(x, y, zz, "high-curvature-terraces")


def build_face_adjacency(mesh: TriangleMesh):
    edges = {}
    for face_id, tri in enumerate(mesh.faces):
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            edge = (a, b) if a < b else (b, a)
            edges.setdefault(edge, []).append(face_id)

    pairs = []
    boundary_edges = []
    for edge, incident in edges.items():
        if len(incident) == 1:
            boundary_edges.append(edge)
        for i in range(len(incident)):
            for j in range(i + 1, len(incident)):
                pairs.append((incident[i], incident[j]))
    return np.asarray(pairs, dtype=np.int64), edges, boundary_edges


def edge_lengths(mesh: TriangleMesh, adjacency: np.ndarray) -> np.ndarray:
    centers = mesh.face_centroids
    return np.linalg.norm(centers[adjacency[:, 0]] - centers[adjacency[:, 1]], axis=1)


def normal_angles(mesh: TriangleMesh, adjacency: np.ndarray) -> np.ndarray:
    normals = mesh.face_normals
    dots = np.clip(
        np.sum(normals[adjacency[:, 0]] * normals[adjacency[:, 1]], axis=1),
        -1.0,
        1.0,
    )
    return np.arccos(dots)


def adjacency_matrix(adjacency: np.ndarray, weights: np.ndarray, n: int):
    rows = np.concatenate((adjacency[:, 0], adjacency[:, 1]))
    cols = np.concatenate((adjacency[:, 1], adjacency[:, 0]))
    vals = np.concatenate((weights, weights))
    return coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()


def connected_components_from_labels(
    labels: np.ndarray, adjacency: np.ndarray, n_faces: int
) -> np.ndarray:
    same = labels[adjacency[:, 0]] == labels[adjacency[:, 1]]
    graph = coo_matrix(
        (
            np.ones(np.count_nonzero(same)),
            (adjacency[same, 0], adjacency[same, 1]),
        ),
        shape=(n_faces, n_faces),
    )
    _, components = connected_components(graph, directed=False)
    return components

