"""Regular grid cloth mesh: particles, constraints, topology."""
from __future__ import annotations

import numpy as np


class ClothMesh:
    """A regular nx x nz particle grid lying in the XZ plane."""

    def __init__(self, nx: int, nz: int, spacing: float, center=(0.0, 0.0, 0.0)):
        self.nx = nx
        self.nz = nz
        self.spacing = spacing
        xs = (np.arange(nx) - (nx - 1) / 2.0) * spacing + center[0]
        zs = (np.arange(nz) - (nz - 1) / 2.0) * spacing + center[2]
        gx, gz = np.meshgrid(xs, zs, indexing="ij")
        gy = np.full_like(gx, center[1])
        self.positions = np.stack([gx, gy, gz], axis=-1).reshape(-1, 3)
        self.n = self.positions.shape[0]
        self._build_topology()

    def vid(self, i: int, j: int) -> int:
        return i * self.nz + j

    def _build_topology(self):
        nx, nz = self.nx, self.nz
        # Quads (i,j) -> 4 vertices, CCW seen from +Y
        quads = []
        for i in range(nx - 1):
            for j in range(nz - 1):
                quads.append([self.vid(i, j), self.vid(i + 1, j),
                              self.vid(i + 1, j + 1), self.vid(i, j + 1)])
        self.quads = np.array(quads, dtype=np.int64)
        # Triangulation (two triangles per quad)
        tris = []
        for q in self.quads:
            tris.append([q[0], q[1], q[2]])
            tris.append([q[0], q[2], q[3]])
        self.triangles = np.array(tris, dtype=np.int64)
        # Structural (stretch) edges: grid neighbours
        edges = set()
        for i in range(nx):
            for j in range(nz):
                if i + 1 < nx:
                    edges.add((self.vid(i, j), self.vid(i + 1, j)))
                if j + 1 < nz:
                    edges.add((self.vid(i, j), self.vid(i, j + 1)))
        # Shear edges (diagonals of each quad) keep the grid from skewing
        for q in self.quads:
            edges.add((q[0], q[2]))
            edges.add((q[1], q[3]))
        self.stretch_edges = np.array(sorted(edges), dtype=np.int64)
        # Bending hinges: vertices two apart along grid axes
        hinges = []
        for i in range(nx):
            for j in range(nz):
                if i + 2 < nx:
                    hinges.append((self.vid(i, j), self.vid(i + 2, j)))
                if j + 2 < nz:
                    hinges.append((self.vid(i, j), self.vid(i, j + 2)))
        self.bend_pairs = np.array(hinges, dtype=np.int64)

    def rest_lengths(self, pairs: np.ndarray) -> np.ndarray:
        d = self.positions[pairs[:, 0]] - self.positions[pairs[:, 1]]
        return np.linalg.norm(d, axis=1)


def vertex_normals(positions: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals for a triangle mesh."""
    p0 = positions[triangles[:, 0]]
    p1 = positions[triangles[:, 1]]
    p2 = positions[triangles[:, 2]]
    fn = np.cross(p1 - p0, p2 - p0)
    normals = np.zeros_like(positions)
    for k in range(3):
        np.add.at(normals, triangles[:, k], fn)
    ln = np.linalg.norm(normals, axis=1, keepdims=True)
    ln[ln < 1e-12] = 1.0
    return normals / ln
