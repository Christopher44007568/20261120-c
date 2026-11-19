"""End-to-end driver: run every experiment and regenerate all figures/CSVs."""

import time

from .experiments import exp1_transmittance, exp2_noise, exp3_render, exp4_surface
from . import figures


def main():
    timing = {}

    t0 = time.perf_counter()
    exp1_transmittance.run()
    timing["exp1_transmittance"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    exp2_noise.run()
    timing["exp2_noise"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    frames, _ = exp3_render.run()
    timing["exp3_render"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    images, metrics = exp4_surface.run()
    timing["exp4_surface"] = time.perf_counter() - t0

    figures.fig1_transmittance()
    figures.fig2_noise()
    figures.fig3_smoke(frames)
    figures.fig4_cloud(frames)
    figures.fig5_surface(images, metrics)

    for name, seconds in timing.items():
        print(f"{name:22s} {seconds:6.2f} s")
    print("all artifacts regenerated under artifacts/")


if __name__ == "__main__":
    main()
