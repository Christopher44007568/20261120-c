"""Transmittance estimators along a ray segment inside a medium.

Four estimators used throughout the experiments:

* uniform ratio tracking: deterministic (optionally jittered) step size dt,
  weight *= 1 - sigma_t * dt; quadrature bias O(dt^2), nearly zero variance.
* exponential ratio tracking (Woodcock ratio tracking): free-flight distances
  sampled from the majorant; unbiased, weight *= 1 - sigma_t / majorant.
* exponential delta tracking with Russian roulette: binary unbiased estimator
  (1 if the ray survives, 0 if a real collision absorbs the path).
* uniform delta (RR): the same binary estimator but evaluated on a uniform grid.
"""

import numpy as np


def uniform_ratio(origins, dirs, t_enter, t_exit, medium, dt, rng, jitter=True):
    n = origins.shape[0]
    weight = np.ones(n)
    steps = np.zeros(n, dtype=np.int64)
    active = ~np.isnan(t_enter)
    seg = np.full(n, dt)
    if jitter:
        seg = rng.uniform(size=n) * dt
    t = t_enter + seg
    max_iters = int(np.ceil(np.nanmax(np.where(active, t_exit - t_enter, 0.0)) / dt)) + 2
    for _ in range(max_iters):
        run = active & (t < t_exit)
        if not run.any():
            break
        points = origins[run] + t[run, None] * dirs[run]
        sigma = medium.sigma_at(points)
        weight[run] *= np.clip(1.0 - sigma * dt, 0.0, 1.0)
        steps[run] += 1
        t[run] += dt
        active &= weight > 1e-9
    return weight, steps


def exponential_delta(origins, dirs, t_enter, t_exit, medium, rng):
    """Binary transmittance: delta tracking with Russian roulette.

    A virtual collision (sigma_a / sigma_t draw) keeps the ray alive, a real
    collision terminates it; surviving the whole segment estimates T = 1.
    """
    n = origins.shape[0]
    majorant = medium.majorant
    alive = np.ones(n, dtype=bool)
    steps = np.zeros(n, dtype=np.int64)
    t = t_enter.copy()
    for _ in range(256):
        run = alive & ~np.isnan(t) & (t < t_exit)
        if not run.any():
            break
        t[run] += rng.exponential(size=run.sum()) / majorant
        run = alive & ~np.isnan(t) & (t < t_exit)
        if not run.any():
            break
        points = origins[run] + t[run, None] * dirs[run]
        sigma = medium.sigma_at(points)
        steps[run] += 1
        real = rng.uniform(size=run.sum()) < (sigma / majorant)
        idx = np.flatnonzero(run)[real]
        alive[idx] = False
    return alive.astype(float), steps


def uniform_delta(origins, dirs, t_enter, t_exit, medium, dt, rng):
    """Binary transmittance evaluated on a uniform grid (Kulla & Fajalle style)."""
    n = origins.shape[0]
    alive = np.ones(n, dtype=bool)
    steps = np.zeros(n, dtype=np.int64)
    t = t_enter + rng.uniform(size=n) * dt
    active = ~np.isnan(t_enter)
    max_iters = int(np.ceil(np.nanmax(np.where(active, t_exit - t_enter, 0.0)) / dt)) + 2
    for _ in range(max_iters):
        run = active & alive & (t < t_exit)
        if not run.any():
            break
        points = origins[run] + t[run, None] * dirs[run]
        sigma = medium.sigma_at(points)
        steps[run] += 1
        collision = rng.uniform(size=run.sum()) < np.clip(sigma * dt, 0.0, 1.0)
        idx = np.flatnonzero(run)[collision]
        alive[idx] = False
        t[run] += dt
    return alive.astype(float), steps


def exponential_ratio(origins, dirs, t_enter, t_exit, medium, rng):
    n = origins.shape[0]
    majorant = medium.majorant
    weight = np.ones(n)
    steps = np.zeros(n, dtype=np.int64)
    t = t_enter.copy()
    active = ~np.isnan(t_enter)
    max_iters = 256
    for _ in range(max_iters):
        run = active & (t < t_exit)
        if not run.any():
            break
        t[run] += rng.exponential(size=run.sum()) / majorant
        run = active & (t < t_exit)
        if not run.any():
            break
        points = origins[run] + t[run, None] * dirs[run]
        sigma = medium.sigma_at(points)
        weight[run] *= 1.0 - sigma / majorant
        steps[run] += 1
    return weight, steps


ESTIMATORS = {
    "uniform_ratio": uniform_ratio,
    "exponential_ratio": exponential_ratio,
    "exponential_delta": exponential_delta,
    "uniform_delta": uniform_delta,
}
