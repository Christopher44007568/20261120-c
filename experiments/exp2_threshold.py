"""Experiment 2: connectivity vs noise threshold, per frequency."""
import csv
import numpy as np
from cavegen import generate_field, extract_cave, analyze

SHAPE = (64, 64, 64)
FREQUENCIES = [2, 4, 8]
THRESHOLDS = [round(t, 2) for t in np.arange(0.30, 0.71, 0.05)]
SEED = 42


def run(out_csv="artifacts/exp2_threshold.csv"):
    rows = []
    for freq in FREQUENCIES:
        field = generate_field(SHAPE, frequency=freq, seed=SEED)
        for thr in THRESHOLDS:
            res = extract_cave(field, thr)
            conn = analyze(res.mask)
            rows.append({
                "frequency": freq,
                "threshold": thr,
                "air_voxels": res.air_voxels,
                "mc_vertices": res.vertices,
                "components": conn.n_components,
                "largest_ratio": round(conn.largest_ratio, 4),
                "percolates_z": conn.percolates_z,
            })
    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    for row in run():
        print(row)
