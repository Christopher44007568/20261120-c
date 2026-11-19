"""Importance sampling of the GGX specular lobe vs uniform hemisphere."""
import math
import random


def _ggx_ndf(cos_h, alpha):
    a2 = alpha * alpha
    d = cos_h * cos_h * (a2 - 1.0) + 1.0
    return a2 / (math.pi * d * d)


def sample_uniform_hemisphere(n, rng):
    dirs = []
    for _ in range(n):
        u1, u2 = rng.random(), rng.random()
        phi = 2.0 * math.pi * u2
        cos_t = u1
        sin_t = math.sqrt(max(0.0, 1.0 - cos_t * cos_t))
        dirs.append((sin_t * math.cos(phi), sin_t * math.sin(phi), cos_t))
    return dirs


def sample_ggx(n, alpha, rng):
    """Walter et al. GGX half-vector importance sampling."""
    dirs = []
    for _ in range(n):
        u1, u2 = rng.random(), rng.random()
        phi = 2.0 * math.pi * u2
        cos_t = math.sqrt((1.0 - u1) / (1.0 + (alpha * alpha - 1.0) * u1))
        sin_t = math.sqrt(max(0.0, 1.0 - cos_t * cos_t))
        dirs.append((sin_t * math.cos(phi), sin_t * math.sin(phi), cos_t))
    return dirs


def density_report(dirs, alpha, highlight_cos=0.965, dark_cos=0.35, bins=10):
    """Classify samples: near-highlight cone vs dark low-contribution zone."""
    near = sum(1 for d in dirs if d[2] >= highlight_cos)
    dark = sum(1 for d in dirs if d[2] < dark_cos)
    total = len(dirs)
    hist = [0] * bins
    for d in dirs:
        theta = math.degrees(math.acos(max(-1.0, min(1.0, d[2]))))
        hist[min(bins - 1, int(theta / 90.0 * bins))] += 1
    weight = sum(_ggx_ndf(d[2], alpha) for d in dirs) / total
    return {
        "samples": total,
        "near_highlight": near,
        "near_highlight_pct": 100.0 * near / total,
        "dark_waste": dark,
        "dark_waste_pct": 100.0 * dark / total,
        "mean_ndf_weight": weight,
        "theta_hist_deg": hist,
    }


def compare_sampling(n=20000, alpha=0.2, seed=42):
    rng = random.Random(seed)
    uni = density_report(sample_uniform_hemisphere(n, rng), alpha)
    ggx = density_report(sample_ggx(n, alpha, rng), alpha)
    return {"uniform": uni, "ggx": ggx, "alpha": alpha, "n": n}
