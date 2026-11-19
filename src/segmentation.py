from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import eigsh
from sklearn.cluster import KMeans

from .mesh_ops import (
    TriangleMesh,
    adjacency_matrix,
    connected_components_from_labels,
    normal_angles,
)


@dataclass
class Segmentation:
    labels: np.ndarray
    method: str
    target_islands: int


def _normal_aware_weights(
    mesh: TriangleMesh, adjacency: np.ndarray, length_scale: np.ndarray
) -> np.ndarray:
    angles = normal_angles(mesh, adjacency)
    theta0 = np.deg2rad(10.0)
    normal_factor = np.minimum((angles / theta0) ** 2, 8.0)
    return length_scale * (0.18 + normal_factor)


def _geodesic_distance(
    mesh: TriangleMesh, adjacency: np.ndarray, source: int
) -> np.ndarray:
    lengths = np.linalg.norm(
        mesh.face_centroids[adjacency[:, 0]]
        - mesh.face_centroids[adjacency[:, 1]],
        axis=1,
    )
    graph = adjacency_matrix(adjacency, lengths, len(mesh.faces))
    return dijkstra(graph, directed=False, indices=source)


def _farthest_seeds(
    mesh: TriangleMesh, adjacency: np.ndarray, k: int
) -> np.ndarray:
    centers = mesh.face_centroids
    normals = mesh.face_normals
    centroid = centers.mean(axis=0)
    first = int(np.argmin(np.sum((centers - centroid) ** 2, axis=1)))
    seeds = [first]
    nearest_geo = _geodesic_distance(mesh, adjacency, first)
    nearest_angle = np.arccos(
        np.clip(normals @ normals[first], -1.0, 1.0)
    )

    for _ in range(1, k):
        geo_span = nearest_geo / max(np.percentile(nearest_geo, 95), 1e-9)
        normal_span = nearest_angle / (np.pi / 3.0)
        score = geo_span * (1.0 + 0.45 * np.minimum(normal_span, 2.0))
        seed = int(np.argmax(score))
        seeds.append(seed)
        next_geo = _geodesic_distance(mesh, adjacency, seed)
        nearest_geo = np.minimum(nearest_geo, next_geo)
        nearest_angle = np.minimum(
            nearest_angle,
            np.arccos(np.clip(normals @ normals[seed], -1.0, 1.0)),
        )
    return np.asarray(seeds, dtype=np.int64)


def geodesic_normal_segmentation(
    mesh: TriangleMesh,
    adjacency: np.ndarray,
    k: int,
) -> Segmentation:
    centers = mesh.face_centroids
    lengths = np.linalg.norm(
        centers[adjacency[:, 0]] - centers[adjacency[:, 1]], axis=1
    )
    weights = _normal_aware_weights(mesh, adjacency, lengths)
    graph = adjacency_matrix(adjacency, weights, len(mesh.faces))

    seeds = _farthest_seeds(mesh, adjacency, k)
    distances = dijkstra(
        graph,
        directed=False,
        indices=seeds,
        min_only=False,
    )

    # Additive source offsets turn the geodesic Voronoi diagram into an
    # area-balanced one. The offsets are updated on the same normal-aware
    # geodesic metric used for the final assignment.
    total_area = float(mesh.face_areas.sum())
    offsets = np.zeros(k)
    scale = max(float(np.median(np.min(distances, axis=0))), 1e-6)
    for _ in range(36):
        labels = np.argmin(distances + offsets[:, None], axis=0)
        areas = np.bincount(labels, weights=mesh.face_areas, minlength=k)
        error = areas / total_area - 1.0 / k
        offsets += 0.55 * scale * error
        offsets -= offsets.mean()
    labels = np.argmin(distances + offsets[:, None], axis=0).astype(np.int64)
    labels[seeds] = np.arange(k)
    labels = _repair_connected_labels(labels, adjacency, len(mesh.faces))
    return Segmentation(labels, "normal-geodesic", k)


def _repair_connected_labels(
    labels: np.ndarray, adjacency: np.ndarray, n_faces: int
) -> np.ndarray:
    labels = labels.copy()
    for _ in range(12):
        components = connected_components_from_labels(labels, adjacency, n_faces)
        if len(np.unique(components)) == len(np.unique(labels)):
            break
        sizes = np.bincount(components)
        for component in np.argsort(sizes):
            owners = labels[components == component]
            if len(owners) == 0:
                continue
            label = int(owners[0])
            same_label_components = np.unique(components[labels == label])
            if len(same_label_components) == 1:
                continue
            keep = max(same_label_components, key=lambda c: sizes[c])
            if component == keep:
                continue
            members = components == component
            boundary = members[adjacency[:, 0]] ^ members[adjacency[:, 1]]
            if not np.any(boundary):
                continue
            neighbor_labels = []
            for a, b in adjacency[boundary]:
                if members[a]:
                    neighbor_labels.append(int(labels[b]))
                else:
                    neighbor_labels.append(int(labels[a]))
            target = int(np.bincount(neighbor_labels).argmax())
            labels[members] = target
    return labels


def spectral_segmentation(
    mesh: TriangleMesh,
    adjacency: np.ndarray,
    k: int,
    random_state: int = 7,
) -> Segmentation:
    centers = mesh.face_centroids
    d = np.linalg.norm(
        centers[adjacency[:, 0]] - centers[adjacency[:, 1]], axis=1
    )
    angles = normal_angles(mesh, adjacency)
    sigma_theta = np.deg2rad(6.0)
    sigma_d = max(float(np.median(d)) * 2.5, 1e-9)
    affinity = np.exp(
        -0.5 * (angles / sigma_theta) ** 2 - 0.05 * (d / sigma_d) ** 2
    )
    affinity = np.maximum(affinity, 1e-5)
    W = adjacency_matrix(adjacency, affinity, len(mesh.faces))
    degree = np.asarray(W.sum(axis=1)).ravel()
    inv_sqrt = 1.0 / np.sqrt(np.maximum(degree, 1e-12))
    D = csr_matrix((inv_sqrt, (np.arange(len(degree)), np.arange(len(degree)))))
    normalized_affinity = D @ W @ D
    v0 = np.linspace(1.0, 2.0, len(degree))
    v0 /= np.linalg.norm(v0)
    values, vectors = eigsh(
        normalized_affinity, k=k, which="LA", tol=1e-4, v0=v0
    )
    order = np.argsort(values)[::-1]
    embedding = vectors[:, order]
    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    embedding = embedding / np.maximum(norms, 1e-12)
    labels = KMeans(
        n_clusters=k,
        n_init=20,
        random_state=random_state,
    ).fit_predict(embedding)
    labels = _repair_connected_labels(labels, adjacency, len(mesh.faces))
    return Segmentation(labels, "spectral", k)

