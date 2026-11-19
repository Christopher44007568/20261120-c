"""Deterministic random-number helpers built on numpy's Generator API."""

import numpy as np


class RNG:
    """Thin wrapper that keeps a fixed seed so every experiment is reproducible."""

    def __init__(self, seed: int = 12345):
        self.rng = np.random.default_rng(seed)

    def uniform(self, low=0.0, high=1.0, size=None):
        return self.rng.uniform(low, high, size)

    def exponential(self, scale=1.0, size=None):
        return self.rng.exponential(scale, size)

    def isotropic_dirs(self, n: int):
        """Uniformly distributed unit directions on the sphere."""
        z = self.rng.uniform(-1.0, 1.0, n)
        phi = self.rng.uniform(0.0, 2.0 * np.pi, n)
        r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
        return np.stack((r * np.cos(phi), r * np.sin(phi), z), axis=1)

    def cosine_hemisphere(self, n: int):
        """Cosine-weighted directions around the +z normal (z-up local frame)."""
        r1 = self.rng.random(n)
        r2 = self.rng.random(n)
        r = np.sqrt(r1)
        phi = 2.0 * np.pi * r2
        z = np.sqrt(np.maximum(0.0, 1.0 - r1))
        return np.stack((r * np.cos(phi), r * np.sin(phi), z), axis=1)
