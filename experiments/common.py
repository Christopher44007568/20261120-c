"""Shared scene and output configuration for the experiments."""

from __future__ import annotations

import os

import numpy as np

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from parallax.geometry import normalize
from parallax.probe import ReflectionProbe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = os.path.join(ROOT, "artifacts")
DATA_DIR = os.path.join(ARTIFACT_DIR, "data")
PLOT_DIR = os.path.join(ARTIFACT_DIR, "plots")
MESH_DIR = os.path.join(ARTIFACT_DIR, "meshes")

for path in (DATA_DIR, PLOT_DIR, MESH_DIR):
    os.makedirs(path, exist_ok=True)

# A 16 x 10 x 8 metre room used as ground-truth reflecting geometry.
ROOM_LO = np.array([-8.0, -5.0, -4.0])
ROOM_HI = np.array([8.0, 5.0, 4.0])


def room_probe(scale: float = 1.0,
               center=(0.0, 0.0, 0.0)) -> ReflectionProbe:
    half = (ROOM_HI - ROOM_LO) * 0.5 * scale
    c = np.asarray(center, dtype=float)
    return ReflectionProbe(
        name=f"box_{scale:.2f}", center=c, lo=c - half, hi=c + half)


def deterministic_directions(seed: int = 7, count: int = 24):
    """Reproducible unit directions covering the sphere."""
    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(count, 3))
    return [normalize(d) for d in dirs]


def save_csv(path: str, header: list[str], rows: list[list]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(",".join(header) + "\n")
        for row in rows:
            fh.write(",".join(str(v) for v in row) + "\n")
