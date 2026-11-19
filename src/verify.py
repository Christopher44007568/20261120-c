"""Deterministic regression checks for galaxy and L-system pipelines."""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from galaxy import GalaxyConfig, generate_galaxy
from lsystem import LSystemConfig, build_tree
from metrics import (angular_dispersion, arm_alignment_score, arm_roughness,
                     distribution_distance)


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    return condition


def main() -> int:
    ok = True

    # 1. Same seed must reproduce identical star fields.
    a = generate_galaxy(GalaxyConfig(n_stars=5000, seed=11))
    b = generate_galaxy(GalaxyConfig(n_stars=5000, seed=11))
    ok &= check("seed determinism", np.allclose(a["positions"], b["positions"]))

    # 2. Radial distribution stays stable while frequency changes (TVD tiny).
    base = generate_galaxy(GalaxyConfig(n_stars=8000, noise_frequency=1.0))
    tvds, rough = [], []
    for freq in (0.5, 1.0, 2.0, 4.0):
        g = generate_galaxy(GalaxyConfig(n_stars=8000, noise_frequency=freq))
        cfg = g  # config rebuilt inside; recreate for metric helpers
        gc = GalaxyConfig(n_stars=8000, noise_frequency=freq)
        tvds.append(distribution_distance(base["positions"], g["positions"], gc.radius))
        rough.append(arm_roughness(g, gc))
    ok &= check("radial distribution stable across frequencies",
                max(tvds) < 0.01, f"TVD={max(tvds):.4f}")
    ok &= check("arm roughness grows with frequency",
                rough[-1] > rough[0] * 1.5,
                f"roughness {rough[0]:.4f} -> {rough[-1]:.4f}")

    # 3. Arm alignment remains coherent at the default frequency.
    gc = GalaxyConfig(n_stars=8000)
    g = generate_galaxy(gc)
    alignment = arm_alignment_score(g, gc)
    ok &= check("spiral arm alignment coherent", alignment > 0.7,
                f"alignment={alignment:.3f}")
    ok &= check("angular dispersion bounded",
                angular_dispersion(g, gc) < 0.5)

    # 4. L-system depth drives exponential segment growth.
    rules = {"F": "FF+[+F-F-F]-[-F+F+F]"}
    counts = []
    for depth in range(1, 5):
        tree = build_tree(LSystemConfig("F", rules, depth, 22.5, seed=5))
        counts.append(len(tree["segments"]))
    ratios = [counts[i + 1] / counts[i] for i in range(len(counts) - 1)]
    ok &= check("L-system segments grow by ~8x per depth",
                all(abs(r - 8.0) < 0.01 for r in ratios), f"ratios={ratios}")

    # 5. Rule parameters change branch density at fixed depth.
    bushy_rules = {"F": "FF[+F][-F][&F][^F]"}
    sparse_rules = {"F": "F[+F]F[-F][F]"}
    bushy = build_tree(LSystemConfig("F", bushy_rules, 4, 28.0, seed=5))
    sparse = build_tree(LSystemConfig("F", sparse_rules, 4, 16.0, seed=5))
    ok &= check("rule sets change branch counts",
                len(bushy["segments"]) != len(sparse["segments"]),
                f"{len(bushy['segments'])} vs {len(sparse['segments'])}")

    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
