from __future__ import annotations

import argparse
import time
from pathlib import Path

from .animation import make_demo_animation
from .compression import compress_animation
from .metrics import evaluate_reconstruction
from .report import write_json, write_markdown_report, write_sweep_csv
from .subdivision import (
    boundary_vertices,
    build_cube_mesh,
    build_quad_patch_mesh,
    build_tent_mesh,
    sharp_dihedral_degrees,
    sharp_edge_max_deviation,
    subdivide_mesh,
)
from .svg_report import (
    render_action_comparison_svg,
    render_mesh_svg,
    render_quantization_svg,
)

SWEEP_FIELDS = (
    "bits",
    "compression_ratio",
    "compressed_bytes",
    "payload_bytes",
    "quantization_rotation_max_deg",
    "quantization_rotation_rmse_deg",
    "quantization_position_max",
    "interpolation_rotation_max_deg",
    "interpolation_position_max",
    "rotation_max_deg",
    "rotation_rmse_deg",
    "position_max",
    "end_effector_max",
)


def _analyse_tent() -> dict[str, object]:
    mesh = build_tent_mesh()
    levels = []
    render_records = []
    for level in (0, 1, 2):
        result = subdivide_mesh(mesh, levels=level)
        deviation = sharp_edge_max_deviation(
            result.mesh,
            (0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0),
        )
        angles = sharp_dihedral_degrees(result.mesh)
        level_record = {
            "level": level,
            **result.stats,
            "ridge_deviation": deviation,
            "min_crease_deg": min(angles) if angles else 0.0,
            "max_crease_deg": max(angles) if angles else 0.0,
        }
        levels.append(level_record)
        render_records.append(
            {
                "label": f"Tent mesh, level {level}",
                "mesh": result.mesh,
                "boundary_vertices": result.stats["boundary_vertices"],
                "interior_vertices": result.stats["interior_vertices"],
                "ridge_deviation": deviation,
                "min_crease_deg": min(angles) if angles else 0.0,
            }
        )
    expected_sharp = [
        int(levels[0]["sharp_edges"]),
        2 * int(levels[0]["sharp_edges"]),
        4 * int(levels[0]["sharp_edges"]),
    ]
    return {
        "levels": levels,
        "sharp_edge_count_preserved": [
            int(record["sharp_edges"]) == expected
            for record, expected in zip(levels, expected_sharp)
        ],
        "ridge_straight": all(float(record["ridge_deviation"]) <= 1.0e-12 for record in levels),
        "crease_preserved": all(
            abs(float(record["min_crease_deg"]) - 90.0) <= 1.0e-8 for record in levels
        ),
        "render_records": render_records,
    }


def build_mesh_analysis() -> dict[str, object]:
    patch_result = subdivide_mesh(build_quad_patch_mesh(), levels=2)
    patch_boundary = boundary_vertices(patch_result.mesh)
    patch_max_abs_z = max(abs(vertex[2]) for vertex in patch_result.mesh.vertices)
    boundary_rectangle = all(
        abs(vertex[2]) <= 1.0e-12
        and (
            abs(vertex[0]) <= 1.0e-12
            or abs(vertex[0] - 2.0) <= 1.0e-12
            or abs(vertex[1]) <= 1.0e-12
            or abs(vertex[1] - 2.0) <= 1.0e-12
        )
        for vertex in (patch_result.mesh.vertices[index] for index in patch_boundary)
    )
    cube_result = subdivide_mesh(build_cube_mesh(), levels=2)
    tent = _analyse_tent()
    return {
        "open_patch": {
            **patch_result.stats,
            "max_abs_z": patch_max_abs_z,
            "boundary_on_original_rectangle": boundary_rectangle,
        },
        "closed_cube": dict(cube_result.stats),
        "sharp_tent": {
            key: value for key, value in tent.items() if key != "render_records"
        },
        "render_records": tent["render_records"],
    }


def _sweep(
    animation: object,
    bit_values: list[int],
    keyframe_hz: float,
    evaluation_stride: int,
) -> list[dict[str, object]]:
    records = []
    for bits in bit_values:
        result = compress_animation(animation, bits=bits, keyframe_hz=keyframe_hz)
        evaluation = evaluate_reconstruction(
            animation,
            result,
            frame_stride=evaluation_stride,
        )
        metrics = evaluation["metrics"]
        records.append({field: metrics[field] for field in SWEEP_FIELDS})
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--keyframe-hz", type=float, default=10.0)
    parser.add_argument("--bits", type=int, default=16)
    parser.add_argument("--sweep-bits", default="8,10,12,14,16,18,20")
    parser.add_argument("--sweep-stride", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    args.output.mkdir(parents=True, exist_ok=True)
    animation = make_demo_animation(args.duration, args.fps)
    print(
        f"animation: {animation.duration_seconds:.0f}s, {animation.frame_count} frames, "
        f"{len(animation.joints)} joints"
    )

    compressed = compress_animation(
        animation,
        bits=args.bits,
        keyframe_hz=args.keyframe_hz,
    )
    evaluation = evaluate_reconstruction(animation, compressed, frame_stride=1)
    metrics = dict(evaluation["metrics"])
    metrics["series"] = evaluation["series"]
    metrics["pose_comparison"] = evaluation["pose_comparison"]

    bit_values = [int(value.strip()) for value in args.sweep_bits.split(",") if value.strip()]
    sweep = _sweep(animation, bit_values, args.keyframe_hz, args.sweep_stride)
    for record in sweep:
        if int(record["bits"]) == args.bits:
            record.update({field: metrics[field] for field in SWEEP_FIELDS})

    mesh_report = build_mesh_analysis()
    render_records = mesh_report.pop("render_records")
    write_json(
        args.output / "animation_compression_metrics.json",
        {
            "configuration": {
                "duration_seconds": args.duration,
                "fps": args.fps,
                "keyframe_hz": args.keyframe_hz,
                "bits": args.bits,
                "sweep_stride": args.sweep_stride,
            },
            "metrics": metrics,
            "quantization_sweep": sweep,
            "mesh_subdivision": mesh_report,
        },
    )
    write_json(args.output / "mesh_subdivision_metrics.json", mesh_report)
    write_sweep_csv(args.output / "quantization_sweep.csv", sweep)
    render_action_comparison_svg(
        args.output / "action_comparison.svg",
        animation,
        compressed.animation,
        metrics,
    )
    render_quantization_svg(args.output / "quantization_tradeoff.svg", sweep)
    render_mesh_svg(args.output / "mesh_subdivision.svg", render_records)
    write_markdown_report(
        args.output / "animation_compression_report.md",
        metrics,
        sweep,
        mesh_report,
    )
    elapsed = time.perf_counter() - started
    print(
        f"ratio={float(metrics['compression_ratio']):.2f}:1  "
        f"rotation_max={float(metrics['rotation_max_deg']):.5f} deg  "
        f"position_max={float(metrics['position_max']):.3e}  "
        f"end_effector_max={float(metrics['end_effector_max']):.3e}"
    )
    print(f"artifacts: {args.output.resolve()}  elapsed={elapsed:.1f}s")


if __name__ == "__main__":
    main()
