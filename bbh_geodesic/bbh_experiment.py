"""Bounding-box hierarchy, fit validation, timing, and culling experiment."""

from __future__ import annotations

import statistics
import time
from pathlib import Path

from .bvh import BoneBVH
from .culling import benchmark_depths, make_cameras
from .io_utils import write_csv, write_json
from .rig import RunRig


def _rounded(row: dict[str, object]) -> dict[str, object]:
    return {
        key: round(value, 9) if isinstance(value, float) else value
        for key, value in row.items()
    }


def run_bbh_experiment(
    artifact_dir: Path,
    frame_count: int = 48,
    timing_repeats: int = 12,
) -> dict[str, object]:
    rig = RunRig(frame_count=frame_count)
    samples = [rig.pose(frame / frame_count) for frame in range(frame_count)]
    bvh = BoneBVH(rig)

    pose_rows: list[dict[str, object]] = []
    fits: list[dict[str, object]] = []
    for frame, sample in enumerate(samples):
        started = time.perf_counter_ns()
        bvh.update(sample.points, collect_timing=True)
        update_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        fit = bvh.validate_fit(sample.points)
        fits.append(fit)
        center = bvh.root.box.center
        pose_rows.append(
            {
                "frame": frame,
                "phase": sample.phase,
                "root_volume_m3": bvh.root.box.volume,
                "root_center_x": center[0],
                "root_center_y": center[1],
                "root_center_z": center[2],
                "vertex_containment": fit["containment_ratio"],
                "subtree_containment": fit["subtree_contained_ratio"],
                "hierarchy_contains_children": fit["hierarchy_contains_children"],
                "max_outside_distance_m": fit["max_outside_distance"],
                "supported_box_faces_ratio": fit["supported_box_faces_ratio"],
                "box_update_ms": update_ms,
            }
        )

    timing_totals = {name: 0 for name in bvh.nodes}
    measured_total_ns = 0
    for _ in range(timing_repeats):
        for sample in samples:
            started = time.perf_counter_ns()
            bvh.update(sample.points, collect_timing=True)
            measured_total_ns += time.perf_counter_ns() - started
            for name, elapsed in bvh.last_timing.items():
                timing_totals[name] += elapsed
    timed_frames = timing_repeats * frame_count
    node_mean_ns = {name: value / timed_frames for name, value in timing_totals.items()}
    box_update_ms = measured_total_ns / timed_frames / 1_000_000.0

    pipeline_ns: list[int] = []
    for _ in range(timing_repeats):
        for frame in range(frame_count):
            started = time.perf_counter_ns()
            sample = rig.pose(frame / frame_count)
            bvh.update(sample.points)
            pipeline_ns.append(time.perf_counter_ns() - started)

    bvh.update(samples[-1].points, collect_timing=True)
    layers = bvh.layer_metrics({name: int(value) for name, value in node_mean_ns.items()})
    total_layer_volume = sum(row["total_volume_m3"] for row in layers)
    for row in layers:
        row["volume_share"] = row["total_volume_m3"] / total_layer_volume
        row["mean_update_ms_per_frame"] = row["update_ms_per_frame"]

    node_rows = bvh.node_rows()
    for row in node_rows:
        name = str(row["bone"])
        row["mean_update_ms"] = node_mean_ns[name] / 1_000_000.0
    final_fit = bvh.validate_fit(samples[-1].points)
    root_volumes = [float(row["root_volume_m3"]) for row in pose_rows]
    centers = [
        (float(row["root_center_x"]), float(row["root_center_y"]), float(row["root_center_z"]))
        for row in pose_rows
    ]
    center_shifts = [
        sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5
        for a, b in zip(centers, centers[1:])
    ]
    vertex_motions = []
    for previous, current in zip(samples, samples[1:]):
        motion = max(
            sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5
            for name in previous.points
            for a, b in zip(previous.points[name], current.points[name])
        )
        vertex_motions.append(motion)

    fit_summary = {
        "frames": frame_count,
        "vertices_per_frame": final_fit["vertices"],
        "nodes": len(bvh.nodes),
        "depths": max(node.depth for node in bvh.nodes.values()) + 1,
        "all_frames_fully_contained": all(
            fit["containment_ratio"] == 1.0 for fit in fits
        ),
        "all_subtrees_contained": all(
            fit["subtree_contained_ratio"] == 1.0 for fit in fits
        ),
        "all_hierarchies_contain_children": all(
            bool(fit["hierarchy_contains_children"]) for fit in fits
        ),
        "max_outside_distance_m": max(float(fit["max_outside_distance"]) for fit in fits),
        "minimum_supported_faces_ratio": min(
            float(fit["supported_box_faces_ratio"]) for fit in fits
        ),
        "mean_capsule_fill_ratio": statistics.mean(
            float(fit["mean_capsule_fill_ratio"]) for fit in fits
        ),
        "root_volume_min_m3": min(root_volumes),
        "root_volume_mean_m3": statistics.mean(root_volumes),
        "root_volume_max_m3": max(root_volumes),
        "root_volume_range_m3": max(root_volumes) - min(root_volumes),
        "mean_consecutive_root_center_shift_m": statistics.mean(center_shifts),
        "max_consecutive_root_center_shift_m": max(center_shifts),
        "min_max_vertex_motion_between_frames_m": min(vertex_motions),
        "box_update_ms_per_frame": box_update_ms,
        "pose_skin_box_update_ms_per_frame": statistics.mean(pipeline_ns) / 1_000_000.0,
        "pose_skin_box_update_p95_ms": sorted(pipeline_ns)[int(0.95 * len(pipeline_ns))]
        / 1_000_000.0,
        "final_fit": final_fit,
    }

    write_csv(artifact_dir / "pose_fit.csv", [_rounded(row) for row in pose_rows])
    write_csv(
        artifact_dir / "layer_bbox_metrics.csv",
        [_rounded(row) for row in layers],
    )
    write_csv(
        artifact_dir / "node_bbox_metrics.csv",
        [_rounded(row) for row in node_rows],
    )
    write_json(artifact_dir / "bbh_metrics.json", fit_summary)
    return {
        "fit": fit_summary,
        "layers": [_rounded(row) for row in layers],
        "nodes": [_rounded(row) for row in node_rows],
        "pose_rows": [_rounded(row) for row in pose_rows],
        "rig": rig,
        "bvh": bvh,
        "samples": samples,
    }


def run_culling_experiment(
    artifact_dir: Path,
    bbh_result: dict[str, object],
    frame_stride: int = 1,
) -> dict[str, object]:
    bvh: BoneBVH = bbh_result["bvh"]  # type: ignore[assignment]
    samples = bbh_result["samples"]  # type: ignore[assignment]
    selected = list(samples)[::frame_stride]
    bvh.update(selected[0].points)
    cameras = make_cameras(bvh)
    rows, validation = benchmark_depths(bvh, [sample.points for sample in selected], cameras)
    for row in rows:
        row["mean_candidate_rate"] = row["mean_candidate_primitives"] / len(bvh.nodes)
    write_csv(artifact_dir / "culling_depth.csv", [_rounded(row) for row in rows])
    payload = {
        "frames": len(selected),
        "cameras": len(cameras),
        "primitive_count": len(bvh.nodes),
        "validation": validation,
        "depths": [_rounded(row) for row in rows],
    }
    write_json(artifact_dir / "culling_metrics.json", payload)
    return payload
