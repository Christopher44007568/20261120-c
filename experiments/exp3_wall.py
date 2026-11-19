"""Near-wall probe: verify parallax-corrected reflections never cross walls."""

from __future__ import annotations

import os

import numpy as np

from .common import DATA_DIR, PLOT_DIR, save_csv
from parallax.geometry import normalize
from parallax.probe import ReflectionProbe, wall_penetration

# Right wall of the room: x = +8, interior satisfies x <= 8.
WALL_NORMAL = np.array([1.0, 0.0, 0.0])
WALL_D = 8.0


def build_near_wall_probe():
    # Influence box pressed against the wall; its right face is the wall itself.
    lo = np.array([2.0, -5.0, -4.0])
    hi = np.array([8.0, 5.0, 4.0])
    center = np.array([5.0, 0.0, 0.0])
    return ReflectionProbe("near_wall", center, lo, hi)


def run():
    probe = build_near_wall_probe()
    offsets = [0.25, 0.5, 1.0, 2.0]
    rng = np.random.default_rng(11)
    base_dirs = rng.normal(size=(16, 3))
    # Bias directions toward the wall so the test is deliberately adversarial.
    base_dirs[:, 0] = np.abs(base_dirs[:, 0]) + 0.8
    directions = [normalize(d) for d in base_dirs]

    rows = []
    worst = 0.0
    for offset in offsets:
        p = np.array([WALL_D - offset, 0.4, -0.6])
        for idx, r in enumerate(directions):
            result = wall_penetration(probe, p, r, WALL_NORMAL, WALL_D)
            worst = max(worst, result["penetration"])
            rows.append([
                offset, idx,
                f"{r[0]:.3f};{r[1]:.3f};{r[2]:.3f}",
                round(float(result["hit"][0]), 5),
                round(result["t"], 5),
                round(result["signed_distance"], 8),
                round(result["penetration"], 8),
                int(result["leaks"]),
            ])

    csv_path = os.path.join(DATA_DIR, "exp3_wall_penetration.csv")
    save_csv(csv_path, [
        "wall_distance_m", "ray", "direction", "hit_x_m", "ray_t_m",
        "signed_wall_distance_m", "penetration_m", "leaks",
    ], rows)

    # A deliberately wrong, oversized probe demonstrates the failure mode:
    # any influence volume extending past geometry leaks through the wall.
    bad = ReflectionProbe(
        "oversized", probe.center,
        probe.lo, probe.hi + np.array([1.5, 0.0, 0.0]))
    p_bad = np.array([WALL_D - 0.5, 0.4, -0.6])
    bad_rows = []
    for idx, r in enumerate(directions):
        res = wall_penetration(bad, p_bad, r, WALL_NORMAL, WALL_D)
        bad_rows.append([idx, round(float(res["hit"][0]), 4),
                         round(res["penetration"], 4), int(res["leaks"])])
    bad_path = os.path.join(DATA_DIR, "exp3_oversized_leak.csv")
    save_csv(bad_path, ["ray", "hit_x_m", "penetration_m", "leaks"], bad_rows)

    _plot(rows, bad_rows)
    leak_count = sum(int(r[-1]) for r in rows)
    return csv_path, worst, leak_count, bad_path


def _plot(rows, bad_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=False)

    offsets = sorted({r[0] for r in rows})
    data = [[r[6] for r in rows if r[0] == off] for off in offsets]
    bp = axes[0].boxplot(data)
    axes[0].set_xticks(range(1, len(offsets) + 1),
                       labels=[f"{o:g}" for o in offsets])
    axes[0].axhline(0.0, color="#5cb85c", lw=2, label="wall plane (0 leak)")
    axes[0].set_xlabel("shading point distance to wall (m)")
    axes[0].set_ylabel("penetration past wall (m)")
    axes[0].set_title("BPR probe fitted to the room")
    axes[0].legend()

    rays = [r[0] for r in bad_rows]
    pens = [r[2] for r in bad_rows]
    axes[1].bar(rays, pens, color="#c0504d")
    axes[1].axhline(0.0, color="k", lw=1)
    axes[1].set_xlabel("ray sample")
    axes[1].set_ylabel("penetration past wall (m)")
    axes[1].set_title("Oversized probe: expected leak (control case)")

    fig.tight_layout()
    out = os.path.join(PLOT_DIR, "exp3_wall.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    path, worst, leaks, bad_path = run()
    print("wrote", path)
    print(f"BPR max penetration: {worst:.2e} m, leaking rays: {leaks}")
    print("control (oversized) data:", bad_path)
