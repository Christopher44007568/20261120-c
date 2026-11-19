"""Boundary seam: hard probe switching vs distance-weighted blending.

A genuine seam is a finite direction discontinuity that survives arbitrary
mesh refinement. We therefore measure the largest per-sample direction
change at several fixed physical step sizes: hard switching keeps a ~70
degree jump as the step shrinks, while the weighted blend's jump scales
linearly with the step and converges to zero (C0/C1 continuity).
"""

from __future__ import annotations

import os

import numpy as np

from .common import DATA_DIR, PLOT_DIR, save_csv
from parallax.geometry import normalize
from parallax.probe import ReflectionProbe
from parallax.seam import (direction_jump_series, limiting_discontinuity,
                           max_seam_jump, normalized_distance)


def adjacent_probes(half=4.0, overlap=2.0):
    """Two equal cubes whose influence boxes overlap by ``overlap`` metres."""
    shift = half - overlap * 0.5
    lo = np.array([-half, -half, -half])
    hi = np.array([half, half, half])
    left = ReflectionProbe("left", np.array([-shift, 0.0, 0.0]),
                           lo + np.array([-shift, 0, 0]),
                           hi + np.array([-shift, 0, 0]))
    right = ReflectionProbe("right", np.array([shift, 0.0, 0.0]),
                            lo + np.array([shift, 0, 0]),
                            hi + np.array([shift, 0, 0]))
    return left, right


def _sample_line(probes, reflect_dir, sample_count):
    xs = np.linspace(probes[0].lo[0] + 0.02,
                     probes[1].hi[0] - 0.02, sample_count)
    points = np.column_stack([xs, np.full_like(xs, 0.6),
                              np.full_like(xs, -0.4)])
    return xs, points


def run():
    half = 4.0
    overlap = 2.0
    probes = adjacent_probes(half=half, overlap=overlap)
    reflect_dir = normalize([0.35, 0.8, 0.48])

    # Coarse line for the per-position CSV / profile plot.
    xs, points = _sample_line(probes, reflect_dir, 161)
    hard_jumps, soft_jumps = direction_jump_series(
        probes, points, reflect_dir, blend_width=0.25)
    rows = []
    for i, x in enumerate(xs[1:]):
        rows.append([
            round(float(x), 4),
            round(normalized_distance(probes[0], points[i + 1]), 4),
            round(normalized_distance(probes[1], points[i + 1]), 4),
            round(float(hard_jumps[i]), 6),
            round(float(soft_jumps[i]), 6),
        ])
    csv_path = os.path.join(DATA_DIR, "exp2_seam_jumps.csv")
    save_csv(csv_path, ["x_m", "left_dist_01", "right_dist_01",
                        "hard_step_deg", "blended_step_deg"], rows)

    # Refinement test on the direction-vector L2 distance (continuity proof).
    convergence = _refinement_test(probes, reflect_dir)
    volume_rows = _volume_sweep(reflect_dir, overlap)
    hard_max, soft_max = max_seam_jump(probes, points, reflect_dir, 0.25)
    _plot(xs[1:], hard_jumps, soft_jumps, volume_rows,
          convergence, hard_max, soft_max)
    return csv_path, hard_max, soft_max, volume_rows, convergence


def _refinement_test(probes, reflect_dir):
    rows = []
    xs = np.linspace(-1.5, 1.5, 121)
    epsilons = (1e-2, 1e-3, 1e-4, 1e-5)
    hard, soft = limiting_discontinuity(probes, 0, xs, reflect_dir, epsilons)
    for eps, h, s in zip(epsilons, hard, soft):
        rows.append([f"{eps:.0e}", round(h, 6), round(h / eps, 3),
                     round(s, 8), round(s / eps, 5)])
    path = os.path.join(DATA_DIR, "exp2_refinement.csv")
    save_csv(path, ["epsilon_m", "hard_L2_gap", "hard_gap_over_eps",
                    "blended_L2_gap", "blended_gap_over_eps"], rows)
    return rows


def _volume_sweep(reflect_dir, overlap=2.0):
    """Grow probe size while keeping a fixed-width physical overlap."""
    rows = []
    for half in (2.0, 3.0, 4.0, 5.0, 6.0):
        probes = adjacent_probes(half=half, overlap=overlap)
        sample_count = 1601
        _, points = _sample_line(probes, reflect_dir, sample_count)
        hard_max, soft_max = max_seam_jump(probes, points, reflect_dir, 0.25)
        volume = probes[0].volume
        overlap_fraction = overlap / (2.0 * half)
        rows.append([half, round(volume, 3), round(overlap_fraction, 4),
                     round(hard_max, 4), round(soft_max, 4)])

    path = os.path.join(DATA_DIR, "exp2_volume_vs_seam.csv")
    save_csv(path, ["half_extent_m", "probe_volume_m3", "overlap_fraction",
                    "hard_max_jump_deg", "blended_max_jump_deg"], rows)
    return rows


def _plot(xs, hard, soft, volume_rows, convergence, hard_max, soft_max):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    axes[0].plot(xs, hard, label=f"hard switch (max {hard_max:.1f} deg)",
                 color="#c0504d")
    axes[0].plot(xs, soft, label=f"weighted blend (max {soft_max:.2f} deg)",
                 color="#5cb85c")
    axes[0].axvline(0.0, color="k", ls="--", lw=1, label="probe boundary")
    axes[0].set_xlabel("position x (m)")
    axes[0].set_ylabel("direction step (deg)")
    axes[0].set_title("Seam profile (coarse sampling)")
    axes[0].legend()

    eps = [float(r[0]) for r in convergence]
    axes[1].loglog(eps, [r[1] for r in convergence], "o-",
                   label="hard switch L2 gap", color="#c0504d")
    axes[1].loglog(eps, [r[3] for r in convergence], "s-",
                   label="blended L2 gap", color="#5cb85c")
    axes[1].set_xlabel("half-width epsilon (m)")
    axes[1].set_ylabel("max direction-vector L2 gap")
    axes[1].set_title("Continuity: hard gap fixed, blend gap ~ epsilon")
    axes[1].legend()

    halves = [r[0] for r in volume_rows]
    axes[2].plot(halves, [r[3] for r in volume_rows], "o-",
                 label="hard switch", color="#c0504d")
    axes[2].plot(halves, [r[4] for r in volume_rows], "s-",
                 label="weighted blend", color="#5cb85c")
    axes[2].set_xlabel("probe half extent (m)")
    axes[2].set_ylabel("max seam jump (deg)")
    axes[2].set_title("Probe volume vs seam magnitude")
    axes[2].legend()

    fig.tight_layout()
    out = os.path.join(PLOT_DIR, "exp2_seams.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    path, hard_max, soft_max, _, convergence = run()
    print("wrote", path)
    print(f"hard switch max jump: {hard_max:.3f} deg")
    print(f"blended     max jump: {soft_max:.3f} deg (coarse step)")
    for row in convergence:
        print("refinement:", row)
