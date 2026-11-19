from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random
import statistics
import time
from typing import Any

from .builders import BVH, STRATEGIES, build_bvh
from .dynamic import DynamicBVH
from .geometry import AABB, Ray, vec_normalize, vec_sub
from .mesh import MeshData, Triangle
from .traversal import TraversalResult, traverse


DEFAULT_SCENE = {
    "seed": 20261120,
    "triangle_count": 1536,
    "dense_triangle_count": 768,
    "dense_region": [[1.5, -1.5, -1.5], [3.5, 0.5, 0.5]],
    "sparse_region": [[-10.0, -10.0, -10.0], [10.0, 10.0, 10.0]],
    "dense_triangle_scale": 0.07,
    "sparse_triangle_scale": 0.55,
}

DEFAULT_RAY_PARAMETERS = {
    "seed": 424242,
    "ray_count": 1200,
    "focus_ray_percent": 70,
    "camera_radius_factor": 0.52,
    "direction_model": "uniform sphere shell toward a random scene/focus point",
}

DEFAULT_BVH_PARAMETERS = {
    "strategies": list(STRATEGIES),
    "max_leaf_size": 4,
    "sah_bins": 16,
    "build_repeats": 3,
    "traversal_repeats": 5,
}

DEFAULT_DYNAMIC_PARAMETERS = {
    "frames": 8,
    "step": [0.025, 0.015, 0.01],
    "selection": "smallest-volume internal SAH subtree with 16 to 32 triangles",
    "min_group_size": 16,
    "max_group_size": 32,
    "full_rebuild_reference_repeats": 3,
}


@dataclass(slots=True)
class RaySet:
    rays: list[Ray]
    focus_mask: list[bool]
    parameters: dict[str, Any]

    @property
    def focus_rays(self) -> list[Ray]:
        return [ray for ray, focused in zip(self.rays, self.focus_mask) if focused]

    @property
    def background_rays(self) -> list[Ray]:
        return [
            ray for ray, focused in zip(self.rays, self.focus_mask) if not focused
        ]


def _region_point(rng: random.Random, region: Any) -> tuple[float, float, float]:
    lower, upper = region
    return tuple(
        rng.uniform(float(lower[axis]), float(upper[axis])) for axis in range(3)
    )


def _uniform_sphere_direction(rng: random.Random) -> tuple[float, float, float]:
    z = rng.uniform(-1.0, 1.0)
    angle = rng.uniform(0.0, 2.0 * math.pi)
    radial = math.sqrt(max(0.0, 1.0 - z * z))
    return (radial * math.cos(angle), radial * math.sin(angle), z)


def make_ray_set(
    mesh: MeshData,
    seed: int = 424242,
    ray_count: int = 1200,
    focus_ray_percent: int = 70,
    camera_radius_factor: float = 0.52,
) -> RaySet:
    if ray_count <= 0:
        raise ValueError("ray_count must be positive")
    if focus_ray_percent < 0 or focus_ray_percent > 100:
        raise ValueError("focus_ray_percent must be between 0 and 100")
    bounds = mesh.bounds()
    center = bounds.center
    diagonal = math.sqrt(
        (bounds.max_x - bounds.min_x) ** 2
        + (bounds.max_y - bounds.min_y) ** 2
        + (bounds.max_z - bounds.min_z) ** 2
    )
    camera_radius = max(1.0, diagonal * camera_radius_factor)
    scene_region = [list(bounds.min), list(bounds.max)]
    focus_region = mesh.metadata.get("focus_region", scene_region)
    rng = random.Random(seed)
    rays: list[Ray] = []
    focus_mask: list[bool] = []
    for index in range(ray_count):
        shell_direction = _uniform_sphere_direction(rng)
        origin = (
            center[0] + shell_direction[0] * camera_radius,
            center[1] + shell_direction[1] * camera_radius,
            center[2] + shell_direction[2] * camera_radius,
        )
        focused = index % 100 < focus_ray_percent
        target = _region_point(rng, focus_region if focused else scene_region)
        direction = vec_normalize(vec_sub(target, origin))
        rays.append(Ray(origin=origin, direction=direction, t_max=camera_radius * 4.0))
        focus_mask.append(focused)
    parameters = {
        "seed": seed,
        "ray_count": ray_count,
        "focus_ray_percent": focus_ray_percent,
        "focus_ray_count": sum(focus_mask),
        "background_ray_count": ray_count - sum(focus_mask),
        "scene_center": list(center),
        "camera_radius": camera_radius,
        "camera_radius_factor": camera_radius_factor,
        "ray_t_max": camera_radius * 4.0,
        "focus_region": focus_region,
        "direction_model": DEFAULT_RAY_PARAMETERS["direction_model"],
    }
    return RaySet(rays=rays, focus_mask=focus_mask, parameters=parameters)


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _build_repeated(
    triangles: list[Triangle],
    strategy: str,
    max_leaf_size: int,
    sah_bins: int,
    repeats: int,
) -> tuple[BVH, dict[str, Any]]:
    build_times: list[float] = []
    result: BVH | None = None
    for _ in range(max(1, repeats)):
        candidate = build_bvh(
            triangles,
            strategy=strategy,
            max_leaf_size=max_leaf_size,
            sah_bins=sah_bins,
        )
        build_times.append(candidate.build_time_ms)
        if result is None:
            result = candidate
    if result is None:
        raise RuntimeError("build did not produce a BVH")
    result.validate()
    summary = result.summary()
    summary["build_time_ms"] = _median(build_times)
    summary["build_time_ms_min"] = min(build_times)
    summary["build_times_ms"] = build_times
    reachable = result.reachable_nodes()
    summary["internal_node_count"] = len(reachable) - sum(
        1 for _ in result.leaves()
    )
    return result, summary


def _traverse_repeated(
    bvh: BVH,
    triangles: list[Triangle],
    rays: list[Ray],
    repeats: int,
) -> tuple[dict[str, Any], list[Any]]:
    elapsed: list[float] = []
    first_result: TraversalResult | None = None
    for _ in range(max(1, repeats)):
        result = traverse(bvh, triangles, rays, collect_hits=True)
        elapsed.append(result.stats.elapsed_ms)
        if first_result is None:
            first_result = result
        elif (
            result.stats.node_visits != first_result.stats.node_visits
            or result.stats.triangle_tests != first_result.stats.triangle_tests
            or result.stats.hit_count != first_result.stats.hit_count
        ):
            raise AssertionError("traversal counters changed between repeats")
    if first_result is None:
        raise RuntimeError("traversal did not run")
    stats = first_result.stats.as_dict()
    stats["elapsed_ms"] = _median(elapsed)
    stats["elapsed_ms_min"] = min(elapsed)
    stats["elapsed_ms_median"] = _median(elapsed)
    stats["elapsed_times_ms"] = elapsed
    return stats, first_result.hits


def _hits_equal(
    left: list[Any], right: list[Any], tolerance: float = 1.0e-9
) -> bool:
    if len(left) != len(right):
        return False
    for first, second in zip(left, right):
        if first is None or second is None:
            if first is not second:
                return False
            continue
        if first.triangle_index != second.triangle_index:
            return False
        if abs(first.t - second.t) > tolerance:
            return False
    return True


def _reduction_percent(reference: float, candidate: float) -> float:
    if reference <= 0.0:
        return 0.0
    return (reference - candidate) / reference * 100.0


def benchmark_strategies(
    mesh: MeshData,
    triangles: list[Triangle],
    ray_set: RaySet,
    bvh_parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters = dict(DEFAULT_BVH_PARAMETERS)
    if bvh_parameters:
        parameters.update(bvh_parameters)
    max_leaf_size = int(parameters["max_leaf_size"])
    sah_bins = int(parameters["sah_bins"])
    build_repeats = int(parameters["build_repeats"])
    traversal_repeats = int(parameters["traversal_repeats"])
    outputs: dict[str, Any] = {}
    all_hits: dict[str, list[Any]] = {}
    for strategy in parameters["strategies"]:
        bvh, summary = _build_repeated(
            triangles,
            strategy,
            max_leaf_size,
            sah_bins,
            build_repeats,
        )
        total_stats, hits = _traverse_repeated(
            bvh, triangles, ray_set.rays, traversal_repeats
        )
        focus_stats, _ = _traverse_repeated(
            bvh, triangles, ray_set.focus_rays, traversal_repeats
        )
        summary["traversal"] = total_stats
        summary["focus_traversal"] = focus_stats
        outputs[strategy] = summary
        all_hits[strategy] = hits

    reference_hits = all_hits["sah"]
    hits_equal = all(
        _hits_equal(reference_hits, strategy_hits)
        for strategy_hits in all_hits.values()
    )
    sah_focus = outputs["sah"]["focus_traversal"]
    median_focus = outputs["median"]["focus_traversal"]
    lbvh_focus = outputs["lbvh"]["focus_traversal"]
    sah_total = outputs["sah"]["traversal"]
    median_total = outputs["median"]["traversal"]
    lbvh_total = outputs["lbvh"]["traversal"]
    comparison = {
        "all_hit_counts_equal": len(
            {
                outputs[strategy]["traversal"]["hit_count"]
                for strategy in outputs
            }
        )
        == 1,
        "all_nearest_hits_equal": hits_equal,
        "sah_focus_ray_count": ray_set.parameters["focus_ray_count"],
        "sah_focus_node_visits": sah_focus["node_visits"],
        "median_focus_node_visits": median_focus["node_visits"],
        "lbvh_focus_node_visits": lbvh_focus["node_visits"],
        "sah_focus_triangle_tests": sah_focus["triangle_tests"],
        "median_focus_triangle_tests": median_focus["triangle_tests"],
        "lbvh_focus_triangle_tests": lbvh_focus["triangle_tests"],
        "sah_focus_node_visit_reduction_vs_median_percent": _reduction_percent(
            median_focus["node_visits"], sah_focus["node_visits"]
        ),
        "sah_focus_node_visit_reduction_vs_lbvh_percent": _reduction_percent(
            lbvh_focus["node_visits"], sah_focus["node_visits"]
        ),
        "sah_focus_triangle_test_reduction_vs_median_percent": _reduction_percent(
            median_focus["triangle_tests"], sah_focus["triangle_tests"]
        ),
        "sah_focus_triangle_test_reduction_vs_lbvh_percent": _reduction_percent(
            lbvh_focus["triangle_tests"], sah_focus["triangle_tests"]
        ),
        "sah_total_triangle_test_reduction_vs_median_percent": _reduction_percent(
            median_total["triangle_tests"], sah_total["triangle_tests"]
        ),
        "sah_total_triangle_test_reduction_vs_lbvh_percent": _reduction_percent(
            lbvh_total["triangle_tests"], sah_total["triangle_tests"]
        ),
        "sah_focus_traversal_ms": sah_focus["elapsed_ms"],
        "median_focus_traversal_ms": median_focus["elapsed_ms"],
        "lbvh_focus_traversal_ms": lbvh_focus["elapsed_ms"],
        "sah_faster_in_dense_region": (
            sah_focus["node_visits"] < median_focus["node_visits"]
            and sah_focus["node_visits"] < lbvh_focus["node_visits"]
            and sah_focus["triangle_tests"] < median_focus["triangle_tests"]
            and sah_focus["triangle_tests"] < lbvh_focus["triangle_tests"]
        ),
        "dense_region_criterion": (
            "SAH must use fewer focus-ray node visits and triangle tests "
            "than both median and LBVH"
        ),
    }
    return outputs, comparison


def _select_dynamic_group(
    bvh: BVH, min_count: int, max_count: int
) -> tuple[int, list[int], AABB]:
    candidates: list[tuple[float, int]] = []
    for node_index, node in enumerate(bvh.nodes):
        if node.is_leaf:
            continue
        if min_count <= node.count <= max_count and node.bounds.volume > 0.0:
            candidates.append((node.bounds.volume, node_index))
    if not candidates:
        raise ValueError("no compact internal subtree matches the dynamic size range")
    candidates.sort()
    _, node_index = candidates[0]
    return (
        node_index,
        bvh.subtree_primitives(node_index),
        bvh.nodes[node_index].bounds,
    )


def benchmark_dynamic(
    mesh: MeshData,
    dynamic_parameters: dict[str, Any] | None = None,
    bvh_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dynamic_params = dict(DEFAULT_DYNAMIC_PARAMETERS)
    if dynamic_parameters:
        dynamic_params.update(dynamic_parameters)
    bvh_params = dict(DEFAULT_BVH_PARAMETERS)
    if bvh_parameters:
        bvh_params.update(bvh_parameters)
    max_leaf_size = int(bvh_params["max_leaf_size"])
    sah_bins = int(bvh_params["sah_bins"])
    triangles = mesh.triangles()
    dynamic = DynamicBVH(
        triangles,
        strategy="sah",
        max_leaf_size=max_leaf_size,
        sah_bins=sah_bins,
    )
    subtree_root, primitive_indices, initial_bounds = _select_dynamic_group(
        dynamic.bvh,
        int(dynamic_params["min_group_size"]),
        int(dynamic_params["max_group_size"]),
    )
    step = tuple(float(value) for value in dynamic_params["step"])
    frames: list[dict[str, Any]] = []
    for _ in range(int(dynamic_params["frames"])):
        local_stats = dynamic.translate_primitives(primitive_indices, step)
        frame = local_stats.as_dict()
        frames.append(frame)
    dynamic.bvh.validate()
    reference_times: list[float] = []
    reference_node_count = 0
    for _ in range(int(dynamic_params["full_rebuild_reference_repeats"])):
        reference_start = time.perf_counter()
        full_bvh = build_bvh(
            dynamic.triangles,
            strategy="sah",
            max_leaf_size=max_leaf_size,
            sah_bins=sah_bins,
        )
        reference_times.append((time.perf_counter() - reference_start) * 1000.0)
        full_bvh.validate()
        reference_node_count = len(full_bvh.reachable_nodes())
    reference_full_ms = _median(reference_times)
    total_local_ms = sum(float(frame["rebuild_ms"]) for frame in frames)
    total_full_reference_ms = reference_full_ms * len(frames)
    for frame in frames:
        frame["full_rebuild_reference_ms"] = reference_full_ms
        frame["full_rebuild_node_count"] = reference_node_count
        frame["local_to_full_time_ratio"] = (
            float(frame["rebuild_ms"]) / reference_full_ms
            if reference_full_ms > 0.0
            else 0.0
        )
    total_overlap = sum(float(frame["overlap_volume"]) for frame in frames)
    mean_overlap_ratio = sum(
        float(frame["overlap_ratio_of_old"]) for frame in frames
    ) / len(frames)
    return {
        "parameters": {
            **dynamic_params,
            "bvh_strategy": "sah",
            "max_leaf_size": max_leaf_size,
            "sah_bins": sah_bins,
            "step": list(step),
        },
        "chosen_subtree": {
            "node_index": subtree_root,
            "primitive_indices": primitive_indices,
            "primitive_count": len(primitive_indices),
            "initial_bounds": initial_bounds.as_dict(),
        },
        "frames": frames,
        "summary": {
            "all_frames_local": all(frame["local_rebuild"] for frame in frames),
            "actual_full_rebuilds": 0,
            "reference_full_rebuilds": len(reference_times),
            "full_rebuild_reference_samples_ms": reference_times,
            "median_full_rebuild_reference_ms": reference_full_ms,
            "total_local_rebuild_ms": total_local_ms,
            "total_full_rebuild_reference_ms": total_full_reference_ms,
            "local_to_full_time_ratio": (
                total_local_ms / total_full_reference_ms
                if total_full_reference_ms > 0.0
                else 0.0
            ),
            "total_overlap_volume": total_overlap,
            "mean_overlap_ratio_of_old": mean_overlap_ratio,
            "reachable_node_count": len(dynamic.bvh.reachable_nodes()),
            "allocated_node_count": len(dynamic.bvh.nodes),
            "final_bvh_valid": True,
        },
    }


def mesh_sha256(mesh: MeshData) -> str:
    canonical = json.dumps(
        mesh.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_benchmark(
    mesh: MeshData,
    ray_parameters: dict[str, Any] | None = None,
    bvh_parameters: dict[str, Any] | None = None,
    dynamic_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ray_params = dict(DEFAULT_RAY_PARAMETERS)
    if ray_parameters:
        ray_params.update(ray_parameters)
    bvh_params = dict(DEFAULT_BVH_PARAMETERS)
    if bvh_parameters:
        bvh_params.update(bvh_parameters)
    dynamic_params = dict(DEFAULT_DYNAMIC_PARAMETERS)
    if dynamic_parameters:
        dynamic_params.update(dynamic_parameters)
    ray_set = make_ray_set(
        mesh,
        seed=int(ray_params["seed"]),
        ray_count=int(ray_params["ray_count"]),
        focus_ray_percent=int(ray_params["focus_ray_percent"]),
        camera_radius_factor=float(ray_params["camera_radius_factor"]),
    )
    static_triangles = mesh.triangles()
    strategies, comparison = benchmark_strategies(
        mesh, static_triangles, ray_set, bvh_params
    )
    dynamic = benchmark_dynamic(mesh, dynamic_params, bvh_params)
    bounds = mesh.bounds()
    return {
        "schema": "bvh-benchmark-v1",
        "mesh": {
            "name": mesh.metadata.get("name", "unnamed_mesh"),
            "kind": mesh.metadata.get("kind", "unknown"),
            "vertex_count": len(mesh.vertices),
            "triangle_count": len(mesh.indices),
            "sha256": mesh_sha256(mesh),
            "bounds": bounds.as_dict(),
        },
        "scene_parameters": {
            "mesh": mesh.metadata.get("parameters", {}),
            "rays": ray_set.parameters,
            "bvh": bvh_params,
            "dynamic": dynamic_params,
        },
        "strategies": strategies,
        "comparison": comparison,
        "dynamic": dynamic,
        "validation": {
            "all_strategy_bvhs_valid": True,
            "all_strategies_return_same_nearest_hits": comparison[
                "all_nearest_hits_equal"
            ],
            "dense_region_claim_holds": comparison["sah_faster_in_dense_region"],
            "dynamic_rebuilds_are_local": dynamic["summary"][
                "all_frames_local"
            ],
        },
    }


def save_benchmark(result: dict[str, Any], path: str) -> None:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
