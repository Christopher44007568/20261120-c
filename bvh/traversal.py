from __future__ import annotations

from dataclasses import dataclass, field
import time

from .builders import BVH
from .geometry import EPSILON, Ray, RayHit, vec_cross, vec_dot, vec_sub
from .mesh import Triangle


@dataclass(slots=True)
class TraversalStats:
    ray_count: int = 0
    node_visits: int = 0
    triangle_tests: int = 0
    hit_count: int = 0
    elapsed_ms: float = 0.0
    total_t: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "ray_count": self.ray_count,
            "node_visits": self.node_visits,
            "triangle_tests": self.triangle_tests,
            "hit_count": self.hit_count,
            "elapsed_ms": self.elapsed_ms,
            "total_t": self.total_t,
            "node_visits_per_ray": (
                self.node_visits / self.ray_count if self.ray_count else 0.0
            ),
            "triangle_tests_per_ray": (
                self.triangle_tests / self.ray_count if self.ray_count else 0.0
            ),
        }


@dataclass(slots=True)
class TraversalResult:
    stats: TraversalStats
    hits: list[RayHit | None] = field(default_factory=list)


def intersect_triangle(
    ray: Ray, triangle: Triangle, triangle_index: int, closest_t: float
) -> RayHit | None:
    edge1 = vec_sub(triangle.v1, triangle.v0)
    edge2 = vec_sub(triangle.v2, triangle.v0)
    direction_cross_edge2 = vec_cross(ray.direction, edge2)
    determinant = vec_dot(edge1, direction_cross_edge2)
    if abs(determinant) <= EPSILON:
        return None
    inverse = 1.0 / determinant
    origin_to_v0 = vec_sub(ray.origin, triangle.v0)
    u = inverse * vec_dot(origin_to_v0, direction_cross_edge2)
    if u < 0.0 or u > 1.0:
        return None
    origin_cross_edge1 = vec_cross(origin_to_v0, edge1)
    v = inverse * vec_dot(ray.direction, origin_cross_edge1)
    if v < 0.0 or u + v > 1.0:
        return None
    t = inverse * vec_dot(edge2, origin_cross_edge1)
    if t <= ray.t_min or t >= closest_t or t >= ray.t_max:
        return None
    return RayHit(t=t, u=u, v=v, triangle_index=triangle_index)


def intersect_brute_force(
    triangles: list[Triangle], ray: Ray
) -> RayHit | None:
    nearest: RayHit | None = None
    closest_t = ray.t_max
    for primitive, triangle in enumerate(triangles):
        hit = intersect_triangle(ray, triangle, primitive, closest_t)
        if hit is not None:
            nearest = hit
            closest_t = hit.t
    return nearest


def traverse(
    bvh: BVH,
    triangles: list[Triangle],
    rays: list[Ray],
    collect_hits: bool = True,
) -> TraversalResult:
    stats = TraversalStats(ray_count=len(rays))
    hits: list[RayHit | None] = []
    start_time = time.perf_counter()
    for ray in rays:
        nearest = _traverse_ray(bvh, triangles, ray, stats)
        if nearest is not None:
            stats.hit_count += 1
            stats.total_t += nearest.t
        if collect_hits:
            hits.append(nearest)
    stats.elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    return TraversalResult(stats=stats, hits=hits)


def _traverse_ray(
    bvh: BVH, triangles: list[Triangle], ray: Ray, stats: TraversalStats
) -> RayHit | None:
    from .geometry import ray_aabb_interval

    root_interval = ray_aabb_interval(ray, bvh.nodes[bvh.root].bounds)
    if root_interval is None:
        return None
    stack: list[tuple[int, float]] = [(bvh.root, root_interval[0])]
    nearest: RayHit | None = None
    closest_t = ray.t_max
    while stack:
        node_index, entry_t = stack.pop()
        if entry_t > closest_t:
            continue
        stats.node_visits += 1
        node = bvh.nodes[node_index]
        if node.is_leaf:
            end = node.start + node.count
            for order_index in range(node.start, end):
                primitive = bvh.order[order_index]
                stats.triangle_tests += 1
                hit = intersect_triangle(
                    ray, triangles[primitive], primitive, closest_t
                )
                if hit is not None:
                    nearest = hit
                    closest_t = hit.t
            continue
        left_interval = ray_aabb_interval(ray, bvh.nodes[node.left].bounds)
        right_interval = ray_aabb_interval(ray, bvh.nodes[node.right].bounds)
        children: list[tuple[float, int]] = []
        if left_interval is not None and left_interval[0] <= closest_t:
            children.append((left_interval[0], node.left))
        if right_interval is not None and right_interval[0] <= closest_t:
            children.append((right_interval[0], node.right))
        if len(children) == 2 and children[0][0] > children[1][0]:
            children.reverse()
        for child_entry, child_index in reversed(children):
            stack.append((child_index, child_entry))
    return nearest
