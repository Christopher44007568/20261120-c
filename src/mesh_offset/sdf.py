"""Grid-sampled signed distance field used for robust iso-surface offsets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


@dataclass
class SignedDistanceGrid:
    origin: np.ndarray
    spacing: float
    axes: tuple[np.ndarray, np.ndarray, np.ndarray]
    values: np.ndarray
    query_count: int

    @classmethod
    def from_mesh(
        cls,
        mesh: trimesh.Trimesh,
        resolution: float,
        padding: float,
        *,
        chunk_size: int = 200_000,
    ) -> "SignedDistanceGrid":
        if resolution <= 0:
            raise ValueError("resolution must be positive")
        if padding <= resolution:
            raise ValueError("padding must be larger than the grid resolution")

        lower = np.asarray(mesh.bounds[0], dtype=np.float64) - padding
        upper = np.asarray(mesh.bounds[1], dtype=np.float64) + padding
        axes = tuple(
            np.arange(lower[axis], upper[axis] + 0.5 * resolution, resolution)
            for axis in range(3)
        )
        shape = tuple(len(axis) for axis in axes)
        points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
        values = np.empty(len(points), dtype=np.float64)
        for start in range(0, len(points), chunk_size):
            stop = min(start + chunk_size, len(points))
            values[start:stop] = trimesh.proximity.signed_distance(
                mesh, points[start:stop]
            )
        return cls(
            origin=np.asarray([axis[0] for axis in axes], dtype=np.float64),
            spacing=float(resolution),
            axes=axes,
            values=values.reshape(shape),
            query_count=int(len(points)),
        )

    @property
    def bounds(self) -> np.ndarray:
        return np.asarray(
            [
                self.axes[0][0],
                self.axes[1][0],
                self.axes[2][0],
                self.axes[0][-1],
                self.axes[1][-1],
                self.axes[2][-1],
            ],
            dtype=np.float64,
        )

    def sample(self, x: float, y: float, z: float) -> float:
        """Trilinear interpolation; positive values are inside the solid."""

        coordinate = np.asarray([x, y, z], dtype=np.float64)
        local = (coordinate - self.origin) / self.spacing
        upper_index = np.asarray(
            [len(axis) - 1 for axis in self.axes], dtype=np.float64
        )
        local = np.clip(local, 0.0, upper_index - 1.0)
        base = np.floor(local).astype(np.int64)
        fraction = local - base

        i, j, k = (int(value) for value in base)
        fi, fj, fk = (float(value) for value in fraction)
        cube = self.values[i : i + 2, j : j + 2, k : k + 2]
        c000, c100 = cube[0, 0, 0], cube[1, 0, 0]
        c010, c110 = cube[0, 1, 0], cube[1, 1, 0]
        c001, c101 = cube[0, 0, 1], cube[1, 0, 1]
        c011, c111 = cube[0, 1, 1], cube[1, 1, 1]
        return float(
            c000 * (1 - fi) * (1 - fj) * (1 - fk)
            + c100 * fi * (1 - fj) * (1 - fk)
            + c010 * (1 - fi) * fj * (1 - fk)
            + c110 * fi * fj * (1 - fk)
            + c001 * (1 - fi) * (1 - fj) * fk
            + c101 * fi * (1 - fj) * fk
            + c011 * (1 - fi) * fj * fk
            + c111 * fi * fj * fk
        )
