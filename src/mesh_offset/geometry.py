"""Mesh creation, conversion, normals, and topology helpers."""

from __future__ import annotations

from dataclasses import dataclass

import manifold3d
import numpy as np
import trimesh


def manifold_to_trimesh(solid: manifold3d.Manifold) -> trimesh.Trimesh:
    mesh = solid.to_mesh()
    vertices = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    faces = np.asarray(mesh.tri_verts, dtype=np.int64)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def trimesh_to_manifold(mesh: trimesh.Trimesh) -> manifold3d.Manifold:
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
    return manifold3d.Manifold(manifold3d.Mesh(vertices, faces))


def make_holey_plate() -> tuple[trimesh.Trimesh, dict[str, object]]:
    """Create a closed plate with four cylindrical through-holes."""

    size = (6.2, 4.6, 1.4)
    hole_radius = 0.5
    centers = [(-1.55, -0.9), (-1.55, 0.9), (1.55, -0.9), (1.55, 0.9)]
    plate = manifold3d.Manifold.cube(list(size), center=True)
    holes = [
        manifold3d.Manifold.cylinder(
            2.2, hole_radius, circular_segments=64, center=True
        ).translate([x, y, 0.0])
        for x, y in centers
    ]
    solid = plate - manifold3d.Manifold.compose(holes)
    mesh = manifold_to_trimesh(solid)
    mesh.merge_vertices()
    mesh.fix_normals()
    metadata = {
        "name": "holey_plate",
        "size": size,
        "hole_radius": hole_radius,
        "hole_centers": centers,
        "through_holes": len(centers),
    }
    return mesh, metadata


def vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Angle-weighted vertex normals for sharp-edge-aware normal offsetting."""

    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    triangles = vertices[faces]
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0],
    )
    face_lengths = np.linalg.norm(face_normals, axis=1)
    face_normals /= np.maximum(face_lengths[:, None], 1e-15)

    normals = np.zeros_like(vertices)
    for corner in range(3):
        point = triangles[:, corner]
        left = triangles[:, (corner + 1) % 3] - point
        right = triangles[:, (corner + 2) % 3] - point
        angle = np.arctan2(
            np.linalg.norm(np.cross(left, right), axis=1),
            np.sum(left * right, axis=1),
        )
        np.add.at(normals, faces[:, corner], face_normals * angle[:, None])

    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-15)
    return normals


def offset_vertices(
    vertices: np.ndarray, faces: np.ndarray, distance: float
) -> np.ndarray:
    """Move every vertex along its angle-weighted normal by ``distance``."""

    return np.asarray(vertices, dtype=np.float64) + distance * vertex_normals(
        vertices, faces
    )


def sharp_vertex_count(
    vertices: np.ndarray, faces: np.ndarray, angle_degrees: float = 60.0
) -> int:
    """Count vertices incident to at least one edge above the angle threshold."""

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    face_normals = mesh.face_normals
    threshold = np.deg2rad(angle_degrees)
    sharp = set()
    for left, right in mesh.face_adjacency:
        angle = np.arccos(
            np.clip(np.dot(face_normals[left], face_normals[right]), -1.0, 1.0)
        )
        if angle > threshold:
            sharp.update(mesh.faces[left])
            sharp.update(mesh.faces[right])
    return len(sharp)


@dataclass(frozen=True)
class MeshStats:
    vertices: int
    triangles: int
    watertight: bool
    volume: float
    euler_number: int
    boundary_edges: int
    nonmanifold_edges: int

    @property
    def genus(self) -> int:
        return (2 - self.euler_number) // 2


def mesh_stats(mesh: trimesh.Trimesh) -> MeshStats:
    mesh = mesh.copy()
    mesh.merge_vertices()
    edges = mesh.edges_sorted
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return MeshStats(
        vertices=int(len(mesh.vertices)),
        triangles=int(len(mesh.faces)),
        watertight=bool(mesh.is_watertight),
        volume=float(abs(mesh.volume)),
        euler_number=int(mesh.euler_number),
        boundary_edges=int(np.count_nonzero(counts == 1)),
        nonmanifold_edges=int(np.count_nonzero(counts > 2)),
    )
