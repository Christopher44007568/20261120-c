#!/usr/bin/env python3
"""End-to-end checks for numerical properties, exports, and ABI layout."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bindings"))

import curl_noise as bindings  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def check_artifacts(root: Path) -> dict:
    required = [
        "flow_field.csv",
        "particles_initial.csv",
        "particles_final.csv",
        "trajectories.csv",
        "frequency_sweep.csv",
        "metrics.json",
        "summary.txt",
        "flow_field.svg",
        "trajectories.svg",
        "frequency_curvature.svg",
        "layout_c.json",
        "layout_python.json",
    ]
    for name in required:
        path = root / name
        require(path.exists() and path.stat().st_size > 0, f"missing artifact: {path}")

    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    config = metrics["config"]
    flow_rows = read_rows(root / "flow_field.csv")
    initial = read_rows(root / "particles_initial.csv")
    final = read_rows(root / "particles_final.csv")
    trajectories = read_rows(root / "trajectories.csv")
    sweep = read_rows(root / "frequency_sweep.csv")

    require(len(flow_rows) == 96 * 96, "flow field row count mismatch")
    require(len(initial) == config["particle_count"], "initial particle count mismatch")
    require(len(final) == config["particle_count"], "final particle count mismatch")
    expected_trace_rows = (
        config["trace_count"] * metrics["trajectory"]["samples_per_trace"]
    )
    require(len(trajectories) == expected_trace_rows, "trajectory row count mismatch")
    require(len(sweep) == len(metrics["frequency_sweep"]), "sweep row count mismatch")

    divergence = max(abs(float(row["divergence"])) for row in flow_rows)
    require(divergence < 1e-5, f"CSV divergence too large: {divergence}")
    require(metrics["flow"]["divergence_max_abs"] < 1e-6, "divergence threshold failed")
    require(metrics["checks"]["divergence_free"], "divergence-free check failed")

    density = metrics["density"]
    require(not density["clustered"], "density classified as clustered")
    require(density["final"]["clustering_index"] < 2.0, "clustering index too high")
    require(density["final"]["reduced_chi2"] < 2.0, "density chi-square too high")
    require(density["final"]["uniformity"] > 0.80, "density uniformity too low")
    require(metrics["checks"]["distribution_retained"], "distribution check failed")

    trajectory = metrics["trajectory"]
    require(trajectory["mean_curvature"] > 0.0, "trajectories are not curved")
    require(trajectory["samples"] > 0, "missing trajectory samples")
    require(metrics["checks"]["trajectories_curve"], "curvature check failed")

    frequencies = [float(row["frequency"]) for row in sweep]
    curvatures = [float(row["mean_curvature"]) for row in sweep]
    require(frequencies == sorted(frequencies), "frequency sweep is not sorted")
    require(len(frequencies) >= 6, "frequency sweep is too short")
    require(
        curvatures[-1] > 1.5 * curvatures[0],
        "high frequency did not increase curvature",
    )
    require(
        metrics["checks"]["frequency_curvature_correlation"] > 0.85,
        "frequency-curvature correlation too low",
    )
    require(
        metrics["checks"]["frequency_increases_curvature"],
        "frequency conclusion check failed",
    )
    summary = (root / "summary.txt").read_text(encoding="utf-8")
    require("结论:" in summary, "summary has no conclusion section")
    return metrics


def check_layout(root: Path) -> None:
    descriptor = bindings.layout_descriptor()
    c_layout = json.loads((root / "layout_c.json").read_text(encoding="utf-8"))
    py_layout = json.loads((root / "layout_python.json").read_text(encoding="utf-8"))
    require(c_layout == descriptor, "C ABI JSON does not match ctypes descriptor")
    require(py_layout == descriptor, "Python ABI JSON does not match descriptor")
    bindings.verify_layout(root / "layout_c.json")
    require(descriptor["structs"]["CNFlowParams"]["size"] == 36, "FlowParams size")
    require(descriptor["structs"]["CNParticle"]["size"] == 28, "Particle size")
    require(
        descriptor["structs"]["CNTrajectorySample"]["size"] == 36,
        "TrajectorySample size",
    )
    require(descriptor["arrays"]["particles"]["rank"] == 1, "particle rank")
    require(descriptor["arrays"]["particles"]["order"] == "c_contiguous", "particle order")
    require(descriptor["arrays"]["flow_samples"]["rank"] == 2, "flow rank")
    require(descriptor["arrays"]["trajectory_samples"]["rank"] == 2, "trace rank")


def check_numerical_flow() -> float:
    binding = bindings.CurlNoise()
    params = binding.default_params()
    params.octaves = 4
    params.modes_per_octave = 5
    params.frequency = 2.0
    max_divergence = 0.0
    with binding.field(params) as field:
        require(binding.lib.cn_field_mode_count(field.pointer) == 20, "mode count")
        for row in range(64):
            for column in range(64):
                x = (column + 0.5) / 64.0
                y = (row + 0.5) / 64.0
                divergence = binding.divergence(field, x, y, 1e-5)
                max_divergence = max(max_divergence, abs(divergence))
        vx0, vy0 = binding.velocity(field, 0.123, 0.456)
        vx1, vy1 = binding.velocity(field, 1.123, 1.456)
        require(abs(vx0 - vx1) < 2e-6 and abs(vy0 - vy1) < 2e-6, "field not periodic")
    require(max_divergence < 1e-6, f"binding divergence too large: {max_divergence}")
    return max_divergence


def bin_density(particles, count: int, bins: int = 16) -> tuple[float, float]:
    histogram = [0] * (bins * bins)
    for index in range(count):
        bx = min(bins - 1, max(0, int(particles[index].x * bins)))
        by = min(bins - 1, max(0, int(particles[index].y * bins)))
        histogram[by * bins + bx] += 1
    expected = count / (bins * bins)
    chi2 = sum((value - expected) ** 2 / expected for value in histogram)
    reduced = chi2 / (bins * bins - 1)
    cv = math.sqrt(sum((value - expected) ** 2 for value in histogram) / (bins * bins)) / expected
    return reduced, cv * math.sqrt(expected)


def check_advection_density() -> tuple[float, float]:
    binding = bindings.CurlNoise()
    count = 4096
    particles = (bindings.Particle * count)()
    binding.lib.cn_particles_init(particles, count, 1.0, 20261120, 0.85)
    initial_chi2, initial_index = bin_density(particles, count)
    with binding.field() as field:
        binding.lib.cn_particle_advect(field.pointer, particles, count, 0.005, 300)
    final_chi2, final_index = bin_density(particles, count)
    require(final_chi2 < 2.0, f"advected density chi-square too high: {final_chi2}")
    require(final_index < 2.0, f"advected clustering index too high: {final_index}")
    require(
        final_index < max(2.0, initial_index * 2.5),
        "advection produced excessive concentration",
    )
    return final_chi2, final_index


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    metrics = check_artifacts(root)
    check_layout(root)
    numerical_divergence = check_numerical_flow()
    advect_chi2, advect_index = check_advection_density()
    print(
        "checks passed: "
        f"div={numerical_divergence:.2e}, "
        f"cluster_index={metrics['density']['final']['clustering_index']:.3f}, "
        f"frequency_r={metrics['checks']['frequency_curvature_correlation']:.3f}, "
        f"advect_chi2={advect_chi2:.3f}, advect_index={advect_index:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
