"""Command-line entry point for the permutation benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from .benchmark import BenchmarkConfig, run_benchmark
from .report import all_validation_passed, write_artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prune shader permutations and benchmark first-frame compilation."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts"),
        help="artifact output directory (default: artifacts)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="measured runs; compile time uses the median (default: 3)",
    )
    parser.add_argument(
        "--draws-per-variant",
        type=int,
        default=4,
        help="scene requests per pruned variant (default: 4)",
    )
    parser.add_argument(
        "--cache-capacity",
        type=int,
        default=96,
        help="LRU shader cache entry budget (default: 96)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.runs < 1 or args.draws_per_variant < 1 or args.cache_capacity < 1:
        raise SystemExit("runs, draws-per-variant, and cache-capacity must be positive")
    config = BenchmarkConfig(
        cache_capacity=args.cache_capacity,
        draws_per_variant=args.draws_per_variant,
        runs=args.runs,
    )
    result = run_benchmark(config)
    paths = write_artifacts(result, args.out)
    before = result.baseline_first_frame
    after = result.pruned_first_frame
    print(
        f"permutations: {result.baseline_count} -> {result.pruned_count} "
        f"({100.0 * (1.0 - result.pruned_count / result.baseline_count):.2f}% fewer)"
    )
    print(
        "compile: "
        f"{result.baseline_compile.elapsed_ms:.3f} ms -> "
        f"{result.pruned_compile.elapsed_ms:.3f} ms"
    )
    print(
        "first frame: "
        f"{before.elapsed_ms:.3f} ms -> {after.elapsed_ms:.3f} ms "
        f"({100.0 * (1.0 - after.elapsed_ms / before.elapsed_ms):.2f}% lower)"
    )
    print(
        f"cache hit rate: {before.hit_rate:.2%} -> {after.hit_rate:.2%}; "
        f"invalid removed: {result.invalid_removed}"
    )
    print(
        f"dependency graph acyclic: {result.dependency_graph_acyclic}; "
        f"artifacts: {args.out}"
    )
    print("validation: PASS" if all_validation_passed(result) else "validation: FAIL")
    return 0 if all_validation_passed(result) else 1
