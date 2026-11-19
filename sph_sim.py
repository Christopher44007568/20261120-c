from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree


@dataclass
class SPHConfig:
    width: float = 1.20
    height: float = 0.90
    dx: float = 0.014
    rho0: float = 1000.0
    h: float = 0.050
    c0: float = 12.0
    gamma: float = 7.0
    iterations: int = 3
    relaxation: float = 1.0
    xsph: float = 0.020
    max_speed: float = 8.0
    dt: float = 1.0e-3
    t_end: float = 1.60
    gravity: float = 9.81
    seed: int = 7

    @property
    def mass(self) -> float:
        return self.rho0 * self.dx * self.dx

    @property
    def stiffness(self) -> float:
        return self.rho0 * self.c0 * self.c0 / self.gamma


def poly6(r2: np.ndarray, h: float) -> np.ndarray:
    """2D Poly6 kernel; support radius h."""
    q = np.maximum(h * h - r2, 0.0)
    return (4.0 / (np.pi * h**8)) * q**3


def spiky_gradient_coeff(r: np.ndarray, h: float) -> np.ndarray:
    """Scalar part of grad W for r_ij = x_i - x_j."""
    q = np.maximum(h - r, 0.0)
    return -(30.0 / (np.pi * h**5)) * q**2


def neighbor_pairs(
    positions: np.ndarray, radius: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return unique pairs i<j with |x_i-x_j| < radius.

    A cKDTree supplies the candidates. Timing is single-thread CPU time and
    covers tree construction, the pair query, and distance rejection.
    """
    t0 = time.process_time()
    pairs = cKDTree(positions).query_pairs(radius, output_type="ndarray")
    if pairs.size == 0:
        empty = np.empty(0, dtype=np.int32)
        return empty, empty, (time.process_time() - t0) * 1e3
    i_idx = pairs[:, 0].astype(np.int32)
    j_idx = pairs[:, 1].astype(np.int32)
    delta = positions[j_idx] - positions[i_idx]
    r2 = np.einsum("ij,ij->i", delta, delta)
    keep = (r2 > 1.0e-14) & (r2 < radius * radius)
    return i_idx[keep], j_idx[keep], (time.process_time() - t0) * 1e3


class SPHSimulator:
    def __init__(self, config: SPHConfig):
        self.cfg = config
        self.rng = np.random.default_rng(config.seed)
        self.wall = 0.65 * config.dx
        self.positions, self.velocities = self._initial_fluid()
        self.densities = np.full(self.positions.shape[0], config.rho0)
        self.pressures = np.zeros_like(self.densities)
        self.neighbor_time_ms: list[float] = []
        self.neighbor_counts: list[int] = []
        self.compression: list[float] = []
        self.compression_p99: list[float] = []
        self.compression_max: list[float] = []
        self.time = 0.0
        self.steps = 0

    def _initial_fluid(self) -> tuple[np.ndarray, np.ndarray]:
        cfg = self.cfg
        nx = int(np.floor((0.34 - 0.055) / cfg.dx)) + 1
        ny = int(np.floor((0.73 - 0.050) / cfg.dx)) + 1
        x = 0.055 + np.arange(nx) * cfg.dx
        y = 0.050 + np.arange(ny) * cfg.dx
        xx, yy = np.meshgrid(x, y)
        pos = np.column_stack((xx.ravel(), yy.ravel()))
        pos += self.rng.normal(0.0, 0.018 * cfg.dx, pos.shape)
        return pos, np.zeros_like(pos)

    def _density(
        self, positions: np.ndarray, i_idx: np.ndarray, j_idx: np.ndarray
    ) -> np.ndarray:
        cfg = self.cfg
        delta = positions[j_idx] - positions[i_idx]
        r2 = np.einsum("ij,ij->i", delta, delta)
        w0 = poly6(np.array([0.0]), cfg.h)[0]
        density = np.full(positions.shape[0], cfg.mass * w0)
        contribution = cfg.mass * poly6(r2, cfg.h)
        np.add.at(density, i_idx, contribution)
        np.add.at(density, j_idx, contribution)
        return density

    def _constraint_correction(
        self,
        positions: np.ndarray,
        i_idx: np.ndarray,
        j_idx: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """PBF density constraint with Spiky kernel gradients."""
        cfg = self.cfg
        delta = positions[j_idx] - positions[i_idx]
        r2 = np.einsum("ij,ij->i", delta, delta)
        r = np.sqrt(r2)
        grad_scalar = spiky_gradient_coeff(r, cfg.h) / np.maximum(r, 1.0e-12)
        weighted_grad = (
            cfg.mass / cfg.rho0 * grad_scalar
        )[:, None] * delta

        density = self._density(positions, i_idx, j_idx)
        constraint = np.maximum(density / cfg.rho0 - 1.0, 0.0)
        grad_i = np.zeros_like(positions)
        np.add.at(grad_i, i_idx, weighted_grad)
        np.add.at(grad_i, j_idx, -weighted_grad)
        grad2 = np.einsum("ij,ij->i", grad_i, grad_i)
        pair_grad2 = np.einsum("ij,ij->i", weighted_grad, weighted_grad)
        np.add.at(grad2, i_idx, pair_grad2)
        np.add.at(grad2, j_idx, pair_grad2)
        lam = -constraint / (grad2 + 1.0e-8)

        correction = np.zeros_like(positions)
        pair_lam = -(lam[i_idx] + lam[j_idx])[:, None] * weighted_grad
        np.add.at(correction, i_idx, pair_lam)
        np.add.at(correction, j_idx, -pair_lam)
        return correction, density, lam

    def _clamp_positions(self, positions: np.ndarray) -> int:
        cfg = self.cfg
        lo = self.wall
        hi_x = cfg.width - self.wall
        below = positions[:, 0] < lo
        above_x = positions[:, 0] > hi_x
        hits = int(below.sum() + above_x.sum())
        np.clip(positions[:, 0], lo, hi_x, out=positions[:, 0])
        np.clip(positions[:, 1], lo, None, out=positions[:, 1])
        return hits

    def step(self) -> None:
        cfg = self.cfg
        self.velocities[:, 1] -= cfg.gravity * cfg.dt
        predicted = self.positions + cfg.dt * self.velocities
        self._clamp_positions(predicted)
        i_idx, j_idx, search_ms = neighbor_pairs(predicted, cfg.h)
        self.neighbor_time_ms.append(search_ms)
        self.neighbor_counts.append(int(2 * i_idx.size / max(predicted.shape[0], 1)))

        for _ in range(cfg.iterations):
            dp, _, _ = self._constraint_correction(predicted, i_idx, j_idx)
            predicted += cfg.relaxation * dp
            self._clamp_positions(predicted)

        self.densities = self._density(predicted, i_idx, j_idx)
        self.velocities = (predicted - self.positions) / cfg.dt
        delta = predicted[j_idx] - predicted[i_idx]
        r2 = np.einsum("ij,ij->i", delta, delta)
        weights = (
            cfg.mass * poly6(r2, cfg.h) / np.maximum(self.densities[j_idx], 1.0)
        )
        smoothing = np.zeros_like(self.positions)
        dv = weights[:, None] * (self.velocities[j_idx] - self.velocities[i_idx])
        np.add.at(smoothing, i_idx, dv)
        np.add.at(smoothing, j_idx, -dv)
        self.velocities += cfg.xsph * smoothing
        speed = np.linalg.norm(self.velocities, axis=1)
        scale = np.minimum(1.0, cfg.max_speed / np.maximum(speed, 1.0e-12))
        self.velocities *= scale[:, None]
        self.positions = predicted

        ratio = self.densities / cfg.rho0
        self.pressures = cfg.stiffness * np.maximum(ratio**cfg.gamma - 1.0, 0.0)
        compression = np.maximum(ratio - 1.0, 0.0)
        self.compression.append(float(np.percentile(compression, 95)))
        self.compression_p99.append(float(np.percentile(compression, 99)))
        self.compression_max.append(float(np.max(compression)))
        self.time += cfg.dt
        self.steps += 1

    def state(self) -> dict[str, np.ndarray | float | int]:
        speed = np.linalg.norm(self.velocities, axis=1)
        return {
            "time": float(self.time),
            "step": int(self.steps),
            "positions": self.positions.copy(),
            "velocities": self.velocities.copy(),
            "densities": self.densities.copy(),
            "pressures": self.pressures.copy(),
            "speed": speed,
        }
