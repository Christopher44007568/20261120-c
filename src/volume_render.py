"""Light transport inside a participating medium.

A ray crosses a slab of thickness L.  Transmittance is estimated three ways:

1. analytic ground truth (Beer-Lambert / exact optical-depth integral)
2. path-tracing reference: unbiased free-flight (Woodcock delta tracking)
3. ray marching at fixed step dt (left-Riemann or midpoint quadrature),
   reporting the number of marching steps and the resulting transmittance.

Both homogeneous and bounded heterogeneous media are supported.  All
randomness comes from a local LCG so the numbers are fully reproducible.
"""
from math import cos, exp, log, sin, sqrt


class Rng:
    def __init__(self, seed=123456789):
        self.state = seed & 0xFFFFFFFF

    def uniform(self):
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state / 4294967296.0

    def exponential(self, rate):
        return -log(1.0 - self.uniform()) / rate


def sigma_t_field(x, base=1.5, mode="homogeneous"):
    """Extinction coefficient at distance x along the ray."""
    if mode == "heterogeneous":
        return base * (1.0 + 0.8 * sin(2.5 * x))
    return base


def analytic_transmittance(length, base=1.5, mode="homogeneous"):
    if mode == "heterogeneous":
        tau = base * (length + 0.8 * (1.0 - cos(2.5 * length)) / 2.5)
    else:
        tau = base * length
    return exp(-tau)


def delta_tracking(rng, length, base=1.5, mode="homogeneous"):
    """Unbiased Woodcock delta tracking with a tight constant majorant.
    Returns (survived_flag, free_flight_steps, virtual_steps).
    virtual_steps counts null (delta) collisions in the heterogeneous case."""
    majorant = base * 1.8 if mode == "heterogeneous" else base
    x, steps, null_steps, survived = 0.0, 0, 0, 1
    while x < length:
        x += rng.exponential(majorant)
        steps += 1
        if x >= length:
            break
        if rng.uniform() <= sigma_t_field(min(x, length), base, mode) / majorant:
            survived = 0
            break
        null_steps += 1  # null (delta) collision: continue the flight
    return float(survived), steps, null_steps


def ray_march(length, dt, base=1.5, mode="homogeneous", rule="left"):
    """Deterministic fixed-step marcher.
    rule='left' uses the left Riemann sum (first-order, biased);
    rule='midpoint' uses the midpoint rule (second-order, much smaller bias).
    Returns (T_hat, steps_taken)."""
    n_full = int(length // dt)
    remainder = length - n_full * dt
    tau, x, steps = 0.0, 0.0, 0
    for _ in range(n_full):
        xs = x + (0.5 * dt if rule == "midpoint" else 0.0)
        tau += sigma_t_field(xs, base, mode) * dt
        x += dt
        steps += 1
    if remainder > 1e-12:
        xs = x + (0.5 * remainder if rule == "midpoint" else 0.0)
        tau += sigma_t_field(xs, base, mode) * remainder
        steps += 1
    return exp(-tau), steps


def run_experiment(length=2.0, base=1.5, n_rays=100000,
                   step_sizes=(0.5, 0.25, 0.1, 0.05),
                   modes=("homogeneous", "heterogeneous")):
    out = {"length": length, "base_sigma_t": base, "n_rays": n_rays,
           "media": {}}
    for mode in modes:
        truth = analytic_transmittance(length, base, mode)
        rng = Rng(20261120)
        pt_sum = pt_steps = pt_null = 0
        for _ in range(n_rays):
            t, s, null = delta_tracking(rng, length, base, mode)
            pt_sum += t
            pt_steps += s
            pt_null += null
        pt_est = pt_sum / n_rays
        pt_se = sqrt(pt_est * (1.0 - pt_est) / n_rays)
        rows = []
        for dt in step_sizes:
            for rule in ("left", "midpoint"):
                est, steps = ray_march(length, dt, base, mode, rule)
                rows.append({
                    "dt": dt,
                    "rule": rule,
                    "steps": steps,
                    "transmittance": est,
                    "abs_error_vs_analytic": abs(est - truth),
                    "rel_error_vs_analytic_pct":
                        100.0 * abs(est - truth) / truth,
                    "within_pt_1sigma": abs(est - pt_est) <= pt_se,
                })
        out["media"][mode] = {
            "analytic_transmittance": truth,
            "path_tracing": {
                "transmittance": pt_est,
                "standard_error": pt_se,
                "mean_free_flight_steps": pt_steps / n_rays,
                "mean_virtual_steps": pt_null / n_rays,
                "agrees_with_analytic_1sigma": abs(pt_est - truth) <= pt_se,
            },
            "ray_marching": rows,
        }
    return out
