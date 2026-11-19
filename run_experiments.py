"""Compare dual contouring vs marching cubes on sharp-featured fields."""
import json
import os
import time

import numpy as np
from skimage.measure import marching_cubes

from dual_contour import dual_contour
from fields import edge_samples, make_field
from gaussian_fit import box_surface_samples, diagnose, fit_gmm
from metrics import chamfer, edge_distance, sample_mesh, save_obj, sdf_error

BOUNDS = (-1.3, 1.3)
N = 48
FIELDS = ["box", "box_sphere_isect", "box_minus_cyl"]
ART = "artifacts"


def grid_values(f, n):
    axis = np.linspace(BOUNDS[0], BOUNDS[1], n + 1)
    gx, gy, gz = np.meshgrid(axis, axis, axis, indexing="ij")
    pts = np.stack([gx, gy, gz], axis=-1).reshape(-1, 3)
    return f(pts).reshape(n + 1, n + 1, n + 1)


def active_voxel_count(vals):
    inside = vals < 0.0
    n = vals.shape[0] - 1
    count = 0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                c = inside[i : i + 2, j : j + 2, k : k + 2]
                if c.any() and not c.all():
                    count += 1
    return count


def run_mc(vals, n):
    spacing = ((BOUNDS[1] - BOUNDS[0]) / n,) * 3
    verts, faces, _, _ = marching_cubes(vals, level=0.0, spacing=spacing)
    verts = verts + BOUNDS[0]
    return verts, faces.astype(np.int64)


def evaluate(name, f, verts, faces, ref_pts, edges):
    mesh_pts = sample_mesh(verts, faces, 60000, rng=np.random.default_rng(2))
    out = {}
    out.update(sdf_error(f, verts))
    out.update(chamfer(mesh_pts, ref_pts))
    out.update(edge_distance(edges, verts, faces))
    return out


def main():
    os.makedirs(ART, exist_ok=True)
    results = {}
    for name in FIELDS:
        f = make_field(name)
        vals = grid_values(f, N)
        n_active = active_voxel_count(vals)

        t0 = time.time()
        mc_v, mc_f = run_mc(vals, N)
        t_mc = time.time() - t0

        t0 = time.time()
        dc_v, dc_f, dc_cells = dual_contour(f, BOUNDS, N)
        t_dc = time.time() - t0

        # High-resolution reference surface (dense marching cubes).
        ref_vals = grid_values(f, 200)
        rv, rf = run_mc(ref_vals, 200)
        ref_pts = sample_mesh(rv, rf, 80000, rng=np.random.default_rng(3))

        edges = edge_samples(name)
        results[name] = {
            "active_voxels": n_active,
            "dc_cells_with_vertex": dc_cells,
            "mc": {"triangles": len(mc_f), "vertices": len(mc_v),
                   "time_s": round(t_mc, 3),
                   **evaluate(name, f, mc_v, mc_f, ref_pts, edges)},
            "dc": {"triangles": len(dc_f), "vertices": len(dc_v),
                   "time_s": round(t_dc, 3),
                   **evaluate(name, f, dc_v, dc_f, ref_pts, edges)},
        }
        save_obj(os.path.join(ART, f"{name}_mc.obj"), mc_v, mc_f)
        save_obj(os.path.join(ART, f"{name}_dc.obj"), dc_v, dc_f)
        print(f"[done] {name}: active={n_active} "
              f"MC tris={len(mc_f)} DC tris={len(dc_f)}")

    # Gaussian-mixture fitting on box surface samples.
    samples, labels = box_surface_samples()
    results["gaussian_fit"] = []
    for k in (2, 3, 6, 12):
        means, covs, weights = fit_gmm(samples, k)
        rep = diagnose(samples, labels, means, covs, weights, k)
        results["gaussian_fit"].append(rep)
        print(f"[done] gmm k={k}: err={rep['err_mean']:.4f} "
              f"anisotropy={rep['anisotropy']:.2f}")

    with open(os.path.join(ART, "results.json"), "w") as fh:
        json.dump(results, fh, indent=2)
    print("wrote artifacts/results.json")


if __name__ == "__main__":
    main()
