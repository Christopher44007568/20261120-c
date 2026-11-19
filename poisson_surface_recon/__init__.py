"""Poisson surface reconstruction pipeline.

Modules:
    surfaces     : synthetic point clouds (sphere / torus) with ground truth
                   normals and configurable Gaussian noise.
    normals      : normal estimation, random inconsistency and consistent
                   orientation (normal alignment).
    reconstruction: screened Poisson reconstruction via Open3D, timed.
    metrics      : point-to-mesh errors, smoothness and timing helpers.
"""

from .surfaces import sample_sphere, sample_torus
from .normals import (
    estimate_normals,
    make_normals_inconsistent,
    orient_normals_consistent,
    normal_consistency_rate,
)
from .reconstruction import poisson_reconstruct
from .metrics import (
    nearest_distances,
    chamfer_distance,
    reconstruction_errors,
    mesh_smoothness,
    mesh_quality,
)

__all__ = [
    "sample_sphere",
    "sample_torus",
    "estimate_normals",
    "make_normals_inconsistent",
    "orient_normals_consistent",
    "normal_consistency_rate",
    "poisson_reconstruct",
    "nearest_distances",
    "chamfer_distance",
    "reconstruction_errors",
    "mesh_smoothness",
    "mesh_quality",
]
