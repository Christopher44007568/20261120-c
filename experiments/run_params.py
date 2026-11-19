"""Parameter sweep: solver iterations x stiffness -> drape morphology."""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloth.mesh import ClothMesh
from cloth.pbd import ClothSim, RoundTable

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "artifacts")

NX = NZ = 25
SPACING = 0.05
TABLE_R = 0.35
TABLE_H = 0.75
STEPS = 360


def hem_wrinkle_count(pos, nx, nz):
    """Count folds around the hem: oscillations of radius vs azimuth."""
    boundary = []
    for i in range(nx):
        boundary += [i * nz, i * nz + nz - 1]
    for j in range(1, nz - 1):
        boundary += [j, (nx - 1) * nz + j]
    p = pos[np.array(sorted(set(boundary)))]
    theta = np.arctan2(p[:, 2], p[:, 0])
    r = np.hypot(p[:, 0], p[:, 2])
    order = np.argsort(theta)
    r = r[order]
    # smooth lightly, then count sign changes of the derivative
    k = np.ones(5) / 5.0
    rs = np.convolve(np.concatenate([r, r, r]), k, mode="same")[len(r):2 * len(r)]
    dr = np.diff(np.concatenate([rs, rs[:1]]))
    sign = np.sign(dr)
    sign[sign == 0] = 1
    crossings = int(np.sum(sign[1:] * sign[:-1] < 0))
    return crossings // 2


def morphology(sim):
    pos = sim.pos
    edges = sim.mesh.stretch_edges
    d = np.linalg.norm(pos[edges[:, 0]] - pos[edges[:, 1]], axis=1)
    stretch_err = float(np.max(np.abs(d - sim.rest_stretch) / sim.rest_stretch))
    r = np.hypot(pos[:, 0], pos[:, 2])
    hem = hem_wrinkle_count(pos, sim.mesh.nx, sim.mesh.nz)
    e = sim.energy()
    speed = np.linalg.norm(sim.vel, axis=1)
    return {
        "max_stretch_err": stretch_err,
        "skirt_radius_max": float(r.max()),
        "hem_wrinkles": hem,
        "constraint_energy": e["constraint"],
        "mean_speed": float(speed.mean()),
        "self_pairs": sim.n_self_pairs,
        "table_pen": sim.table_penetration(),
    }


def run_one(iterations, k_stretch, k_bend):
    mesh = ClothMesh(NX, NZ, SPACING, center=(0.0, TABLE_H + 0.03, 0.0))
    sim = ClothSim(mesh, table=RoundTable(TABLE_R, TABLE_H), ground_y=0.0,
                   stretch_stiffness=k_stretch, bend_stiffness=k_bend,
                   iterations=iterations, self_collision=True,
                   thickness=0.9 * SPACING, damping=0.02, dt=1.0 / 60.0)
    for _ in range(STEPS):
        sim.step()
    return morphology(sim)


def main():
    os.makedirs(ART, exist_ok=True)
    rows = []
    for iters in (2, 5, 10, 20):
        for k_bend in (0.02, 0.1, 0.5, 1.0):
            m = run_one(iters, 1.0, k_bend)
            rows.append({"iterations": iters, "k_stretch": 1.0,
                         "k_bend": k_bend, **m})
            print("bend", iters, k_bend, {k: round(v, 5) for k, v in m.items()})
    for iters in (2, 5, 10, 20):
        for k_stretch in (0.3, 0.6, 1.0):
            m = run_one(iters, k_stretch, 0.1)
            rows.append({"iterations": iters, "k_stretch": k_stretch,
                         "k_bend": 0.1, **m})
            print("stretch", iters, k_stretch, {k: round(v, 5) for k, v in m.items()})
    keys = list(rows[0].keys())
    with open(os.path.join(ART, "param_sweep.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("saved", os.path.join(ART, "param_sweep.csv"))


if __name__ == "__main__":
    main()
