from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import trimesh

from .mesh_ops import (
    TriangleMesh,
    build_face_adjacency,
    make_high_curvature_model,
    make_smooth_model,
    normal_angles,
)
from .metrics import (
    planar_projection_metrics,
    segmentation_metrics,
)
from .plots import (
    plot_segmentation,
    plot_soft_shadow,
    plot_stretch_maps,
    plot_uv_atlas,
)
from .segmentation import (
    geodesic_normal_segmentation,
    spectral_segmentation,
)
from .soft_shadow import recommended_step, run_step_experiment
from .uv_mapping import (
    build_island_projection_uv,
    build_planar_projection_uv,
)


MODEL_CONFIG = [
    ("smooth", make_smooth_model, 6),
    ("high_curvature", make_high_curvature_model, 8),
]


def _save_mesh(mesh: TriangleMesh, path: Path) -> None:
    trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces).export(path)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def run(output: Path = Path("artifacts")) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "data"
    mesh_dir = output / "meshes"
    data_dir.mkdir(exist_ok=True)
    mesh_dir.mkdir(exist_ok=True)

    all_metrics = []
    model_records = []
    for slug, factory, target_islands in MODEL_CONFIG:
        mesh = factory()
        adjacency, edges, _ = build_face_adjacency(mesh)
        angles = np.degrees(normal_angles(mesh, adjacency))
        _save_mesh(mesh, mesh_dir / f"{slug}.ply")
        np.savez_compressed(
            data_dir / f"{slug}_mesh.npz",
            vertices=mesh.vertices,
            faces=mesh.faces,
            adjacency=adjacency,
        )

        baseline_uv = build_planar_projection_uv(mesh)
        baseline = planar_projection_metrics(mesh, baseline_uv, edges)
        all_metrics.append(baseline)

        segmentation_entries = [
            geodesic_normal_segmentation(mesh, adjacency, target_islands),
            spectral_segmentation(mesh, adjacency, target_islands),
        ]
        method_records = []
        plot_entries = []
        stretch_plot_entries = [("Single planar projection", baseline_uv)]
        atlas_entries = []
        for segmentation in segmentation_entries:
            uv = build_island_projection_uv(mesh, segmentation.labels)
            record = segmentation_metrics(
                mesh, segmentation, uv, adjacency, edges
            )
            all_metrics.append(record)
            method_records.append(record)
            plot_entries.append(
                (segmentation.method, segmentation.labels, record["stretch_p95"])
            )
            stretch_plot_entries.append((segmentation.method, uv))
            atlas_entries.append(
                (segmentation.method, segmentation.labels, uv)
            )
            np.savez_compressed(
                data_dir / f"{slug}_{segmentation.method}.npz",
                labels=segmentation.labels,
                face_uv=uv.face_uv,
            )

        plot_segmentation(
            mesh,
            plot_entries,
            adjacency,
            output / f"segmentation_{slug}.png",
        )
        plot_stretch_maps(
            mesh,
            stretch_plot_entries,
            output / f"stretch_{slug}.png",
        )
        plot_uv_atlas(
            mesh,
            atlas_entries,
            output / f"uv_islands_{slug}.png",
        )

        reductions = {}
        for record in method_records:
            reductions[record["method"]] = {
                "mean_percent": 100.0
                * (1.0 - record["stretch_mean"] / baseline["stretch_mean"]),
                "p95_percent": 100.0
                * (1.0 - record["stretch_p95"] / baseline["stretch_p95"]),
                "max_percent": 100.0
                * (1.0 - record["stretch_max"] / baseline["stretch_max"]),
            }
        model_records.append(
            {
                "slug": slug,
                "name": mesh.name,
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces),
                "target_islands": target_islands,
                "edge_angle_deg": {
                    "mean": float(angles.mean()),
                    "p50": float(np.percentile(angles, 50)),
                    "p90": float(np.percentile(angles, 90)),
                    "p99": float(np.percentile(angles, 99)),
                    "max": float(angles.max()),
                },
                "baseline": baseline,
                "methods": method_records,
                "stretch_reduction_vs_projection": reductions,
            }
        )
        print(
            f"{mesh.name}: {len(mesh.faces)} faces; "
            f"p95 stretch projection="
            f"{baseline['stretch_p95']:.3f}, "
            + ", ".join(
                f"{record['method']}={record['stretch_p95']:.3f}"
                for record in method_records
            )
        )

    shadow = run_step_experiment()
    shadow["recommended"] = recommended_step(shadow)
    plot_soft_shadow(shadow, output / "soft_shadow_tradeoff.png")

    with (output / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(all_metrics), handle, ensure_ascii=False, indent=2)
    with (output / "soft_shadow.json").open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(shadow), handle, ensure_ascii=False, indent=2)

    fields = list(all_metrics[0].keys())
    with (output / "metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_metrics)

    summary = {
        "models": model_records,
        "soft_shadow": {
            "reference_penumbra_width": shadow["reference_penumbra_width"],
            "recommended": shadow["recommended"],
            "rows": shadow["rows"],
        },
    }
    with (output / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(summary), handle, ensure_ascii=False, indent=2)
    return summary


if __name__ == "__main__":
    run()
