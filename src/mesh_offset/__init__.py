"""Normal-offset shelling with signed-distance self-intersection repair."""

from .geometry import (
    make_holey_plate,
    manifold_to_trimesh,
    mesh_stats,
    offset_vertices,
    trimesh_to_manifold,
    vertex_normals,
)
from .intersections import count_self_intersections
from .shelling import OffsetSurfaces, build_offset_surfaces, build_shell
from .sdf import SignedDistanceGrid

__all__ = [
    "OffsetSurfaces",
    "SignedDistanceGrid",
    "build_offset_surfaces",
    "build_shell",
    "count_self_intersections",
    "make_holey_plate",
    "manifold_to_trimesh",
    "mesh_stats",
    "offset_vertices",
    "trimesh_to_manifold",
    "vertex_normals",
]
