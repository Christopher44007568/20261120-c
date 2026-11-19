"""Phase functions for volumetric scattering."""

import numpy as np


def isotropic_pdf():
    return 1.0 / (4.0 * np.pi)


def henyey_greenstein_pdf(cos_theta, g=0.0):
    g2 = g * g
    denom = 1.0 + g2 - 2.0 * g * cos_theta
    return (1.0 - g2) / (4.0 * np.pi * np.maximum(denom, 1e-8) ** 1.5)


def sample_hg(g, rng, n):
    """Sample Henyey-Greenstein; g=0 reduces to an isotropic direction."""
    if abs(g) < 1e-6:
        return rng.isotropic_dirs(n)
    u = rng.uniform(n)
    g2 = g * g
    cos = (1.0 + g2 - ((1.0 - g2) / (1.0 - g + 2.0 * g * u)) ** 2) / (2.0 * g)
    cos = np.clip(cos, -1.0, 1.0)
    phi = 2.0 * np.pi * rng.uniform(n)
    sin = np.sqrt(np.maximum(0.0, 1.0 - cos ** 2))
    return np.stack((sin * np.cos(phi), sin * np.sin(phi), cos), axis=1)
