"""Verification suite for seamless spherical noise mapping.

Checks:
  A. Longitude seam (lon 0 == lon 360): dual-parameterization identity and
     physical continuity of a fine ring crossing the seam.
  B. Pole singularity: all longitudes at lat +-90 are one 3D point.
  C. Latitude-band physical gradient statistics: texture density must be
     latitude-independent (no polar stretching/compression).
  D. Polar ring continuity at 1 deg colatitude, incl. deterministic re-eval.
  E. Naive 2D-UV noise control: demonstrates the seam plus polar stretch
     that the 3D mapping avoids.
Writes artifacts/verification_report.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spherical_noise import fbm_3d, sphere_directions
from planet_terrain import (ARTIFACTS, WIDTH, HEIGHT, SEED, BASE_FREQ,
                            compose_height)


def check_a_longitude_seam():
    lat = np.linspace(-80, 80, 321)
    d0 = sphere_directions(np.zeros_like(lat), lat)
    d360 = sphere_directions(np.full_like(lat, 360.0), lat)
    dual = np.abs(compose_height(d0) - compose_height(d360)).max()
    lon = np.linspace(-2.0, 2.0, 1601)
    lat_rows = np.linspace(-75, 75, 31)
    lon2d, lat2d = np.meshgrid(lon, lat_rows)
    ring = compose_height(sphere_directions(lon2d, lat2d))
    steps = np.abs(np.diff(ring, axis=1))
    mid = steps.shape[1] // 2
    across = steps[:, mid - 1:mid + 1].max()
    interior = steps.mean()
    return {
        "same_point_dual_param_max_diff": float(dual),
        "seam_crossing_step_max": float(across),
        "interior_step_mean": float(interior),
        "seam_vs_interior_ratio": float(across / interior),
    }


def check_b_pole_singularity():
    lon = np.linspace(0, 360, 720, endpoint=False)
    out = {}
    for name, latv in [("north", 90.0), ("south", -90.0)]:
        v = compose_height(sphere_directions(lon, np.full_like(lon, latv)))
        out["exact_%s_pole_range" % name] = float(v.max() - v.min())
    for name, latv in [("north", 89.9), ("south", -89.9)]:
        v = compose_height(sphere_directions(lon, np.full_like(lon, latv)))
        out["%s_row_std_at_89.9" % name] = float(v.std())
    return out


def _physical_gradient(height):
    dlon = np.radians(360.0 / WIDTH)
    dlat = np.radians(180.0 / HEIGHT)
    dh_dlon = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) \
        / (2.0 * dlon)
    dh_dlat = (np.roll(height, 1, axis=0) - np.roll(height, -1, axis=0)) \
        / (2.0 * dlat)
    lat = 90.0 - (np.arange(HEIGHT) + 0.5) * 180.0 / HEIGHT
    cos_lat = np.maximum(np.cos(np.radians(lat)), 1e-3)[:, None]
    return np.hypot(dh_dlon / cos_lat, dh_dlat), lat


def check_c_latitude_bands(height):
    """Parameterization-independent texture-stretch check.

    The physical gradient is measured by re-sampling the 3D noise field at
    a fixed metric offset (0.25 deg arc) along the local east/north tangent
    directions, NOT from the equirectangular grid. Grid-based differences
    would conflate texture stretch with longitude sampling density.
    """
    delta = np.radians(0.25)
    step = 4
    lat = 90.0 - (np.arange(HEIGHT) + 0.5) * 180.0 / HEIGHT
    lon = (np.arange(WIDTH) + 0.5) * 360.0 / WIDTH
    lon2d, lat2d = np.meshgrid(lon[::step], lat[::step])
    p = sphere_directions(lon2d, lat2d)
    lat_r = np.radians(lat2d)
    lon_r = np.radians(lon2d)
    east = np.stack([-np.sin(lon_r), np.zeros_like(lon_r), np.cos(lon_r)], -1)
    north = np.stack([-np.sin(lat_r) * np.cos(lon_r), np.cos(lat_r),
                      -np.sin(lat_r) * np.sin(lon_r)], -1)

    def at(v):
        return compose_height(v / np.linalg.norm(v, axis=-1, keepdims=True))

    g_east = (at(p + delta * east) - at(p - delta * east)) / (2.0 * delta)
    g_north = (at(p + delta * north) - at(p - delta * north)) / (2.0 * delta)
    grad = np.hypot(g_east, g_north).ravel()
    abs_lat = np.abs(lat2d).ravel()
    bands = [(0, 15), (15, 30), (30, 60), (60, 75), (75, 90)]
    stats = []
    for lo, hi in bands:
        sel = (abs_lat >= lo) & (abs_lat < hi)
        g = grad[sel]
        stats.append({
            "lat_band": "%d-%d" % (lo, hi),
            "rms": float(np.sqrt((g ** 2).mean())),
            "mean": float(g.mean()),
            "p95": float(np.percentile(g, 95)),
            "east_rms": float(np.sqrt((g_east.ravel()[sel] ** 2).mean())),
            "north_rms": float(np.sqrt((g_north.ravel()[sel] ** 2).mean())),
            "sample_count": int(g.size),
        })
    rms = np.array([s["rms"] for s in stats])
    return {
        "bands": stats,
        "polar_to_equator_rms_ratio": float(rms[-1] / rms[0]),
        "max_rms_deviation_pct": float((rms.max() - rms.min()) / rms.mean()
                                       * 100.0),
    }


def check_d_polar_ring():
    lon = np.linspace(0, 360, 4096, endpoint=False)
    polar = compose_height(sphere_directions(lon, np.full_like(lon, 89.0)))
    equator = compose_height(sphere_directions(lon, np.zeros_like(lon)))
    re_eval = compose_height(sphere_directions(lon, np.full_like(lon, 89.0)))
    wrap_gap = abs(polar[-1] - polar[0])
    step = np.abs(np.diff(polar)).mean()
    return {
        "colatitude_deg": 1.0,
        "deterministic_reeval_max_diff": float(np.abs(polar - re_eval).max()),
        "polar_ring_value_range": float(polar.max() - polar.min()),
        "equator_ring_value_range": float(equator.max() - equator.min()),
        "range_ratio_polar_over_equator":
            float((polar.max() - polar.min())
                  / (equator.max() - equator.min())),
        "wrap_gap": float(wrap_gap),
        "wrap_gap_over_mean_step": float(wrap_gap / step),
    }


def check_e_naive_uv2d_control():
    """What a naive 2D-UV noise mapping would look like (the failure mode)."""
    lon = (np.arange(WIDTH) + 0.5) * 360.0 / WIDTH
    lat = 90.0 - (np.arange(HEIGHT) + 0.5) * 180.0 / HEIGHT
    lon2d, lat2d = np.meshgrid(lon, lat)
    pts = np.stack([lon2d / 360.0 * 8.0,
                    lat2d / 180.0 * 4.0,
                    np.zeros_like(lon2d)], axis=-1)
    h2d = np.empty((HEIGHT, WIDTH))
    chunk = 128
    for row0 in range(0, HEIGHT, chunk):
        rows = slice(row0, min(row0 + chunk, HEIGHT))
        h2d[rows] = fbm_3d(pts[rows], octaves=5, seed=SEED)
    grad, latv = _physical_gradient(h2d)
    abs_lat = np.abs(latv)
    eq = grad[abs_lat < 15]
    po = grad[abs_lat >= 75]
    seam = np.abs(h2d[:, 0] - h2d[:, -1])
    return {
        "uv2d_polar_rms": float(np.sqrt((po ** 2).mean())),
        "uv2d_equator_rms": float(np.sqrt((eq ** 2).mean())),
        "uv2d_polar_to_equator_ratio":
            float(np.sqrt((po ** 2).mean()) / np.sqrt((eq ** 2).mean())),
        "uv2d_seam_max_abs_diff": float(seam.max()),
        "uv2d_height_range": float(h2d.max() - h2d.min()),
    }


def main():
    height = np.load(os.path.join(ARTIFACTS, "height_physical.npy"))\
        .astype(np.float64)
    report = {
        "grid": {"width": WIDTH, "height": HEIGHT},
        "A_longitude_seam_3d": check_a_longitude_seam(),
        "B_pole_singularity": check_b_pole_singularity(),
        "C_lat_band_physical_gradient": check_c_latitude_bands(height),
        "D_pole_ring_continuity": check_d_polar_ring(),
        "E_naive_uv2d_control": check_e_naive_uv2d_control(),
    }
    out = os.path.join(ARTIFACTS, "verification_report.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
