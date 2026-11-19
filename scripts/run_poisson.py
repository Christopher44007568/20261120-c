#!/usr/bin/env python3
"""Run the noisy point-cloud Poisson reconstruction benchmark."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from poisson_recon.benchmark import BenchmarkConfig, run_benchmark  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="small smoke run")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "outputs" / "poisson"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.quick:
        config = BenchmarkConfig(
            n_points=6000,
            n_ground_truth=12000,
            seeds=(0,),
            noise_fractions=(0.0, 0.02, 0.04),
            depth=7,
        )
    else:
        config = BenchmarkConfig()
    payload = run_benchmark(args.out, config, make_plots=not args.no_plots)
    print(f"backend: {payload['backend']}  elapsed: {payload['elapsed_s']:.1f} s")
    print("shape         noise_mm  method      rmse_mm  p95_mm  chamfer_mm")
    for row in payload["summary"]:
        if row["noise_fraction"] in (0.0, 0.02, 0.04):
            print(
                f"{row['shape']:13s} {row['noise_mm']:8.1f}  "
                f"{row['method']:10s} {row['radial_rmse_mm_mean']:8.3f} "
                f"{row['radial_p95_mm_mean']:7.3f} {row['chamfer_mm_mean']:10.2f}"
            )
    for shape, check in payload["checks"].items():
        print(
            f"{shape}: clean={check['clean_rmse_mm']:.3f} mm, "
            f"max-noise={check['max_noise_rmse_mm']:.3f} mm, "
            f"improvement=x{check['max_noise_improvement_factor']:.2f}, "
            f"exponent={check['loglog_error_exponent']:.3f}, "
            f"robust={all(check[key] for key in check if key.endswith('_pass'))}"
        )


if __name__ == "__main__":
    main()
