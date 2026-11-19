"""Organic mesh generation and uniform quad remeshing.

The organic shape is a unit sphere displaced by a deterministic smooth
trigonometric field, so both the input triangle mesh and the remeshed
quad mesh describe the same surface and element quality is directly
comparable.
"""

from __future__ import annotations

import numpy as np


def organic_radius(direction: np.ndarray) -> float:
    d = np.asarray(direction, dtype=float)
    x, y, z = d / (np.linalg.norm(d) + 1e-12)
    return (1.0
            + 0.16 * np.sin(3.2 * x + 1.1) * np.cos(2.7 * y - 0.4)
            + 0.10 * np.sin(4.1 * z + 0.7) * np.cos(1.9 * x)
            + 0.06 * np.cos(3.5 * y + 2.2 * z))


def organic_point(direction: np.ndarray) -> np.ndarray:
    d = np.asarray(direction, dtype=float)
    return d / np.linalg.norm(d) * organic_radius(d)


def _icosahedron():
    t = (1.0 + np.sqrt(5.0)) / 2.0
    verts = [
        (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
        (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
        (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
    ]
    verts = [np.array(v, dtype=float) / np.linalg.norm(v) for v in verts]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    return verts, faces


def organic_tri_mesh(subdivisions: int = 3):
    """Noisy icosphere triangle mesh that serves as the remesh input."""
    verts, faces = _icosahedron()
    for _ in range(subdivisions):
        cache = {}

        def midpoint(i, j):
            key = (min(i, j), max(i, j))
            if key not in cache:
                m = (verts[i] + verts[j]) * 0.5
                cache[key] = len(verts)
                verts.append(m / np.linalg.norm(m))
            return cache[key]

        new_faces = []
        for a, b, c in faces:
            ab = midpoint(a, b)
            bc = midpoint(b, c)
            ca = midpoint(c, a)
            new_faces.extend([
                (a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca),
            ])
        faces = new_faces
    points = np.array([organic_point(v) for v in verts])
    return points, [tuple(int(i) for i in f) for f in faces]


def _cube_faces():
    corners = [np.array(v, dtype=float) for v in [
        (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    ]]
    quads = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (3, 2, 6, 7), (1, 2, 6, 5), (0, 3, 7, 4),
    ]
    return corners, quads


def organic_quad_mesh(resolution: int = 16):
    """Cubemap-style quad sphere, subdivided with welded shared vertices.

    Each of the 6 cube faces becomes ``resolution`` x ``resolution`` quads;
    edge and corner vertices are shared across faces, so the result is a
    watertight pure-quad mesh with near-uniform parametric spacing.
    """
    corners, faces = _cube_faces()
    n = resolution
    index = {}
    points = []

    def vertex_id(corner_indices, u, v):
        a, b, c, d = corner_indices
        p = ((1 - u) * (1 - v) * corners[a] + u * (1 - v) * corners[b]
             + u * v * corners[c] + (1 - u) * v * corners[d])
        p = p / np.linalg.norm(p)
        key = tuple(np.round(p, 10))
        if key not in index:
            index[key] = len(points)
            points.append(organic_point(p))
        return index[key]

    quads = []
    for face in faces:
        grid = [[vertex_id(face, j / n, i / n) for j in range(n + 1)]
                for i in range(n + 1)]
        for i in range(n):
            for j in range(n):
                quads.append((grid[i][j], grid[i][j + 1],
                              grid[i + 1][j + 1], grid[i + 1][j]))
    points = np.array(points)
    points = relax_on_surface(points, quads, iterations=200)
    return points, quads


def relax_on_surface(points: np.ndarray, quads, iterations: int = 60,
                     stiffness: float = 0.5) -> np.ndarray:
    """Laplacian smoothing projected back onto the organic surface.

    Vertex connectivity is fixed; every relaxation step averages neighbor
    positions and re-projects each vertex to its original radial shell, so
    the organic silhouette is preserved while quad edge lengths equalize.
    """
    points = np.array(points, dtype=float)
    neighbors = [set() for _ in points]
    for face in quads:
        for i, vertex in enumerate(face):
            neighbors[vertex].add(face[(i + 1) % len(face)])
            neighbors[vertex].add(face[(i - 1) % len(face)])
    neighbors = [list(nbr) for nbr in neighbors]

    target_length = float(np.mean([
        np.linalg.norm(points[b] - points[a])
        for face in quads for a, b in
        [(face[k], face[(k + 1) % len(face)]) for k in range(len(face))]
    ]))

    for _ in range(iterations):
        updated = points.copy()
        for i, nbr in enumerate(neighbors):
            spring = np.zeros(3)
            for j in nbr:
                delta = points[j] - points[i]
                length = np.linalg.norm(delta) + 1e-12
                spring += delta * ((length - target_length) / length)
            laplacian = np.mean(points[nbr], axis=0) - points[i]
            candidate = points[i] + stiffness * (0.5 * laplacian + 0.5 * spring)
            direction = candidate / np.linalg.norm(candidate)
            updated[i] = direction * organic_radius(direction)
        points = updated
    return points
