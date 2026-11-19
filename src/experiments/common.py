"""Shared configuration for the experiment scripts."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "artifacts", "data")
FIG_DIR = os.path.join(ROOT, "artifacts", "figures")

# Homogeneous slab used for the Beer-Lambert / estimator-variance studies.
SIGMA_T = 1.2
SLAB_BOUNDS = [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]

# Number of independent rays per depth point.
N_RAYS_CURVE = 40_000
N_RAYS_NOISE = 160_000
BATCHES = 40


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(FIG_DIR, exist_ok=True)
