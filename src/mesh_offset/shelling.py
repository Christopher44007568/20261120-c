"""Normal-offset surface reconstruction and shell generation."""

from __future__ import annotations

from dataclasses import dataclass

import manifold3d
import numpy as np
import trimesh

from .geometry import offset_vertices
from .intersections import IntersectionReport, count_self_intersections
from .sdf import SignedDistanceGrid


@dataclass
class OffsetSurfaces:
    distance: float
    outer: manifold3d.Manifold
    inner: manifold3d.Manifold
    outer_raw_triangles: int
    inner_raw_triangles: int
    outer_triangles: int
    inner_triangles: int
    raw_outer_intersections: IntersectionReport
    raw_inner_intersections: IntersectionReport

    @property
    def repair_count(self) -> int:
        return (
            self.raw_outer_intersections.count
            + self.raw_inner_intersections.count
        )


def _status_ok(solid: manifold3d.Manifold) -> bool:
    return "NoError" in str(solid.status()) and not solid.is_empty()


def build_offset_surfaces(
    mesh: trimesh.Trimesh,
    grid: SignedDistanceGrid,
    distance: float,
    *,
    edge_length: float,
    simplify_tolerance: float = 0.004,
    check_raw_intersections: bool = True,
) -> OffsetSurfaces:
    """Build outer/inner equidistant surfaces from the signed distance field."""

    if distance <= 0:
        raise ValueError("offset distance must be positive")
    if not mesh.is_watertight:
        raise ValueError("input mesh must be watertight")

    def outer_field(x: float, y: float, z: float) -> float:
        return grid.sample(x, y, z) + distance

    def inner_field(x: float, y: float, z: float) -> float:
        return grid.sample(x, y, z) - distance

    bounds = grid.bounds
    outer = manifold3d.Manifold.level_set(
        outer_field, bounds, edge_length, 0.0
    )
    inner = manifold3d.Manifold.level_set(
        inner_field, bounds, edge_length, 0.0
    )
    if not _status_ok(outer) or not _status_ok(inner):
        raise RuntimeError("iso-surface extraction failed; reduce distance or resolution")
    if simplify_tolerance > 0:
        outer = outer.simplify(simplify_tolerance)
        inner = inner.simplify(simplify_tolerance)

    raw_outer = count_self_intersections(
        offset_vertices(mesh.vertices, mesh.faces, distance), mesh.faces
    ) if check_raw_intersections else IntersectionReport(0, 0, ())
    raw_inner = count_self_intersections(
        offset_vertices(mesh.vertices, mesh.faces, -distance), mesh.faces
    ) if check_raw_intersections else IntersectionReport(0, 0, ())

    return OffsetSurfaces(
        distance=float(distance),
        outer=outer,
        inner=inner,
        outer_raw_triangles=int(mesh.faces.shape[0]),
        inner_raw_triangles=int(mesh.faces.shape[0]),
        outer_triangles=int(outer.num_tri()),
        inner_triangles=int(inner.num_tri()),
        raw_outer_intersections=raw_outer,
        raw_inner_intersections=raw_inner,
    )


def build_shell(surfaces: OffsetSurfaces) -> manifold3d.Manifold:
    shell = surfaces.outer - surfaces.inner
    if not _status_ok(shell):
        raise RuntimeError("shell boolean failed")
    return shell
