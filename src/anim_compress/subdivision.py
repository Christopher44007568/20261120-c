from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees

from .math3d import (
    Vec3,
    vec_add,
    vec_cross,
    vec_dot,
    vec_length,
    vec_normalize,
    vec_scale,
    vec_sub,
)


@dataclass(frozen=True)
class Mesh:
    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, ...], ...]
    sharp_edges: frozenset[tuple[int, int]] = frozenset()
    corner_vertices: frozenset[int] = frozenset()


@dataclass(frozen=True)
class SubdivisionResult:
    mesh: Mesh
    levels: int
    stats: dict[str, float | int]


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def build_quad_patch_mesh() -> Mesh:
    vertices = tuple(
        (float(x), float(y), 0.0)
        for y in range(3)
        for x in range(3)
    )
    faces = tuple(
        (
            row * 3 + column,
            row * 3 + column + 1,
            (row + 1) * 3 + column + 1,
            (row + 1) * 3 + column,
        )
        for row in range(2)
        for column in range(2)
    )
    return Mesh(vertices=vertices, faces=faces)


def build_tent_mesh() -> Mesh:
    vertices = (
        (-1.0, -1.0, 0.0),
        (0.0, -1.0, 1.0),
        (1.0, -1.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0),
        (-1.0, 1.0, 0.0),
        (0.0, 1.0, 1.0),
        (1.0, 1.0, 0.0),
    )
    faces = (
        (0, 1, 4, 3),
        (3, 4, 7, 6),
        (1, 2, 5, 4),
        (4, 5, 8, 7),
    )
    sharp_edges = frozenset({_edge_key(1, 4), _edge_key(4, 7)})
    return Mesh(vertices=vertices, faces=faces, sharp_edges=sharp_edges)


def build_cube_mesh() -> Mesh:
    vertices = (
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    )
    faces = (
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    )
    return Mesh(vertices=vertices, faces=faces)


def _face_point(mesh: Mesh, face: tuple[int, ...]) -> Vec3:
    total = (0.0, 0.0, 0.0)
    for vertex_index in face:
        total = vec_add(total, mesh.vertices[vertex_index])
    return vec_scale(total, 1.0 / len(face))


def _edge_map(mesh: Mesh) -> dict[tuple[int, int], list[int]]:
    result: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(mesh.faces):
        for offset in range(len(face)):
            edge = _edge_key(face[offset], face[(offset + 1) % len(face)])
            result.setdefault(edge, []).append(face_index)
    return result


def _vertex_neighbors(edge_faces: dict[tuple[int, int], list[int]]) -> dict[int, set[int]]:
    neighbors: dict[int, set[int]] = {}
    for a, b in edge_faces:
        neighbors.setdefault(a, set()).add(b)
        neighbors.setdefault(b, set()).add(a)
    return neighbors


def _smooth_vertex(
    vertex: Vec3,
    incident_faces: list[int],
    incident_edges: list[tuple[int, int]],
    face_points: dict[int, Vec3],
    edge_midpoints: dict[tuple[int, int], Vec3],
) -> Vec3:
    face_average = (0.0, 0.0, 0.0)
    for face_index in incident_faces:
        face_average = vec_add(face_average, face_points[face_index])
    face_average = vec_scale(face_average, 1.0 / len(incident_faces))
    edge_average = (0.0, 0.0, 0.0)
    for edge in incident_edges:
        edge_average = vec_add(edge_average, edge_midpoints[edge])
    edge_average = vec_scale(edge_average, 1.0 / len(incident_edges))
    valence = len(incident_faces)
    return vec_scale(
        vec_add(
            vec_add(face_average, vec_scale(edge_average, 2.0)),
            vec_scale(vertex, valence - 3.0),
        ),
        1.0 / valence,
    )


def _is_corner(vertex: Vec3, crease_neighbors: list[int], vertices: tuple[Vec3, ...]) -> bool:
    if len(crease_neighbors) >= 3:
        return True
    if len(crease_neighbors) != 2:
        return False
    direction_a = vec_normalize(vec_sub(vertices[crease_neighbors[0]], vertex))
    direction_b = vec_normalize(vec_sub(vertices[crease_neighbors[1]], vertex))
    return vec_dot(direction_a, direction_b) > -0.5


def _subdivide_once(mesh: Mesh) -> Mesh:
    edge_faces = _edge_map(mesh)
    neighbors = _vertex_neighbors(edge_faces)
    face_points = {
        face_index: _face_point(mesh, face)
        for face_index, face in enumerate(mesh.faces)
    }
    edge_midpoints = {
        edge: vec_scale(vec_add(mesh.vertices[edge[0]], mesh.vertices[edge[1]]), 0.5)
        for edge in edge_faces
    }
    edge_points: dict[tuple[int, int], Vec3] = {}
    for edge, adjacent_faces in edge_faces.items():
        if len(adjacent_faces) == 1 or edge in mesh.sharp_edges:
            edge_points[edge] = edge_midpoints[edge]
        else:
            face_sum = (0.0, 0.0, 0.0)
            for face_index in adjacent_faces[:2]:
                face_sum = vec_add(face_sum, face_points[face_index])
            edge_points[edge] = vec_scale(
                vec_add(vec_add(mesh.vertices[edge[0]], mesh.vertices[edge[1]]), face_sum),
                0.25,
            )

    new_vertices = list(mesh.vertices)
    for vertex_index, vertex in enumerate(mesh.vertices):
        incident_edges = [edge for edge in edge_faces if vertex_index in edge]
        incident_faces = sorted(
            {
                face_index
                for edge in incident_edges
                for face_index in edge_faces[edge]
            }
        )
        crease_neighbors = [
            edge[1] if edge[0] == vertex_index else edge[0]
            for edge in incident_edges
            if len(edge_faces[edge]) == 1 or edge in mesh.sharp_edges
        ]
        is_boundary = any(len(edge_faces[edge]) == 1 for edge in incident_edges)
        if vertex_index in mesh.corner_vertices or _is_corner(
            vertex, crease_neighbors, mesh.vertices
        ):
            new_vertices[vertex_index] = vertex
        elif len(crease_neighbors) == 2:
            neighbor_sum = vec_add(
                mesh.vertices[crease_neighbors[0]],
                mesh.vertices[crease_neighbors[1]],
            )
            new_vertices[vertex_index] = vec_scale(
                vec_add(vec_scale(vertex, 6.0), neighbor_sum), 0.125
            )
        elif is_boundary:
            new_vertices[vertex_index] = vertex
        else:
            new_vertices[vertex_index] = _smooth_vertex(
                vertex,
                incident_faces,
                incident_edges,
                face_points,
                edge_midpoints,
            )

    edge_indices: dict[tuple[int, int], int] = {}
    for edge in sorted(edge_points):
        edge_indices[edge] = len(new_vertices)
        new_vertices.append(edge_points[edge])
    face_indices: dict[int, int] = {}
    for face_index in range(len(mesh.faces)):
        face_indices[face_index] = len(new_vertices)
        new_vertices.append(face_points[face_index])

    new_faces = []
    for face_index, face in enumerate(mesh.faces):
        for offset, vertex_index in enumerate(face):
            previous = face[(offset - 1) % len(face)]
            following = face[(offset + 1) % len(face)]
            new_faces.append(
                (
                    vertex_index,
                    edge_indices[_edge_key(vertex_index, following)],
                    face_indices[face_index],
                    edge_indices[_edge_key(previous, vertex_index)],
                )
            )

    new_sharp_edges: set[tuple[int, int]] = set()
    for a, b in mesh.sharp_edges:
        midpoint_index = edge_indices[_edge_key(a, b)]
        new_sharp_edges.add(_edge_key(a, midpoint_index))
        new_sharp_edges.add(_edge_key(midpoint_index, b))

    return Mesh(
        vertices=tuple(new_vertices),
        faces=tuple(new_faces),
        sharp_edges=frozenset(new_sharp_edges),
        corner_vertices=frozenset(),
    )


def _face_normal(mesh: Mesh, face: tuple[int, ...]) -> Vec3:
    normal = (0.0, 0.0, 0.0)
    for offset, vertex_index in enumerate(face):
        current = mesh.vertices[vertex_index]
        following = mesh.vertices[face[(offset + 1) % len(face)]]
        normal = vec_add(
            normal,
            vec_cross(
                current,
                following,
            ),
        )
    return vec_normalize(normal)


def sharp_dihedral_degrees(mesh: Mesh) -> list[float]:
    edge_faces = _edge_map(mesh)
    normals = {
        face_index: _face_normal(mesh, face)
        for face_index, face in enumerate(mesh.faces)
    }
    angles = []
    for edge in mesh.sharp_edges:
        adjacent = edge_faces.get(_edge_key(*edge), [])
        if len(adjacent) != 2:
            continue
        dot = max(-1.0, min(1.0, vec_dot(normals[adjacent[0]], normals[adjacent[1]])))
        angles.append(degrees(acos(dot)))
    return angles


def boundary_edges(mesh: Mesh) -> list[tuple[int, int]]:
    return [edge for edge, faces in _edge_map(mesh).items() if len(faces) == 1]


def boundary_vertices(mesh: Mesh) -> set[int]:
    return {vertex for edge in boundary_edges(mesh) for vertex in edge}


def sharp_edge_max_deviation(mesh: Mesh, point: Vec3, direction: Vec3) -> float:
    direction = vec_normalize(direction)
    if vec_length(direction) == 0.0:
        return 0.0
    vertex_indices = {vertex for edge in mesh.sharp_edges for vertex in edge}
    maximum = 0.0
    for vertex_index in vertex_indices:
        relative = vec_sub(mesh.vertices[vertex_index], point)
        perpendicular = vec_sub(relative, vec_scale(direction, vec_dot(relative, direction)))
        maximum = max(maximum, vec_length(perpendicular))
    return maximum


def subdivide_mesh(mesh: Mesh, levels: int = 1) -> SubdivisionResult:
    if levels < 0:
        raise ValueError("levels must be non-negative")
    for face in mesh.faces:
        if len(face) < 3:
            raise ValueError("faces must have at least three vertices")
        if any(index < 0 or index >= len(mesh.vertices) for index in face):
            raise ValueError("face references an invalid vertex")

    result = mesh
    for _ in range(levels):
        result = _subdivide_once(result)

    boundary = boundary_vertices(result)
    crease_angles = sharp_dihedral_degrees(result)
    stats: dict[str, float | int] = {
        "vertices": len(result.vertices),
        "faces": len(result.faces),
        "edges": len(_edge_map(result)),
        "boundary_edges": len(boundary_edges(result)),
        "boundary_vertices": len(boundary),
        "interior_vertices": len(result.vertices) - len(boundary),
        "sharp_edges": len(result.sharp_edges),
        "min_sharp_dihedral_deg": min(crease_angles) if crease_angles else 0.0,
        "max_sharp_dihedral_deg": max(crease_angles) if crease_angles else 0.0,
    }
    return SubdivisionResult(mesh=result, levels=levels, stats=stats)
