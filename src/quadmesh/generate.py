"""Procedural organic triangle models with explicit feature-edge tags."""

from __future__ import annotations

import math

from .geometry import (
    Edge,
    Mesh,
    Vec3,
    cross,
    dot,
    edge,
    face_normal,
    normalize,
    vadd,
    vmul,
    vsub,
)


def _organic_radius(direction: Vec3) -> float:
    theta = math.atan2(direction[2], direction[0])
    phi = math.asin(max(-1.0, min(1.0, direction[1])))
    lobes = 1.0
    lobes += 0.055 * math.sin(3.0 * theta + 0.4) * math.cos(2.0 * phi)
    lobes += 0.025 * math.sin(5.0 * phi + 2.0 * theta)
    creases = 0.050 * abs(direction[0]) + 0.024 * abs(direction[1] + 0.25)
    return lobes - creases


def project_organic(cube_point: Vec3) -> Vec3:
    direction = normalize(cube_point)
    radius = (1.35, 1.05, 0.86)
    scale = _organic_radius(direction)
    return tuple(direction[idx] * radius[idx] * scale for idx in range(3))  # type: ignore[return-value]


def _cube_faces() -> list[tuple[Vec3, Vec3, Vec3]]:
    return [
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
        ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
        ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
    ]


def cube_sphere_quads(divisions: int) -> Mesh:
    """Six welded cube faces projected to a star-shaped organic surface."""
    vertices: list[Vec3] = []
    vertex_ids: dict[tuple[int, int, int], int] = {}
    faces: list[tuple[int, ...]] = []

    def get_vertex(coord: tuple[int, int, int]) -> int:
        if coord not in vertex_ids:
            vertex_ids[coord] = len(vertices)
            vertices.append(project_organic(coord))
        return vertex_ids[coord]

    for axis, tangent_u, tangent_v in _cube_faces():
        for i in range(divisions):
            for j in range(divisions):
                coords = []
                for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    cu = -divisions + 2 * (i + di)
                    cv = -divisions + 2 * (j + dj)
                    coord = tuple(
                        axis[k] * divisions + cu * tangent_u[k] + cv * tangent_v[k]
                        for k in range(3)
                    )
                    coords.append(get_vertex(coord))  # type: ignore[arg-type]
                face = tuple(coords)
                points = [vertices[idx] for idx in face]
                centroid = vmul(vadd(vadd(points[0], points[1]), vadd(points[2], points[3])), 0.25)
                normal = cross(vsub(points[1], points[0]), vsub(points[2], points[0]))
                if dot(normal, centroid) < 0.0:
                    face = face[::-1]
                faces.append(face)
    return Mesh(vertices, faces, name="organic_blob_quads")


def open_organic_quads(divisions_u: int = 48, divisions_v: int = 28) -> Mesh:
    """A leaf-like open organic surface with a free boundary."""
    vertices: list[Vec3] = []
    faces: list[tuple[int, ...]] = []

    def surface(u: float, v: float) -> Vec3:
        x = 4.2 * (u - 0.5)
        y = 2.4 * (v - 0.5)
        envelope = (math.sin(math.pi * u) ** 0.45) * (math.sin(math.pi * v) ** 0.30)
        z = 0.40 * envelope * (0.72 + 0.28 * math.cos(2.0 * math.pi * u))
        z += 0.08 * math.sin(3.0 * math.pi * u + 0.6) * math.sin(2.0 * math.pi * v)
        return (x, y, z)

    for j in range(divisions_v + 1):
        for i in range(divisions_u + 1):
            vertices.append(surface(i / divisions_u, j / divisions_v))
    stride = divisions_u + 1
    for j in range(divisions_v):
        for i in range(divisions_u):
            a = j * stride + i
            faces.append((a, a + 1, a + stride + 1, a + stride))
    return Mesh(vertices, faces, name="organic_leaf_quads")


def organic_ring_quads(divisions_u: int = 96, divisions_v: int = 18) -> Mesh:
    """Closed tubular organic form with low-distortion periodic quad topology."""
    vertices: list[Vec3] = []
    faces: list[tuple[int, ...]] = []
    vertex_ids: dict[tuple[int, int], int] = {}

    def surface(u: float, v: float) -> Vec3:
        major = 2.2
        minor = 0.42
        minor *= 1.0 + 0.10 * math.sin(3.0 * u + 0.3)
        minor *= 1.0 + 0.06 * math.cos(2.0 * v)
        minor -= 0.032 * abs(math.sin(4.0 * v))
        radial = major + minor * math.cos(v)
        return (
            radial * math.cos(u),
            radial * math.sin(u),
            minor * math.sin(v) + 0.12 * math.sin(3.0 * u),
        )

    def get_vertex(i: int, j: int) -> int:
        key = (i % divisions_u, j % divisions_v)
        if key not in vertex_ids:
            vertex_ids[key] = len(vertices)
            vertices.append(
                surface(
                    2.0 * math.pi * key[0] / divisions_u,
                    2.0 * math.pi * key[1] / divisions_v,
                )
            )
        return vertex_ids[key]

    for j in range(divisions_v):
        for i in range(divisions_u):
            faces.append(
                (
                    get_vertex(i, j),
                    get_vertex(i + 1, j),
                    get_vertex(i + 1, j + 1),
                    get_vertex(i, j + 1),
                )
            )
    return Mesh(vertices, faces, name="organic_ring_quads")


def detect_features(mesh: Mesh, angle_deg: float = 18.0) -> set[Edge]:
    """Mark boundary edges and creases whose dihedral angle exceeds a threshold."""
    features: set[Edge] = set()
    for item, incident in mesh.edges().items():
        if len(incident) != 2:
            features.add(item)
            continue
        normals = [face_normal(mesh.vertices, mesh.faces[idx]) for idx in incident]
        angle = math.degrees(math.acos(max(-1.0, min(1.0, dot(normals[0], normals[1])))))
        if angle >= angle_deg:
            features.add(item)
    return features


def triangulate_quads(quad_mesh: Mesh) -> Mesh:
    """Split each quad by its shorter diagonal; feature edges are never diagonals."""
    triangles: list[tuple[int, ...]] = []
    for face in quad_mesh.faces:
        if len(face) != 4:
            raise ValueError("triangulate_quads expects a pure quad mesh")
        a, b, c, d = face
        diag_ac = dot(vsub(quad_mesh.vertices[a], quad_mesh.vertices[c]), vsub(quad_mesh.vertices[a], quad_mesh.vertices[c]))
        diag_bd = dot(vsub(quad_mesh.vertices[b], quad_mesh.vertices[d]), vsub(quad_mesh.vertices[b], quad_mesh.vertices[d]))
        if diag_ac <= diag_bd:
            triangles.extend(((a, b, c), (a, c, d)))
        else:
            triangles.extend(((a, b, d), (b, c, d)))
    return Mesh(
        vertices=list(quad_mesh.vertices),
        faces=triangles,
        feature_edges=set(quad_mesh.feature_edges),
        name=quad_mesh.name.replace("_quads", "_triangles"),
    )


def make_organic_blob(divisions: int = 28) -> tuple[Mesh, Mesh]:
    quads = cube_sphere_quads(divisions)
    quads.feature_edges = detect_features(quads, angle_deg=18.0)
    triangles = triangulate_quads(quads)
    return triangles, quads


def make_organic_leaf(divisions_u: int = 48, divisions_v: int = 28) -> tuple[Mesh, Mesh]:
    quads = open_organic_quads(divisions_u, divisions_v)
    quads.feature_edges = detect_features(quads, angle_deg=12.0)
    triangles = triangulate_quads(quads)
    return triangles, quads


def make_organic_ring(divisions_u: int = 96, divisions_v: int = 18) -> tuple[Mesh, Mesh]:
    quads = organic_ring_quads(divisions_u, divisions_v)
    quads.feature_edges = detect_features(quads, angle_deg=18.0)
    triangles = triangulate_quads(quads)
    return triangles, quads
