"""Experiment 1: cave connectivity vs noise frequency (fixed threshold)."""
import csv

from cavegen import generate_field, extract_cave, analyze

SHAPE = (64, 64, 64)
THRESHOLD = 0.5
FREQUENCIES = [1, 2, 3, 4, 6, 8]
SEED = 42


def run(out_csv="artifacts/exp1_frequency.csv"):
    rows = []
    for freq in FREQUENCIES:
        field = generate_field(SHAPE, frequency=freq, seed=SEED)
        res = extract_cave(field, THRESHOLD)
        conn = analyze(res.mask)
        rows.append({
            "frequency": freq,
            "threshold": THRESHOLD,
            "air_voxels": res.air_voxels,
            "solid_voxels": res.solid_voxels,
            "mc_vertices": res.vertices,
            "mc_faces": res.faces,
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
