"""Quantitative structure metrics for galaxy arms and stability checks."""
from __future__ import annotations

import numpy as np


def arm_alignment_score(galaxy: dict, cfg) -> float:
    """Fraction of stars whose angle sits close to their arm's spiral centreline.

    1.0 means every star lies exactly on the ideal spiral; lower means dispersed.
    """
    pos = galaxy["positions"]
    radius = np.hypot(pos[:, 0], pos[:, 1])
    angle = np.mod(np.arctan2(pos[:, 1], pos[:, 0]), 2 * np.pi)
    centreline = np.mod(
        2 * np.pi * galaxy["arm_index"] / cfg.arms
        + cfg.twist * radius / cfg.radius,
        2 * np.pi,
    )
    delta = np.abs(np.arctan2(np.sin(angle - centreline),
                              np.cos(angle - centreline)))
    within = delta < (cfg.arm_width * 1.8)
    return float(np.mean(within))


def radial_distribution(positions: np.ndarray, bins: int = 20,
                        radius: float = 10.0) -> np.ndarray:
    r = np.hypot(positions[:, 0], positions[:, 1])
    hist, _ = np.histogram(r, bins=bins, range=(0, radius * 1.05))
    return hist.astype(np.float64) / max(hist.sum(), 1)


def distribution_distance(pos_a: np.ndarray, pos_b: np.ndarray,
                          radius: float = 10.0) -> float:
    """Total variation distance between two radial star distributions."""
    ha = radial_distribution(pos_a, radius=radius)
    hb = radial_distribution(pos_b, radius=radius)
    return float(0.5 * np.abs(ha - hb).sum())


def angular_dispersion(galaxy: dict, cfg) -> float:
    """Std-dev of angular offset from the ideal spiral (radians)."""
    pos = galaxy["positions"]
    radius = np.hypot(pos[:, 0], pos[:, 1])
    angle = np.arctan2(pos[:, 1], pos[:, 0])
    centreline = (2 * np.pi * galaxy["arm_index"] / cfg.arms
                  + cfg.twist * radius / cfg.radius)
    delta = np.arctan2(np.sin(angle - centreline), np.cos(angle - centreline))
    return float(np.std(delta))


def arm_roughness(galaxy: dict, cfg, bins: int = 40) -> float:
    """Mean second-difference of the mean arm centreline angle vs radius.

    Higher values mean a more wrinkled / fragmented spiral; smooth arms -> 0.
    """
    pos = galaxy["positions"]
    radius = np.hypot(pos[:, 0], pos[:, 1])
    angle = np.arctan2(pos[:, 1], pos[:, 0])
    centreline = (2 * np.pi * galaxy["arm_index"] / cfg.arms
                  + cfg.twist * radius / cfg.radius)
    delta = np.arctan2(np.sin(angle - centreline), np.cos(angle - centreline))
    edges = np.linspace(radius.min(), radius.max(), bins + 1)
    means = []
    for i in range(bins):
        mask = (radius >= edges[i]) & (radius < edges[i + 1])
        if mask.sum() >= 8:
            means.append(float(np.mean(delta[mask])))
        else:
            means.append(np.nan)
    series = np.array(means)
    valid = ~np.isnan(series)
    series = np.interp(np.arange(bins), np.where(valid)[0], series[valid])
    second_diff = np.diff(series, n=2)
    return float(np.sqrt(np.mean(second_diff ** 2)))


def arm_arc_energy(galaxy: dict, cfg) -> float:
    """Total angular arc energy: large-scale winding + high-frequency wrinkle."""
    pos = galaxy["positions"]
    radius = np.hypot(pos[:, 0], pos[:, 1])
    angle = np.arctan2(pos[:, 1], pos[:, 0])
    centreline = (2 * np.pi * galaxy["arm_index"] / cfg.arms
                  + cfg.twist * radius / cfg.radius)
    delta = np.arctan2(np.sin(angle - centreline), np.cos(angle - centreline))
    return float(np.sum(delta ** 2) / delta.size)


def view_stability(views: list[dict]) -> dict:
    """Compare projected star counts / centroid spread across camera views."""
    counts = np.array([v["visible_stars"] for v in views], dtype=np.float64)
    centroids = np.array([v["centroid"] for v in views])
    return {
        "visible_mean": float(counts.mean()),
        "visible_cv": float(counts.std() / counts.mean()),
        "centroid_drift_px": float(np.linalg.norm(centroids - centroids.mean(axis=0),
                                                  axis=1).max()),
    }
