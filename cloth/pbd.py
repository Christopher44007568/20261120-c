"""Position Based Dynamics cloth solver.

Constraints: distance (stretch/shear), hinge bending, particle-particle
self-collision via spatial hashing, analytic colliders (round table,
ground plane). Tracks energy and vertex jitter diagnostics.
"""
from __future__ import annotations

import numpy as np

from .mesh import ClothMesh


class RoundTable:
    """Circular table: cylinder of given radius, top at height h_top."""

    def __init__(self, radius: float, h_top: float):
        self.radius = radius
        self.h_top = h_top

    def project(self, p: np.ndarray) -> np.ndarray:
        """Push points out of the cylinder (vectorised)."""
        out = p.copy()
        r = np.hypot(p[:, 0], p[:, 2])
        inside = (r < self.radius) & (p[:, 1] < self.h_top)
        if not np.any(inside):
            return out
        d_top = self.h_top - p[inside, 1]
        d_side = self.radius - r[inside]
        use_top = d_top <= d_side
        idx = np.nonzero(inside)[0]
        top_idx = idx[use_top]
        side_idx = idx[~use_top]
        out[top_idx, 1] = self.h_top
        if side_idx.size:
            rr = r[side_idx]
            rr[rr < 1e-9] = 1e-9
            scale = self.radius / rr
            out[side_idx, 0] = p[side_idx, 0] * scale
            out[side_idx, 2] = p[side_idx, 2] * scale
        return out


class ClothSim:
    def __init__(self, mesh: ClothMesh, table: RoundTable | None = None,
                 ground_y: float = 0.0, gravity: float = -9.8,
                 stretch_stiffness: float = 1.0, bend_stiffness: float = 0.1,
                 iterations: int = 10, self_collision: bool = True,
                 thickness: float | None = None, damping: float = 0.01,
                 dt: float = 1.0 / 60.0):
        self.mesh = mesh
        self.table = table
        self.ground_y = ground_y
        self.gravity = gravity
        self.k_stretch = stretch_stiffness
        self.k_bend = bend_stiffness
        self.iterations = iterations
        self.self_collision = self_collision
        self.thickness = thickness if thickness is not None else 0.8 * mesh.spacing
        self.damping = damping
        self.dt = dt
        self.pos = mesh.positions.copy()
        self.prev = self.pos.copy()
        self.vel = np.zeros_like(self.pos)
        self.rest_stretch = mesh.rest_lengths(mesh.stretch_edges)
        self.rest_bend = mesh.rest_lengths(mesh.bend_pairs)
        self.time = 0.0
        self.n_self_pairs = 0
        self._pairs_cache = None

    def _project_distance(self, pairs, rest, stiffness):
        a = self.pos[pairs[:, 0]]
        b = self.pos[pairs[:, 1]]
        delta = a - b
        d = np.linalg.norm(delta, axis=1)
        mask = d > 1e-12
        if not np.any(mask):
            return
        c = (d[mask] - rest[mask]) / d[mask]
        corr = (0.5 * stiffness) * c[:, None] * delta[mask]
        pa = pairs[mask, 0]
        pb = pairs[mask, 1]
        # Weighted Jacobi: average simultaneous corrections per vertex so a
        # vertex shared by many constraints cannot overshoot and diverge.
        acc = np.zeros_like(self.pos)
        cnt = np.zeros(self.mesh.n)
        np.add.at(acc, pa, -corr)
        np.add.at(acc, pb, corr)
        np.add.at(cnt, pa, 1.0)
        np.add.at(cnt, pb, 1.0)
        self.pos += acc / np.maximum(cnt, 1.0)[:, None]

    def _self_collision_pairs(self):
        """All particle pairs closer than thickness (exact brute force)."""
        n = self.mesh.n
        iu = np.triu_indices(n, 1)
        d2 = np.sum((self.pos[iu[0]] - self.pos[iu[1]]) ** 2, axis=1)
        close = d2 < self.thickness ** 2
        if not np.any(close):
            return None
        pairs = np.stack([iu[0][close], iu[1][close]], 1)
        # Exclude immediate topological neighbours (cloth constraints handle them)
        i, j = pairs[:, 0], pairs[:, 1]
        gi, gj = i // self.mesh.nz, i % self.mesh.nz
        hi, hj = j // self.mesh.nz, j % self.mesh.nz
        near = (np.abs(gi - hi) <= 1) & (np.abs(gj - hj) <= 1)
        return pairs[~near] if np.any(~near) else None

    def _project_self_collision(self):
        pairs = self._pairs_cache
        if pairs is None:
            return 0
        a = self.pos[pairs[:, 0]]
        b = self.pos[pairs[:, 1]]
        delta = a - b
        d = np.linalg.norm(delta, axis=1)
        d[d < 1e-9] = 1e-9
        corr = 0.5 * (self.thickness - d) / d
        corr = np.maximum(corr, 0.0)[:, None] * delta
        acc = np.zeros_like(self.pos)
        cnt = np.zeros(self.mesh.n)
        np.add.at(acc, pairs[:, 0], corr)
        np.add.at(acc, pairs[:, 1], -corr)
        np.add.at(cnt, pairs[:, 0], 1.0)
        np.add.at(cnt, pairs[:, 1], 1.0)
        self.pos += acc / np.maximum(cnt, 1.0)[:, None]
        return len(pairs)

    def _project_colliders(self):
        if self.table is not None:
            self.pos = self.table.project(self.pos)
        below = self.pos[:, 1] < self.ground_y
        self.pos[below, 1] = self.ground_y

    def step(self):
        dt = self.dt
        self.vel += np.array([0.0, self.gravity, 0.0]) * dt
        self.vel *= (1.0 - self.damping)
        self.prev = self.pos.copy()
        self.pos += self.vel * dt
        # Pair list is built once per step (positions change little within
        # the iteration loop); projections still run every iteration.
        self._pairs_cache = self._self_collision_pairs() \
            if self.self_collision else None
        for _ in range(self.iterations):
            self._project_distance(self.mesh.stretch_edges, self.rest_stretch,
                                   self.k_stretch)
            self._project_distance(self.mesh.bend_pairs, self.rest_bend,
                                   self.k_bend)
            if self.self_collision:
                self.n_self_pairs = self._project_self_collision()
            self._project_colliders()
        self.vel = (self.pos - self.prev) / dt
        self.time += dt

    def energy(self):
        ke = 0.5 * float(np.sum(self.vel ** 2))
        pe = -self.gravity * float(np.sum(self.pos[:, 1]))

        def ce(pairs, rest, k):
            d = np.linalg.norm(self.pos[pairs[:, 0]] - self.pos[pairs[:, 1]],
                               axis=1)
            return 0.5 * k * float(np.sum((d - rest) ** 2))

        ec = (ce(self.mesh.stretch_edges, self.rest_stretch, self.k_stretch)
              + ce(self.mesh.bend_pairs, self.rest_bend, self.k_bend))
        return {"kinetic": ke, "potential": pe, "constraint": ec,
                "total": ke + pe + ec}

    def min_self_distance(self):
        """Min distance between non-neighbouring particles (penetration check)."""
        pairs = self._self_collision_pairs()
        if pairs is None:
            return None
        d = np.linalg.norm(self.pos[pairs[:, 0]] - self.pos[pairs[:, 1]], axis=1)
        return float(d.min()) if d.size else None

    def table_penetration(self):
        """Max depth any particle sits inside the table cylinder."""
        if self.table is None:
            return 0.0
        r = np.hypot(self.pos[:, 0], self.pos[:, 2])
        inside = (r < self.table.radius) & (self.pos[:, 1] < self.table.h_top)
        if not np.any(inside):
            return 0.0
        d_top = self.table.h_top - self.pos[inside, 1]
        d_side = self.table.radius - r[inside]
        return float(np.minimum(d_top, d_side).max())
