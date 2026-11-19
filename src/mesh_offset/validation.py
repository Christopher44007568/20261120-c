"""Continuity, equidistance, and volume validation for generated shells."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import manifold3d
import numpy as np
import trimesh

from .geometry import manifold_to_trimesh
from .intersections import count_self_intersections
from .shelling import OffsetSurfaces


@dataclass
class SurfaceMetrics:
    triangles: int
    volume: float
    components: int
    genus: int
    boundary_edges: int
    nonmanifold_edges: int
    equidistance_mean_abs_error: float
    equidistance_p95_abs_error: float
    equidistance_max_abs_error: float
    status: str


@dataclass
class ValidationResult:
    outer: SurfaceMetrics
    inner: SurfaceMetrics
    shell_triangles: int
    shell_volume: float
    shell_components: int
    shell_boundary_edges: int
    shell_nonmanifold_edges: int
    shell_surface_components: int
    shell_surface_watertight: bool
    final_self_intersections: int
    volume_consistent: bool
    status_ok: bool
    topology_ok: bool
    inner_outer_continuous: bool
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _edge_stats(mesh: trimesh.Trimesh) -> tuple[int, int]:
    mesh.merge_vertices()
    edges = mesh.edges_sorted
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.count_nonzero(counts == 1)), int(np.count_nonzero(counts > 2))


def _equidistance(
    surface: trimesh.Trimesh,
    reference: trimesh.Trimesh,
    distance: float,
    sample_limit: int = 4000,
) -> tuple[float, float, float]:
    count = len(surface.vertices)
    if count > sample_limit:
        indices = np.linspace(0, count - 1, sample_limit).astype(np.int64)
        points = surface.vertices[indices]
    else:
        points = surface.vertices
    _, unsigned, _ = trimesh.proximity.closest_point(reference, points)
    errors = np.abs(np.asarray(unsigned, dtype=np.float64) - distance)
    return (
        float(errors.mean()),
        float(np.percentile(errors, 95)),
        float(errors.max()),
    )


def _surface_metrics(
    solid: manifold3d.Manifold,
    reference: trimesh.Trimesh,
    distance: float,
) -> SurfaceMetrics:
    mesh = manifold_to_trimesh(solid)
    boundary, nonmanifold = _edge_stats(mesh)
    components = len(solid.decompose())
    mean_error, p95_error, max_error = _equidistance(mesh, reference, distance)
    return SurfaceMetrics(
        triangles=int(solid.num_tri()),
        volume=float(solid.volume()),
        components=int(components),
        genus=int(solid.genus()) if components == 1 else -1,
        boundary_edges=boundary,
        nonmanifold_edges=nonmanifold,
        equidistance_mean_abs_error=mean_error,
        equidistance_p95_abs_error=p95_error,
        equidistance_max_abs_error=max_error,
        status=str(solid.status()),
    )


def validate_shell(
    surfaces: OffsetSurfaces,
    shell: manifold3d.Manifold,
    reference: trimesh.Trimesh,
    *,
    expected_genus: int,
) -> ValidationResult:
    outer = _surface_metrics(surfaces.outer, reference, surfaces.distance)
    inner = _surface_metrics(surfaces.inner, reference, surfaces.distance)

    shell_mesh = manifold_to_trimesh(shell)
    shell_mesh.merge_vertices()
    shell_boundary, shell_nonmanifold = _edge_stats(shell_mesh)
    shell_components = len(shell.decompose())
    surface_parts = shell_mesh.split(only_watertight=False)
    shell_surface_components = len(surface_parts)
    shell_surface_watertight = bool(
        shell_surface_components == 2
        and all(part.is_watertight for part in surface_parts)
    )
    intersections = count_self_intersections(
        shell_mesh.vertices, shell_mesh.faces
    ).count

    expected_volume = surfaces.outer.volume() - surfaces.inner.volume()
    volume_consistent = bool(
        abs(shell.volume() - expected_volume)
        <= max(1e-6, 1e-5 * abs(expected_volume))
    )
    status_ok = all(
        "NoError" in value
        for value in (outer.status, inner.status, str(shell.status()))
    )
    topology_ok = bool(
        outer.components == 1
        and inner.components == 1
        and outer.genus == expected_genus
        and inner.genus == expected_genus
        and outer.boundary_edges == 0
        and inner.boundary_edges == 0
        and outer.nonmanifold_edges == 0
        and inner.nonmanifold_edges == 0
        and shell_boundary == 0
        and shell_nonmanifold == 0
        and shell_surface_watertight
    )
    continuous = bool(
        status_ok
        and topology_ok
        and shell_components == 2
        and intersections == 0
        and volume_consistent
    )
    return ValidationResult(
        outer=outer,
        inner=inner,
        shell_triangles=int(shell.num_tri()),
        shell_volume=float(shell.volume()),
        shell_components=int(shell_components),
        shell_boundary_edges=shell_boundary,
        shell_nonmanifold_edges=shell_nonmanifold,
        shell_surface_components=shell_surface_components,
        shell_surface_watertight=shell_surface_watertight,
        final_self_intersections=int(intersections),
        volume_consistent=volume_consistent,
        status_ok=status_ok,
        topology_ok=topology_ok,
        inner_outer_continuous=continuous,
        passed=continuous,
    )
