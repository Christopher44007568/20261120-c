"""Surface-only vs volumetric path: verify light transport consistency.

An absorbing-only homogeneous slab sits between the camera and a Lambertian
ground plane.  Energy conservation requires

    L_vol / L_surf = T(Beer-Lambert) = exp(-sigma_a * d),

and the scattering + absorption fractions must sum to one.
"""

import csv
import numpy as np

from ..medium import HomogeneousMedium
from ..tracer import render, render_surface_only
from .common import DATA_DIR, ensure_dirs

WIDTH = 128
HEIGHT = 128
SPP = 64
VIEW = {"bounds": np.array([[-1.2, -1.2], [1.2, 1.2]]), "z": 2.6}
SLAB = [[-1.0, -1.0, 0.4], [1.0, 1.0, 2.4]]
SIGMA = 0.6


def _average(medium, mode, albedo, max_bounces=3):
    medium.albedo = albedo
    accum = np.zeros((HEIGHT, WIDTH))
    for s in range(SPP):
        image, _ = render(medium, VIEW, WIDTH, HEIGHT, mode=mode,
                          dt=0.05, seed=500 + s, max_bounces=0,
                          sun_radiance=0.0, ambient=1.0, ground_albedo=1.0)
        accum += image
    return accum / SPP


def run():
    ensure_dirs()
    thickness = SLAB[1][2] - SLAB[0][2]
    beer_T = float(np.exp(-SIGMA * thickness))
    view_lo, view_hi = VIEW["bounds"]
    xs = np.linspace(view_lo[0], view_hi[0], WIDTH)
    ys = np.linspace(view_lo[1], view_hi[1], HEIGHT)
    xx, yy = np.meshgrid(xs, ys)
    inside = ((xx >= SLAB[0][0]) & (xx <= SLAB[1][0]) &
              (yy >= SLAB[0][1]) & (yy <= SLAB[1][1]))

    surface_img, _ = render_surface_only(VIEW, WIDTH, HEIGHT, seed=1,
                                         sun_radiance=0.0, ambient=1.0,
                                         ground_albedo=1.0)

    absorbing = HomogeneousMedium(SLAB, SIGMA, albedo=0.0)
    absorbing_img = _average(absorbing, "exponential", albedo=0.0,
                             max_bounces=0)

    scattering = HomogeneousMedium(SLAB, SIGMA, albedo=1.0)
    scattering_img = _average(scattering, "exponential", albedo=1.0,
                              max_bounces=0)

    ratio_absorb = (absorbing_img / surface_img)[inside]
    # The scattering image contains both the transmitted ground term
    # (T * ground response) and the in-scattered term (1 - T).  Subtract the
    # transmitted part to isolate in-scattering, then normalize by (1 - T).
    transmitted = beer_T * surface_img
    in_scatter = np.maximum(scattering_img - transmitted, 0.0)
    ratio_scatter = (in_scatter / surface_img)[inside]
    energy_sum = float(ratio_absorb.mean() +
                       (in_scatter[inside] / surface_img[inside]).mean())

    metrics = {
        "scattering_energy_ratio": float(ratio_scatter.mean()),
        "absorption_energy_ratio": float(ratio_absorb.mean()),
        "beer_lambert_energy_T": beer_T,
        "energy_conservation_sum": energy_sum,
        "absorption_energy_relative_error":
            float(abs(ratio_absorb.mean() - beer_T) / beer_T),
        "absorption_median_pixel_ratio": float(np.median(ratio_absorb)),
        "absorption_vs_beer_correlation":
            float(1.0 - ratio_absorb.std() / max(ratio_absorb.mean(), 1e-9)),
        "absorption_mean_relative_error_vs_beer":
            float(np.mean(np.abs(ratio_absorb - beer_T) / beer_T)),
        "scattering_mean_relative_error_vs_beer":
            float(np.mean(np.abs(ratio_scatter - (1.0 - beer_T))
                          / max(1.0 - beer_T, 1e-6))),
    }
    with open(f"{DATA_DIR}/surface_consistency.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for key, value in metrics.items():
            writer.writerow([key, value])

    images = {
        "surface": surface_img,
        "absorption": absorbing_img,
        "scattering": scattering_img,
        "ratio_absorb": np.where(
            inside, absorbing_img / surface_img, np.nan),
        "mask": inside,
        "beer_T": beer_T,
    }
    return images, metrics


if __name__ == "__main__":
    _, metrics = run()
    for key, value in metrics.items():
        print(f"{key:42s} {value:.6f}")
