from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .benchmark import (
    DEFAULT_DYNAMIC_PARAMETERS,
    DEFAULT_RAY_PARAMETERS,
    DEFAULT_SCENE,
    run_benchmark,
    save_benchmark,
)
from .mesh import (
    generate_random_mesh,
    load_mesh,
    make_fixed_mesh,
    save_mesh,
)


def command_generate(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    random_mesh = generate_random_mesh(
        triangle_count=args.triangles,
        seed=args.seed,
        dense_triangle_count=args.dense_triangles,
    )
    fixed_mesh = make_fixed_mesh()
    save_mesh(random_mesh, output_dir / "random_mesh.json")
    save_mesh(fixed_mesh, output_dir / "fixed_mesh.json")
    print(f"wrote {output_dir / 'random_mesh.json'}")
    print(f"wrote {output_dir / 'fixed_mesh.json'}")
    return 0


def command_benchmark(args: argparse.Namespace) -> int:
    mesh = load_mesh(args.mesh)
    ray_parameters = {
        "seed": args.ray_seed,
        "ray_count": args.rays,
        "focus_ray_percent": args.focus_percent,
        "camera_radius_factor": DEFAULT_RAY_PARAMETERS["camera_radius_factor"],
    }
    bvh_parameters = {
        "max_leaf_size": args.max_leaf,
        "sah_bins": args.sah_bins,
        "build_repeats": args.build_repeats,
        "traversal_repeats": args.traversal_repeats,
    }
    dynamic_parameters = {
        "frames": args.dynamic_frames,
        "step": [args.dynamic_step_x, args.dynamic_step_y, args.dynamic_step_z],
        "min_group_size": args.dynamic_group_min,
        "max_group_size": args.dynamic_group_max,
    }
    result = run_benchmark(
        mesh,
        ray_parameters=ray_parameters,
        bvh_parameters=bvh_parameters,
        dynamic_parameters=dynamic_parameters,
    )
    save_benchmark(result, args.out)
    comparison = result["comparison"]
    print(
        f"mesh={mesh.metadata.get('name')} triangles={len(mesh.indices)} "
        f"rays={ray_parameters['ray_count']}"
    )
    for strategy in ("sah", "median", "lbvh"):
        stats = result["strategies"][strategy]
        traversal = stats["traversal"]
        focus = stats["focus_traversal"]
        print(
            f"{strategy:6} build={stats['build_time_ms']:.3f}ms "
            f"nodes={stats['node_count']} avg_leaf={stats['average_leaf_triangles']:.3f} "
            f"visits={traversal['node_visits']} tests={traversal['triangle_tests']} "
            f"focus_tests={focus['triangle_tests']}"
        )
    print(
        "SAH dense-region reduction: "
        f"visits vs median={comparison['sah_focus_node_visit_reduction_vs_median_percent']:.2f}% "
        f"tests vs median={comparison['sah_focus_triangle_test_reduction_vs_median_percent']:.2f}%"
    )
    print(f"SAH dense-region claim verified={comparison['sah_faster_in_dense_region']}")
    dynamic_summary = result["dynamic"]["summary"]
    print(
        "dynamic local rebuilds="
        f"{dynamic_summary['all_frames_local']} "
        f"local/full time={dynamic_summary['local_to_full_time_ratio']:.4f} "
        f"overlap_volume_sum={dynamic_summary['total_overlap_volume']:.6f}"
    )
    print(f"wrote {args.out}")
    valid = (
        comparison["all_nearest_hits_equal"]
        and comparison["sah_faster_in_dense_region"]
        and dynamic_summary["all_frames_local"]
    )
    return 0 if valid else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bvh")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="write reproducible mesh JSON")
    generate.add_argument("--output-dir", default="data")
    generate.add_argument("--triangles", type=int, default=DEFAULT_SCENE["triangle_count"])
    generate.add_argument(
        "--dense-triangles", type=int, default=DEFAULT_SCENE["dense_triangle_count"]
    )
    generate.add_argument("--seed", type=int, default=DEFAULT_SCENE["seed"])
    generate.set_defaults(func=command_generate)

    benchmark = subparsers.add_parser("benchmark", help="run all strategies")
    benchmark.add_argument("--mesh", default="data/random_mesh.json")
    benchmark.add_argument("--out", default="artifacts/benchmark.json")
    benchmark.add_argument("--rays", type=int, default=DEFAULT_RAY_PARAMETERS["ray_count"])
    benchmark.add_argument(
        "--focus-percent",
        type=int,
        default=DEFAULT_RAY_PARAMETERS["focus_ray_percent"],
    )
    benchmark.add_argument("--ray-seed", type=int, default=DEFAULT_RAY_PARAMETERS["seed"])
    benchmark.add_argument("--max-leaf", type=int, default=4)
    benchmark.add_argument("--sah-bins", type=int, default=16)
    benchmark.add_argument("--build-repeats", type=int, default=3)
    benchmark.add_argument("--traversal-repeats", type=int, default=5)
    benchmark.add_argument(
        "--dynamic-frames", type=int, default=DEFAULT_DYNAMIC_PARAMETERS["frames"]
    )
    benchmark.add_argument("--dynamic-step-x", type=float, default=0.025)
    benchmark.add_argument("--dynamic-step-y", type=float, default=0.015)
    benchmark.add_argument("--dynamic-step-z", type=float, default=0.01)
    benchmark.add_argument("--dynamic-group-min", type=int, default=16)
    benchmark.add_argument("--dynamic-group-max", type=int, default=32)
    benchmark.set_defaults(func=command_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
