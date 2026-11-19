"""Preview renders: equirectangular terrain preview, orthographic globes,
and the latitude-band gradient chart (3D mapping vs naive 2D control).
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from planet_terrain import ARTIFACTS
from polar_caps import colorize

GLOBE_SIZE = 512
SUN = np.array([-0.55, 0.45, 0.70])
SUN = SUN / np.linalg.norm(SUN)


def _bilinear(grid, lon_deg, lat_deg):
    """Sample the equirectangular grid; wraps in lon, clamps in lat."""
    h, w = grid.shape
    x = (lon_deg / 360.0 * w - 0.5) % w
    y = np.clip((90.0 - lat_deg) / 180.0 * h - 0.5, 0, h - 1.001)
    x0 = np.floor(x).astype(int) % w
    x1 = (x0 + 1) % w
    y0 = np.floor(y).astype(int)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = x - np.floor(x)
    fy = y - np.floor(y)
    return ((grid[y0, x0] * (1 - fx) + grid[y0, x1] * fx) * (1 - fy)
            + (grid[y1, x0] * (1 - fx) + grid[y1, x1] * fx) * fy)


def render_globe(height, normals, view_lon, out_path):
    n = GLOBE_SIZE
    px = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    xx, yy = np.meshgrid(px, px)
    r2 = xx ** 2 + yy ** 2
    inside = r2 <= 1.0
    zz = np.sqrt(np.clip(1.0 - r2, 0, None))
    a = np.radians(view_lon)
    dx = zz * np.sin(a) + xx * np.cos(a)
    dz = zz * np.cos(a) - xx * np.sin(a)
    lat = np.degrees(np.arcsin(np.clip(-yy, -1, 1)))
    lon = np.degrees(np.arctan2(dz, dx)) % 360.0
    h = _bilinear(height, lon, lat)
    nx = _bilinear(normals[..., 0], lon, lat)
    ny = _bilinear(normals[..., 1], lon, lat)
    nz = _bilinear(normals[..., 2], lon, lat)
    cx = nx * np.cos(a) - nz * np.sin(a)
    cz = nx * np.sin(a) + nz * np.cos(a)
    shade = np.clip(cx * SUN[0] + ny * SUN[1] + cz * SUN[2], 0, 1)
    rgb = colorize(h).astype(np.float64)
    ocean = h < 0
    rgb[ocean] *= (0.35 + 0.65 * shade[ocean])[..., None]
    rgb[~ocean] *= (0.45 + 0.55 * shade[~ocean])[..., None]
    rgb[~inside] = 8
    Image.fromarray(rgb.astype(np.uint8)).save(out_path)


def render_band_chart(report, out_path):
    bands = report["C_lat_band_physical_gradient"]["bands"]
    ctrl = report["E_naive_uv2d_control"]
    w, hh = 640, 360
    img = Image.new("RGB", (w, hh), (18, 18, 24))
    dr = ImageDraw.Draw(img)
    rms = [b["rms"] for b in bands]
    vmax = max(max(rms), ctrl["uv2d_polar_rms"]) * 1.1
    bw = 60
    for i, b in enumerate(bands):
        x0 = 60 + i * (bw + 24)
        bh = b["rms"] / vmax * (hh - 90)
        dr.rectangle([x0, hh - 50 - bh, x0 + bw, hh - 50],
                     fill=(90, 160, 230))
        dr.text((x0 + 4, hh - 44), b["lat_band"], fill=(220, 220, 220))
        dr.text((x0 + 4, hh - 60 - bh), "%.2f" % b["rms"],
                fill=(160, 210, 255))
    x0 = 60 + len(bands) * (bw + 24)
    bh = ctrl["uv2d_polar_rms"] / vmax * (hh - 90)
    dr.rectangle([x0, hh - 50 - bh, x0 + bw, hh - 50], fill=(220, 90, 80))
    dr.text((x0 - 6, hh - 44), "2D pole", fill=(220, 220, 220))
    dr.text((x0 - 6, hh - 60 - bh), "%.1f" % ctrl["uv2d_polar_rms"],
            fill=(255, 160, 150))
    dr.text((60, 14), "Physical gradient RMS per latitude band "
            "(blue: 3D seamless, red: naive 2D-UV polar)",
            fill=(230, 230, 230))
    img.save(out_path)


def main():
    height = np.load(os.path.join(ARTIFACTS, "height_physical.npy"))
    normals = np.load(os.path.join(ARTIFACTS, "normals_object.npy"))
    Image.fromarray(colorize(height)).save(
        os.path.join(ARTIFACTS, "terrain_preview.png"))
    for view in (0, 90, 180):
        render_globe(height, normals, view,
                     os.path.join(ARTIFACTS, "globe_%03d.png" % view))
    with open(os.path.join(ARTIFACTS, "verification_report.json")) as fh:
        report = json.load(fh)
    render_band_chart(report,
                      os.path.join(ARTIFACTS, "polar_gradient_bands.png"))
    print("previews written")


if __name__ == "__main__":
    main()
