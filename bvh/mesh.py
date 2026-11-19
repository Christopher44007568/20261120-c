from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable

from .geometry import AABB, EPSILON, Vec3, vec_cross, vec_length, vec_sub


@dataclass(slots=True)
class Triangle:
    v0: Vec3
    v1: Vec3
    v2: Vec3
    bounds: AABB = field(init=False)
    centroid: Vec3 = field(init=False)

    def __post_init__(self) -> None:
        self.bounds = AABB.from_points((self.v0, self.v1, self.v2))
        self.centroid = self.bounds.center

    @property
    def vertices(self) -> tuple[Vec3, Vec3, Vec3]:
        return self.v0, self.v1, self.v2

    @property
    def area(self) -> float:
        return 0.5 * vec_length(vec_cross(vec_sub(self.v1, self.v0), vec_sub(self.v2, self.v0)))

    def set_vertices(self, v0: Vec3, v1: Vec3, v2: Vec3) -> None:
        self.v0, self.v1, self.v2 = v0, v1, v2
        self.bounds = AABB.from_points((v0, v1, v2))
        self.centroid = self.bounds.center

    def translated(self, delta: Vec3) -> Triangle:
        return Triangle(
            (self.v0[0] + delta[0], self.v0[1] + delta[1], self.v0[2] + delta[2]),
            (self.v1[0] + delta[0], self.v1[1] + delta[1], self.v1[2] + delta[2]),
            (self.v2[0] + delta[0], self.v2[1] + delta[1], self.v2[2] + delta[2]),
        )

    def as_dict(self) -> dict[str, list[float]]:
        return {
            "v0": list(self.v0),
            "v1": list(self.v1),
            "v2": list(self.v2),
        }


@dataclass(slots=True)
class MeshData:
    vertices: list[Vec3]
    indices: list[tuple[int, int, int]]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeshData:
        vertices = [tuple(float(value) for value in point) for point in data["vertices"]]
        indices = [tuple(int(value) for value in face) for face in data["indices"]]
        metadata = dict(data.get("metadata", {}))
        result = cls(vertices, indices, metadata)
        result.validate()
        return result

    def validate(self) -> None:
        vertex_count = len(self.vertices)
        if vertex_count == 0:
            raise ValueError("mesh has no vertices")
        if not self.indices:
            raise ValueError("mesh has no triangles")
        for face_index, face in enumerate(self.indices):
            if len(face) != 3:
                raise ValueError(f"triangle {face_index} does not have three indices")
            if any(index < 0 or index >= vertex_count for index in face):
                raise ValueError(f"triangle {face_index} has an out-of-range index")
            if len(set(face)) != 3:
                raise ValueError(f"triangle {face_index} has repeated vertex indices")

    def triangles(self) -> list[Triangle]:
        result: list[Triangle] = []
        for i, j, k in self.indices:
            triangle = Triangle(self.vertices[i], self.vertices[j], self.vertices[k])
            if triangle.area <= EPSILON:
                raise ValueError("mesh contains a degenerate triangle")
            result.append(triangle)
        return result

    def bounds(self) -> AABB:
        return AABB.from_points(tuple(self.vertices))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "bvh-mesh-v1",
            "vertices": [[round(value, 9) for value in point] for point in self.vertices],
            "indices": [list(face) for face in self.indices],
            "metadata": self.metadata,
        }


def load_mesh(path: str | Path) -> MeshData:
    with Path(path).open("r", encoding="utf-8") as handle:
        return MeshData.from_dict(json.load(handle))


def save_mesh(mesh: MeshData, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(mesh.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _random_triangle(
    rng: random.Random,
    center: Vec3,
    scale: float,
) -> Triangle:
    vertices: list[Vec3] = []
    for _ in range(3):
        point = (
            center[0] + rng.uniform(-scale, scale),
            center[1] + rng.uniform(-scale, scale),
            center[2] + rng.uniform(-scale, scale),
        )
        vertices.append(point)
    triangle = Triangle(vertices[0], vertices[1], vertices[2])
    if triangle.area <= EPSILON:
        return Triangle(
            (center[0] - scale, center[1], center[2]),
            (center[0], center[1] + scale, center[2]),
            (center[0], center[1], center[2] + scale),
        )
    return triangle


def generate_random_mesh(
    triangle_count: int = 1536,
    seed: int = 20261120,
    dense_triangle_count: int = 768,
    dense_region: tuple[Vec3, Vec3] = ((1.5, -1.5, -1.5), (3.5, 0.5, 0.5)),
    sparse_region: tuple[Vec3, Vec3] = ((-10.0, -10.0, -10.0), (10.0, 10.0, 10.0)),
    dense_triangle_scale: float = 0.07,
    sparse_triangle_scale: float = 0.55,
) -> MeshData:
    if triangle_count <= 0:
        raise ValueError("triangle_count must be positive")
    if dense_triangle_count < 0 or dense_triangle_count > triangle_count:
        raise ValueError("dense_triangle_count is out of range")

    rng = random.Random(seed)
    triangles: list[Triangle] = []
    for _ in range(dense_triangle_count):
        center = tuple(
            rng.uniform(dense_region[0][axis], dense_region[1][axis])
            for axis in range(3)
        )
        triangles.append(_random_triangle(rng, center, dense_triangle_scale))

    for _ in range(triangle_count - dense_triangle_count):
        center = tuple(
            rng.uniform(sparse_region[0][axis], sparse_region[1][axis])
            for axis in range(3)
        )
        triangles.append(_random_triangle(rng, center, sparse_triangle_scale))

    vertices: list[Vec3] = []
    indices: list[tuple[int, int, int]] = []
    for triangle in triangles:
        base = len(vertices)
        vertices.extend(triangle.vertices)
        indices.append((base, base + 1, base + 2))

    metadata = {
        "name": "random_triangle_mesh",
        "kind": "triangle_soup",
        "description": "Deterministic random triangles with one dense focus region.",
        "parameters": {
            "seed": seed,
            "triangle_count": triangle_count,
            "dense_triangle_count": dense_triangle_count,
            "dense_region": [list(dense_region[0]), list(dense_region[1])],
            "sparse_region": [list(sparse_region[0]), list(sparse_region[1])],
            "dense_triangle_scale": dense_triangle_scale,
            "sparse_triangle_scale": sparse_triangle_scale,
        },
        "focus_region": [list(dense_region[0]), list(dense_region[1])],
        "dynamic_group_selection": (
            "smallest-volume internal SAH subtree containing 16 to 32 triangles"
        ),
    }
    return MeshData(vertices, indices, metadata)


def make_fixed_mesh() -> MeshData:
    vertices: list[Vec3] = [
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    ]
    indices: list[tuple[int, int, int]] = [
        (0, 2, 1), (0, 3, 2),
        (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4),
        (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6),
        (3, 0, 4), (3, 4, 7),
    ]
    metadata = {
        "name": "fixed_index_cube",
        "kind": "indexed_triangle_mesh",
        "description": "A fixed 8-vertex, 12-triangle cube with shared vertices.",
        "parameters": {
            "vertex_count": 8,
            "triangle_count": 12,
            "cube_min": [-1.0, -1.0, -1.0],
            "cube_max": [1.0, 1.0, 1.0],
        },
    }
    mesh = MeshData(vertices, indices, metadata)
    mesh.validate()
    return mesh


def triangles_for_indices(
    triangles: list[Triangle], indices: Iterable[int]
) -> list[Triangle]:
    return [triangles[index] for index in indices]


def centroid_bounds(triangles: list[Triangle]) -> AABB:
    return AABB.from_points(tuple(triangle.centroid for triangle in triangles))


def scene_diagonal(bounds: AABB) -> float:
    dx = bounds.max_x - bounds.min_x
    dy = bounds.max_y - bounds.min_y
    dz = bounds.max_z - bounds.min_z
    return math.sqrt(dx * dx + dy * dy + dz * dz)
