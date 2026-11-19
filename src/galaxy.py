"""Procedural spiral galaxy: particles + fBm noise define the arms."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from noise import fbm3


@dataclass(frozen=True)
class GalaxyConfig:
    n_stars: int = 12000
    arms: int = 3
    radius: float = 10.0
    thickness: float = 0.55
    twist: float = 2.6
    arm_width: float = 0.24
    noise_frequency: float = 1.0
    noise_strength: float = 0.45
    octaves: int = 4
    seed: int = 20261120


def generate_galaxy(cfg: GalaxyConfig) -> dict:
    """Return star positions (N,3), colours (N,3) and per-star metadata."""
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_stars

    # Radius biased toward the core; small uniform halo keeps the bulge full.
    u = rng.random(n)
    radius = cfg.radius * np.power(u, 0.62)
    arm_index = rng.integers(0, cfg.arms, n)
    base_angle = (2.0 * np.pi * arm_index / cfg.arms).astype(np.float64)

    # Logarithmic-style spiral angle plus noise-driven jitter.
    spiral_angle = cfg.twist * radius / cfg.radius
    r_norm = radius / cfg.radius
    nx = fbm3(r_norm * 3.0, np.zeros(n), np.zeros(n),
              octaves=cfg.octaves, frequency=cfg.noise_frequency, seed=cfg.seed)
    ny = fbm3(np.zeros(n), r_norm * 3.0, np.ones(n) * 3.1,
              octaves=cfg.octaves, frequency=cfg.noise_frequency, seed=cfg.seed + 17)
    angular_jitter = cfg.noise_strength * (nx - 0.5) * 2.4
    angle = base_angle + spiral_angle + angular_jitter

    # Gaussian scatter around the arm centreline, widened slightly by noise.
    scatter = rng.normal(0.0, cfg.arm_width * (0.55 + 0.7 * ny), n)
    angle += scatter
    radial_scatter = rng.normal(0.0, cfg.arm_width * 0.3, n) * radius.clip(min=0.5)
    radius = np.clip(radius + radial_scatter, 0.05, cfg.radius * 1.05)

    x = radius * np.cos(angle)
    y = radius * np.sin(angle)
    # Disc thickness shrinks toward the rim.
    z_sigma = cfg.thickness * np.exp(-radius / (cfg.radius * 0.55)) + 0.06
    z = rng.normal(0.0, z_sigma, n)
    z += 0.35 * (fbm3(x / cfg.radius * 3.0, y / cfg.radius * 3.0,
                      np.ones(n) * 7.7, octaves=3,
                      frequency=cfg.noise_frequency, seed=cfg.seed + 31) - 0.5)

    positions = np.stack([x, y, z], axis=1)

    # Colour grading: hot blue-white young stars on arms, warm core stars.
    core_weight = np.exp(-radius / (cfg.radius * 0.28))
    t = rng.random(n)
    blue = np.clip(1.2 - 0.7 * (radius / cfg.radius) + 0.2 * (t - 0.5), 0.0, 1.0)
    r_col = np.clip(0.38 + 0.62 * core_weight + 0.15 * (1 - blue), 0, 1)
    g_col = np.clip(0.48 + 0.42 * core_weight, 0, 1)
    b_col = np.clip(0.4 + 0.6 * blue, 0, 1)
    colors = np.stack([r_col, g_col, b_col], axis=1)

    # Brightness: dense core + sprinkled bright giants.
    brightness = 0.5 + 0.5 * core_weight
    giants = rng.random(n) < 0.02
    brightness[giants] *= rng.uniform(1.6, 2.4, giants.sum())
    sizes = np.where(giants, rng.uniform(1.6, 2.4, n), rng.uniform(0.45, 0.95, n))

    return {
        "positions": positions,
        "colors": np.clip(colors * brightness[:, None], 0, 1.5),
        "sizes": sizes,
        "radius": radius,
        "arm_index": arm_index,
        "brightness": brightness,
    }
