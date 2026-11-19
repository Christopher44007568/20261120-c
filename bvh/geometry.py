from __future__ import annotations

from dataclasses import dataclass
import math

Vec3 = tuple[float, float, float]
EPSILON = 1.0e-9


def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_length(a: Vec3) -> float:
    return math.sqrt(vec_dot(a, a))


def vec_normalize(a: Vec3) -> Vec3:
    length = vec_length(a)
    if length <= EPSILON:
        return (0.0, 0.0, 0.0)
    return vec_mul(a, 1.0 / length)


@dataclass(slots=True)
class AABB:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @classmethod
    def from_points(cls, points: tuple[Vec3, ...]) -> AABB:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        return cls(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    @property
    def min(self) -> Vec3:
        return (self.min_x, self.min_y, self.min_z)

    @property
    def max(self) -> Vec3:
        return (self.max_x, self.max_y, self.max_z)

    @property
    def center(self) -> Vec3:
        return (
            0.5 * (self.min_x + self.max_x),
            0.5 * (self.min_y + self.max_y),
            0.5 * (self.min_z + self.max_z),
        )

    def extent(self, axis: int) -> float:
        if axis == 0:
            return self.max_x - self.min_x
        if axis == 1:
            return self.max_y - self.min_y
        return self.max_z - self.min_z

    @property
    def surface_area(self) -> float:
        dx = self.max_x - self.min_x
        dy = self.max_y - self.min_y
        dz = self.max_z - self.min_z
        return 2.0 * (dx * dy + dy * dz + dz * dx)

    @property
    def volume(self) -> float:
        return max(0.0, self.max_x - self.min_x) * max(
            0.0, self.max_y - self.min_y
        ) * max(0.0, self.max_z - self.min_z)

    def contains_point(self, point: Vec3) -> bool:
        return (
            self.min_x <= point[0] <= self.max_x
            and self.min_y <= point[1] <= self.max_y
            and self.min_z <= point[2] <= self.max_z
        )

    def contains_aabb(self, other: AABB) -> bool:
        return (
            self.min_x <= other.min_x
            and self.min_y <= other.min_y
            and self.min_z <= other.min_z
            and self.max_x >= other.max_x
            and self.max_y >= other.max_y
            and self.max_z >= other.max_z
        )

    def merged(self, other: AABB) -> AABB:
        return AABB(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            min(self.min_z, other.min_z),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
            max(self.max_z, other.max_z),
        )

    def intersection(self, other: AABB) -> AABB | None:
        result = AABB(
            max(self.min_x, other.min_x),
            max(self.min_y, other.min_y),
            max(self.min_z, other.min_z),
            min(self.max_x, other.max_x),
            min(self.max_y, other.max_y),
            min(self.max_z, other.max_z),
        )
        if result.min_x > result.max_x:
            return None
        if result.min_y > result.max_y:
            return None
        if result.min_z > result.max_z:
            return None
        return result

    def as_dict(self) -> dict[str, list[float] | float]:
        return {
            "min": list(self.min),
            "max": list(self.max),
            "surface_area": self.surface_area,
            "volume": self.volume,
        }


def union_bounds(bounds: list[AABB]) -> AABB:
    if not bounds:
        raise ValueError("bounds must not be empty")
    result = bounds[0]
    for bound in bounds[1:]:
        result = result.merged(bound)
    return result


@dataclass(slots=True)
class Ray:
    origin: Vec3
    direction: Vec3
    t_min: float = 0.0
    t_max: float = math.inf

    def at(self, t: float) -> Vec3:
        return vec_add(self.origin, vec_mul(self.direction, t))


@dataclass(slots=True)
class RayHit:
    t: float
    u: float
    v: float
    triangle_index: int


def ray_aabb_interval(ray: Ray, bounds: AABB) -> tuple[float, float] | None:
    t_near = ray.t_min
    t_far = ray.t_max

    for origin, direction, lower, upper in (
        (ray.origin[0], ray.direction[0], bounds.min_x, bounds.max_x),
        (ray.origin[1], ray.direction[1], bounds.min_y, bounds.max_y),
        (ray.origin[2], ray.direction[2], bounds.min_z, bounds.max_z),
    ):
        if abs(direction) <= EPSILON:
            if origin < lower or origin > upper:
                return None
            continue
        inv = 1.0 / direction
        t0 = (lower - origin) * inv
        t1 = (upper - origin) * inv
        if t0 > t1:
            t0, t1 = t1, t0
        t_near = max(t_near, t0)
        t_far = min(t_far, t1)
        if t_near > t_far:
            return None
    return t_near, t_far
