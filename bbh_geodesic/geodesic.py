"""Geodesic shortest paths on a height-field surface with a circular obstacle."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from .geometry import Vec3

Point2 = tuple[float, float]


@dataclass
class SurfaceMesh:
    vertices: list[Vec3]
    adjacency: list[list[tuple[int, float]]]
    spacing: float
    obstacle_radius: float
    curved: bool


def surface_height(x: float, y: float, obstacle_radius: float, curved: bool) -> float:
    if not curved:
        return 0.0
    radius = math.hypot(x, y)
    outer = 2.40
    t = max(0.0, min(1.0, (radius - obstacle_radius) / (outer - obstacle_radius)))
    theta = math.atan2(y, x)
    return 0.18 * t * t + 0.032 * math.sin(3.0 * theta) * math.sin(math.pi * t)


def _neighbor_moves() -> tuple[tuple[int, int], ...]:
    moves: list[tuple[int, int]] = []
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if (dx == 0 and dy == 0) or math.gcd(abs(dx), abs(dy)) != 1:
                continue
            if dx * dx + dy * dy <= 10:
                moves.append((dx, dy))
    return tuple(moves)


def build_surface(
    spacing: float = 0.02,
    obstacle_radius: float = 0.60,
    domain_radius: float = 1.80,
    curved: bool = False,
) -> SurfaceMesh:
    count = int(round(2.0 * domain_radius / spacing)) + 1
    coordinates = [-domain_radius + i * spacing for i in range(count)]
    index_by_grid: dict[tuple[int, int], int] = {}
    vertices: list[Vec3] = []
    for iy, y in enumerate(coordinates):
        for ix, x in enumerate(coordinates):
            if x * x + y * y <= obstacle_radius * obstacle_radius:
                continue
            index_by_grid[(ix, iy)] = len(vertices)
            vertices.append((x, y, surface_height(x, y, obstacle_radius, curved)))

    adjacency: list[list[tuple[int, float]]] = [[] for _ in vertices]

    def connect(a: int, b: int) -> None:
        ax, ay = vertices[a][0], vertices[a][1]
        bx, by = vertices[b][0], vertices[b][1]
        if _point_segment_distance_2d((0.0, 0.0), (ax, ay), (bx, by)) < obstacle_radius - 1e-12:
            return
        weight = math.dist(vertices[a], vertices[b])
        adjacency[a].append((b, weight))
        adjacency[b].append((a, weight))

    for (ix, iy), current in index_by_grid.items():
        for dx, dy in _neighbor_moves():
            neighbor = index_by_grid.get((ix + dx, iy + dy))
            if neighbor is not None and current < neighbor:
                connect(current, neighbor)
    return SurfaceMesh(vertices, adjacency, spacing, obstacle_radius, curved)


def nearest_vertex(mesh: SurfaceMesh, point: Vec3) -> int:
    return min(
        range(len(mesh.vertices)),
        key=lambda i: (mesh.vertices[i][0] - point[0]) ** 2
        + (mesh.vertices[i][1] - point[1]) ** 2,
    )


def shortest_path(
    mesh: SurfaceMesh,
    start: Vec3,
    goal: Vec3,
) -> tuple[float, list[Vec3], list[int]]:
    source = nearest_vertex(mesh, start)
    target = nearest_vertex(mesh, goal)

    distances = [math.inf] * len(mesh.vertices)
    previous = [-1] * len(mesh.vertices)
    distances[source] = 0.0
    queue: list[tuple[float, int]] = [(0.0, source)]
    while queue:
        current_distance, node = heapq.heappop(queue)
        if current_distance > distances[node] + 1e-15:
            continue
        if node == target:
            break
        for neighbor, weight in mesh.adjacency[node]:
            candidate = current_distance + weight
            if candidate < distances[neighbor] - 1e-15:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if not math.isfinite(distances[target]):
        raise ValueError("start and goal are not connected")
    path_indices: list[int] = []
    cursor = target
    while cursor != -1:
        path_indices.append(cursor)
        if cursor == source:
            break
        cursor = previous[cursor]
    path_indices.reverse()
    points = [mesh.vertices[index] for index in path_indices]
    return distances[target], points, path_indices


def _wrap_angle(angle: float) -> float:
    while angle < 0.0:
        angle += 2.0 * math.pi
    while angle >= 2.0 * math.pi:
        angle -= 2.0 * math.pi
    return angle


def _arc_delta(a: float, b: float) -> float:
    difference = abs(_wrap_angle(a) - _wrap_angle(b))
    return min(difference, 2.0 * math.pi - difference)


def _point_segment_distance_2d(point: Point2, a: Point2, b: Point2) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    apx, apy = point[0] - a[0], point[1] - a[1]
    denominator = abx * abx + aby * aby
    if denominator <= 1e-30:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / denominator))
    return math.hypot(apx - t * abx, apy - t * aby)


def analytic_circle_path(
    start: Point2,
    goal: Point2,
    center: Point2,
    radius: float,
) -> dict[str, object]:
    """Exact planar shortest path outside a disk, including disjoint case."""
    sx, sy = start[0] - center[0], start[1] - center[1]
    gx, gy = goal[0] - center[0], goal[1] - center[1]
    ds, dg = math.hypot(sx, sy), math.hypot(gx, gy)
    if ds < radius or dg < radius:
        raise ValueError("start and goal must lie outside the obstacle")
    if _point_segment_distance_2d((0.0, 0.0), (sx, sy), (gx, gy)) >= radius:
        return {
            "distance": math.hypot(gx - sx, gy - sy),
            "points": [start, goal],
            "blocked": False,
        }

    alpha_s, alpha_g = math.atan2(sy, sx), math.atan2(gy, gx)
    beta_s, beta_g = math.acos(radius / ds), math.acos(radius / dg)
    best_length = math.inf
    best_pair: tuple[float, float] | None = None
    for tangent_s in (alpha_s + beta_s, alpha_s - beta_s):
        for tangent_g in (alpha_g + beta_g, alpha_g - beta_g):
            arc = _arc_delta(tangent_s, tangent_g)
            candidate = math.sqrt(ds * ds - radius * radius)
            candidate += math.sqrt(dg * dg - radius * radius)
            candidate += radius * arc
            if candidate < best_length:
                best_length = candidate
                best_pair = (tangent_s, tangent_g)
    assert best_pair is not None
    tangent_s, tangent_g = best_pair
    arc = _arc_delta(tangent_s, tangent_g)
    direction = 1.0 if _wrap_angle(tangent_g - tangent_s) <= math.pi else -1.0
    arc_steps = max(2, int(math.ceil(arc / (math.pi / 180.0))))
    points: list[Point2] = [start]
    for k in range(arc_steps + 1):
        angle = tangent_s + direction * arc * k / arc_steps
        points.append(
            (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
        )
    points.append(goal)
    return {"distance": best_length, "points": points, "blocked": True}


def polyline_length(points: list[Vec3]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def minimum_clearance(points: list[Vec3]) -> float:
    clearance = math.inf
    for a, b in zip(points, points[1:]):
        clearance = min(
            clearance,
            _point_segment_distance_2d((0.0, 0.0), (a[0], a[1]), (b[0], b[1])),
        )
    return clearance
