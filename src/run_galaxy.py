"""End-to-end pipeline: frequency sweep, multi-view renders and JSON report."""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from camera import orbit_camera, perspective, project
from galaxy import GalaxyConfig, generate_galaxy
from metrics import (angular_dispersion, arm_alignment_score, arm_arc_energy,
                     arm_roughness, distribution_distance)
from renderer import generate_nebula, render_scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "artifacts")

N_STARS = 12000
N_NEBULA = 2600
FREQUENCIES = [0.5, 1.0, 2.0, 4.0]
VIEWS = [
    ("top", 88, 20),
    ("oblique", 32, 45),
    ("edge", 4, 110),
    ("side", 55, 200),
]


def main() -> None:
    os.makedirs(os.path.join(OUT, "renders"), exist_ok=True)
    proj = perspective(50.0, 1.0, 0.1, 200.0)
    report: dict = {"star_count": N_STARS, "nebula_points": N_NEBULA,
                    "frequency_sweep": [], "views": {}}

    base_galaxy = generate_galaxy(GalaxyConfig(n_stars=N_STARS, noise_frequency=1.0))
    base_pos = base_galaxy["positions"].copy()

    for freq in FREQUENCIES:
        cfg = GalaxyConfig(n_stars=N_STARS, noise_frequency=freq)
        galaxy = generate_galaxy(cfg)
        nebula = generate_nebula(galaxy, n_points=N_NEBULA)
        view = orbit_camera(88, 20)
        img, stats = render_scene(galaxy, nebula, view, proj, 720, 720)
        fname = f"renders/galaxy_freq{freq:.1f}.png"
        img.save(os.path.join(OUT, fname))
        tvd = distribution_distance(base_pos, galaxy["positions"], cfg.radius)
        entry = {
            "noise_frequency": freq,
            "arm_alignment": round(arm_alignment_score(galaxy, cfg), 4),
            "angular_dispersion_rad": round(angular_dispersion(galaxy, cfg), 4),
            "arm_roughness": round(arm_roughness(galaxy, cfg), 5),
            "arm_arc_energy": round(arm_arc_energy(galaxy, cfg), 5),
            "radial_tvd_vs_baseline": round(tvd, 4),
            "star_count": stats.star_count,
            "visible_stars": stats.visible_stars,
            "draw_batches": stats.draw_batches,
            "draw_calls": stats.draw_calls,
            "image": fname,
        }
        report["frequency_sweep"].append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    # Multi-view structural validation on the baseline (frequency = 1.0).
    galaxy = base_galaxy
    nebula = generate_nebula(galaxy, n_points=N_NEBULA)
    view_records = []
    for name, el, az in VIEWS:
        view = orbit_camera(el, az)
        img, stats = render_scene(galaxy, nebula, view, proj, 720, 720)
        fname = f"renders/galaxy_view_{name}.png"
        img.save(os.path.join(OUT, fname))
        xy, vis = project(galaxy["positions"], view, proj, 720, 720)
        centroid = xy[vis, :2].mean(axis=0)
        record = {
            "view": name,
            "elevation_deg": el,
            "azimuth_deg": az,
            "visible_stars": stats.visible_stars,
            "draw_batches": stats.draw_batches,
            "draw_calls": stats.draw_calls,
            "centroid": [round(float(centroid[0]), 2), round(float(centroid[1]), 2)],
            "image": fname,
        }
        view_records.append(record)
        report["views"][name] = record
        print(json.dumps(record, ensure_ascii=False))

    counts = np.array([r["visible_stars"] for r in view_records], dtype=np.float64)
    centroids = np.array([r["centroid"] for r in view_records])
    report["view_stability"] = {
        "visible_mean": round(float(counts.mean()), 2),
        "visible_cv": round(float(counts.std() / counts.mean()), 6),
        "centroid_drift_px": round(float(
            np.linalg.norm(centroids - centroids.mean(axis=0), axis=1).max()), 3),
    }

    with open(os.path.join(OUT, "galaxy_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("report -> artifacts/galaxy_report.json")


if __name__ == "__main__":
    main()
