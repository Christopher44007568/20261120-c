"""Terrain profiles used by the gait generator and contact checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class Terrain(Protocol):
    name: str

    def height(self, x: float | np.ndarray) -> float | np.ndarray: ...

    def slope(self, x: float | np.ndarray) -> float | np.ndarray: ...

    def signed_distance(self, points: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class PlaneTerrain:
    """Infinite plane ``z = tan(slope) * x + intercept``.

    Positive slope is uphill for a walker moving in +x.
    """

    slope_deg: float
    intercept: float = 0.0
    name: str = "plane"

    @property
    def slope_rad(self) -> float:
        return float(np.deg2rad(self.slope_deg))

    def height(self, x: float | np.ndarray) -> float | np.ndarray:
        return np.tan(self.slope_rad) * np.asarray(x) + self.intercept

    def slope(self, x: float | np.ndarray) -> float | np.ndarray:
        x_arr = np.asarray(x)
        return np.full_like(x_arr, np.tan(self.slope_rad), dtype=float)

    def signed_distance(self, points: np.ndarray) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        vertical = pts[:, 1] - self.height(pts[:, 0])
        return vertical * np.cos(self.slope_rad)

    def angle_at(self, x: float | np.ndarray) -> float | np.ndarray:
        x_arr = np.asarray(x)
        return np.full_like(x_arr, self.slope_rad, dtype=float)


@dataclass(frozen=True)
class WaveTerrain:
    """Smooth sinusoidal profile for changing-slope adaptation tests."""

    amplitude: float = 0.12
    wavelength: float = 4.0
    intercept: float = 0.0
    name: str = "wave"

    @property
    def wave_number(self) -> float:
        return 2.0 * np.pi / self.wavelength

    def height(self, x: float | np.ndarray) -> float | np.ndarray:
        return self.intercept + self.amplitude * np.sin(self.wave_number * np.asarray(x))

    def slope(self, x: float | np.ndarray) -> float | np.ndarray:
        return (
            self.amplitude
            * self.wave_number
            * np.cos(self.wave_number * np.asarray(x))
        )

    def signed_distance(self, points: np.ndarray) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        slope = self.slope(pts[:, 0])
        vertical = pts[:, 1] - self.height(pts[:, 0])
        return vertical / np.sqrt(1.0 + slope**2)

    def angle_at(self, x: float | np.ndarray) -> float | np.ndarray:
        return np.arctan(self.slope(x))


def make_terrain(kind: str = "plane", slope_deg: float = 0.0) -> Terrain:
    kind = kind.lower()
    if kind == "plane":
        return PlaneTerrain(slope_deg=slope_deg)
    if kind == "wave":
        return WaveTerrain()
    raise ValueError(f"unknown terrain kind: {kind!r}")
