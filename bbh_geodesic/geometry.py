"""Small dependency-free 3D geometry kernel used by the experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

Vec3 = tuple[float, float, float]


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


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
    n = length(a)
    if n <= 1e-15:
        return (0.0, 0.0, 0.0)
    return scale(a, 1.0 / n)


Mat3 = tuple[Vec3, Vec3, Vec3]
IDENTITY3: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def mat_mul(a: Mat3, b: Mat3) -> Mat3:
    return tuple(
        tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3))
        for r in range(3)
    )  # type: ignore[return-value]


def mat_vec(a: Mat3, v: Vec3) -> Vec3:
    return tuple(sum(a[r][k] * v[k] for k in range(3)) for r in range(3))  # type: ignore[return-value]


def rotation_xyz(rx: float, ry: float, rz: float) -> Mat3:
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rxm: Mat3 = ((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx))
    rym: Mat3 = ((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy))
    rzm: Mat3 = ((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0))
    return mat_mul(mat_mul(rxm, rym), rzm)


@dataclass(frozen=True)
class Transform:
    rotation: Mat3 = IDENTITY3
    translation: Vec3 = (0.0, 0.0, 0.0)

    def apply(self, p: Vec3) -> Vec3:
        return add(mat_vec(self.rotation, p), self.translation)

    def compose(self, child: "Transform") -> "Transform":
        return Transform(
            mat_mul(self.rotation, child.rotation),
            add(mat_vec(self.rotation, child.translation), self.translation),
        )


@dataclass(frozen=True)
class AABB:
    minimum: Vec3
    maximum: Vec3

    @classmethod
    def from_points(cls, points: Iterable[Vec3]) -> "AABB":
        iterator = iter(points)
        try:
            first = next(iterator)
        except StopIteration:
            raise ValueError("an AABB needs at least one point")
        lo = list(first)
        hi = list(first)
        for point in iterator:
            for axis in range(3):
                lo[axis] = min(lo[axis], point[axis])
                hi[axis] = max(hi[axis], point[axis])
        return cls(tuple(lo), tuple(hi))  # type: ignore[arg-type]

    @classmethod
    def from_boxes(cls, boxes: Sequence["AABB"]) -> "AABB":
        if not boxes:
            raise ValueError("at least one box is required")
        lo = [min(box.minimum[a] for box in boxes) for a in range(3)]
        hi = [max(box.maximum[a] for box in boxes) for a in range(3)]
        return cls(tuple(lo), tuple(hi))  # type: ignore[arg-type]

    @property
    def center(self) -> Vec3:
        return tuple((self.minimum[a] + self.maximum[a]) * 0.5 for a in range(3))  # type: ignore[return-value]

    @property
    def extents(self) -> Vec3:
        return tuple(self.maximum[a] - self.minimum[a] for a in range(3))  # type: ignore[return-value]

    @property
    def volume(self) -> float:
        ex, ey, ez = self.extents
        return max(0.0, ex) * max(0.0, ey) * max(0.0, ez)

    def expanded(self, padding: float) -> "AABB":
        p = (padding, padding, padding)
        return AABB(sub(self.minimum, p), add(self.maximum, p))

    def contains(self, point: Vec3, tolerance: float = 1e-9) -> bool:
        return all(
            self.minimum[a] - tolerance <= point[a] <= self.maximum[a] + tolerance
            for a in range(3)
        )

    def contains_box(self, other: "AABB", tolerance: float = 1e-9) -> bool:
        return all(
            self.minimum[a] - tolerance <= other.minimum[a]
            and other.maximum[a] <= self.maximum[a] + tolerance
            for a in range(3)
        )

    def intersects(self, other: "AABB") -> bool:
        return all(
            self.minimum[a] <= other.maximum[a]
            and other.minimum[a] <= self.maximum[a]
            for a in range(3)
        )

    def support_plane(self, normal: Vec3, offset: float) -> float:
        """Maximum of dot(normal, point) + offset over this box."""
        farthest = sum(
            normal[a] * (self.maximum[a] if normal[a] >= 0.0 else self.minimum[a])
            for a in range(3)
        )
        return farthest + offset
