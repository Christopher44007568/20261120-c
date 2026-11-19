"""Small dependency-free mesh and vector helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path


Vec3 = tuple[float, float, float]
Edge = tuple[int, int]


def vadd(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec3) -> Vec3:
    size = length(a)
    return vmul(a, 1.0 / size) if size > 1e-15 else (0.0, 0.0, 0.0)


def edge(a: int, b: int) -> Edge:
    return (a, b) if a < b else (b, a)


def face_normal(vertices: list[Vec3], face: tuple[int, ...]) -> Vec3:
    a, b, c = (vertices[idx] for idx in face[:3])
    return normalize(cross(vsub(b, a), vsub(c, a)))


def polygon_area(vertices: list[Vec3], face: tuple[int, ...]) -> float:
    total: Vec3 = (0.0, 0.0, 0.0)
    origin = vertices[face[0]]
    for idx in range(1, len(face) - 1):
        total = vadd(
            total,
            cross(vsub(vertices[face[idx]], origin), vsub(vertices[face[idx + 1]], origin)),
        )
    return 0.5 * length(total)


@dataclass
class Mesh:
    vertices: list[Vec3]
    faces: list[tuple[int, ...]]
    feature_edges: set[Edge] = field(default_factory=set)
    name: str = "mesh"

    def edges(self) -> dict[Edge, list[int]]:
        result: dict[Edge, list[int]] = {}
        for face_index, face in enumerate(self.faces):
            for a, b in zip(face, face[1:] + face[:1]):
                result.setdefault(edge(a, b), []).append(face_index)
        return result

    def boundary_edges(self) -> set[Edge]:
        return {item for item, faces in self.edges().items() if len(faces) == 1}

    def stats(self) -> dict[str, int]:
        counts: dict[int, int] = {}
        for face in self.faces:
            counts[len(face)] = counts.get(len(face), 0) + 1
        return {
            "vertices": len(self.vertices),
            "faces": len(self.faces),
            **{f"faces_{size}": count for size, count in sorted(counts.items())},
            "edges": len(self.edges()),
            "feature_edges": len(self.feature_edges),
            "boundary_edges": len(self.boundary_edges()),
        }


def write_obj(mesh: Mesh, path: Path) -> None:
    lines = [f"# {mesh.name}", f"# vertices={len(mesh.vertices)} faces={len(mesh.faces)}"]
    lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in mesh.vertices)
    lines.extend("f " + " ".join(str(idx + 1) for idx in face) for face in mesh.faces)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mesh_json(mesh: Mesh, path: Path) -> None:
    payload = {
        "name": mesh.name,
        "stats": mesh.stats(),
        "vertices": [list(vertex) for vertex in mesh.vertices],
        "faces": [list(face) for face in mesh.faces],
        "feature_edges": [list(item) for item in sorted(mesh.feature_edges)],
    }
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
