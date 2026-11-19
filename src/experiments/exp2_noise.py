"""Noise variance, bias, cost and efficiency of every transmittance estimator."""

import csv
import time
import numpy as np

from ..rng import RNG
from ..medium import HomogeneousMedium, Medium
from ..fields import smoke_plume, SMOKE_BOUNDS
from ..ray import intersect_box
from .. import sampling
from .common import SIGMA_T, N_RAYS_NOISE, BATCHES, DATA_DIR, ensure_dirs


def _make_rays(bounds, n, seed):
    rng = np.random.default_rng(seed)
    lo, hi = bounds
    origins = np.empty((n, 3))
    origins[:, 0] = lo[0] - 0.01
    origins[:, 1] = rng.uniform(lo[1], hi[1], n)
    origins[:, 2] = rng.uniform(lo[2], hi[2], n)
    dirs = np.zeros((n, 3))
    dirs[:, 0] = 1.0
    return origins, dirs


def _estimate(name, medium, origins, dirs, t_enter, t_exit, rng):
    if name.startswith("uniform ratio"):
        dt = float(name.split("dt=")[1])
        return sampling.uniform_ratio(origins, dirs, t_enter, t_exit,
                                      medium, dt, rng, jitter=False)
    if name == "exponential ratio":
        return sampling.exponential_ratio(origins, dirs, t_enter, t_exit, medium, rng)
    if name == "exponential delta RR":
        return sampling.exponential_delta(origins, dirs, t_enter, t_exit, medium, rng)
    dt = float(name.split("dt=")[1])
    return sampling.uniform_delta(origins, dirs, t_enter, t_exit, medium, dt, rng)


ESTIMATOR_NAMES = [
    "uniform ratio dt=0.2",
    "uniform ratio dt=0.1",
    "uniform ratio dt=0.05",
    "exponential ratio",
    "exponential delta RR",
    "uniform RR dt=0.05",
]


def _benchmark(field_name, medium, bounds, truth):
    n = N_RAYS_NOISE // BATCHES
    rng = RNG(99)
    rows = []
    origins_all, dirs_all = _make_rays(bounds, N_RAYS_NOISE, 5)
    t_enter, t_exit = intersect_box(origins_all, dirs_all, bounds)
    for name in ESTIMATOR_NAMES:
        batch_means = np.empty(BATCHES)
        steps = 0
        t0 = time.perf_counter()
        for b in range(BATCHES):
            sl = slice(b * n, (b + 1) * n)
            values, step_counts = _estimate(
                name, medium, origins_all[sl], dirs_all[sl],
                t_enter[sl], t_exit[sl], rng)
            batch_means[b] = values.mean()
            steps += step_counts.sum()
        seconds = time.perf_counter() - t0
        mean = batch_means.mean()
        batch_var = batch_means.var(ddof=1)
        bias = mean - truth
        mse = batch_var + bias ** 2
        rows.append({
            "field": field_name,
            "estimator": name,
            "mean": mean,
            "reference": truth,
            "bias": bias,
            "batch_var": batch_var,
            "mse": mse,
            "avg_steps": steps / N_RAYS_NOISE,
            "seconds": seconds,
            "efficiency": 1.0 / (mse * seconds),
        })
    return rows


def run():
    ensure_dirs()
    all_rows = []

    # Heterogeneous smoke plume; reference = fine-step unbiased-ish quadrature.
    smoke = Medium(SMOKE_BOUNDS, smoke_plume(), sigma_t0=3.0, albedo=0.95)
    ref_origins, ref_dirs = _make_rays(SMOKE_BOUNDS, N_RAYS_NOISE, 5)
    re, rx = intersect_box(ref_origins, ref_dirs, SMOKE_BOUNDS)
    ref_values, _ = sampling.uniform_ratio(ref_origins, ref_dirs, re, rx,
                                           smoke, 0.01, RNG(321), jitter=False)
    smoke_truth = float(ref_values.mean())
    all_rows += _benchmark("smoke", smoke, SMOKE_BOUNDS, smoke_truth)

    # Dense homogeneous slab, thickness 3 m (matches the transmittance study).
    slab_bounds = [[0.0, 0.0, 0.0], [3.0, 1.0, 1.0]]
    slab = HomogeneousMedium(slab_bounds, SIGMA_T)
    all_rows += _benchmark("homogeneous", slab, slab_bounds,
                           slab.analytic_transmittance(3.0))

    path = f"{DATA_DIR}/noise_variance.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    return all_rows


if __name__ == "__main__":
    for row in run():
        print(f"{row['field']:11s} {row['estimator']:22s} "
              f"mse={row['mse']:.3e} steps={row['avg_steps']:7.2f} "
              f"t={row['seconds']:.3f} eff={row['efficiency']:.3e}")
