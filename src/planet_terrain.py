"""Procedural planet terrain on a sphere.

Pipeline: equirectangular (lon, lat) grid -> unit-sphere directions ->
3D fBm continents plus ridged mountains -> sea level -> heightfield ->
object-space normals. All noise is evaluated in 3D, so the result is
seamless across the longitude wrap and singular-free at the poles.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spherical_noise import fbm_3d, ridged_fbm_3d, sphere_directions

WIDTH, HEIGHT = 2048, 1024          # equirectangular grid, lon x lat
SEED = 1337
BASE_FREQ = 1.8                     # base noise frequency (cycles/radius)
MOUNTAIN_FREQ = 3.4                 # ridged mountain base frequency
OCEAN_FRACTION = 0.60               # target fraction of surface below sea
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "artifacts")


def compose_height(dirs):
    """Layered terrain: continents, ridged mountains, ocean basins."""
    continents = fbm_3d(dirs * BASE_FREQ, octaves=6, gain=0.5, seed=SEED)
    detail = fbm_3d(dirs * BASE_FREQ * 4.0, octaves=4, gain=0.55,
                    seed=SEED + 41)
    land_mask = np.clip(continents * 3.0 + 0.35, 0.0, 1.0)
    ridges = ridged_fbm_3d(dirs * MOUNTAIN_FREQ, octaves=5, seed=SEED)
    height = (0.62 * continents
              + 0.10 * detail
              + 0.34 * land_mask * ridges ** 1.6)
    return height


def build_heightfield():
    """Evaluate height on the full grid in row chunks (memory friendly)."""
    lon = (np.arange(WIDTH) + 0.5) * 360.0 / WIDTH
    lat = 90.0 - (np.arange(HEIGHT) + 0.5) * 180.0 / HEIGHT
    height = np.empty((HEIGHT, WIDTH), dtype=np.float64)
    chunk = 128
    for row0 in range(0, HEIGHT, chunk):
        rows = slice(row0, min(row0 + chunk, HEIGHT))
        lon2d, lat2d = np.meshgrid(lon, lat[rows])
        dirs = sphere_directions(lon2d, lat2d)
        height[rows] = compose_height(dirs)
    sea_level = np.quantile(height, OCEAN_FRACTION)
    height = height - sea_level          # sea level -> 0
    return height, lon, lat


def compute_normals(height, lon, lat):
    """Object-space normals from spherical central differences.

    Physical slopes: dh/ds_lon = (1/cos lat) dh/dlon, dh/ds_lat = dh/dlat
    (unit radius). Longitude differences wrap around the seam via np.roll.
    """
    dlon = np.radians(360.0 / WIDTH)
    dlat = np.radians(180.0 / HEIGHT)
    dh_dlon = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) \
        / (2.0 * dlon)
    dh_dlat = (np.roll(height, 1, axis=0) - np.roll(height, -1, axis=0)) \
        / (2.0 * dlat)
    lat_rad = np.radians(lat)[:, None]
    cos_lat = np.maximum(np.cos(lat_rad), 1e-3)
    slope_east = dh_dlon / cos_lat
    slope_north = -dh_dlat

    lon_rad = np.radians(lon)[None, :]
    sin_lon = np.broadcast_to(np.sin(lon_rad), height.shape)
    cos_lon = np.broadcast_to(np.cos(lon_rad), height.shape)
    sin_lat = np.broadcast_to(np.sin(lat_rad), height.shape)
    cos_lat_b = np.broadcast_to(np.cos(lat_rad), height.shape)
    radial = np.stack([cos_lat_b * cos_lon, sin_lat, cos_lat_b * sin_lon], -1)
    east = np.stack([-sin_lon, np.zeros_like(sin_lon), cos_lon], -1)
    north = np.stack([-sin_lat * cos_lon, cos_lat_b, -sin_lat * sin_lon], -1)
    n = radial - slope_east[..., None] * east - slope_north[..., None] * north
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def save_outputs(height, normals):
    os.makedirs(ARTIFACTS, exist_ok=True)
    h_min, h_max = float(height.min()), float(height.max())
    h_norm = (height - h_min) / (h_max - h_min)

    u16 = np.round(h_norm * 65535.0).astype(np.uint16)
    Image.fromarray(u16).save(
        os.path.join(ARTIFACTS, "heightmap_16bit.png"))
    np.save(os.path.join(ARTIFACTS, "height_physical.npy"),
            height.astype(np.float32))

    np.save(os.path.join(ARTIFACTS, "normals_object.npy"),
            normals.astype(np.float32))
    rgb = np.round((normals * 0.5 + 0.5) * 255.0).astype(np.uint8)
    Image.fromarray(rgb).save(
        os.path.join(ARTIFACTS, "normalmap_rgb.png"))

    sea_u = (0.0 - h_min) / (h_max - h_min)
    metadata = {
        "width": WIDTH,
        "height": HEIGHT,
        "seed": SEED,
        "base_frequency": BASE_FREQ,
        "mountain_frequency": MOUNTAIN_FREQ,
        "ocean_fraction": OCEAN_FRACTION,
        "height_min": h_min,
        "height_max": h_max,
        "sea_level_normalized_u": sea_u,
        "height_decoding": "h = height_min + u16/65535 * (height_max - height_min)",
        "normal_encoding": "object-space xyz mapped via rgb = n*0.5+0.5",
        "projection": "equirectangular lon[0,360) x lat[90,-90]",
        "noise_domain": "3D unit-sphere directions (seamless by construction)",
    }
    with open(os.path.join(ARTIFACTS, "planet_metadata.json"), "w") as fh:
        json.dump(metadata, fh, indent=2)
    return metadata


def main():
    height, lon, lat = build_heightfield()
    normals = compute_normals(height, lon, lat)
    metadata = save_outputs(height, normals)
    print("height range: %.4f .. %.4f" % (metadata["height_min"],
                                          metadata["height_max"]))
    print("sea level u: %.4f" % metadata["sea_level_normalized_u"])
    print("artifacts written to", os.path.abspath(ARTIFACTS))


if __name__ == "__main__":
    main()
