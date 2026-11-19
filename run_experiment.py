"""Command-line entry point for the ASG lighting experiment."""

from __future__ import annotations

import argparse
from pathlib import Path

from asg_experiment.experiment import ExperimentConfig, run_experiment


def parse_counts(value: str) -> tuple[int, ...]:
    counts = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    if not counts or counts[0] < 1:
        raise argparse.ArgumentTypeError("counts must be a comma-separated list of positive integers")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--counts",
        type=parse_counts,
        default=(1, 2, 3, 4, 6, 8, 12, 16),
        help="comma-separated ASG counts",
    )
    parser.add_argument("--mc-samples", type=int, default=1 << 20)
    parser.add_argument("--fit-samples", type=int, default=1024)
    parser.add_argument("--fit-max-nfev", type=int, default=150)
    parser.add_argument("--quick", action="store_true", help="smaller MC/fit workload")
    args = parser.parse_args()

    if args.quick:
        args.mc_samples = min(args.mc_samples, 1 << 16)
        args.fit_samples = min(args.fit_samples, 640)
        args.fit_max_nfev = min(args.fit_max_nfev, 100)

    config = ExperimentConfig(
        output_dir=args.output,
        lobe_counts=args.counts,
        fit_samples=args.fit_samples,
        fit_max_nfev=args.fit_max_nfev,
        mc_samples=args.mc_samples,
        selected_count=max(args.counts),
    )
    result = run_experiment(config)
    selected = result["scan"][-1]
    print(
        "completed: "
        f"N={selected['n_gauss']}, "
        f"fit={selected['fit_time_ms']:.1f} ms, "
        f"brightness rel-L1={100.0 * selected['brightness_rel_l1']:.3f}%"
    )


if __name__ == "__main__":
    main()
