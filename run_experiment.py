#!/usr/bin/env python3
"""Run the complete quad-remeshing and rendering-bandwidth experiment."""

from __future__ import annotations

import csv
import json
import platform
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quadmesh.generate import make_organic_leaf, make_organic_ring  # noqa: E402
from quadmesh.geometry import Mesh, write_mesh_json, write_obj  # noqa: E402
from quadmesh.metrics import evaluate_pair  # noqa: E402
from quadmesh.plotting import grouped_bars, mesh_comparison  # noqa: E402
from quadmesh.raster_validation import validate as raster_validate  # noqa: E402
from quadmesh.remesh import greedy_quad_pairing  # noqa: E402
from quadmesh.render_compare import (  # noqa: E402
    build_suite,
    conditional_conclusion,
    repeatability_check,
)


Factory = Callable[..., tuple[Mesh, Mesh]]
MODEL_SPECS: dict[str, dict[str, object]] = {
    "organic_ring": {
        "factory": make_organic_ring,
        "nominal": (96, 18),
        "variants": {"coarse": (84, 16), "nominal": (96, 18), "fine": (108, 20)},
        "role": "primary closed organic model",
    },
    "organic_leaf": {
        "factory": make_organic_leaf,
        "nominal": (48, 28),
        "variants": {"coarse": (40, 24), "nominal": (48, 28), "fine": (56, 32)},
        "role": "supplemental open organic model",
    },
}


def _checks(metrics: dict[str, object], pairing: dict[str, int]) -> dict[str, bool]:
    edge = metrics["output_edge_length"]  # type: ignore[index]
    quality = metrics["quality"]  # type: ignore[index]
    feature = metrics["feature_retention"]  # type: ignore[index]
    manifold = metrics["manifold"]  # type: ignore[index]
    check = {
        "no_triangle_fallback": pairing["fallback"] == 0,
        "pure_quads": bool(manifold["pure_quads"]),
        "manifold": manifold["nonmanifold_edges"] == 0 and manifold["degenerate_faces"] == 0,
        "edge_length_cv_at_most_0_20": edge["cv"] <= 0.20,
        "quality_mean_at_least_0_90": quality["mean"] >= 0.90,
        "quality_p05_at_least_0_75": quality["p05"] >= 0.75,
        "quality_ge_0_7_at_least_0_99": metrics["quality_ge_0_7"] >= 0.99,  # type: ignore[index]
        "angles_within_15deg_at_least_0_95": metrics["angles_within_15_deg_of_90"] >= 0.95,  # type: ignore[index]
        "feature_exact_rate_at_least_0_99": feature["exact_rate"] >= 0.99,
        "feature_geometric_rate_at_least_0_99": feature["geometric_coverage_rate"] >= 0.99,
    }
    check["subdivision_ready"] = all(check.values())
    return check


def _reference_recovery(source: Mesh, output: Mesh, reference_quads: Mesh) -> dict[str, float | int]:
    expected = {tuple(sorted(face)) for face in reference_quads.faces}
    actual = {tuple(sorted(face)) for face in output.faces}
    recovered = len(expected & actual)
    return {
        "reference_quads": len(expected),
        "exactly_recovered_quads": recovered,
        "recovery_rate": recovered / len(expected) if expected else 1.0,
    }


def run_variant(name: str, factory: Factory, parameters: tuple[int, ...]) -> dict[str, object]:
    source, reference_quads = factory(*parameters)
    output, pairing = greedy_quad_pairing(source, min_score=0.31)
    metrics = evaluate_pair(source, output)
    return {
        "parameters": list(parameters),
        "source": source,
        "output": output,
        "pairing": pairing,
        "metrics": metrics,
        "checks": _checks(metrics, pairing),
        "reference_recovery": _reference_recovery(source, output, reference_quads),
    }


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    names = fieldnames or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def _histogram_rows(name: str, metrics: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for kind in ("quality_histogram", "source_angle_histogram", "output_angle_histogram"):
        for item in metrics[kind]:  # type: ignore[index]
            rows.append(
                {
                    "model": name,
                    "metric": kind.replace("_histogram", ""),
                    "lower": item["lower"],
                    "upper": item["upper"],
                    "count": item["count"],
                    "fraction": item["fraction"],
                }
            )
    for kind in ("source_edge_length_histogram", "output_edge_length_histogram"):
        for item in metrics[kind]:  # type: ignore[index]
            rows.append(
                {
                    "model": name,
                    "metric": kind.replace("_histogram", ""),
                    "lower": item["lower"],
                    "upper": item["upper"],
                    "count": item["count"],
                    "fraction": item["fraction"],
                }
            )
    return rows


def _serializable_result(result: dict[str, object]) -> dict[str, object]:
    return {
        "parameters": result["parameters"],
        "pairing": result["pairing"],
        "metrics": result["metrics"],
        "checks": result["checks"],
        "reference_recovery": result["reference_recovery"],
    }


def _make_model_charts(name: str, result: dict[str, object], chart_dir: Path) -> None:
    metrics = result["metrics"]  # type: ignore[assignment]
    quality = metrics["quality_histogram"]
    labels = [f"{item['lower']:.2f}-{item['upper']:.2f}" for item in quality]
    grouped_bars(
        chart_dir / f"{name}_quality_histogram.svg",
        f"{name}: quad quality histogram ({len(result['output'].faces)} quads)",  # type: ignore[union-attr]
        labels,
        [("quad quality", [100.0 * item["fraction"] for item in quality])],
        "face fraction",
    )
    angle_bins = metrics["source_angle_histogram"]
    angle_labels = [f"{item['lower']:.0f}-{item['upper']:.0f}" for item in angle_bins]
    grouped_bars(
        chart_dir / f"{name}_angle_distribution.svg",
        f"{name}: interior-angle distribution",
        angle_labels,
        [
            ("triangle source", [100.0 * item["fraction"] for item in angle_bins]),
            ("quad output", [100.0 * item["fraction"] for item in metrics["output_angle_histogram"]]),
        ],
        "angle fraction",
    )
    edge_bins = metrics["source_edge_length_histogram"]
    edge_labels = [f"{item['lower']:.3f}-{item['upper']:.3f}" for item in edge_bins]
    grouped_bars(
        chart_dir / f"{name}_edge_length_distribution.svg",
        f"{name}: edge-length distribution",
        edge_labels,
        [
            ("triangle source", [100.0 * item["fraction"] for item in edge_bins]),
            ("quad output", [100.0 * item["fraction"] for item in metrics["output_edge_length_histogram"]]),
        ],
        "edge fraction",
    )
    mesh_comparison(
        chart_dir / f"{name}_wireframe.svg",
        f"{name}: source triangles vs quad remesh",
        result["source"],  # type: ignore[arg-type]
        result["output"],  # type: ignore[arg-type]
    )


def _rendering_charts(suite: dict[str, object], chart_dir: Path) -> None:
    frames = suite["frames"]
    selected = [
        row
        for row in frames
        if (row["width"], row["height"], row["msaa"])
        in ((1920, 1080, 1), (1920, 1080, 4), (3840, 2160, 1), (3840, 2160, 4))
    ]
    labels = [f"{row['width']}x{row['height']} {row['msaa']}x" for row in selected]
    grouped_bars(
        chart_dir / "rendering_framebuffer_memory.svg",
        "Framebuffer memory: deferred G-buffer vs visibility buffer",
        labels,
        [
            ("deferred", [row["deferred_memory_bytes"] / 2**20 for row in selected]),
            ("visibility", [row["visibility_memory_bytes"] / 2**20 for row in selected]),
        ],
        "MiB",
        suffix=" MiB",
    )
    grouped_bars(
        chart_dir / "rendering_frame_bandwidth.svg",
        "Frame traffic at 65% coverage, zero material-cache penalty",
        labels,
        [
            ("deferred", [row["deferred_traffic_bytes"] / 2**30 for row in selected]),
            ("visibility", [row["visibility_traffic_bytes"] / 2**30 for row in selected]),
        ],
        "GiB per frame",
        suffix=" GiB",
    )


def main() -> int:
    artifact_dir = ROOT / "artifacts"
    data_dir = artifact_dir / "data"
    chart_dir = artifact_dir / "charts"
    mesh_dir = artifact_dir / "meshes"
    for directory in (data_dir, chart_dir, mesh_dir):
        directory.mkdir(parents=True, exist_ok=True)

    model_results: dict[str, dict[str, object]] = {}
    variant_rows: list[dict[str, object]] = []
    histogram_rows: list[dict[str, object]] = []
    for name, spec in MODEL_SPECS.items():
        nominal_params = spec["nominal"]
        nominal = run_variant(name, spec["factory"], nominal_params)  # type: ignore[arg-type]
        variants: dict[str, object] = {}
        for variant_name, parameters in spec["variants"].items():  # type: ignore[union-attr]
            current = nominal if parameters == nominal_params else run_variant(name, spec["factory"], parameters)  # type: ignore[arg-type]
            variants[variant_name] = _serializable_result(current)
            metrics = current["metrics"]  # type: ignore[assignment]
            variant_rows.append(
                {
                    "model": name,
                    "variant": variant_name,
                    "parameters": str(parameters),
                    "quad_count": current["output"].stats()["faces"],  # type: ignore[union-attr]
                    "edge_length_cv": metrics["output_edge_length"]["cv"],
                    "quad_quality_mean": metrics["quality"]["mean"],
                    "quad_quality_p05": metrics["quality"]["p05"],
                    "angles_within_15deg": metrics["angles_within_15_deg_of_90"],
                    "feature_exact_rate": metrics["feature_retention"]["exact_rate"],
                    "feature_geometric_rate": metrics["feature_retention"]["geometric_coverage_rate"],
                    "subdivision_ready": current["checks"]["subdivision_ready"],  # type: ignore[index]
                }
            )
        model_results[name] = {
            "role": spec["role"],
            "nominal": _serializable_result(nominal),
            "variants": variants,
        }
        histogram_rows.extend(_histogram_rows(name, nominal["metrics"]))  # type: ignore[arg-type]
        source, output = nominal["source"], nominal["output"]
        assert isinstance(source, Mesh) and isinstance(output, Mesh)
        write_obj(source, mesh_dir / f"{name}_triangles.obj")
        write_obj(output, mesh_dir / f"{name}_quads.obj")
        write_mesh_json(source, mesh_dir / f"{name}_triangles.json")
        write_mesh_json(output, mesh_dir / f"{name}_quads.json")
        _make_model_charts(name, nominal, chart_dir)

    feature_chart_models = list(model_results)
    grouped_bars(
        chart_dir / "feature_edge_retention.svg",
        "Feature-edge retention after quad remeshing",
        ["exact edge", "length weighted", "geometric coverage"],
        [
            (
                model_name,
                [
                    100.0 * model_results[model_name]["nominal"]["metrics"]["feature_retention"]["exact_rate"],  # type: ignore[index]
                    100.0 * model_results[model_name]["nominal"]["metrics"]["feature_retention"]["length_weighted_rate"],  # type: ignore[index]
                    100.0 * model_results[model_name]["nominal"]["metrics"]["feature_retention"]["geometric_coverage_rate"],  # type: ignore[index]
                ],
            )
            for model_name in feature_chart_models
        ],
        "retention",
    )

    render_suite = build_suite()
    reproducibility = repeatability_check(runs=5)
    conclusion = conditional_conclusion(render_suite)
    ring_source, _ = make_organic_ring(*MODEL_SPECS["organic_ring"]["nominal"])  # type: ignore[arg-type]
    raster = raster_validate(ring_source, width=240, height=135, repeats=3)
    _rendering_charts(render_suite, chart_dir)

    results = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "gpu_profiler": "not available; deterministic architecture/model experiment",
        },
        "definitions": {
            "edge_length_cv": "standard deviation / mean of unique mesh-edge lengths",
            "quad_quality": "min over corners of min(angle, 180-angle) / 90",
            "feature_exact_rate": "fraction of source feature edges present as the same vertex-pair edge",
            "feature_geometric_rate": "source feature length covered within 0.2% of bbox diagonal",
            "subdivision_ready": "all quality, uniformity, manifold, and feature-retention checks pass",
            "deferred_gbuffer": "20 bytes/sample (albedo 4, normal 8, material 4, params 4) + depth 4",
            "visibility_buffer": "8-byte geometry/instance ID + depth 4, HDR 8 in both paths",
        },
        "organic_models": model_results,
        "rendering": {
            "suite": render_suite,
            "repeatability": reproducibility,
            "raster_cross_check": raster,
            "conditional_conclusion": conclusion,
        },
        "overall": {
            "all_models_subdivision_ready": all(
                model_results[name]["nominal"]["checks"]["subdivision_ready"]  # type: ignore[index]
                for name in model_results
            ),
            "all_variants_subdivision_ready": all(row["subdivision_ready"] for row in variant_rows),
            "all_feature_rates_exact": all(
                model_results[name]["nominal"]["metrics"]["feature_retention"]["exact_rate"] == 1.0  # type: ignore[index]
                for name in model_results
            ),
            "rendering_model_repeatable": reproducibility["bit_identical"],
            "raster_cross_check_repeatable": raster["all_repeatable"],
        },
    }

    (artifact_dir / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True), encoding="utf-8"
    )

    model_rows = []
    for name, payload in model_results.items():
        metrics = payload["nominal"]["metrics"]
        model_rows.append(
            {
                "model": name,
                "triangles_before": metrics["source_stats"]["faces_3"],
                "quads_after": metrics["output_stats"]["faces_4"],
                "source_feature_edges": metrics["feature_retention"]["source_edges"],
                "quads_exactly_recovered": payload["nominal"]["reference_recovery"]["exactly_recovered_quads"],
                "source_edge_cv": metrics["source_edge_length"]["cv"],
                "quad_edge_cv": metrics["output_edge_length"]["cv"],
                "source_edge_variance": metrics["source_edge_length"]["variance"],
                "quad_edge_variance": metrics["output_edge_length"]["variance"],
                "quad_quality_mean": metrics["quality"]["mean"],
                "quad_quality_p05": metrics["quality"]["p05"],
                "angles_within_15deg": metrics["angles_within_15_deg_of_90"],
                "feature_exact_rate": metrics["feature_retention"]["exact_rate"],
                "feature_geometric_rate": metrics["feature_retention"]["geometric_coverage_rate"],
                "subdivision_ready": payload["nominal"]["checks"]["subdivision_ready"],
            }
        )
    _write_csv(data_dir / "organic_summary.csv", model_rows)
    _write_csv(data_dir / "organic_variants.csv", variant_rows)
    _write_csv(data_dir / "histograms.csv", histogram_rows)
    _write_csv(data_dir / "rendering_frames.csv", render_suite["frames"])
    _write_csv(data_dir / "rendering_sensitivity.csv", render_suite["sensitivity"])
    _write_csv(data_dir / "raster_cross_check.csv", raster["rows"])
    _write_csv(data_dir / "reproducibility.csv", [reproducibility])

    for row in model_rows:
        print(
            f"{row['model']}: {row['triangles_before']} tris -> {row['quads_after']} quads, "
            f"edge CV {row['quad_edge_cv']:.3f}, quality {row['quad_quality_mean']:.3f}, "
            f"feature {100.0 * row['feature_exact_rate']:.1f}%, "
            f"subdivision_ready={row['subdivision_ready']}"
        )
    print(
        "Rendering (1080p): memory saving "
        f"{render_suite['frames'][0]['memory_saving_percent']:.1f}% at 1x MSAA, "
        f"{render_suite['frames'][2]['traffic_saving_percent']:.1f}% traffic saving at 4x MSAA."
    )
    print(f"Repeatable model={reproducibility['bit_identical']}, raster={raster['all_repeatable']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
