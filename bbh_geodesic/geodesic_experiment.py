"""Run flat/curved obstacle-surface shortest-path validation."""

from __future__ import annotations

import math
import time
from pathlib import Path

from .geodesic import (
    analytic_circle_path,
    build_surface,
    minimum_clearance,
    nearest_vertex,
    polyline_length,
    shortest_path,
)
from .io_utils import write_csv, write_json


def _path_rows(points: list[tuple[float, float, float]]) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    cumulative = 0.0
    for index, point in enumerate(points):
        segment = math.dist(points[index - 1], point) if index else 0.0
        cumulative += segment
        rows.append(
            {
                "step": index,
                "x_m": point[0],
                "y_m": point[1],
                "z_m": point[2],
                "segment_m": segment,
                "cumulative_m": cumulative,
            }
        )
    return rows


def _rounded(row: dict[str, object]) -> dict[str, object]:
    rounded: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, bool) or isinstance(value, int):
            rounded[key] = value
        elif isinstance(value, float):
            rounded[key] = round(value, 9)
        else:
            rounded[key] = value
    return rounded


def _solve(
    spacing: float,
    curved: bool,
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
) -> dict[str, object]:
    started = time.perf_counter()
    mesh = build_surface(spacing=spacing, curved=curved)
    start = mesh.vertices[nearest_vertex(mesh, (start_xy[0], start_xy[1], 0.0))]
    goal = mesh.vertices[nearest_vertex(mesh, (goal_xy[0], goal_xy[1], 0.0))]
    distance, points, indices = shortest_path(mesh, start, goal)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    measured = polyline_length(points)
    return {
        "spacing_m": spacing,
        "curved": curved,
        "mesh_vertices": len(mesh.vertices),
        "path_vertices": len(points),
        "start": start,
        "goal": goal,
        "distance_m": distance,
        "rederived_length_m": measured,
        "clearance_m": minimum_clearance(points),
        "solve_ms": elapsed_ms,
        "points": points,
        "indices": indices,
    }


def run_geodesic_experiment(artifact_dir: Path) -> dict[str, object]:
    start_xy = (-1.40, -0.52)
    goal_xy = (1.40, -0.52)
    analytic = analytic_circle_path(start_xy, goal_xy, (0.0, 0.0), 0.60)

    flat = _solve(0.015, False, start_xy, goal_xy)
    curved_coarse = _solve(0.02, True, start_xy, goal_xy)
    curved_fine = _solve(0.01, True, start_xy, goal_xy)

    analytic_distance = float(analytic["distance"])
    flat_error = abs(float(flat["distance_m"]) - analytic_distance) / analytic_distance
    curved_convergence = abs(
        float(curved_fine["distance_m"]) - float(curved_coarse["distance_m"])
    ) / float(curved_fine["distance_m"])
    euclidean_start_goal = math.dist(start_xy, goal_xy)

    rows = [
        {
            "case": "flat_mesh_dijkstra",
            "spacing_m": flat["spacing_m"],
            "mesh_vertices": flat["mesh_vertices"],
            "path_vertices": flat["path_vertices"],
            "distance_m": flat["distance_m"],
            "reference_m": analytic_distance,
            "relative_difference": flat_error,
            "clearance_m": flat["clearance_m"],
            "solve_ms": flat["solve_ms"],
        },
        {
            "case": "curved_coarse",
            "spacing_m": curved_coarse["spacing_m"],
            "mesh_vertices": curved_coarse["mesh_vertices"],
            "path_vertices": curved_coarse["path_vertices"],
            "distance_m": curved_coarse["distance_m"],
            "reference_m": curved_fine["distance_m"],
            "relative_difference": curved_convergence,
            "clearance_m": curved_coarse["clearance_m"],
            "solve_ms": curved_coarse["solve_ms"],
        },
        {
            "case": "curved_fine",
            "spacing_m": curved_fine["spacing_m"],
            "mesh_vertices": curved_fine["mesh_vertices"],
            "path_vertices": curved_fine["path_vertices"],
            "distance_m": curved_fine["distance_m"],
            "reference_m": curved_fine["distance_m"],
            "relative_difference": 0.0,
            "clearance_m": curved_fine["clearance_m"],
            "solve_ms": curved_fine["solve_ms"],
        },
    ]
    for row in rows:
        row["blocked_by_obstacle"] = analytic["blocked"]
        row["euclidean_start_goal_m"] = euclidean_start_goal
        row["path_longer_than_euclidean"] = float(row["distance_m"]) > euclidean_start_goal

    write_csv(
        artifact_dir / "geodesic_validation.csv",
        [_rounded(row) for row in rows],
    )
    write_csv(
        artifact_dir / "geodesic_path_curved.csv",
        [_rounded(row) for row in _path_rows(curved_fine["points"])],
    )
    write_csv(
        artifact_dir / "geodesic_path_flat.csv",
        [_rounded(row) for row in _path_rows(flat["points"])],
    )
    analytic_points = [(x, y, 0.0) for x, y in analytic["points"]]
    write_csv(
        artifact_dir / "geodesic_path_analytic.csv",
        [_rounded(row) for row in _path_rows(analytic_points)],
    )

    checks = {
        "analytic_blocked": analytic["blocked"],
        "flat_relative_error": flat_error,
        "flat_error_below_1pct": flat_error < 0.01,
        "curved_convergence_difference": curved_convergence,
        "curved_convergence_below_0_1pct": curved_convergence < 0.001,
        "flat_clearance_ok": float(flat["clearance_m"]) >= 0.60 - 1e-6,
        "curved_clearance_ok": float(curved_fine["clearance_m"]) >= 0.60 - 1e-6,
        "curved_path_longer_than_euclidean": float(curved_fine["distance_m"])
        > euclidean_start_goal,
        "start": curved_fine["start"],
        "goal": curved_fine["goal"],
        "analytic_distance_m": analytic_distance,
        "flat_distance_m": flat["distance_m"],
        "curved_coarse_distance_m": curved_coarse["distance_m"],
        "curved_fine_distance_m": curved_fine["distance_m"],
        "euclidean_start_goal_m": euclidean_start_goal,
    }
    payload = {
        "checks": checks,
        "validation_rows": [_rounded(row) for row in rows],
        "flat": {key: value for key, value in flat.items() if key != "points" and key != "indices"},
        "curved_coarse": {
            key: value
            for key, value in curved_coarse.items()
            if key != "points" and key != "indices"
        },
        "curved_fine": {
            key: value
            for key, value in curved_fine.items()
            if key != "points" and key != "indices"
        },
    }
    write_json(artifact_dir / "geodesic_metrics.json", payload)
    return {
        "checks": checks,
        "rows": [_rounded(row) for row in rows],
        "flat_points": flat["points"],
        "curved_points": curved_fine["points"],
        "analytic_points": analytic_points,
        "curved_mesh_vertices": curved_fine["mesh_vertices"],
        "flat_mesh_vertices": flat["mesh_vertices"],
    }
