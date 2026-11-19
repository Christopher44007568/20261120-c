#!/usr/bin/env python3
"""Run walking analysis, Poisson benchmark, and generate the report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_report import main as make_report  # noqa: E402
from poisson_recon.benchmark import BenchmarkConfig, run_benchmark  # noqa: E402
from run_walking import main as run_walking  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-poisson", action="store_true")
    args = parser.parse_args()
    run_walking()
    if not args.skip_poisson:
        print("running Poisson noise benchmark ...")
        if args.quick:
            config = BenchmarkConfig(
                n_points=6000,
                n_ground_truth=12000,
                seeds=(0,),
                noise_fractions=(0.0, 0.02, 0.04),
                depth=7,
            )
            run_benchmark(ROOT / "outputs" / "poisson", config)
        else:
            run_benchmark(ROOT / "outputs" / "poisson", BenchmarkConfig())
        print("Poisson benchmark complete")
    make_report()


if __name__ == "__main__":
    main()
