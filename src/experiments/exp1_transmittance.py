"""Transmittance vs optical depth: uniform stepping vs exponential stepping."""

import time
import csv
import numpy as np

from ..rng import RNG
from ..medium import HomogeneousMedium
from ..ray import intersect_box
from .. import sampling
from .common import (SIGMA_T, SLAB_BOUNDS, N_RAYS_CURVE,
                     DATA_DIR, ensure_dirs)

DT = 0.08


def _rays_through_slab(depth, n):
    """Rays entering a slab whose thickness along x is `depth`."""
    bounds = np.array([[0.0, 0.0, 0.0], [depth, 1.0, 1.0]])
    origins = np.zeros((n, 3))
    origins[:, 0] = -0.01
    dirs = np.zeros((n, 3))
    dirs[:, 0] = 1.0
    return origins, dirs, bounds


def run():
    ensure_dirs()
    rng = RNG(2024)
    depths = np.linspace(0.05, 3.0, 20)
    rows = []
    for depth in depths:
        origins, dirs, bounds = _rays_through_slab(depth, N_RAYS_CURVE)
        medium = HomogeneousMedium(bounds, SIGMA_T)
        t_enter, t_exit = intersect_box(origins, dirs, bounds)
        truth = medium.analytic_transmittance(depth)

        t0 = time.perf_counter()
        u_ratio, u_steps = sampling.uniform_ratio(
            origins, dirs, t_enter, t_exit, medium, DT, rng)
        u_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        e_ratio, e_steps = sampling.exponential_ratio(
            origins, dirs, t_enter, t_exit, medium, rng)
        e_time = time.perf_counter() - t0

        e_bern, _ = sampling.exponential_delta(
            origins, dirs, t_enter, t_exit, medium, rng)
        u_bern, _ = sampling.uniform_delta(
            origins, dirs, t_enter, t_exit, medium, DT, rng)

        rows.append({
            "depth": depth,
            "truth": truth,
            "uniform_mean": u_ratio.mean(),
            "uniform_var": u_ratio.var(ddof=1),
            "exponential_mean": e_ratio.mean(),
            "exponential_var": e_ratio.var(ddof=1),
            "exp_bernoulli_var": e_bern.var(ddof=1),
            "uniform_bernoulli_var": u_bern.var(ddof=1),
            "uniform_steps": u_steps.mean(),
            "exponential_steps": e_steps.mean(),
            "uniform_time": u_time,
            "exponential_time": e_time,
        })

    path = f"{DATA_DIR}/transmittance_curves.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    rows = run()
    for row in rows:
        print(f"d={row['depth']:.3f} truth={row['truth']:.4f} "
              f"uni={row['uniform_mean']:.4f} exp={row['exponential_mean']:.4f} "
              f"steps u/e={row['uniform_steps']:.1f}/{row['exponential_steps']:.2f}")
