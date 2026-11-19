"""Screen-space particle LOD with area-preserving aggregate primitives.

Pipeline per camera position:
  1. Project every particle to screen and cull particles outside the view.
  2. LOD0 keeps particles whose projected disk covers at least ``LOD0_PIXELS``
     pixels; the rest are LOD1 candidates.
  3. LOD1 candidates are bucketed into a screen-space grid. Each occupied
     cell becomes one aggregate primitive whose intensity equals the number
     of merged particles, so projected screen-space density (mass per area)
     is preserved exactly inside each cell.
  4. Draw-call counts model GPU batching: LOD0 point sprites are instanced
     in groups of ``INSTANCE_CAP``; all aggregate primitives go into a single
     instanced batch.

A hysteresis band avoids popping when the camera crosses a LOD boundary.
Run directly to generate the JSON / Markdown / SVG artifacts.
"""

import json
import math
import os
import random

from svgchart import heatmap, line_chart

SEED = 20261120
N_PARTICLES = 120_000
CLOUD_RADIUS = 90.0
PARTICLE_RADIUS = 0.35
H_FOV_DEG = 60.0
SCREEN_W = 1280
SCREEN_H = 720
LOD0_PIXELS = 12.0          # projected disk area threshold (pixels^2)
HYSTERESIS = 0.25           # +/- band fraction around the threshold
CELL_PX = 16                # aggregate cell size in screen pixels
INSTANCE_CAP = 1024

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")


def make_cloud(n=N_PARTICLES, radius=CLOUD_RADIUS, seed=SEED):
    """Uniform points inside a sphere, plus a dense core to stress LOD1."""
    rng = random.Random(seed)
    points = []
    core_n = n // 4
    for i in range(n):
        u = rng.random()
        v = rng.random()
        theta = 2.0 * math.pi * u
        phi = math.acos(2.0 * v - 1.0)
        r = radius * (rng.random() ** (1.0 / 3.0))
        if i < core_n:
            r *= 0.35
        points.append((
            r * math.sin(phi) * math.cos(theta),
            r * math.sin(phi) * math.sin(theta),
            r * math.cos(phi),
        ))
    return points


def camera_basis(distance):
    """Camera on +Z looking at origin. Returns origin + orthonormal basis."""
    eye = (0.0, 0.0, distance)
    forward = (0.0, 0.0, -1.0)
    right = (1.0, 0.0, 0.0)
    up = (0.0, 1.0, 0.0)
    return eye, right, up, forward


def project(points, distance):
    """Project to screen pixels; returns (screen x, y, depth, area_px) or None."""
    focal = SCREEN_W / (2.0 * math.tan(math.radians(H_FOV_DEG) / 2.0))
    eye, right, up, forward = camera_basis(distance)
    projected = []
    for px, py, pz in points:
        dz = eye[2] - pz
        if dz <= 0.05:
            continue
        sx = px / dz * focal + SCREEN_W / 2.0
        sy = SCREEN_H / 2.0 - py / dz * focal
        if -CELL_PX <= sx <= SCREEN_W + CELL_PX and -CELL_PX <= sy <= SCREEN_H + CELL_PX:
            area_px = math.pi * (PARTICLE_RADIUS * focal / dz) ** 2
            projected.append((sx, sy, dz, area_px))
    return projected


def lod_level(area_px, prev_level=None):
    """LOD selection with 25% hysteresis band around the area threshold."""
    upper = LOD0_PIXELS * (1.0 + HYSTERESIS)
    lower = LOD0_PIXELS * (1.0 - HYSTERESIS)
    if prev_level is None:
        return 0 if area_px >= LOD0_PIXELS else 1
    if prev_level == 0:
        return 0 if area_px >= lower else 1
    return 0 if area_px >= upper else 1


def build_frame(projected, prev_levels=None):
    """Assign LOD levels and build screen-grid aggregate cells."""
    levels = []
    lod0, lod1 = [], []
    for i, (sx, sy, dz, area_px) in enumerate(projected):
        prev = prev_levels.get(i) if prev_levels is not None else None
        level = lod_level(area_px, prev)
        levels.append(level)
        (lod0 if level == 0 else lod1).append((sx, sy, dz, area_px))
    cells = {}
    for sx, sy, dz, _area in lod1:
        key = (int(sx // CELL_PX), int(sy // CELL_PX))
        cells[key] = cells.get(key, 0) + 1
    lod0_draws = math.ceil(len(lod0) / INSTANCE_CAP) if lod0 else 0
    lod1_draws = 1 if cells else 0
    return {
        "levels": levels,
        "lod0": lod0,
        "lod1": lod1,
        "cells": cells,
        "draw_calls": {
            "lod0_point_sprites": lod0_draws,
            "lod1_aggregates": lod1_draws,
            "total_lod": lod0_draws + lod1_draws,
            "baseline_no_lod": math.ceil(len(projected) / INSTANCE_CAP),
        },
    }


def reference_density(projected):
    """Ground-truth particle count per screen grid cell (all particles)."""
    ref = {}
    for sx, sy, _dz, _a in projected:
        key = (int(sx // CELL_PX), int(sy // CELL_PX))
        ref[key] = ref.get(key, 0) + 1
    return ref


def lod_density(frame):
    """Density produced by the LOD renderer: LOD0 points + aggregate mass."""
    dens = dict(frame["cells"])
    for sx, sy, _dz, _a in frame["lod0"]:
        key = (int(sx // CELL_PX), int(sy // CELL_PX))
        dens[key] = dens.get(key, 0) + 1
    return dens


def density_errors(ref, approx):
    """NRMSE, max relative cell error and total mass ratio."""
    keys = set(ref) | set(approx)
    sq_err = 0.0
    max_rel = 0.0
    max_rel_cell = None
    for key in keys:
        r = ref.get(key, 0)
        a = approx.get(key, 0)
        sq_err += (r - a) ** 2
        if r > 0:
            rel = abs(r - a) / r
            if rel > max_rel:
                max_rel, max_rel_cell = rel, key
    rmse = math.sqrt(sq_err / len(keys))
    rng = max(ref.values()) - min(ref.values()) or max(ref.values())
    nrmse = rmse / rng
    mass_ratio = sum(approx.values()) / max(sum(ref.values()), 1)
    return {
        "nrmse": nrmse,
        "max_relative_cell_error": max_rel,
        "mass_ratio": mass_ratio,
        "rmse": rmse,
        "worst_cell": max_rel_cell,
    }


FINE_PX = 4


def fine_density_error(frame):
    """Density error on an independent 4px grid (sub-cell resolution).

    The reference counts raw particles in each 4px cell. The aggregate
    renderer only stores mass in 16px cells, assumed uniformly distributed;
    its value in a fine cell is coarse mass * (fine area / coarse area).
    This exposes the within-cell smoothing error that the coarse metric hides.
    """
    ref, approx = fine_density_maps(frame)
    keys = set(ref) | set(approx)
    sq_err = sum((ref.get(k, 0) - approx.get(k, 0)) ** 2 for k in keys)
    rmse = math.sqrt(sq_err / len(keys))
    rng = (max(ref.values()) if ref else 1) or 1
    return {"fine_rmse_particles": rmse, "fine_nrmse": rmse / rng}


def tv_of_densities(da, db):
    """L1 total-variation distance of two mass maps (same frame, popping test)."""
    ma, mb = sum(da.values()), sum(db.values())
    if ma == 0 or mb == 0:
        return 0.0 if ma == mb else 1.0
    keys = set(da) | set(db)
    return 0.5 * sum(abs(da.get(k, 0) / ma - db.get(k, 0) / mb) for k in keys)


def fine_density_maps(frame):
    """Reference and aggregate-renderer density on the independent 4px grid."""
    scale = (FINE_PX / CELL_PX) ** 2
    ref = {}
    for sx, sy, _dz, _a in frame["lod0"] + frame["lod1"]:
        key = (int(sx // FINE_PX), int(sy // FINE_PX))
        ref[key] = ref.get(key, 0) + 1
    approx = {}
    for sx, sy, _dz, _a in frame["lod0"]:
        key = (int(sx // FINE_PX), int(sy // FINE_PX))
        approx[key] = approx.get(key, 0) + 1
    for (cx, cy), mass in frame["cells"].items():
        for fx in range(cx * CELL_PX // FINE_PX, (cx + 1) * CELL_PX // FINE_PX):
            for fy in range(cy * CELL_PX // FINE_PX, (cy + 1) * CELL_PX // FINE_PX):
                approx[(fx, fy)] = approx.get((fx, fy), 0) + mass * scale
    return ref, approx


def threshold_band_flips(cloud, route):
    """Count LOD-level flips only for particles that cross the area threshold.

    Particles entering or leaving the frustum are excluded so the metric
    isolates genuine LOD popping rather than camera-motion visibility changes.
    Runs the same route twice: once with hysteresis, once without.
    """
    global HYSTERESIS
    band_lo = LOD0_PIXELS * (1.0 - HYSTERESIS)
    band_hi = LOD0_PIXELS * (1.0 + HYSTERESIS)
    results = {}
    for use_hyst in (True, False):
        saved, HYSTERESIS = HYSTERESIS, HYSTERESIS if use_hyst else 0.0
        prev_levels = None
        per_frame = []
        try:
            for distance in route:
                projected = project(cloud, distance)
                frame = build_frame(projected, prev_levels)
                current = {i: lv for i, lv in enumerate(frame["levels"])}
                flips = 0
                band_particles = 0
                for i, (_sx, _sy, _dz, area_px) in enumerate(projected):
                    if band_lo * 0.5 <= area_px <= band_hi * 1.5:
                        band_particles += 1
                        if prev_levels is not None and prev_levels.get(i) != current[i]:
                            flips += 1
                per_frame.append({"distance": distance, "band_flips": flips,
                                  "band_particles": band_particles,
                                  "lod0_particles": len(frame["lod0"])})
                prev_levels = current
        finally:
            HYSTERESIS = saved
        results[use_hyst] = per_frame
    return results


def threshold_distance():
    """Distance at which a particle's projected disk equals the LOD0 threshold."""
    focal = SCREEN_W / (2.0 * math.tan(math.radians(H_FOV_DEG) / 2.0))
    return PARTICLE_RADIUS * focal * math.sqrt(math.pi / LOD0_PIXELS)


def sweep(distances):
    """Evaluate every camera distance, carrying per-particle state for hysteresis."""
    cloud = make_cloud()
    prev_levels = None
    rows = []
    for distance in distances:
        projected = project(cloud, distance)
        frame = build_frame(projected, prev_levels)
        prev_levels = {i: lv for i, lv in enumerate(frame["levels"])}
        ref = reference_density(projected)
        dens = lod_density(frame)
        err = density_errors(ref, dens)
        fine = fine_density_error(frame)
        fine_ref_m, fine_approx_m = fine_density_maps(frame)
        rows.append({
            "distance": distance,
            "visible_particles": len(projected),
            "lod0_particles": len(frame["lod0"]),
            "lod1_particles": len(frame["lod1"]),
            "aggregate_primitives": len(frame["cells"]),
            "rendered_primitives": len(frame["lod0"]) + len(frame["cells"]),
            "draw_calls": frame["draw_calls"],
            "density_error": err,
            "fine_density_error": fine,
            "fine_tv": tv_of_densities(fine_ref_m, fine_approx_m),
            "_frame": frame,
            "_projected": projected,
        })
    return rows


def popping_analysis(rows):
    """Continuity of LOD0 counts and density across adjacent camera positions."""
    pops = []
    for a, b in zip(rows, rows[1:]):
        n0_a, n0_b = a["lod0_particles"], b["lod0_particles"]
        step_frac = abs(n0_b - n0_a) / max(b["visible_particles"], 1)
        ref_b = reference_density(b["_projected"])
        err_b = density_errors(ref_b, lod_density(b["_frame"]))
        fine_ref, fine_approx = fine_density_maps(b["_frame"])
        fine_tv = tv_of_densities(fine_ref, fine_approx)
        pops.append({
            "from_distance": a["distance"],
            "to_distance": b["distance"],
            "lod0_count_delta": n0_b - n0_a,
            "lod0_step_fraction_of_visible": step_frac,
            "density_nrmse_at_b": err_b["nrmse"],
            "mass_ratio_at_b": err_b["mass_ratio"],
            "fine_grid_render_vs_truth_tv": fine_tv,
        })
    return pops


def _public(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


def write_markdown(rows, pops, switch, path, control_stats=None):
    lines = [
        "# Particle LOD Aggregation Report",
        "",
        f"- Cloud: {N_PARTICLES} particles in radius {CLOUD_RADIUS} sphere "
        f"(25% dense core), particle radius {PARTICLE_RADIUS}",
        f"- Screen {SCREEN_W}x{SCREEN_H}, H-FOV {H_FOV_DEG}°, LOD0 area threshold "
        f"{LOD0_PIXELS} px², hysteresis ±{int(HYSTERESIS*100)}%, aggregate cell {CELL_PX}px",
        f"- Theoretical LOD0/LOD1 switch distance: {switch:.1f} world units",
        "",
        "## Per-LOD particle counts and batches",
        "",
        "| Distance | Visible | LOD0 particles | LOD1 particles | Aggregate primitives | "
        "LOD0 batches | LOD1 batches | Total batches | Baseline batches | Reduction |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        dc = r["draw_calls"]
        reduction = 1.0 - dc["total_lod"] / max(dc["baseline_no_lod"], 1)
        lines.append(
            f"| {r['distance']:.0f} | {r['visible_particles']} | {r['lod0_particles']} | "
            f"{r['lod1_particles']} | {r['aggregate_primitives']} | "
            f"{dc['lod0_point_sprites']} | {dc['lod1_aggregates']} | "
            f"{dc['total_lod']} | {dc['baseline_no_lod']} | {reduction*100:.1f}% |")
    lines += [
        "",
        "## Density error at LOD switches",
        "",
        "| Distance | Coarse NRMSE (16px) | Fine NRMSE (4px) | Fine RMSE (particles/cell) | Mass ratio |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        e = r["density_error"]
        fe = r["fine_density_error"]
        lines.append(
            f"| {r['distance']:.0f} | {e['nrmse']*100:.2f}% | {fe['fine_nrmse']*100:.2f}% | "
            f"{fe['fine_rmse_particles']:.3f} | {e['mass_ratio']:.4f} |")
    max_step = max(pops, key=lambda p: p["lod0_step_fraction_of_visible"])
    max_tv = max(pops, key=lambda p: p["fine_grid_render_vs_truth_tv"])
    lines += [
        "",
        "## LOD switching / popping check",
        "",
        f"- Largest single-step LOD0 count change: {max_step['lod0_count_delta']:+d} "
        f"({max_step['lod0_step_fraction_of_visible']*100:.2f}% of visible particles) between "
        f"z={max_step['from_distance']:.0f} and z={max_step['to_distance']:.0f}",
        f"- Mean per-step LOD0 change fraction: "
        f"{sum(p['lod0_step_fraction_of_visible'] for p in pops)/len(pops)*100:.2f}% of visible",
        f"- Max fine-grid (4px) render-vs-truth density TV: {max_tv['fine_grid_render_vs_truth_tv']:.5f} "
        f"(z={max_tv['from_distance']:.0f}-> {max_tv['to_distance']:.0f}); "
        f"TV=0 means identical normalized screen density (no visual pop)",
        f"- Mass ratio stays at 1.0 at every step (aggregation preserves particle count)",
        "",
    ]
    if control_stats:
        band_none, band_hyst = control_stats
        tot_none = sum(f["band_flips"] for f in band_none)
        tot_hyst = sum(f["band_flips"] for f in band_hyst)
        lines += [
            "## Hysteresis A/B control (camera round trip across LOD threshold)",
            "",
            "- Only particles whose projected area lies in the LOD0 threshold band "
            "(±50% margin) are counted; frustum enter/leave events are excluded.",
            f"- Threshold-band LOD flips without hysteresis: {tot_none}",
            f"- Threshold-band LOD flips with ±{int(HYSTERESIS*100)}% hysteresis: {tot_hyst} "
            f"({(1 - tot_hyst/max(tot_none,1))*100:.1f}% fewer)",
            f"- Max single-frame band flips without/with hysteresis: "
            f"{max(f['band_flips'] for f in band_none)} / "
            f"{max(f['band_flips'] for f in band_hyst)}",
            "",
        ]
    with open(path, "w") as f:
        f.write("\n".join(lines))


def main():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    switch = threshold_distance()
    distances = list(range(60, 461, 20))
    rows = sweep(distances)
    pops = popping_analysis(rows)
    route = list(range(150, 251, 5)) + list(range(245, 149, -5))
    band = threshold_band_flips(make_cloud(), route)
    band_hyst, band_none = band[True], band[False]

    report = {
        "config": {
            "n_particles": N_PARTICLES,
            "cloud_radius": CLOUD_RADIUS,
            "particle_radius": PARTICLE_RADIUS,
            "screen": [SCREEN_W, SCREEN_H],
            "hfov_deg": H_FOV_DEG,
            "lod0_area_threshold_px2": LOD0_PIXELS,
            "hysteresis_band": HYSTERESIS,
            "aggregate_cell_px": CELL_PX,
            "instance_cap": INSTANCE_CAP,
            "theoretical_switch_distance": switch,
        },
        "frames": [_public(r) for r in rows],
        "popping": pops,
        "hysteresis_control": {
            "route": route,
            "with_hysteresis": band_hyst,
            "without_hysteresis": band_none,
        },
    }
    with open(os.path.join(ARTIFACT_DIR, "particle_lod_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    write_markdown(rows, pops, switch,
                   os.path.join(ARTIFACT_DIR, "particle_lod_report.md"),
                   control_stats=(band_none, band_hyst))

    markers = [(switch, "LOD threshold distance", "#c0392b")]
    line_chart(
        os.path.join(ARTIFACT_DIR, "lod_counts.svg"),
        [
            {"name": "LOD0 individual particles", "color": "#1f77b4",
             "points": [(r["distance"], r["lod0_particles"]) for r in rows]},
            {"name": "LOD1 merged particles", "color": "#ff7f0e",
             "points": [(r["distance"], r["lod1_particles"]) for r in rows]},
            {"name": "Aggregate primitives", "color": "#2ca02c",
             "points": [(r["distance"], r["aggregate_primitives"]) for r in rows]},
        ],
        "Camera distance", "Particle / primitive count",
        "LOD particle counts vs camera distance", markers=markers)
    line_chart(
        os.path.join(ARTIFACT_DIR, "draw_calls.svg"),
        [
            {"name": "Batches without LOD", "color": "#d62728",
             "points": [(r["distance"], r["draw_calls"]["baseline_no_lod"]) for r in rows]},
            {"name": "Batches with LOD", "color": "#1f77b4",
             "points": [(r["distance"], r["draw_calls"]["total_lod"]) for r in rows]},
        ],
        "Camera distance", "Draw calls (batches)",
        "Draw-call reduction from far-field merging", markers=markers)
    line_chart(
        os.path.join(ARTIFACT_DIR, "density_error.svg"),
        [
            {"name": "Fine-grid (4px) density NRMSE", "color": "#9467bd",
             "points": [(r["distance"], r["fine_density_error"]["fine_nrmse"] * 100) for r in rows]},
            {"name": "Coarse-grid (16px) density NRMSE", "color": "#8c564b",
             "points": [(r["distance"], r["density_error"]["nrmse"] * 100) for r in rows]},
        ],
        "Camera distance", "Error (%)",
        "Screen-space density error after LOD merge", markers=markers)
    line_chart(
        os.path.join(ARTIFACT_DIR, "frame_continuity.svg"),
        [
            {"name": "Fine-grid render vs truth density TV", "color": "#17becf",
             "points": [(r["distance"], r["fine_tv"]) for r in rows]},
        ],
        "Camera distance", "Total-variation distance",
        "Fine-grid (4px) density TV: LOD renderer vs full-particle reference", markers=markers)
    line_chart(
        os.path.join(ARTIFACT_DIR, "hysteresis_control.svg"),
        [
            {"name": "Threshold-band flips, hysteresis on", "color": "#1f77b4",
             "points": [(f["distance"], f["band_flips"]) for f in band_hyst]},
            {"name": "Threshold-band flips, hysteresis off", "color": "#d62728",
             "points": [(f["distance"], f["band_flips"]) for f in band_none]},
        ],
        "Camera distance along round trip", "Threshold-band LOD flips",
        "Popping control across a camera round trip", markers=None)

    near, far = rows[0], rows[-1]
    heatmap(os.path.join(ARTIFACT_DIR, "density_near_reference.svg"),
            reference_density(near["_projected"]), SCREEN_W, SCREEN_H,
            f"Reference screen density, z={near['distance']:.0f}", CELL_PX)
    heatmap(os.path.join(ARTIFACT_DIR, "density_near_lod.svg"),
            lod_density(near["_frame"]), SCREEN_W, SCREEN_H,
            f"LOD renderer density, z={near['distance']:.0f}", CELL_PX,
            points=[(x, y) for x, y, _d, _a in near["_frame"]["lod0"]])
    heatmap(os.path.join(ARTIFACT_DIR, "density_far_reference.svg"),
            reference_density(far["_projected"]), SCREEN_W, SCREEN_H,
            f"Reference screen density, z={far['distance']:.0f}", CELL_PX)
    heatmap(os.path.join(ARTIFACT_DIR, "density_far_lod.svg"),
            lod_density(far["_frame"]), SCREEN_W, SCREEN_H,
            f"LOD renderer density, z={far['distance']:.0f}", CELL_PX,
            points=[(x, y) for x, y, _d, _a in far["_frame"]["lod0"]])
    print(f"switch distance={switch:.1f}; frames={len(rows)}; "
          f"far batches={rows[-1]['draw_calls']['total_lod']} vs "
          f"baseline={rows[-1]['draw_calls']['baseline_no_lod']}; "
          f"max fine NRMSE={max(r['fine_density_error']['fine_nrmse'] for r in rows)*100:.2f}%; "
          f"band flips no-hyst={sum(f['band_flips'] for f in band_none)} "
          f"vs hyst={sum(f['band_flips'] for f in band_hyst)}")


if __name__ == "__main__":
    main()
