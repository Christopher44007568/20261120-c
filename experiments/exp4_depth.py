"""Experiment 4: depth interpolation over an extremely foreshortened quad."""
import csv
import numpy as np
from cavegen.depth_interp import Vertex, rasterize_quad

W, H = 320, 240
FOCAL = 200.0
Z_NEAR, Z_FAR = 2.0, 50.0
HALF_X, FLOOR_Y = 2.0, -1.0


def _project(x, y, z):
    sx = FOCAL * x / z + W / 2
    sy = FOCAL * y / z + H / 2
    return Vertex(x=sx, y=sy, z=z, w=z)


def run(out_csv="artifacts/exp4_depth.csv"):
    quad = [
        _project(-HALF_X, FLOOR_Y, Z_NEAR),
        _project(HALF_X, FLOOR_Y, Z_NEAR),
        _project(HALF_X, FLOOR_Y, Z_FAR),
        _project(-HALF_X, FLOOR_Y, Z_FAR),
    ]
    res = rasterize_quad(quad, W, H)
    cov = res["covered"]

    # Analytic depth: ray through pixel hits plane y = FLOOR_Y.
    py, px = np.mgrid[0:H, 0:W]
    dy = (py + 0.5 - H / 2) / FOCAL
    with np.errstate(divide="ignore", invalid="ignore"):
        z_exact = np.where(dy != 0, FLOOR_Y / dy, np.nan)
    valid = cov & np.isfinite(z_exact) & (z_exact > 0)

    err_float = np.abs(res["float"][valid] - z_exact[valid])
    err_fixed_vs_float = np.abs(res["fixed"][valid] - res["float"][valid])
    rel_fixed = err_fixed_vs_float / np.abs(res["float"][valid])

    stats = {
        "pixels_covered": int(valid.sum()),
        "depth_range": f"{Z_NEAR}..{Z_FAR}",
        "float_max_abs_err_vs_exact": float(err_float.max()),
        "float_mean_abs_err_vs_exact": float(err_float.mean()),
        "fixed_max_abs_err_vs_float": float(err_fixed_vs_float.max()),
        "fixed_mean_abs_err_vs_float": float(err_fixed_vs_float.mean()),
        "fixed_max_rel_err_vs_float": float(rel_fixed.max()),
        "consistent_rel_1e-3": bool(np.all(rel_fixed < 1e-3)),
    }
    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(stats))
        writer.writeheader()
        writer.writerow(stats)
    return stats


if __name__ == "__main__":
    for k, v in run().items():
        print(f"{k}: {v}")
