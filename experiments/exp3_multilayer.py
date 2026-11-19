"""Experiment 3: multi-layer cave channel connectivity vs threshold."""
import csv
import numpy as np
from cavegen import (generate_field, extract_cave, carve_vertical_shaft,
                     layer_channel_report)

SHAPE = (64, 64, 96)   # 3 stacked layers of 32 slices
N_LAYERS = 3
FREQUENCY = 4
THRESHOLDS = [round(t, 2) for t in np.arange(0.30, 0.71, 0.05)]
SEED = 7


def run(out_csv="artifacts/exp3_multilayer.csv"):
    field = generate_field(SHAPE, frequency=FREQUENCY, seed=SEED)
    rows = []
    for mode in ("pure", "shaft"):
        for thr in THRESHOLDS:
            res = extract_cave(field, thr)
            mask = res.mask
            if mode == "shaft":
                mask = carve_vertical_shaft(mask, radius=3)
            rep = layer_channel_report(mask, N_LAYERS)
            crossings_ok = all(c["connected"] for c in rep["crossings"])
            rows.append({
                "mode": mode,
                "threshold": thr,
                "air_voxels": int(mask.sum()),
                "crossings_ok": crossings_ok,
                "top_to_bottom": rep["top_to_bottom"],
                "largest_ratio": round(rep["largest_ratio"], 4),
                "layer_components": [l["components"] for l in rep["layers"]],
            })
    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    for row in run():
        print(row)
