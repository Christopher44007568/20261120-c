"""Render the smoke plume and cloud/fog bank with both stepping modes."""

import csv
import time
import numpy as np

from ..medium import Medium
from ..fields import (smoke_plume, cloud_fog, SMOKE_BOUNDS, CLOUD_BOUNDS)
from ..tracer import render
from .common import DATA_DIR, ensure_dirs

WIDTH = 168
HEIGHT = 168
SPP = 48
DT = 0.25

def run():
    ensure_dirs()
    scenes = {
        "smoke": (smoke_plume(), SMOKE_BOUNDS, 0.12,
                  {"bounds": np.array([[-1.7, -1.2], [1.7, 1.2]]), "z": 3.4}),
        "cloud": (cloud_fog(), CLOUD_BOUNDS, 0.5,
                  {"bounds": np.array([[-2.2, -1.2], [2.2, 1.2]]), "z": 2.8}),
    }
    stats = []
    frames = {}
    for name, (density, bounds, sigma0, view) in scenes.items():
        medium = Medium(bounds, density, sigma_t0=sigma0, albedo=0.95)
        frames[name] = {}
        for mode in ["exponential", "uniform"]:
            accum = np.zeros((HEIGHT, WIDTH))
            step_accum = np.zeros((HEIGHT, WIDTH))
            t0 = time.perf_counter()
            for s in range(SPP):
                image, step_map = render(medium, view, WIDTH, HEIGHT,
                                         mode=mode, dt=DT, seed=100 + s)
                accum += image
                step_accum += step_map
            seconds = time.perf_counter() - t0
            image = accum / SPP
            step_map = step_accum / SPP
            frames[name][mode] = (image, step_map)
            inside = step_map > 0
            stats.append({
                "field": name,
                "mode": mode,
                "seconds": seconds,
                "mean_steps": float(step_map[inside].mean()),
                "max_steps": float(step_map.max()),
                "mean_radiance": float(image.mean()),
            })
    with open(f"{DATA_DIR}/render_stats.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(stats[0].keys()))
        writer.writeheader()
        writer.writerows(stats)
    return frames, stats


if __name__ == "__main__":
    _, stats = run()
    for row in stats:
        print(row)
