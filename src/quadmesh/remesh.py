"""Constrained triangle pairing and all-quad subdivision fallback."""

from __future__ import annotations

import math
from collections import deque
from typing import Callable

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


def _angle(a: Vec3, b: Vec3, c: Vec3) -> float:
    u = normalize(vsub(a, b))
    v = normalize(vsub(c, b))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(u, v)))))


def quad_angles(vertices: list[Vec3], face: tuple[int, ...]) -> list[float]:
    count = len(face)
    return [
        _angle(vertices[face[(idx - 1) % count]], vertices[face[idx]], vertices[face[(idx + 1) % count]])
        for idx in range(count)
    ]


def quad_quality(vertices: list[Vec3], face: tuple[int, ...]) -> float:
    """Angle-based scaled quality: 1 for a square, 0 for a degenerate corner."""
    angles = quad_angles(vertices, face)
    return min(min(angle, 180.0 - angle) / 90.0 for angle in angles)


def _cycle_from_triangle_pair(
    a: int, b: int, first_other: int, second_other: int
) -> tuple[int, int, int, int] | None:
    adjacency = {
        a: [first_other, second_other],
        b: [first_other, second_other],
        first_other: [a, b],
        second_other: [a, b],
    }
    if any(len(items) != 2 for items in adjacency.values()):
        return None
    start = min(adjacency)
    cycle = [start]
    previous = -1
    current = start
    for _ in range(3):
        candidates = [item for item in adjacency[current] if item != previous]
        if not candidates:
            return None
        previous, current = current, candidates[0]
        cycle.append(current)
    if current == start or len(set(cycle[:3])) != 3:
        return None
    return tuple(cycle[:3]) + (cycle[3],)  # type: ignore[return-value]


def _pair_candidate(
    mesh: Mesh, shared: Edge, first: int, second: int
) -> tuple[float, tuple[int, int, int, int]] | None:
    f1 = mesh.faces[first]
    f2 = mesh.faces[second]
    other1 = next(idx for idx in f1 if idx not in shared)
    other2 = next(idx for idx in f2 if idx not in shared)
    quad = _cycle_from_triangle_pair(shared[0], shared[1], other1, other2)
    if quad is None:
        return None
    normal_a = face_normal(mesh.vertices, f1)
    normal_b = face_normal(mesh.vertices, f2)
    average_normal = normalize(vadd(normal_a, normal_b))
    if dot(face_normal(mesh.vertices, quad), average_normal) < 0.0:
        quad = quad[::-1]
    angles = quad_angles(mesh.vertices, quad)
    if min(angles) <= 20.0 or max(angles) >= 160.0:
        return None
    edge_lengths = [
        math.dist(mesh.vertices[quad[idx]], mesh.vertices[quad[(idx + 1) % 4]])
        for idx in range(4)
    ]
    if min(edge_lengths) <= 1e-12:
        return None
    angle_score = max(0.0, 1.0 - sum(abs(angle - 90.0) for angle in angles) / 180.0)
    aspect_score = min(edge_lengths) / max(edge_lengths)
    planarity = max(0.0, dot(normal_a, normal_b))
    diagonal = math.dist(mesh.vertices[shared[0]], mesh.vertices[shared[1]])
    side_mean = sum(edge_lengths) / 4.0
    diagonal_score = min(diagonal / side_mean, 1.5) / 1.5
    score = 0.50 * angle_score + 0.20 * aspect_score + 0.18 * planarity + 0.12 * diagonal_score
    return score, quad


def _maximum_cardinality_augment(
    match: list[int],
    adjacency: list[list[int]],
    weights: dict[tuple[int, int], float],
) -> list[int]:
    """Edmonds' blossom augmentation, seeded with an existing matching."""
    count = len(match)
    parent = [-1] * count
    base = list(range(count))
    used = [False] * count
    blossom = [False] * count

    def lowest_common_ancestor(first: int, second: int) -> int:
        on_path = [False] * count
        while True:
            first = base[first]
            on_path[first] = True
            if match[first] == -1:
                break
            first = parent[match[first]]
        while True:
            second = base[second]
            if on_path[second]:
                return second
            second = parent[match[second]]

    def mark_path(vertex: int, blossom_base: int, child: int) -> None:
        while base[vertex] != blossom_base:
            blossom[base[vertex]] = True
            blossom[base[match[vertex]]] = True
            parent[vertex] = child
            child = match[vertex]
            vertex = parent[match[vertex]]

    def find_path(root: int) -> int:
        nonlocal parent, base, used, blossom
        parent = [-1] * count
        base = list(range(count))
        used = [False] * count
        queue = deque([root])
        used[root] = True
        while queue:
            vertex = queue.popleft()
            for neighbor in adjacency[vertex]:
                if base[vertex] == base[neighbor] or match[vertex] == neighbor:
                    continue
                if neighbor == root or (match[neighbor] != -1 and parent[match[neighbor]] != -1):
                    common = lowest_common_ancestor(vertex, neighbor)
                    blossom = [False] * count
                    mark_path(vertex, common, neighbor)
                    mark_path(neighbor, common, vertex)
                    for idx in range(count):
                        if blossom[base[idx]]:
                            base[idx] = common
                            if not used[idx]:
                                used[idx] = True
                                queue.append(idx)
                elif parent[neighbor] == -1:
                    parent[neighbor] = vertex
                    if match[neighbor] == -1:
                        return neighbor
                    next_vertex = match[neighbor]
                    used[next_vertex] = True
                    queue.append(next_vertex)
        return -1

    for root in range(count):
        if match[root] != -1:
            continue
        endpoint = find_path(root)
        while endpoint != -1:
            previous = parent[endpoint]
            previous_match = match[previous]
            match[endpoint] = previous
            match[previous] = endpoint
            endpoint = previous_match

    # Pair swaps preserve cardinality and improve the score locally.
    changed = True
    passes = 0
    while changed and passes < 12:
        passes += 1
        changed = False
        for first in range(count):
            second = match[first]
            if second == -1 or second < first:
                continue
            for third in adjacency[first]:
                if third == second or match[third] == -1:
                    continue
                fourth = match[third]
                if fourth == first or fourth == second:
                    continue
                old = weights.get((min(first, second), max(first, second)), 0.0)
                old += weights.get((min(third, fourth), max(third, fourth)), 0.0)
                options = (
                    ((min(first, third), max(first, third)), (min(second, fourth), max(second, fourth))),
                    ((min(first, fourth), max(first, fourth)), (min(second, third), max(second, third))),
                )
                for option_a, option_b in options:
                    if option_a not in weights or option_b not in weights:
                        continue
                    new = weights[option_a] + weights[option_b]
                    if new <= old + 1e-12:
                        continue
                    match[first], match[third] = third, first
                    match[second], match[fourth] = fourth, second
                    changed = True
                    break
                if changed:
                    break
            if changed:
                break
    return match


def greedy_quad_pairing(mesh: Mesh, min_score: float = 0.52) -> tuple[Mesh, dict[str, int]]:
    """Pair adjacent triangles into quads without cutting tagged feature edges."""
    if any(len(face) != 3 for face in mesh.faces):
        raise ValueError("greedy_quad_pairing expects a pure triangle mesh")
    candidates: list[tuple[float, Edge, int, int, tuple[int, int, int, int]]] = []
    adjacency: list[list[int]] = [[] for _ in mesh.faces]
    weights: dict[tuple[int, int], float] = {}
    for item, incident in mesh.edges().items():
        if len(incident) != 2 or item in mesh.feature_edges:
            continue
        candidate = _pair_candidate(mesh, item, incident[0], incident[1])
        if candidate is not None and candidate[0] >= min_score:
            _, quad = candidate
            quality = quad_quality(mesh.vertices, quad)
            candidates.append((quality, item, incident[0], incident[1], quad))
            weights[(min(incident[0], incident[1]), max(incident[0], incident[1]))] = quality
            adjacency[incident[0]].append(incident[1])
            adjacency[incident[1]].append(incident[0])
    candidates.sort(key=lambda record: (-record[0], record[1]))

    matched = [-1] * len(mesh.faces)
    quads_by_first: dict[int, tuple[int, ...]] = {}
    for _, _, first, second, quad in candidates:
        if matched[first] != -1 or matched[second] != -1:
            continue
        matched[first] = second
        matched[second] = first
        quads_by_first[min(first, second)] = quad

    unmatched = [idx for idx, partner in enumerate(matched) if partner == -1]
    if unmatched:
        matched = _maximum_cardinality_augment(matched, adjacency, weights)
        quads_by_first = {}
        for (first, second), _ in weights.items():
            if matched[first] != second:
                continue
            shared = set(mesh.faces[first]) & set(mesh.faces[second])
            if len(shared) != 2:
                continue
            item = edge(*shared)
            candidate = _pair_candidate(mesh, item, first, second)
            if candidate is not None:
                quads_by_first[first] = candidate[1]
        unmatched = [idx for idx, partner in enumerate(matched) if partner == -1]
    if unmatched:
        rescue: list[tuple[float, Edge, int, int, tuple[int, int, int, int]]] = []
        unmatched_set = set(unmatched)
        for item, incident in mesh.edges().items():
            if len(incident) != 2 or item in mesh.feature_edges:
                continue
            if incident[0] not in unmatched_set or incident[1] not in unmatched_set:
                continue
            candidate = _pair_candidate(mesh, item, incident[0], incident[1])
            if candidate is not None:
                rescue.append((candidate[0], item, incident[0], incident[1], candidate[1]))
        for _, _, first, second, quad in sorted(rescue, key=lambda record: (-record[0], record[1])):
            if matched[first] != -1 or matched[second] != -1:
                continue
            matched[first] = second
            matched[second] = first
            quads_by_first[first] = quad
        unmatched = [idx for idx, partner in enumerate(matched) if partner == -1]

    if unmatched:
        # A controlled fallback keeps the output conforming and all-quad.
        fallback = triangle_quad_subdivision(mesh)
        fallback.name = f"{mesh.name}_fallback"
        return fallback, {
            "paired_triangles": len(mesh.faces) - len(unmatched),
            "unmatched_triangles": len(unmatched),
            "fallback": 1,
        }

    output = Mesh(
        vertices=list(mesh.vertices),
        faces=[quads_by_first[idx] for idx in sorted(quads_by_first)],
        feature_edges=set(mesh.feature_edges),
        name=f"{mesh.name}_remeshed",
    )
    return output, {
        "paired_triangles": len(mesh.faces),
        "unmatched_triangles": 0,
        "fallback": 0,
    }


def triangle_quad_subdivision(mesh: Mesh) -> Mesh:
    """Conforming 1-to-3 quad subdivision used only when matching is incomplete."""
    vertices = list(mesh.vertices)
    midpoint_ids: dict[Edge, int] = {}
    centroid_ids: dict[int, int] = {}

    def midpoint(a: int, b: int) -> int:
        key = edge(a, b)
        if key not in midpoint_ids:
            midpoint_ids[key] = len(vertices)
            vertices.append(vmul(vadd(mesh.vertices[a], mesh.vertices[b]), 0.5))
        return midpoint_ids[key]

    faces: list[tuple[int, ...]] = []
    output_features: set[Edge] = set()
    for face_index, face in enumerate(mesh.faces):
        a, b, c = face
        mab, mbc, mca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        centroid_ids[face_index] = len(vertices)
        center = len(vertices)
        vertices.append(vmul(vadd(vadd(mesh.vertices[a], mesh.vertices[b]), mesh.vertices[c]), 1.0 / 3.0))
        faces.extend(
            (
                (a, mab, center, mca),
                (b, mbc, center, mab),
                (c, mca, center, mbc),
            )
        )
        for first, second, middle in ((a, b, mab), (b, c, mbc), (c, a, mca)):
            if edge(first, second) in mesh.feature_edges:
                output_features.add(edge(first, middle))
                output_features.add(edge(middle, second))
    return Mesh(vertices, faces, output_features, name=f"{mesh.name}_subdivided")


def tangential_relax(
    mesh: Mesh,
    project: Callable[[Vec3], Vec3],
    iterations: int = 4,
    step: float = 0.20,
) -> Mesh:
    """Relax non-feature vertices tangentially, then project back to the surface."""
    neighbors: dict[int, set[int]] = {}
    locked: set[int] = set()
    for item in mesh.edges():
        a, b = item
        neighbors.setdefault(a, set()).add(b)
        neighbors.setdefault(b, set()).add(a)
        if item in mesh.feature_edges:
            locked.update(item)
    vertices = list(mesh.vertices)
    for _ in range(iterations):
        updated = list(vertices)
        for idx, point in enumerate(vertices):
            if idx in locked or len(neighbors.get(idx, ())) < 3:
                continue
            target = vmul(
                sum((vertices[item] for item in neighbors[idx]), (0.0, 0.0, 0.0)),  # type: ignore[arg-type]
                1.0 / len(neighbors[idx]),
            )
            delta = vsub(target, point)
            radial = normalize(point)
            tangential = vsub(delta, vmul(radial, dot(delta, radial)))
            updated[idx] = project(vadd(point, vmul(tangential, step)))
        vertices = updated
    return Mesh(vertices, list(mesh.faces), set(mesh.feature_edges), name=mesh.name)
