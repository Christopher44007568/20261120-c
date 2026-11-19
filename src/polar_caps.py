"""Polar-cap texture mapping supplement.

Equirectangular maps degenerate at the poles (a whole texture row collapses
to one point). For latitudes beyond +-CAP_LAT we therefore provide dedicated
polar-cap textures in an azimuthal equidistant projection:

    pixel (x, y) -> angular distance rho = r/R * (90 - CAP_LAT) from pole
                 -> azimuth psi = atan2(y, x) = longitude
                 -> 3D direction -> same seamless noise field

The cap texture meets the equirectangular chart at lat = +-CAP_LAT; the
overlap ring is verified to match. Output: polar_north.png / polar_south.png
plus consistency metrics merged into verification_report.json.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spherical_noise import sphere_directions
from planet_terrain import ARTIFACTS, compose_height

CAP_LAT = 60.0          # cap covers |lat| >= 60 deg
CAP_SIZE = 512          # cap texture resolution (square)


def cap_directions(pole):
    """Azimuthal equidistant grid of 3D directions for one polar cap."""
    n = CAP_SIZE
    px = (np.arange(n) + 0.5) / n * 2.0 - 1.0     # [-1, 1)
    xx, yy = np.meshgrid(px, px)
    r = np.hypot(xx, yy)
    rho = r * np.radians(90.0 - CAP_LAT)          # angular dist from pole
    psi = np.arctan2(yy, xx)                      # azimuth = longitude
    if pole == "north":
        lat = 90.0 - np.degrees(rho)
        lon = np.degrees(psi)
    else:
        lat = -90.0 + np.degrees(rho)
        lon = np.degrees(psi)
    inside = r <= 1.0
    return sphere_directions(lon, lat), inside, r


def render_cap(pole):
    dirs, inside, _ = cap_directions(pole)
    h = compose_height(dirs)
    return h, inside


def colorize(height, inside=None):
    """Simple terrain palette: deep ocean -> shelf -> land -> snow."""
    stops = [(-0.60, (8, 32, 86)), (-0.05, (24, 78, 148)),
             (0.00, (56, 132, 190)), (0.02, (194, 178, 128)),
             (0.12, (70, 120, 60)), (0.30, (110, 96, 70)),
             (0.55, (240, 240, 245))]
    img = np.zeros(height.shape + (3,), dtype=np.float64)
    hs = np.array([s[0] for s in stops])
    cs = np.array([s[1] for s in stops], dtype=np.float64)
    for ch in range(3):
        img[..., ch] = np.interp(height, hs, cs[:, ch])
    if inside is not None:
        img[~inside] = 12
    return img.astype(np.uint8)


def verify_cap(pole, cap_h):
    """Consistency of the cap texture with the global field."""
    n = CAP_SIZE
    center = cap_h[n // 2, n // 2]
    pole_dir = sphere_directions(
        np.array([0.0]), np.array([90.0 if pole == "north" else -90.0]))
    exact = compose_height(pole_dir)[0]
    lon = np.linspace(0, 360, 1440, endpoint=False)
    edge_lat = CAP_LAT if pole == "north" else -CAP_LAT
    chart = compose_height(sphere_directions(lon, np.full_like(lon, edge_lat)))
    ring_x = np.round((np.cos(np.radians(lon)) * 0.995 + 1) / 2 * n - 0.5)\
        .astype(int) % n
    ring_y = np.round((np.sin(np.radians(lon)) * 0.995 + 1) / 2 * n - 0.5)\
        .astype(int) % n
    ring = cap_h[ring_y, ring_x]
    ring_err = np.abs(ring - chart)
    # Azimuth wrap line is psi = +-180 deg, i.e. the negative x-axis
    # (y = 0, x < 0). Pixels just above/below it must be continuous,
    # like any other vertical neighbor pair inside the cap.
    row = n // 2
    wrap_gap = abs(cap_h[row - 1, 1] - cap_h[row, 1])
    interior_step = np.abs(np.diff(cap_h[n // 4:3 * n // 4, n // 4],
                                   axis=0)).mean()
    return {
        "center_vs_exact_pole_absdiff": float(abs(center - exact)),
        "boundary_ring_max_absdiff": float(ring_err.max()),
        "boundary_ring_rms": float(np.sqrt((ring_err ** 2).mean())),
        "azimuth_wrap_gap": float(wrap_gap),
        "azimuth_wrap_vs_interior_step": float(wrap_gap / interior_step),
    }


def main():
    report = {}
    for pole in ("north", "south"):
        h, inside = render_cap(pole)
        Image.fromarray(colorize(h, inside)).save(
            os.path.join(ARTIFACTS, "polar_%s.png" % pole))
        report[pole] = verify_cap(pole, h)
        report[pole]["cap_lat"] = CAP_LAT
        report[pole]["cap_size"] = CAP_SIZE
        report[pole]["projection"] = "azimuthal equidistant"
    path = os.path.join(ARTIFACTS, "verification_report.json")
    with open(path) as fh:
        full = json.load(fh)
    full["F_polar_cap_mapping"] = report
    with open(path, "w") as fh:
        json.dump(full, fh, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
