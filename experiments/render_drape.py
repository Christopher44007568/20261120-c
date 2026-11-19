"""Plots and shaded renders for the drape experiment."""
from __future__ import annotations

import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloth.render import shaded_surface, new_fig

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "artifacts")


def _col(log, key):
    return np.array([row[key] for row in log], dtype=float)


def plot_energy(log, path):
    t = _col(log, "time")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    ax = axes[0]
    for k, lbl in [("kinetic", "kinetic"), ("potential", "potential"),
                   ("constraint", "constraint"), ("total", "total")]:
        ax.plot(t, _col(log, k), label=lbl)
    ax.set_title("Energy vs time")
    ax.set_xlabel("t [s]")
    ax.legend()
    ax.grid(alpha=0.3)
    ax = axes[1]
    ax.semilogy(t, np.maximum(_col(log, "max_speed"), 1e-12),
                label="max |v|")
    ax.semilogy(t, np.maximum(_col(log, "mean_speed"), 1e-12),
                label="mean |v|")
    ax.set_title("Vertex jitter (speed) vs time")
    ax.set_xlabel("t [s]")
    ax.legend()
    ax.grid(alpha=0.3)
    ax = axes[2]
    ax.plot(t, _col(log, "self_pairs"), label="active self-collision pairs")
    pen = _col(log, "table_pen")
    ax.plot(t, np.maximum(pen, 1e-17), label="table penetration [m]")
    ax.set_yscale("log")
    ax.set_title("Self-collision activity")
    ax.set_xlabel("t [s]")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def render_all(sim, sim_off, log, log_off):
    plot_energy(log, os.path.join(ART, "drape_energy.png"))
    table = sim.table
    fig, axes = new_fig(2)
    shaded_surface(axes[0], sim.pos, sim.mesh.triangles, table=table,
                   title="Draped cloth (self-collision ON) - view A")
    shaded_surface(axes[1], sim.pos, sim.mesh.triangles, table=table,
                   title="view B", azim=115, elev=28)
    fig.savefig(os.path.join(ART, "drape_render.png"), dpi=140)
    plt.close(fig)

    fig, axes = new_fig(2)
    shaded_surface(axes[0], sim.pos, sim.mesh.triangles, table=table,
                   title="self-collision ON")
    shaded_surface(axes[1], sim_off.pos, sim_off.mesh.triangles, table=table,
                   title="self-collision OFF (layers interpenetrate)")
    fig.savefig(os.path.join(ART, "drape_selfcoll.png"), dpi=140)
    plt.close(fig)


class _Mock:
    pass


def _mock_sim(npz_path, table):
    from cloth.mesh import ClothMesh
    d = np.load(npz_path)
    s = _Mock()
    s.pos = d["positions"]
    s.mesh = _Mock()
    s.mesh.triangles = d["triangles"]
    s.table = table
    return s


if __name__ == "__main__":
    import csv
    import sys
    sys.path.insert(0, os.path.dirname(ART))
    from cloth.pbd import RoundTable
    d = np.load(os.path.join(ART, "drape_final.npz"))
    table = RoundTable(float(d["table_r"]), float(d["table_h"]))
    sim = _mock_sim(os.path.join(ART, "drape_final.npz"), table)
    sim_off = _mock_sim(os.path.join(ART, "drape_final_nocoll.npz"), table)
    with open(os.path.join(ART, "drape_log.csv")) as f:
        log = [{k: float(v) for k, v in row.items()}
               for row in csv.DictReader(f)]
    with open(os.path.join(ART, "drape_log_nocoll.csv")) as f:
        log_off = [{k: float(v) for k, v in row.items()}
                   for row in csv.DictReader(f)]
    render_all(sim, sim_off, log, log_off)
    print("renders written to", ART)
