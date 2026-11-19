"""Noise sweep for Poisson reconstruction against analytic ground truth."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .clouds import (
    bumpy_sphere_shape,
    chamfer_metrics_mm,
    estimate_normals_pca,
    fibonacci_directions,
    radial_error_metrics,
    sample_mesh,
    sample_shape,
    sphere_shape,
    write_ply,
)
from .reconstruct import safe_poisson_reconstruct


@dataclass(frozen=True)
class BenchmarkConfig:
    n_points: int = 18000
    n_ground_truth: int = 30000
    seeds: tuple[int, ...] = (0, 1, 2)
    noise_fractions: tuple[float, ...] = (0.0, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.04)
    depth: int = 8
    scale: float = 1.1
    neighbors: int = 30


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["shape"], round(row["noise_fraction"], 8), row["method"])
        groups.setdefault(key, []).append(row)
    summary: list[dict[str, Any]] = []
    for (shape, noise, method), items in sorted(groups.items()):
        out: dict[str, Any] = {
            "shape": shape,
            "noise_fraction": noise,
            "noise_mm": float(np.mean([item["noise_mm"] for item in items])),
            "method": method,
            "runs": len(items),
            "backend": items[0]["backend"],
        }
        for metric in (
            "radial_rmse_mm",
            "radial_mean_mm",
            "radial_p95_mm",
            "chamfer_mm",
            "runtime_s",
            "vertices",
        ):
            values = np.array([item[metric] for item in items], dtype=float)
            out[f"{metric}_mean"] = float(values.mean())
            out[f"{metric}_std"] = float(values.std())
        summary.append(out)
    return summary


def _robustness_checks(
    summary: list[dict[str, Any]], noise_fractions: Iterable[float]
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    max_noise = max(noise_fractions)
    for shape in sorted({row["shape"] for row in summary}):
        shape_rows = [row for row in summary if row["shape"] == shape]
        poisson = {
            round(row["noise_fraction"], 8): row
            for row in shape_rows
            if row["method"] == "poisson"
        }
        raw = {
            round(row["noise_fraction"], 8): row
            for row in shape_rows
            if row["method"] == "raw_points"
        }
        clean_rmse = poisson[0.0]["radial_rmse_mm_mean"]
        high_rmse = poisson[round(max_noise, 8)]["radial_rmse_mm_mean"]
        high_raw = raw[round(max_noise, 8)]["radial_rmse_mm_mean"]
        noise_levels = sorted(key for key in poisson if key > 0.0)
        improvement = [
            raw[key]["radial_rmse_mm_mean"] / poisson[key]["radial_rmse_mm_mean"]
            for key in noise_levels
        ]
        sigma = np.array([key * 500.0 for key in noise_levels])
        errors = np.array(
            [poisson[key]["radial_rmse_mm_mean"] for key in noise_levels]
        )
        slope = float(np.polyfit(np.log(sigma), np.log(errors), 1)[0])
        checks[shape] = {
            "clean_rmse_mm": float(clean_rmse),
            "clean_rmse_pass": bool(clean_rmse < 1.0),
            "max_noise_fraction": float(max_noise),
            "max_noise_rmse_mm": float(high_rmse),
            "max_noise_raw_rmse_mm": float(high_raw),
            "max_noise_improvement_factor": float(high_raw / high_rmse),
            "max_noise_rmse_pass": bool(
                high_rmse < high_raw and high_rmse / (max_noise * 500.0) < 0.65
            ),
            "always_better_than_raw": bool(all(value > 1.0 for value in improvement)),
            "min_improvement_factor": float(min(improvement)),
            "loglog_error_exponent": slope,
            "graceful_degradation_pass": bool(slope < 1.25),
        }
    return checks


def run_benchmark(
    out_dir: str | Path,
    config: BenchmarkConfig | None = None,
    make_plots: bool = True,
) -> dict[str, Any]:
    config = config or BenchmarkConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    shapes = [sphere_shape(0.5), bumpy_sphere_shape(0.5, 0.06)]
    gt_points = {
        shape.name: shape.points_from_directions(
            fibonacci_directions(config.n_ground_truth)
        )
        for shape in shapes
    }
    rows: list[dict[str, Any]] = []
    examples: dict[str, dict[str, Any]] = {}
    started = time.perf_counter()

    for shape in shapes:
        for noise_fraction in config.noise_fractions:
            sigma = noise_fraction * shape.radius
            for seed in config.seeds:
                rng = np.random.default_rng(seed + 1000 * len(shape.name))
                points, _ = sample_shape(
                    shape, config.n_points, rng, noise_sigma=sigma
                )
                normals = estimate_normals_pca(
                    points, neighbors=config.neighbors, center=np.zeros(3)
                )
                reconstruction = safe_poisson_reconstruct(
                    points,
                    normals,
                    depth=config.depth,
                    scale=config.scale,
                )
                mesh_samples = sample_mesh(
                    reconstruction.vertices,
                    reconstruction.faces,
                    config.n_points,
                    rng,
                )
                radial_mesh = radial_error_metrics(reconstruction.vertices, shape)
                radial_raw = radial_error_metrics(points, shape)
                chamfer_mesh = chamfer_metrics_mm(
                    mesh_samples, gt_points[shape.name]
                )
                chamfer_raw = chamfer_metrics_mm(points, gt_points[shape.name])
                for method, radial, chamfer, backend, verts, runtime in (
                    (
                        "poisson",
                        radial_mesh,
                        chamfer_mesh,
                        reconstruction.backend,
                        len(reconstruction.vertices),
                        reconstruction.runtime_s,
                    ),
                    (
                        "raw_points",
                        radial_raw,
                        chamfer_raw,
                        "none",
                        len(points),
                        0.0,
                    ),
                ):
                    rows.append(
                        {
                            "shape": shape.name,
                            "noise_fraction": float(noise_fraction),
                            "noise_mm": float(sigma * 1000.0),
                            "seed": int(seed),
                            "method": method,
                            "backend": backend,
                            "vertices": int(verts),
                            "faces": int(len(reconstruction.faces))
                            if method == "poisson"
                            else 0,
                            "runtime_s": float(runtime),
                            **radial,
                            **chamfer,
                        }
                    )
                if (
                    shape.name == "sphere"
                    and seed == config.seeds[0]
                    and noise_fraction in (0.0, 0.02, 0.04)
                ):
                    key = f"{noise_fraction:.3f}"
                    examples[key] = {
                        "noise_fraction": noise_fraction,
                        "points": points,
                        "mesh_vertices": reconstruction.vertices,
                        "mesh_faces": reconstruction.faces,
                        "backend": reconstruction.backend,
                    }
                    write_ply(
                        out / f"sphere_noise_{int(noise_fraction*1000):03d}mm_mesh.ply",
                        reconstruction.vertices,
                        reconstruction.faces,
                    )
                    write_ply(
                        out / f"sphere_noise_{int(noise_fraction*1000):03d}mm_points.ply",
                        points,
                    )

    summary = _aggregate(rows)
    checks = _robustness_checks(summary, config.noise_fractions)
    _write_csv(out / "poisson_metrics_raw.csv", rows)
    _write_csv(out / "poisson_metrics_summary.csv", summary)
    elapsed = time.perf_counter() - started
    payload = {
        "config": {
            "n_points": config.n_points,
            "n_ground_truth": config.n_ground_truth,
            "seeds": list(config.seeds),
            "noise_fractions": list(config.noise_fractions),
            "depth": config.depth,
            "scale": config.scale,
            "neighbors": config.neighbors,
        },
        "backend": rows[0]["backend"],
        "elapsed_s": elapsed,
        "checks": checks,
        "summary": summary,
        "metrics": rows,
    }
    (out / "poisson_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if make_plots:
        from .visualize import plot_examples, plot_noise_curve

        plot_noise_curve(summary, checks, out / "poisson_noise_curve.png")
        plot_examples(examples, out / "poisson_reconstruction_examples.png")
    return payload
