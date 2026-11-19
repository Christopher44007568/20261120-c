from __future__ import annotations

import numpy as np
from scipy.sparse.csgraph import dijkstra

from .mesh_ops import (
    TriangleMesh,
    adjacency_matrix,
    connected_components_from_labels,
    normal_angles,
)
from .segmentation import Segmentation
from .uv_mapping import UVMap, texture_stretch


def shared_edge_lengths(mesh: TriangleMesh, adjacency: np.ndarray) -> np.ndarray:
    lengths = np.empty(len(adjacency))
    for i, (a, b) in enumerate(adjacency):
        shared = np.intersect1d(mesh.faces[a], mesh.faces[b])
        if len(shared) == 2:
            lengths[i] = np.linalg.norm(
                mesh.vertices[shared[0]] - mesh.vertices[shared[1]]
            )
        else:
            lengths[i] = np.linalg.norm(
                mesh.face_centroids[a] - mesh.face_centroids[b]
            )
    return lengths


def mesh_boundary_length(
    mesh: TriangleMesh, edges: dict[tuple[int, int], list[int]]
) -> float:
    return float(
        sum(
            np.linalg.norm(mesh.vertices[a] - mesh.vertices[b])
            for (a, b), incident in edges.items()
            if len(incident) == 1
        )
    )


def normal_coherence(
    mesh: TriangleMesh, labels: np.ndarray
) -> float:
    normals = mesh.face_normals
    areas = mesh.face_areas
    total = 0.0
    for label in np.unique(labels):
        members = labels == label
        mean_normal = np.sum(normals[members] * areas[members, None], axis=0)
        mean_normal /= max(np.linalg.norm(mean_normal), 1e-12)
        dots = np.clip(normals[members] @ mean_normal, -1.0, 1.0)
        total += float(np.sum(areas[members] * np.arccos(dots)))
    return float(np.degrees(total / max(areas.sum(), 1e-12)))


def geodesic_compactness(
    mesh: TriangleMesh, labels: np.ndarray, adjacency: np.ndarray
) -> float:
    lengths = shared_edge_lengths(mesh, adjacency)
    graph = adjacency_matrix(adjacency, lengths, len(mesh.faces))
    weighted = []
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        if len(members) <= 1:
            continue
        subgraph = graph[members][:, members]
        distances = dijkstra(subgraph, directed=False, indices=0, limit=np.inf)
        diameter = float(np.nanmax(distances[np.isfinite(distances)]))
        area = float(mesh.face_areas[members].sum())
        weighted.append(diameter / max(np.sqrt(area), 1e-9))
    return float(np.mean(weighted))


def segmentation_metrics(
    mesh: TriangleMesh,
    segmentation: Segmentation,
    uv: UVMap,
    adjacency: np.ndarray,
    edges: dict[tuple[int, int], list[int]],
) -> dict[str, float | int | str]:
    labels = segmentation.labels
    cut_mask = labels[adjacency[:, 0]] != labels[adjacency[:, 1]]
    cut_lengths = shared_edge_lengths(mesh, adjacency)
    cut_length = float(cut_lengths[cut_mask].sum())
    external = mesh_boundary_length(mesh, edges)
    angles = np.degrees(normal_angles(mesh, adjacency))
    seam_angles = angles[cut_mask]
    all_angles = angles
    threshold = float(np.percentile(all_angles, 90))
    high_mask = all_angles >= threshold
    capture = (
        float(np.count_nonzero(high_mask & cut_mask) / max(np.count_nonzero(high_mask), 1))
        if len(high_mask)
        else 0.0
    )
    seam_fraction = float(np.count_nonzero(cut_mask) / max(len(cut_mask), 1))
    enrichment = capture / max(seam_fraction, 1e-12)
    component_count = len(
        np.unique(connected_components_from_labels(labels, adjacency, len(mesh.faces)))
    )
    stretch = texture_stretch(mesh, uv)
    area_fractions = np.bincount(
        labels, weights=mesh.face_areas, minlength=int(labels.max()) + 1
    )
    area_fractions = area_fractions[area_fractions > 0] / mesh.face_areas.sum()
    return {
        "model": mesh.name,
        "method": segmentation.method,
        "target_islands": segmentation.target_islands,
        "islands": component_count,
        "cut_length": cut_length,
        "boundary_length": cut_length + external,
        "external_boundary_length": external,
        "seam_angle_mean_deg": float(np.mean(seam_angles)) if len(seam_angles) else 0.0,
        "seam_angle_p90_deg": float(np.percentile(seam_angles, 90))
        if len(seam_angles)
        else 0.0,
        "mesh_edge_angle_mean_deg": float(np.mean(all_angles)),
        "mesh_edge_angle_p90_deg": threshold,
        "seam_edge_fraction": seam_fraction,
        "high_curvature_capture": capture,
        "high_curvature_enrichment": enrichment,
        "seam_angle_ratio": float(np.mean(seam_angles) / max(np.mean(all_angles), 1e-12))
        if len(seam_angles)
        else 0.0,
        "normal_coherence_deg": normal_coherence(mesh, labels),
        "geodesic_compactness": geodesic_compactness(mesh, labels, adjacency),
        "island_area_max": float(area_fractions.max()),
        "island_area_min": float(area_fractions.min()),
        "stretch_mean": stretch["mean"],
        "stretch_p95": stretch["p95"],
        "stretch_max": stretch["max"],
        "flip_ratio": stretch["flip_ratio"],
    }


def planar_projection_metrics(
    mesh: TriangleMesh,
    uv: UVMap,
    edges: dict[tuple[int, int], list[int]],
) -> dict[str, float | int | str]:
    stretch = texture_stretch(mesh, uv)
    return {
        "model": mesh.name,
        "method": "planar-projection",
        "target_islands": 1,
        "islands": 1,
        "cut_length": 0.0,
        "boundary_length": mesh_boundary_length(mesh, edges),
        "external_boundary_length": mesh_boundary_length(mesh, edges),
        "seam_angle_mean_deg": 0.0,
        "seam_angle_p90_deg": 0.0,
        "mesh_edge_angle_mean_deg": 0.0,
        "mesh_edge_angle_p90_deg": 0.0,
        "seam_edge_fraction": 0.0,
        "high_curvature_capture": 0.0,
        "high_curvature_enrichment": 0.0,
        "seam_angle_ratio": 0.0,
        "normal_coherence_deg": 0.0,
        "geodesic_compactness": 0.0,
        "island_area_max": 1.0,
        "island_area_min": 1.0,
        "stretch_mean": stretch["mean"],
        "stretch_p95": stretch["p95"],
        "stretch_max": stretch["max"],
        "flip_ratio": stretch["flip_ratio"],
    }

