"""Drape a PBD cloth over a round table; log energy, jitter, collisions."""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloth.mesh import ClothMesh
from cloth.pbd import ClothSim, RoundTable

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "artifacts")

NX = NZ = 41
SPACING = 0.04
TABLE_R = 0.35
TABLE_H = 0.75
STEPS = 600
LOG_EVERY = 5


def build_sim(self_collision=True, iterations=12, k_bend=0.08, nx=NX, nz=NZ):
    mesh = ClothMesh(nx, nz, SPACING, center=(0.0, TABLE_H + 0.03, 0.0))
    table = RoundTable(TABLE_R, TABLE_H)
    return ClothSim(mesh, table=table, ground_y=0.0,
                    stretch_stiffness=1.0, bend_stiffness=k_bend,
                    iterations=iterations, self_collision=self_collision,
                    thickness=0.9 * SPACING,
                    damping=0.02, dt=1.0 / 60.0)


def run(sim, steps, log_every=LOG_EVERY, tail=120):
    log = []
    tail_pos = []
    for s in range(steps):
        sim.step()
        if s % log_every == 0 or s == steps - 1:
            e = sim.energy()
            speed = np.linalg.norm(sim.vel, axis=1)
            log.append({
                "step": s, "time": sim.time,
                "kinetic": e["kinetic"], "potential": e["potential"],
                "constraint": e["constraint"], "total": e["total"],
                "max_speed": float(speed.max()),
                "mean_speed": float(speed.mean()),
                "self_pairs": sim.n_self_pairs,
                "min_self_dist": sim.min_self_distance() or np.nan,
                "table_pen": sim.table_penetration(),
            })
        if s >= steps - tail and s % 2 == 0:
            tail_pos.append(sim.pos.copy())
    tail_arr = np.stack(tail_pos)
    jitter = tail_arr.std(axis=0).mean(axis=1)
    stats = {
        "jitter_mean": float(jitter.mean()),
        "jitter_max": float(jitter.max()),
        "final_min_self_dist": sim.min_self_distance(),
        "final_table_pen": sim.table_penetration(),
        "final_self_pairs": sim.n_self_pairs,
    }
    return log, stats


def save_csv(log, path):
    keys = list(log[0].keys())
    with open(path, "w") as f:
        f.write(",".join(keys) + "\n")
        for row in log:
            f.write(",".join(f"{row[k]:.6g}" if isinstance(row[k], float)
                             else str(row[k]) for k in keys) + "\n")


def main():
    os.makedirs(ART, exist_ok=True)
    sim = build_sim(self_collision=True)
    log, stats = run(sim, STEPS)
    save_csv(log, os.path.join(ART, "drape_log.csv"))
    np.savez(os.path.join(ART, "drape_final.npz"),
             positions=sim.pos, triangles=sim.mesh.triangles,
             quads=sim.mesh.quads, nx=sim.mesh.nx, nz=sim.mesh.nz,
             spacing=sim.mesh.spacing, table_r=TABLE_R, table_h=TABLE_H)
    fmt = lambda v: (round(v, 6) if isinstance(v, (int, float)) else v)
    print("self-collision ON :", {k: fmt(v) for k, v in stats.items()})

    sim_off = build_sim(self_collision=False)
    log_off, stats_off = run(sim_off, STEPS)
    save_csv(log_off, os.path.join(ART, "drape_log_nocoll.csv"))
    np.savez(os.path.join(ART, "drape_final_nocoll.npz"),
             positions=sim_off.pos, triangles=sim_off.mesh.triangles)
    print("self-collision OFF:", {k: fmt(v) for k, v in stats_off.items()})

    from experiments import render_drape
    render_drape.render_all(sim, sim_off, log, log_off)


if __name__ == "__main__":
    main()
