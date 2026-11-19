"""End-to-end Poisson reconstruction experiment.

Scenarios
---------
* Clean sphere and torus (consistent normals) -> baseline.
* Noisy sphere and torus with 35% randomly flipped normals, reconstructed
  both *before* and *after* normal alignment.
* Noise sweep (sigma = 0, 0.5%, 1%, 2%, 4% of the sphere radius) to test
  robustness to measurement noise.

Outputs (artifacts/):
    results.csv             machine-readable per-run metrics
    report.txt              human-readable summary with vertex counts/timings
    meshes/*.ply            reconstructed meshes
    figures/*.png           error and smoothness comparison charts
"""

from __future__ import annotations

import csv
import os
import time

import numpy as np
import open3d as o3d

from poisson_surface_recon import (
    sample_sphere,
    sample_torus,
    estimate_normals,
    make_normals_inconsistent,
    orient_normals_consistent,
    normal_consistency_rate,
    poisson_reconstruct,
    reconstruction_errors,
    mesh_smoothness,
    mesh_quality,
)

RADIUS = 1.0
SEED = 42
DEPTH = 8
N_SPHERE = 6000
N_TORUS = 8000

ROOT = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(ROOT, "artifacts")
MESH_DIR = os.path.join(ART, "meshes")
FIG_DIR = os.path.join(ART, "figures")
for directory in (ART, MESH_DIR, FIG_DIR):
    os.makedirs(directory, exist_ok=True)


def build_scenario(name, kind, n_points, noise_sigma, rng):
    """Generate a noisy point cloud plus estimated / flipped / aligned normals."""
    if kind == "sphere":
        points, gt_normals = sample_sphere(
            n_points, radius=RADIUS, noise_sigma=noise_sigma, rng=rng
        )
    elif kind == "torus":
        points, gt_normals = sample_torus(
            n_points, noise_sigma=noise_sigma, rng=rng
        )
    else:
        raise ValueError(kind)
    _, estimated = estimate_normals(points)
    inconsistent, _ = make_normals_inconsistent(
        estimated, flip_fraction=0.35, rng=rng
    )
    aligned = orient_normals_consistent(points, inconsistent)
    return {
        "name": name,
        "kind": kind,
        "points": points,
        "gt_normals": gt_normals,
        "estimated": estimated,
        "inconsistent": inconsistent,
        "aligned": aligned,
        "noise_sigma": noise_sigma,
    }


def run_one(scenario, normal_key, label, rng):
    """Reconstruct with one normal field and collect the full metric set."""
    points = scenario["points"]
    normals = scenario[normal_key]
    consistency = normal_consistency_rate(normals, scenario["gt_normals"])

    mesh, build_info = poisson_reconstruct(
        points, normals, depth=DEPTH, density_quantile=0.05
    )
    errors = reconstruction_errors(mesh, points, n_mesh_samples=20000, rng=rng)
    smooth = mesh_smoothness(mesh)
    quality = mesh_quality(mesh)

    mesh_path = os.path.join(
        MESH_DIR, f"{scenario['name']}_{label}.ply"
    )
    o3d.io.write_triangle_mesh(mesh_path, mesh)

    row = {
        "scenario": scenario["name"],
        "shape": scenario["kind"],
        "noise_sigma": scenario["noise_sigma"],
        "normal_state": label,
        "normal_consistency": round(consistency, 6),
        "n_vertices": build_info["n_vertices"],
        "n_triangles": build_info["n_triangles"],
        "recon_time_sec": round(build_info["elapsed_sec"], 6),
        "chamfer": round(errors["chamfer"], 6),
        "accuracy_mean": round(errors["accuracy_mean"], 6),
        "accuracy_rmse": round(errors["accuracy_rmse"], 6),
        "accuracy_p95": round(errors["accuracy_p95"], 6),
        "completeness_mean": round(errors["completeness_mean"], 6),
        "hausdorff": round(errors["hausdorff"], 6),
        "normal_variation_deg": round(smooth["normal_variation_deg"], 6),
        "edge_length_cv": round(smooth["edge_length_cv"], 6),
        "boundary_edges": quality["boundary_edges"],
        "non_manifold_edges": quality["non_manifold_edges"],
        "mesh_path": os.path.relpath(mesh_path, ROOT),
    }
    return row, mesh


def main():
    rng = np.random.default_rng(SEED)
    rows = []
    total_start = time.perf_counter()

    # --- Primary scenarios: clean and noisy sphere / torus ---------------
    primary = [
        ("sphere_clean", "sphere", N_SPHERE, 0.0),
        ("sphere_noisy", "sphere", N_SPHERE, 0.02),
        ("torus_clean", "torus", N_TORUS, 0.0),
        ("torus_noisy", "torus", N_TORUS, 0.02),
    ]
    for name, kind, n_points, sigma in primary:
        scenario = build_scenario(name, kind, n_points, sigma, rng)
        # Baseline uses the locally estimated normals before corruption.
        row_clean, _ = run_one(scenario, "estimated", "estimated", rng)
        row_before, _ = run_one(
            scenario, "inconsistent", "before_alignment", rng
        )
        row_after, _ = run_one(
            scenario, "aligned", "after_alignment", rng
        )
        rows.extend([row_clean, row_before, row_after])

    # --- Noise robustness sweep on the sphere -----------------------------
    sigmas = [0.0, 0.005, 0.01, 0.02, 0.04]
    sweep_rows = []
    for sigma in sigmas:
        scenario = build_scenario(
            f"sweep_s{sigma:.3f}", "sphere", N_SPHERE, sigma, rng
        )
        before, _ = run_one(
            scenario, "inconsistent", "before_alignment", rng
        )
        after, _ = run_one(scenario, "aligned", "after_alignment", rng)
        sweep_rows.append((sigma, before, after))
        rows.extend([before, after])

    total_elapsed = time.perf_counter() - total_start
    write_csv(rows)
    write_report(rows, sweep_rows, total_elapsed)
    plot_results(rows, sweep_rows)
    print(f"Done in {total_elapsed:.2f}s. See artifacts/report.txt")


def write_csv(rows):
    csv_path = os.path.join(ART, "results.csv")
    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows, sweep_rows, total_elapsed):
    lines = []
    lines.append("=" * 78)
    lines.append(" Poisson Surface Reconstruction - Experiment Report")
    lines.append("=" * 78)
    lines.append(f" octree depth={DEPTH}, density crop quantile=0.05")
    lines.append(f" sphere samples={N_SPHERE}, torus samples={N_TORUS}")
    lines.append("")

    header = (
        f"{'scenario':<16}{'normals':<18}{'consist.':>9}"
        f"{'verts':>8}{'time(s)':>9}{'chamfer':>10}{'rmse':>9}"
        f"{'p95':>9}{'smooth°':>9}"
    )
    groups = {}
    for row in rows:
        groups.setdefault(row["scenario"], []).append(row)

    lines.append(header)
    lines.append("-" * len(header))
    for scenario, group in groups.items():
        if scenario.startswith("sweep"):
            continue
        for row in group:
            lines.append(
                f"{row['scenario']:<16}{row['normal_state']:<18}"
                f"{row['normal_consistency']:>9.4f}"
                f"{row['n_vertices']:>8d}{row['recon_time_sec']:>9.3f}"
                f"{row['chamfer']:>10.5f}{row['accuracy_rmse']:>9.5f}"
                f"{row['accuracy_p95']:>9.5f}"
                f"{row['normal_variation_deg']:>9.3f}"
            )
        lines.append("")

    lines.append("-" * 78)
    lines.append(" Error change after normal alignment (noisy point clouds)")
    lines.append("-" * 78)
    for scenario in ("sphere_noisy", "torus_noisy"):
        group = {r["normal_state"]: r for r in groups[scenario]}
        before = group["before_alignment"]
        after = group["after_alignment"]
        drop = 100.0 * (before["chamfer"] - after["chamfer"]) / before["chamfer"]
        lines.append(
            f" {scenario}: chamfer {before['chamfer']:.5f} -> "
            f"{after['chamfer']:.5f}  ({drop:+.1f}%), "
            f"RMSE {before['accuracy_rmse']:.5f} -> "
            f"{after['accuracy_rmse']:.5f}"
        )
    lines.append("")

    lines.append("-" * 78)
    lines.append(" Noise robustness sweep (aligned normals), sigma = stddev of")
    lines.append(" 3D Gaussian noise as a fraction of the unit-sphere radius")
    lines.append("-" * 78)
    lines.append(
        f"{'sigma':>8}{'chamfer(before)':>16}{'chamfer(after)':>17}"
        f"{'RMSE(after)':>13}{'smooth°':>10}{'verts':>8}"
    )
    for sigma, before, after in sweep_rows:
        lines.append(
            f"{sigma:>8.3f}{before['chamfer']:>16.5f}"
            f"{after['chamfer']:>17.5f}{after['accuracy_rmse']:>13.5f}"
            f"{after['normal_variation_deg']:>10.3f}{after['n_vertices']:>8d}"
        )
    lines.append("")
    lines.append(f" Total wall-clock for all reconstructions: {total_elapsed:.2f} s")
    lines.append("=" * 78)

    report_path = os.path.join(ART, "report.txt")
    with open(report_path, "w") as handle:
        handle.write("\n".join(lines) + "\n")


def plot_results(rows, sweep_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = {}
    for row in rows:
        groups.setdefault(row["scenario"], {})[row["normal_state"]] = row

    # Figure 1: Chamfer error, before vs after alignment -------------------
    scenarios = [
        name for name in groups
        if not name.startswith("sweep") and name.endswith(("noisy", "clean"))
    ]
    labels, before_vals, after_vals = [], [], []
    for name in scenarios:
        labels.append(name)
        before_vals.append(groups[name]["before_alignment"]["chamfer"])
        after_vals.append(groups[name]["after_alignment"]["chamfer"])
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width / 2, before_vals, width, label="before alignment")
    ax.bar(x + width / 2, after_vals, width, label="after alignment")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20)
    ax.set_ylabel("symmetric Chamfer distance")
    ax.set_title("Reconstruction error before / after normal alignment")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "chamfer_comparison.png"), dpi=140)
    plt.close(fig)

    # Figure 2: noise robustness sweep -------------------------------------
    sigmas = [s for s, _, _ in sweep_rows]
    chamfer_before = [b["chamfer"] for _, b, _ in sweep_rows]
    chamfer_after = [a["chamfer"] for _, _, a in sweep_rows]
    rmse_after = [a["accuracy_rmse"] for _, _, a in sweep_rows]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(sigmas, chamfer_before, "o--", label="Chamfer before alignment")
    ax.plot(sigmas, chamfer_after, "s-", label="Chamfer after alignment")
    ax.plot(sigmas, rmse_after, "^-", label="RMSE after alignment")
    ax.set_xlabel("Gaussian noise sigma (fraction of sphere radius)")
    ax.set_ylabel("point-to-mesh error")
    ax.set_title("Poisson reconstruction robustness to noise")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "noise_sweep.png"), dpi=140)
    plt.close(fig)

    # Figure 3: smoothness --------------------------------------------------
    smooth_before = [
        groups[name]["before_alignment"]["normal_variation_deg"]
        for name in scenarios
    ]
    smooth_after = [
        groups[name]["after_alignment"]["normal_variation_deg"]
        for name in scenarios
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width / 2, smooth_before, width, label="before alignment")
    ax.bar(x + width / 2, smooth_after, width, label="after alignment")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20)
    ax.set_ylabel("mean adjacent-normal angle (degrees)")
    ax.set_title("Surface smoothness (lower = smoother)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "smoothness.png"), dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
