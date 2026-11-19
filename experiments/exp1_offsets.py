"""Compare reflection offsets before/after parallax correction.

Schemes: uncorrected cubemap, single-plane projection and box projected
reflection (BPR). Ground truth is the specular ray hitting the room box.
"""

from __future__ import annotations

import os

import numpy as np

from .common import (DATA_DIR, PLOT_DIR, ROOM_HI, ROOM_LO,
                     deterministic_directions, room_probe, save_csv)
from parallax.geometry import angle_between, normalize
from parallax.probe import offset_metrics, true_reflection_hit


def plane_projection_row(probe, p, r):
    """Floor-plane projection variant used by planar reflection probes."""
    normal = np.array([0.0, 0.0, 1.0])
    d = ROOM_LO[2]
    t = (d - p[2]) / r[2] if abs(r[2]) > 1e-9 else None
    if t is None or t < 0:
        return None
    hit = p + t * r
    direction = normalize(hit - probe.center)
    truth = true_reflection_hit(p, r, ROOM_LO, ROOM_HI)
    return {
        "hit": hit,
        "world_offset": float(np.linalg.norm(hit - truth)),
        "angular_error_deg": np.degrees(
            angle_between(direction, truth - probe.center)),
    }


def run():
    probe = room_probe(scale=1.0)
    p = np.array([2.5, 1.5, -1.0])
    directions = deterministic_directions()

    rows = []
    for idx, r in enumerate(directions):
        metrics = offset_metrics(probe, p, r, ROOM_LO, ROOM_HI)
        plane = plane_projection_row(probe, p, r)
        rows.append([
            idx,
            f"{r[0]:.3f};{r[1]:.3f};{r[2]:.3f}",
            round(metrics["uncorrected"]["world_offset"], 4),
            round(metrics["uncorrected"]["angular_error_deg"], 4),
            round(plane["world_offset"], 4) if plane else "miss",
            round(plane["angular_error_deg"], 4) if plane else "miss",
            round(metrics["box"]["world_offset"], 4),
            round(metrics["box"]["angular_error_deg"], 4),
        ])

    csv_path = os.path.join(DATA_DIR, "exp1_reflection_offsets.csv")
    save_csv(csv_path, [
        "sample", "direction",
        "uncorrected_world_offset_m", "uncorrected_angular_err_deg",
        "plane_world_offset_m", "plane_angular_err_deg",
        "box_world_offset_m", "box_angular_err_deg",
    ], rows)

    header = [
        "sample", "direction",
        "uncorrected_world_offset_m", "uncorrected_angular_err_deg",
        "plane_world_offset_m", "plane_angular_err_deg",
        "box_world_offset_m", "box_angular_err_deg",
    ]

    # Aggregate statistics over all directions.
    def column(name):
        col_idx = header.index(name)
        return np.array([float(row[col_idx]) for row in rows
                         if row[col_idx] != "miss"])

    summary = {
        "uncorrected": column("uncorrected_angular_err_deg"),
        "plane": column("plane_angular_err_deg"),
        "box": column("box_angular_err_deg"),
    }

    _plot(summary, rows)
    return csv_path, summary


def _plot(summary, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    labels = ["Uncorrected", "Plane projection", "Box BPR"]
    keys = ["uncorrected", "plane", "box"]
    means = [float(np.mean(summary[k])) for k in keys]
    stds = [float(np.std(summary[k])) for k in keys]
    axes[0].bar(labels, means, yerr=stds, capsize=5,
                color=["#c0504d", "#f0ad4e", "#5cb85c"])
    axes[0].set_ylabel("Angular error (deg)")
    axes[0].set_title("Cubemap fetch direction error")
    axes[0].tick_params(axis="x", rotation=15)

    samples = [row[0] for row in rows]
    for key, col, color in [
        ("uncorrected", 3, "#c0504d"),
        ("plane", 5, "#f0ad4e"),
        ("box", 7, "#5cb85c"),
    ]:
        xs, ys = [], []
        for row in rows:
            if row[col] != "miss":
                xs.append(row[0])
                ys.append(float(row[col]))
        axes[1].plot(xs, ys, marker="o", ms=3, label=key, color=color)
    axes[1].set_xlabel("Ray sample")
    axes[1].set_ylabel("Angular error (deg)")
    axes[1].set_title("Per-ray error across the sphere")
    axes[1].legend()

    fig.tight_layout()
    out = os.path.join(PLOT_DIR, "exp1_offsets.png")
    fig.savefig(out, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    path, summary = run()
    print("wrote", path)
    for key, vals in summary.items():
        print(f"{key:12s} mean angular err = {np.mean(vals):7.3f} deg")
