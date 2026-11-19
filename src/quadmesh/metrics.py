"""Mesh-quality, distribution, and feature-retention metrics."""

from __future__ import annotations

import math
import statistics

from .geometry import Edge, Mesh, edge
from .remesh import quad_angles, quad_quality


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]

    mean = statistics.fmean(values)
    variance = statistics.fmean((value - mean) ** 2 for value in values)
    return {
        "count": len(values),
        "mean": mean,
        "variance": variance,
        "std": math.sqrt(variance),
        "cv": math.sqrt(variance) / mean if mean > 0.0 else 0.0,
        "min": ordered[0],
        "p05": percentile(0.05),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }


def edge_lengths(mesh: Mesh) -> list[float]:
    return [
        math.dist(mesh.vertices[first], mesh.vertices[second])
        for first, second in mesh.edges()
    ]


def face_angles(mesh: Mesh) -> list[float]:
    values: list[float] = []
    for face in mesh.faces:
        if len(face) == 4:
            values.extend(quad_angles(mesh.vertices, face))
            continue
        count = len(face)
        for idx in range(count):
            a = mesh.vertices[face[(idx - 1) % count]]
            b = mesh.vertices[face[idx]]
            c = mesh.vertices[face[(idx + 1) % count]]
            u = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
            v = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
            denominator = math.sqrt(sum(item * item for item in u) * sum(item * item for item in v))
            cosine = sum(x * y for x, y in zip(u, v)) / denominator if denominator else 1.0
            values.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return values


def histogram(values: list[float], bins: list[float]) -> list[dict[str, float | int]]:
    counts = [0] * (len(bins) - 1)
    for value in values:
        if value < bins[0] or value > bins[-1]:
            continue
        index = min(len(counts) - 1, max(0, int((value - bins[0]) / (bins[1] - bins[0]))))
        if value == bins[-1]:
            index = len(counts) - 1
        counts[index] += 1
    total = sum(counts)
    return [
        {
            "lower": bins[idx],
            "upper": bins[idx + 1],
            "count": counts[idx],
            "fraction": counts[idx] / total if total else 0.0,
        }
        for idx in range(len(counts))
    ]


def _bbox_diagonal(mesh: Mesh) -> float:
    minimum = [min(vertex[idx] for vertex in mesh.vertices) for idx in range(3)]
    maximum = [max(vertex[idx] for vertex in mesh.vertices) for idx in range(3)]
    return math.dist(minimum, maximum)


def _point_segment_distance(point: tuple[float, ...], first: tuple[float, ...], second: tuple[float, ...]) -> float:
    segment = tuple(b - a for a, b in zip(first, second))
    offset = tuple(p - a for p, a in zip(point, first))
    denominator = sum(item * item for item in segment)
    if denominator == 0.0:
        return math.dist(point, first)
    parameter = max(0.0, min(1.0, sum(a * b for a, b in zip(offset, segment)) / denominator))
    closest = tuple(a + parameter * b for a, b in zip(first, segment))
    return math.dist(point, closest)


def feature_retention(source: Mesh, output: Mesh) -> dict[str, float]:
    source_edges = sorted(source.feature_edges)
    output_edges = sorted(output.feature_edges)
    exact = sum(1 for item in source_edges if item in output.feature_edges)
    source_length = sum(math.dist(source.vertices[a], source.vertices[b]) for a, b in source_edges)
    retained_length = sum(
        math.dist(source.vertices[a], source.vertices[b])
        for a, b in source_edges
        if (a, b) in output.feature_edges
    )
    scale = max(_bbox_diagonal(source), 1e-12)
    tolerance = 0.002 * scale
    if exact == len(source_edges):
        return {
            "source_edges": len(source_edges),
            "exact_edges": exact,
            "exact_rate": 1.0,
            "length_weighted_rate": 1.0,
            "geometric_coverage_rate": 1.0,
            "max_deviation": 0.0,
            "max_deviation_normalized": 0.0,
            "tolerance_normalized": 0.002,
        }
    covered = 0.0
    maximum_distance = 0.0
    for a, b in source_edges:
        first, second = source.vertices[a], source.vertices[b]
        edge_length = math.dist(first, second)
        retained = True
        for step in range(5):
            fraction = step / 4.0
            point = tuple(x + fraction * (y - x) for x, y in zip(first, second))
            nearest = min(
                (
                    _point_segment_distance(point, output.vertices[c], output.vertices[d])
                    for c, d in output_edges
                ),
                default=float("inf"),
            )
            maximum_distance = max(maximum_distance, nearest)
            if nearest > tolerance:
                retained = False
        if retained:
            covered += edge_length
    return {
        "source_edges": len(source_edges),
        "exact_edges": exact,
        "exact_rate": exact / len(source_edges) if source_edges else 1.0,
        "length_weighted_rate": retained_length / source_length if source_length else 1.0,
        "geometric_coverage_rate": covered / source_length if source_length else 1.0,
        "max_deviation": maximum_distance,
        "max_deviation_normalized": maximum_distance / scale,
        "tolerance_normalized": 0.002,
    }


def manifold_report(mesh: Mesh) -> dict[str, int | bool]:
    incidence = mesh.edges()
    boundary = sum(1 for faces in incidence.values() if len(faces) == 1)
    nonmanifold = sum(1 for faces in incidence.values() if len(faces) > 2)
    degenerate = 0
    for face in mesh.faces:
        area = 0.0
        origin = mesh.vertices[face[0]]
        for idx in range(1, len(face) - 1):
            a = mesh.vertices[face[idx]]
            b = mesh.vertices[face[idx + 1]]
            u = (a[0] - origin[0], a[1] - origin[1], a[2] - origin[2])
            v = (b[0] - origin[0], b[1] - origin[1], b[2] - origin[2])
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            area += 0.5 * math.sqrt(sum(item * item for item in cross))
        if area < 1e-12:
            degenerate += 1
    return {
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "degenerate_faces": degenerate,
        "pure_quads": all(len(face) == 4 for face in mesh.faces),
        "closed": boundary == 0,
    }


def evaluate_pair(source: Mesh, output: Mesh) -> dict[str, object]:
    source_lengths = edge_lengths(source)
    output_lengths = edge_lengths(output)
    source_angles = face_angles(source)
    output_angles = face_angles(output)
    qualities = [quad_quality(output.vertices, face) for face in output.faces]
    angle_deviation = [abs(angle - 90.0) for angle in output_angles]
    length_max = max(source_lengths + output_lengths) * 1.01
    length_bins = [length_max * index / 20.0 for index in range(21)]
    return {
        "source_stats": source.stats(),
        "output_stats": output.stats(),
        "source_edge_length": _summary(source_lengths),
        "output_edge_length": _summary(output_lengths),
        "source_edge_length_histogram": histogram(source_lengths, length_bins),
        "output_edge_length_histogram": histogram(output_lengths, length_bins),
        "source_angles": _summary(source_angles),
        "output_angles": _summary(output_angles),
        "source_angle_histogram": histogram(source_angles, [float(item) for item in range(0, 181, 10)]),
        "output_angle_histogram": histogram(output_angles, [float(item) for item in range(0, 181, 10)]),
        "quality": _summary(qualities),
        "quality_histogram": histogram(
            qualities, [index / 20.0 for index in range(21)]
        ),
        "quality_ge_0_7": sum(value >= 0.7 for value in qualities) / len(qualities),
        "quality_ge_0_85": sum(value >= 0.85 for value in qualities) / len(qualities),
        "angles_within_15_deg_of_90": sum(value <= 15.0 for value in angle_deviation) / len(angle_deviation),
        "feature_retention": feature_retention(source, output),
        "manifold": manifold_report(output),
    }
